#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分类服务 - 从阿里云MNS接收消息并执行文章分类任务

该服务支持多进程处理，每个进程从MNS队列接收消息并执行分类任务。

主要功能：
1. 从阿里云MNS队列接收消息
2. 根据消息内容执行文章分类
3. 更新auto_sub_task和auto_task状态

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
import multiprocessing
from typing import Optional, Dict, Any

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mns.account import Account

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.tools.log import info, warning, debug, error, set_dev_mode, set_level
from deepsearcher.tools.json_util import safe_json_loads
from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from scripts.classify_raw_article import RawArticleClassifier


class ClassifyServiceWorker:
    """分类服务工作进程"""
    
    def __init__(self, worker_id: int, config: Configuration, mns_config: dict):
        """
        初始化工作进程
        
        Args:
            worker_id: 工作进程ID
            config: 配置对象
            mns_config: MNS配置字典
        """
        self.worker_id = worker_id
        self.config = config
        self.mns_config = mns_config
        self.running = True
        self.connection = None
        self.mns_account = None
        self.mns_queue = None
        
    def _init_mns_connection(self):
        """初始化MNS连接"""
        try:
            endpoint = self.mns_config.get('endpoint')
            access_id = self.mns_config.get('access_id')
            access_key = self.mns_config.get('access_key')
            queue_name = self.mns_config.get('queue_name')
            # 是否验证SSL证书，默认为False（在开发环境中禁用SSL验证）
            verify_ssl = self.mns_config.get('verify_ssl', False)
            
            if not all([endpoint, access_id, access_key, queue_name]):
                raise ValueError("MNS配置不完整")
            
            # 如果不验证SSL，需要禁用SSL警告并设置环境变量
            if not verify_ssl:
                pass
                # import ssl
                # import urllib3
                # urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                # # 设置不验证SSL
                # ssl._create_default_https_context = ssl._create_unverified_context
                # warning(f"Worker {self.worker_id}: SSL验证已禁用（不推荐用于生产环境）")
            
            # 创建MNS账户连接（设置debug=False以减少输出）
            self.mns_account = Account(endpoint, access_id, access_key, debug=False)
            self.mns_queue = self.mns_account.get_queue(queue_name)
            info(f"Worker {self.worker_id}: MNS连接成功 - {queue_name}")
        except Exception as e:
            error(f"Worker {self.worker_id}: MNS连接失败: {e}")
            raise
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info(f"Worker {self.worker_id}: 数据库连接成功")
        except Exception as e:
            error(f"Worker {self.worker_id}: 数据库连接失败: {e}")
            raise
    
    def _ensure_db_connection(self):
        """确保数据库连接有效，如果断开则重连"""
        try:
            # 尝试ping数据库
            if self.connection:
                self.connection.ping(reconnect=True)
        except Exception as e:
            warning(f"Worker {self.worker_id}: 数据库连接失效，尝试重连: {e}")
            try:
                self._init_db_connection()
            except Exception as reconnect_error:
                error(f"Worker {self.worker_id}: 数据库重连失败: {reconnect_error}")
                raise
    
    
    def _update_auto_sub_task_status(self, auto_sub_task_id: int, status: str, params: Optional[Dict] = None):
        """
        更新auto_sub_task状态
        
        Args:
            auto_sub_task_id: 子任务ID
            status: 状态值
            params: 可选的参数字典（用于更新params字段）
        """
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            with self.connection.cursor() as cursor:
                if params:
                    sql = """
                    UPDATE auto_sub_task 
                    SET status = %s, params = %s, modified = NOW()
                    WHERE id = %s
                    """
                    cursor.execute(sql, (status, json.dumps(params), auto_sub_task_id))
                else:
                    sql = """
                    UPDATE auto_sub_task 
                    SET status = %s, modified = NOW()
                    WHERE id = %s
                    """
                    cursor.execute(sql, (status, auto_sub_task_id))
                self.connection.commit()
                info(f"Worker {self.worker_id}: 更新auto_sub_task {auto_sub_task_id} 状态为 {status}")
        except Exception as e:
            error(f"Worker {self.worker_id}: 更新auto_sub_task状态失败: {e}")
            self.connection.rollback()
    
    def _check_and_update_auto_task_status(self, auto_task_id: int):
        """
        检查auto_task的所有子任务是否都完成，如果是则更新auto_task状态
        
        Args:
            auto_task_id: 任务ID
        """
        try:
            # 确保数据库连接有效
            self._ensure_db_connection()
            
            with self.connection.cursor() as cursor:
                # 查询该任务下所有子任务的状态
                sql = """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status = '10' THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN status = '20' THEN 1 ELSE 0 END) as failed
                FROM auto_sub_task
                WHERE auto_task_id = %s
                """
                cursor.execute(sql, (auto_task_id,))
                result = cursor.fetchone()
                
                if not result:
                    return
                
                total = result['total']
                completed = result['completed']
                failed = result['failed']
                
                # 如果所有子任务都完成了（成功或失败）
                if completed + failed == total:
                    # 确定任务最终状态
                    if failed == 0:
                        final_status = '10'  # 全部成功
                    elif completed == 0:
                        final_status = '20'  # 全部失败
                    else:
                        final_status = '10'  # 部分成功也算完成
                    
                    # 更新auto_task状态
                    update_sql = """
                    UPDATE auto_task 
                    SET status = %s, finished = NOW(), modified = NOW()
                    WHERE id = %s
                    """
                    cursor.execute(update_sql, (final_status, auto_task_id))
                    self.connection.commit()
                    info(
                        f"Worker {self.worker_id}: 任务 {auto_task_id} 所有子任务完成 "
                        f"(成功:{completed}, 失败:{failed}), 更新状态为 {final_status}"
                    )
        except Exception as e:
            error(f"Worker {self.worker_id}: 检查并更新auto_task状态失败: {e}")
            self.connection.rollback()
    
    def _process_message(self, message_data: Dict[str, Any]) -> bool:
        """
        处理单条消息
        
        Args:
            message_data: 消息数据字典，包含以下字段：
                - auto_task_id: 任务ID
                - auto_sub_task_id: 子任务ID
                - raw_article_id: 文章ID
                - base_id: 用户库ID
                - classifier_id: 分类器ID（可选，与classifier_group_id二选一）
                - classifier_group_id: 分类器组ID（可选，与classifier_id二选一）
                
        Returns:
            是否处理成功
        """
        auto_task_id = message_data.get('auto_task_id')
        auto_sub_task_id = message_data.get('auto_sub_task_id')
        raw_article_id = message_data.get('raw_article_id')
        base_id = message_data.get('base_id')
        base_id = base_id if base_id else None
        classifier_id = message_data.get('classifier_id')
        classifier_group_id = message_data.get('classifier_group_id')
        
        # 验证必需字段
        if not all([auto_task_id, auto_sub_task_id, raw_article_id]):
            error(f"Worker {self.worker_id}: 消息字段不完整: {message_data}")
            return False
        
        # classifier_id 和 classifier_group_id 必须至少提供其中之一
        if not classifier_id and not classifier_group_id:
            error(
                f"Worker {self.worker_id}: classifier_id 和 classifier_group_id 必须提供其中之一: {message_data}"
            )
            self._update_auto_sub_task_status(
                auto_sub_task_id, 
                '20',
                params={'error': 'classifier_id和classifier_group_id必须提供其中之一'}
            )
            return False
        
        # 如果同时提供了classifier_id和classifier_group_id，优先使用classifier_group_id
        if classifier_id and classifier_group_id:
            warning(
                f"Worker {self.worker_id}: 同时提供了classifier_id({classifier_id})和classifier_group_id({classifier_group_id})，"
                f"将使用classifier_group_id，忽略classifier_id"
            )
            classifier_id = None  # 清空classifier_id，确保后续只使用classifier_group_id

        try:
            # 更新子任务状态为执行中
            self._update_auto_sub_task_status(auto_sub_task_id, '2')
            
            # 初始化分类器
            classifier = RawArticleClassifier(
                self.config,
                configuration.vector_db,
                configuration.embedding_model,
                configuration.academic_translator,
                env=self.config.rbase_settings.get('env', 'dev')
            )
            
            # 执行分类
            if classifier_id:
                # 提供了classifier_id
                info(
                    f"Worker {self.worker_id}: 处理任务 {auto_task_id}/{auto_sub_task_id} - "
                    f"文章 {raw_article_id}, 分类器 {classifier_id}"
                )
                result = classifier.classify_article(
                    classifier_id=classifier_id,
                    classifier_group_id=None,
                    raw_article_id=raw_article_id,
                    base_id=base_id,
                    cancel_history_results=True
                )
            else:
                # 提供了classifier_group_id
                info(
                    f"Worker {self.worker_id}: 处理任务 {auto_task_id}/{auto_sub_task_id} - "
                    f"文章 {raw_article_id}, 分类器组 {classifier_group_id}"
                )
                result = classifier.classify_article(
                    classifier_id=None,
                    classifier_group_id=classifier_group_id,
                    raw_article_id=raw_article_id,
                    base_id=base_id,
                    cancel_history_results=True
                )
            
            # 清理资源
            classifier.cleanup()
            
            # 判断任务执行结果
            success = False
            if isinstance(result, dict):
                success = result.get('success_count', 0) > 0
            
            # 更新子任务状态
            if success:
                self._update_auto_sub_task_status(
                    auto_sub_task_id, 
                    '10',
                    params={'result': result}
                )
                info(f"Worker {self.worker_id}: 任务 {auto_sub_task_id} 执行成功")
            else:
                self._update_auto_sub_task_status(
                    auto_sub_task_id, 
                    '20',
                    params={'error': '分类失败', 'result': result}
                )
                error(f"Worker {self.worker_id}: 任务 {auto_sub_task_id} 执行失败")
            
            # 检查并更新auto_task状态
            self._check_and_update_auto_task_status(auto_task_id)
            
            return success
            
        except Exception as e:
            error(f"Worker {self.worker_id}: 处理消息异常: {e}")
            # 更新子任务状态为失败
            self._update_auto_sub_task_status(
                auto_sub_task_id, 
                '20',
                params={'error': str(e)}
            )
            # 检查并更新auto_task状态
            self._check_and_update_auto_task_status(auto_task_id)
            return False
    
    def _receive_and_process_messages(self):
        """接收并处理消息（循环）"""
        wait_seconds = 30  # 长轮询等待时间
        
        while self.running:
            try:
                # 接收消息（长轮询）
                recv_msg = self.mns_queue.receive_message(wait_seconds)

                if recv_msg.dequeue_count >= 3:
                    info(f"消息 {recv_msg.message_id} 已重试3次，跳过处理")
                    self.mns_queue.delete_message(recv_msg.receipt_handle)
                    continue
                
                # 解析消息
                message_body = recv_msg.message_body
                debug(f"Worker {self.worker_id}: 收到消息: {message_body}")
                
                # 解析JSON
                message_data = safe_json_loads(message_body)
                if not message_data:
                    error(f"Worker {self.worker_id}: 消息解析失败: {message_body}")
                    # 删除无效消息
                    self.mns_queue.delete_message(recv_msg.receipt_handle)
                    continue
                
                # 处理消息
                success = self._process_message(message_data)
                
                # 删除已处理的消息
                self.mns_queue.delete_message(recv_msg.receipt_handle)
                info(
                    f"Worker {self.worker_id}: 消息处理完成 - "
                    f"{'成功' if success else '失败'}"
                )
                
            except Exception as e:
                # MNS队列为空时会抛出异常，这是正常情况
                error_msg = str(e)
                if "QueueNotExist" in error_msg or "MessageNotExist" in error_msg:
                    debug(f"Worker {self.worker_id}: 队列暂无消息，继续等待...")
                    time.sleep(1)
                else:
                    error(f"Worker {self.worker_id}: 接收消息异常: {e}")
                    time.sleep(10)
    
    def run(self):
        """运行工作进程"""
        info(f"Worker {self.worker_id}: 启动")
        
        try:
            # 初始化连接
            self._init_db_connection()
            self._init_mns_connection()
            
            # 开始处理消息
            self._receive_and_process_messages()
            
        except KeyboardInterrupt:
            info(f"Worker {self.worker_id}: 收到中断信号，准备退出")
        except Exception as e:
            error(f"Worker {self.worker_id}: 运行异常: {e}")
        finally:
            # 清理资源
            if self.connection:
                close_mysql_connection()
            info(f"Worker {self.worker_id}: 退出")
    
    def stop(self):
        """停止工作进程"""
        self.running = False


