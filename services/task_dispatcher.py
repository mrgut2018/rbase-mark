#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务分配服务 - 轮询auto_task并创建子任务和MNS消息

该服务负责：
1. 轮询auto_task表中待处理的任务
2. 根据任务类型创建相应的auto_sub_task
3. 向MNS队列发送消息触发分类服务处理

作者: AI Assistant
创建时间: 2025年11月14日
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
from typing import Optional, List, Dict, Any
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mns.account import Account
from mns.queue import Message

from deepsearcher.configuration import Configuration
from deepsearcher.tools.log import info, warning, debug, error, set_dev_mode, set_level
from deepsearcher.tools.json_util import safe_json_loads
from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection


# 任务类型枚举
class TaskType:
    AI_GENERAL_CLASSIFY_RAW_ARTICLE = "AI_GENERAL_CLASSIFY_RAW_ARTICLE"
    AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE = "AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE"
    AI_SINGLE_CLASSIFY_RAW_ARTICLE = "AI_SINGLE_CLASSIFY_RAW_ARTICLE"


class TaskDispatcher:
    """任务分配器"""
    
    def __init__(self, config: Configuration):
        """
        初始化任务分配器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.connection = None
        self.mns_account = None
        self.mns_queue = None
        self.running = True
        
        # 获取MNS配置
        self.mns_config = config.rbase_settings.get('mns', {})
        
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise
    
    def _ensure_db_connection(self):
        """确保数据库连接有效，如果断开则重连"""
        try:
            # 尝试ping数据库
            if self.connection:
                self.connection.ping(reconnect=True)
        except Exception as e:
            warning(f"数据库连接失效，尝试重连: {e}")
            try:
                self._init_db_connection()
            except Exception as reconnect_error:
                error(f"数据库重连失败: {reconnect_error}")
                raise
    
    def _init_mns_connection(self):
        """初始化MNS连接"""
        try:
            endpoint = self.mns_config.get('endpoint')
            access_id = self.mns_config.get('access_id')
            access_key = self.mns_config.get('access_key')
            queue_name = self.mns_config.get('queue_name')
            
            if not all([endpoint, access_id, access_key, queue_name]):
                raise ValueError("MNS配置不完整")
            
            self.mns_account = Account(endpoint, access_id, access_key, debug=False)
            self.mns_queue = self.mns_account.get_queue(queue_name)
            info(f"MNS连接成功 - {queue_name}")
        except Exception as e:
            error(f"MNS连接失败: {e}")
            raise
    
    def _get_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        获取待处理的任务列表
        
        Returns:
            待处理任务列表
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, foreign_key_id, type, input, priority, status, created, modified
                FROM auto_task
                WHERE status = 1 
                  AND type IN (%s, %s, %s)
                ORDER BY priority DESC, id ASC
                LIMIT 100
                """
                cursor.execute(sql, (
                    TaskType.AI_GENERAL_CLASSIFY_RAW_ARTICLE,
                    TaskType.AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE,
                    TaskType.AI_SINGLE_CLASSIFY_RAW_ARTICLE
                ))
                tasks = cursor.fetchall()
                return tasks if tasks else []
        except Exception as e:
            error(f"获取待处理任务失败: {e}")
            return []
    
    def _update_task_status(self, task_id: int, status: int):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                UPDATE auto_task 
                SET status = %s, modified = NOW()
                WHERE id = %s
                """
                cursor.execute(sql, (status, task_id))
                self.connection.commit()
                info(f"更新任务 {task_id} 状态为 {status}")
        except Exception as e:
            error(f"更新任务状态失败: {e}")
            self.connection.rollback()
    
    def _get_classifier_groups_by_base_id(self, base_id: Optional[int]) -> List[Dict[str, Any]]:
        """
        根据base_id获取分类器组列表
        
        Args:
            base_id: 用户库ID，None表示查询base_id为NULL的组
            
        Returns:
            分类器组列表
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                if base_id is None:
                    sql = """
                    SELECT id, name, `desc`, base_id
                    FROM classifier_group
                    WHERE base_id IS NULL AND status = 1
                    ORDER BY id ASC
                    """
                    cursor.execute(sql)
                else:
                    sql = """
                    SELECT id, name, `desc`, base_id
                    FROM classifier_group
                    WHERE base_id = %s AND status = 1
                    ORDER BY id ASC
                    """
                    cursor.execute(sql, (base_id,))
                
                groups = cursor.fetchall()
                return groups if groups else []
        except Exception as e:
            error(f"获取分类器组失败: {e}")
            return []
    
    def _check_classifier_exists(self, classifier_id: int) -> Optional[Dict[str, Any]]:
        """
        检查分类器是否存在
        
        Args:
            classifier_id: 分类器ID
            
        Returns:
            分类器信息，不存在返回None
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, name, alias, status
                FROM classifier
                WHERE id = %s AND status = 1
                """
                cursor.execute(sql, (classifier_id,))
                return cursor.fetchone()
        except Exception as e:
            error(f"检查分类器失败: {e}")
            return None
    
    def _create_sub_task(self, auto_task_id: int, task_name: str, params: Dict[str, Any]) -> Optional[int]:
        """
        创建子任务
        
        Args:
            auto_task_id: 主任务ID
            task_name: 子任务名称
            params: 子任务参数
            
        Returns:
            子任务ID，失败返回None
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                INSERT INTO auto_sub_task (auto_task_id, task_name, params, status, created, modified)
                VALUES (%s, %s, %s, '1', NOW(), NOW())
                """
                cursor.execute(sql, (auto_task_id, task_name, json.dumps(params, ensure_ascii=False)))
                self.connection.commit()
                sub_task_id = cursor.lastrowid
                debug(f"创建子任务: {sub_task_id} - {task_name}")
                return sub_task_id
        except Exception as e:
            error(f"创建子任务失败: {e}")
            self.connection.rollback()
            return None
    
    def _send_mns_message(self, message_data: Dict[str, Any]) -> bool:
        """
        向MNS队列发送消息
        
        Args:
            message_data: 消息数据
            
        Returns:
            是否发送成功
        """
        try:
            message_body = json.dumps(message_data, ensure_ascii=False)
            message = Message(message_body=message_body)
            msg = self.mns_queue.send_message(message)
            debug(f"发送MNS消息成功: {msg.message_id}")
            return True
        except Exception as e:
            error(f"发送MNS消息失败: {e}")
            return False
    
    def _process_general_classify_task(self, task: Dict[str, Any], task_params: Dict[str, Any]) -> bool:
        """
        处理通用分类任务（AI_GENERAL_CLASSIFY_RAW_ARTICLE）
        
        Args:
            task: 任务信息
            task_params: 任务参数
            
        Returns:
            是否处理成功
        """
        task_id = task['id']
        raw_article_id = task_params.get('raw_article_id')
        base_id = task_params.get('base_id', 0)
        
        if not raw_article_id:
            error(f"任务 {task_id} 缺少 raw_article_id 参数")
            return False
        
        # 获取所有base_id为NULL的分类器组
        groups = self._get_classifier_groups_by_base_id(None)
        
        if not groups:
            warning(f"任务 {task_id}: 未找到通用分类器组（base_id为NULL）")
            return False
        
        info(f"任务 {task_id}: 找到 {len(groups)} 个通用分类器组")
        
        success_count = 0
        for group in groups:
            # 创建子任务
            sub_task_params = {
                'raw_article_id': raw_article_id,
                'base_id': base_id,
                'classifier_group_id': group['id']
            }
            
            sub_task_id = self._create_sub_task(
                task_id,
                group['name'],
                sub_task_params
            )
            
            if sub_task_id:
                # 发送MNS消息
                mns_message = {
                    'auto_task_id': task_id,
                    'auto_sub_task_id': sub_task_id,
                    'raw_article_id': raw_article_id,
                    'base_id': base_id,
                    'classifier_group_id': group['id']
                }
                
                if self._send_mns_message(mns_message):
                    success_count += 1
        
        info(f"任务 {task_id}: 成功创建并发送 {success_count}/{len(groups)} 个子任务")
        return success_count > 0
    
    def _process_specific_base_classify_task(self, task: Dict[str, Any], task_params: Dict[str, Any]) -> bool:
        """
        处理特定库分类任务（AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE）
        
        Args:
            task: 任务信息
            task_params: 任务参数
            
        Returns:
            是否处理成功
        """
        task_id = task['id']
        raw_article_id = task_params.get('raw_article_id')
        base_id = task_params.get('base_id')
        
        if not raw_article_id or not base_id:
            error(f"任务 {task_id} 缺少必需参数: raw_article_id 或 base_id")
            return False
        
        # 获取指定base_id的分类器组
        groups = self._get_classifier_groups_by_base_id(base_id)
        
        if not groups:
            warning(f"任务 {task_id}: 未找到 base_id={base_id} 的分类器组")
            return False
        
        info(f"任务 {task_id}: 找到 {len(groups)} 个分类器组（base_id={base_id}）")
        
        success_count = 0
        for group in groups:
            # 创建子任务
            sub_task_params = {
                'raw_article_id': raw_article_id,
                'base_id': base_id,
                'classifier_group_id': group['id']
            }
            
            sub_task_id = self._create_sub_task(
                task_id,
                group['name'],
                sub_task_params
            )
            
            if sub_task_id:
                # 发送MNS消息
                mns_message = {
                    'auto_task_id': task_id,
                    'auto_sub_task_id': sub_task_id,
                    'raw_article_id': raw_article_id,
                    'base_id': base_id,
                    'classifier_group_id': group['id']
                }
                
                if self._send_mns_message(mns_message):
                    success_count += 1
        
        info(f"任务 {task_id}: 成功创建并发送 {success_count}/{len(groups)} 个子任务")
        return success_count > 0
    
    def _process_single_classify_task(self, task: Dict[str, Any], task_params: Dict[str, Any]) -> bool:
        """
        处理单个分类器任务（AI_SINGLE_CLASSIFY_RAW_ARTICLE）
        
        Args:
            task: 任务信息
            task_params: 任务参数
            
        Returns:
            是否处理成功
        """
        task_id = task['id']
        raw_article_id = task_params.get('raw_article_id')
        base_id = task_params.get('base_id', 0)
        classifier_id = task_params.get('classifier_id')
        
        if not raw_article_id or not classifier_id:
            error(f"任务 {task_id} 缺少必需参数: raw_article_id 或 classifier_id")
            return False
        
        # 检查分类器是否存在
        classifier = self._check_classifier_exists(classifier_id)
        
        if not classifier:
            error(f"任务 {task_id}: 分类器 {classifier_id} 不存在或已禁用")
            return False
        
        info(f"任务 {task_id}: 找到分类器 {classifier_id} - {classifier['name']}")
        
        # 创建子任务
        sub_task_params = {
            'raw_article_id': raw_article_id,
            'base_id': base_id,
            'classifier_id': classifier_id
        }
        
        sub_task_id = self._create_sub_task(
            task_id,
            classifier['name'],
            sub_task_params
        )
        
        if not sub_task_id:
            return False
        
        # 发送MNS消息
        mns_message = {
            'auto_task_id': task_id,
            'auto_sub_task_id': sub_task_id,
            'raw_article_id': raw_article_id,
            'base_id': base_id,
            'classifier_id': classifier_id
        }
        
        if self._send_mns_message(mns_message):
            info(f"任务 {task_id}: 成功创建并发送子任务")
            return True
        
        return False
    
    def _process_task(self, task: Dict[str, Any]) -> bool:
        """
        处理单个任务
        
        Args:
            task: 任务信息
            
        Returns:
            是否处理成功
        """
        task_id = task['id']
        task_type = task['type']
        input_str = task['input']
        
        info(f"处理任务 {task_id} - 类型: {task_type}")
        
        # 解析input参数
        task_params = safe_json_loads(input_str)
        if not task_params:
            error(f"任务 {task_id} input 解析失败: {input_str}")
            self._update_task_status(task_id, 20)  # 标记为失败
            return False
        
        # 更新任务状态为执行中
        self._update_task_status(task_id, 2)
        
        try:
            # 根据任务类型处理
            if task_type == TaskType.AI_GENERAL_CLASSIFY_RAW_ARTICLE:
                success = self._process_general_classify_task(task, task_params)
            elif task_type == TaskType.AI_SPECIFIC_BASE_CLASSIFY_RAW_ARTICLE:
                success = self._process_specific_base_classify_task(task, task_params)
            elif task_type == TaskType.AI_SINGLE_CLASSIFY_RAW_ARTICLE:
                success = self._process_single_classify_task(task, task_params)
            else:
                error(f"未知的任务类型: {task_type}")
                success = False
            
            # 注意：不在这里更新任务为完成状态
            # 任务状态会由classify_service在所有子任务完成后更新
            
            return success
            
        except Exception as e:
            error(f"处理任务 {task_id} 异常: {e}")
            self._update_task_status(task_id, 20)  # 标记为失败
            return False
    
    def run(self, interval: int = 5):
        """
        运行任务分配器
        
        Args:
            interval: 轮询间隔（秒）
        """
        info("任务分配器启动")
        
        try:
            # 初始化连接
            self._init_db_connection()
            self._init_mns_connection()
            
            # 主循环
            while self.running:
                try:
                    # 获取待处理任务
                    tasks = self._get_pending_tasks()
                    
                    if tasks:
                        info(f"发现 {len(tasks)} 个待处理任务")
                        
                        for task in tasks:
                            if not self.running:
                                break
                            self._process_task(task)
                    else:
                        debug("暂无待处理任务")
                    
                    # 等待一段时间后继续
                    time.sleep(interval)
                    
                except Exception as e:
                    error(f"处理任务列表异常: {e}")
                    time.sleep(interval)
            
        except KeyboardInterrupt:
            info("收到中断信号，准备退出")
        except Exception as e:
            error(f"任务分配器运行异常: {e}")
        finally:
            # 清理资源
            if self.connection:
                close_mysql_connection()
            info("任务分配器退出")
    
    def stop(self):
        """停止任务分配器"""
        self.running = False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='任务分配服务 - 轮询auto_task并创建子任务')
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.rbase.yaml',
        help='配置文件路径（默认: config.rbase.yaml）'
    )
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=5,
        help='轮询间隔（秒）（默认: 5）'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    else:
        set_dev_mode(False)
        set_level(logging.INFO)
    
    # 禁用第三方库的DEBUG日志
    logging.getLogger('mns_python_sdk').setLevel(logging.WARNING)
    logging.getLogger('mns').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # 获取配置文件绝对路径
    if not os.path.isabs(args.config):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            args.config
        )
    else:
        config_path = args.config
    
    if not os.path.exists(config_path):
        print(f"错误: 配置文件不存在: {config_path}")
        return 1
    
    # 加载配置
    config = Configuration(config_path)
    
    # 创建并运行任务分配器
    try:
        dispatcher = TaskDispatcher(config)
        
        # 注册信号处理
        def signal_handler(signum, frame):
            dispatcher.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        dispatcher.run(interval=args.interval)
        return 0
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