def worker_process(worker_id: int, config_path: str, mns_config: dict, verbose: bool):
    """
    工作进程入口函数
    
    Args:
        worker_id: 工作进程ID
        config_path: 配置文件路径
        mns_config: MNS配置字典
        verbose: 是否显示详细日志
    """
    # 设置日志
    if verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    else:
        set_dev_mode(False)
        set_level(logging.INFO)
    
    # 禁用第三方库的DEBUG日志（避免输出过多HTTP请求详情）
    logging.getLogger('mns_python_sdk').setLevel(logging.WARNING)  # MNS SDK的默认logger名称
    logging.getLogger('mns').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # 初始化配置
    config = Configuration(config_path)
    init_config(config)
    
    # 创建并运行工作进程
    worker = ClassifyServiceWorker(worker_id, config, mns_config)
    
    # 注册信号处理
    def signal_handler(signum, frame):
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    worker.run()


class ClassifyService:
    """分类服务主进程"""
    
    def __init__(self, config_path: str, num_workers: int = 4, verbose: bool = False):
        """
        初始化服务
        
        Args:
            config_path: 配置文件路径
            num_workers: 工作进程数量
            log_level: 日志级别
        """
        self.config_path = config_path
        self.num_workers = num_workers
        self.verbose = verbose 
        self.workers = []
        self.running = True
        
        # 加载配置
        self.config = Configuration(config_path)
        self.mns_config = self.config.rbase_settings.get('mns', {})
        
        # 验证MNS配置
        if not all([
            self.mns_config.get('endpoint'),
            self.mns_config.get('access_id'),
            self.mns_config.get('access_key'),
            self.mns_config.get('queue_name')
        ]):
            raise ValueError("MNS配置不完整，请检查config.rbase.yaml中的rbase_settings.mns配置")
        
    
    def start(self):
        """启动服务"""
        info(f"启动分类服务，工作进程数: {self.num_workers}")
        
        # 启动工作进程
        for i in range(self.num_workers):
            worker = multiprocessing.Process(
                target=worker_process,
                args=(i + 1, self.config_path, self.mns_config, self.verbose)
            )
            worker.start()
            self.workers.append(worker)
            info(f"工作进程 {i + 1} 已启动 (PID: {worker.pid})")
        
        # 等待所有工作进程
        try:
            for worker in self.workers:
                worker.join()
        except KeyboardInterrupt:
            info("收到中断信号，准备停止服务")
            self.stop()
    
    def stop(self):
        """停止服务"""
        self.running = False
        info("停止所有工作进程...")
        
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=10)
                if worker.is_alive():
                    worker.kill()
        
        info("分类服务已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='分类服务 - 从MNS接收消息并执行分类任务')
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.rbase.yaml',
        help='配置文件路径（默认: config.rbase.yaml）'
    )
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=4,
        help='工作进程数量（默认: 4）'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    # 确定日志级别
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    else:
        set_dev_mode(False)
        set_level(logging.INFO)
    
    # 禁用第三方库的DEBUG日志（避免输出过多HTTP请求详情）
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
    
    # 创建并启动服务
    try:
        service = ClassifyService(config_path, args.workers, args.verbose)
        service.start()
        return 0
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

