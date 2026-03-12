#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为符合条件的文章执行分类的脚本。

该脚本的执行流程：
1. 接收classifier_group_id和term_id参数
2. 根据SQL查询获取符合条件的raw_article_id列表
3. 对于每个raw_article_id：
   - 检查该分类器组中的所有分类器是否已有进行中的任务
   - 如果有任务则跳过，否则执行分类
4. 输出统计信息

作者: AI Assistant
创建时间: 2025年10月31日
"""

import logging
import os
import sys
import time
import argparse
from typing import List, Tuple
from datetime import datetime
from deepsearcher.rbase.ai_models import LabelRawArticleTaskStatus
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from scripts.classify_raw_article import RawArticleClassifier

class BatchArticleClassifierStatus:
    def __init__(self):
        self.has_task: bool = False
        self.task_ids: List[int] = []
        self.classifier_ids: List[int] = []
        self.has_running_task: bool = False
        self.running_task_ids: List[int] = []
        self.has_unexpected_error_task: bool = False

    def reset(self):
        self.has_task = False
        self.task_ids = []
        self.classifier_ids = []
        self.has_running_task = False
        self.running_task_ids = []
        self.has_unexpected_error_task = False


class BatchArticleClassifier:
    """批量文章分类器类"""
    
    def __init__(self, config: Configuration, **kwargs):
        """
        初始化批量文章分类器
        
        Args:
            config: 配置对象
            **kwargs: 其他参数
        """
        self.config = config
        self.connection = None
        self.env = kwargs.get('env', 'dev')
        self.collection_name = kwargs.get('collection_name', 'classifier_value_entities')
        
        self._init_db_connection()
        
        # 统计信息
        self.stats = {
            'total': 0,
            'skipped': [],  # 跳过的文章ID及原因
            'failed': [],   # 失败的文章ID及原因
            'success': [],  # 成功的文章ID
        }
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise
    
    def get_articles_by_term(self, term_id: int, dimension_id: int = 2, 
                            limit: int = 10, offset: int = 0) -> List[int]:
        """
        根据term_id查询符合条件的文章ID列表
        
        Args:
            term_id: 词条ID
            dimension_id: 维度ID，默认为2
            limit: 返回结果数量限制
            offset: 结果偏移量
            
        Returns:
            文章ID列表
        """
        try:
            # 确保数据库连接可用
            if not self.connection or not self.connection.open:
                self._init_db_connection()
                
            with self.connection.cursor() as cursor:
                sql = """
                SELECT a.raw_article_id FROM `article_label` al 
                JOIN article a ON al.article_id = a.id 
                WHERE al.term_id = %s 
                    AND al.status = 1 AND al.dimension_id = %s AND al.article_id > 0 
                    AND a.status = 1 AND a.txt_file LIKE '%%.md'
                ORDER BY a.id ASC LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (term_id, dimension_id, limit, offset))
                results = cursor.fetchall()
                
                article_ids = [row['raw_article_id'] for row in results]
                info(f"查询到 {len(article_ids)} 篇符合条件的文章")
                return article_ids
                
        except Exception as e:
            error(f"查询文章失败: {e}")
            return []
    
    def get_classifier_ids_by_group(self, classifier_group_id: int) -> Tuple[List[int], str]:
        """
        根据分类器组ID获取其中的分类器ID列表
        
        Args:
            classifier_group_id: 分类器组ID
            
        Returns:
            (分类器ID列表, 分类器组名称)
        """
        try:
            # 确保数据库连接可用
            if not self.connection or not self.connection.open:
                self._init_db_connection()
                
            with self.connection.cursor() as cursor:
                # 验证分类器组是否存在
                cursor.execute(
                    "SELECT id, name, `desc` FROM classifier_group WHERE id = %s AND status = 1",
                    (classifier_group_id,)
                )
                group_result = cursor.fetchone()
                if not group_result:
                    error(f"分类器组ID {classifier_group_id} 不存在或状态无效")
                    return [], ""
                
                debug(f"找到分类器组: {group_result['name']} - {group_result['desc']}")
                
                # 获取分类器组中的分类器列表
                sql = """
                SELECT cgr.classifier_id, cgr.seq, c.name, c.alias
                FROM classifier_group_relation cgr
                INNER JOIN classifier c ON cgr.classifier_id = c.id
                WHERE cgr.classifier_group_id = %s AND c.status = 1
                ORDER BY cgr.seq ASC, cgr.classifier_id ASC
                """
                cursor.execute(sql, (classifier_group_id,))
                results = cursor.fetchall()
                
                if not results:
                    error(f"分类器组 {classifier_group_id} 中没有有效的分类器")
                    return [], group_result['name']
                
                classifier_ids = []
                debug(f"分类器组中包含 {len(results)} 个分类器:")
                for result in results:
                    classifier_ids.append(result['classifier_id'])
                    debug(f"  - ID: {result['classifier_id']}, 名称: {result['name']} ({result['alias']})")
                
                return classifier_ids, group_result['name']
                
        except Exception as e:
            error(f"查询分类器组失败: {e}")
            return [], ""
    
    def check_existing_tasks(self, raw_article_id: int, classifier_ids: List[int], days: int = 30) -> BatchArticleClassifierStatus:
        """
        检查指定文章和分类器列表是否已有进行中的任务
        
        Args:
            raw_article_id: 文章ID
            classifier_ids: 分类器ID列表
            days: 检查的时间范围，默认为30天
            
        Returns:
            (是否有任务, 有任务的分类器ID列表)
        """
        try:
            # 确保数据库连接可用
            if not self.connection or not self.connection.open:
                self._init_db_connection()
            
            with self.connection.cursor() as cursor:
                # 查询该文章是否有进行中的任务（status = 100表示正常取消的任务， 大于100表示非正常取消）
                sql = """
                SELECT DISTINCT lrati.classifier_id, lrati.status as status, lrat.id as task_id
                FROM label_raw_article_task lrat
                JOIN label_raw_article_task_item lrati ON lrat.id = lrati.label_raw_article_task_id
                WHERE lrat.raw_article_id = %s 
                    AND lrat.created >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND lrat.status != %s
                    AND lrati.status != %s
                    AND lrati.classifier_id IN ({})
                """.format(','.join(['%s'] * len(classifier_ids)))
                params = [raw_article_id, days, LabelRawArticleTaskStatus.CANCELLED.value, LabelRawArticleTaskStatus.CANCELLED.value]
                cursor.execute(sql,  params + classifier_ids)
                results = cursor.fetchall()
                
                status = BatchArticleClassifierStatus()
                for row in results:
                    status.has_task = True
                    if row['status'] == LabelRawArticleTaskStatus.UNEXPECTED_ERROR:
                        status.has_unexpected_error_task = True
                    if row['status'] == LabelRawArticleTaskStatus.RUNNING:
                        status.has_running_task = True
                        if row['task_id'] not in status.running_task_ids:
                            status.running_task_ids.append(row['task_id'])
                    if row['task_id'] not in status.task_ids:
                        status.task_ids.append(row['task_id'])
                
                if status.has_unexpected_error_task:
                    debug(f"文章 {raw_article_id} 有状态异常的任务，需要删除: {status.task_ids}")
                    self.delete_tasks(status.task_ids)
                    status.reset()
                
                if status.has_task:
                    if status.has_running_task:
                        debug(f"文章 {raw_article_id} 已有以下分类器的进行中任务: {status.running_task_ids}")
                    else:
                        debug(f"文章 {raw_article_id} 已有以下分类器的执行完成的任务: {status.task_ids}")
                else:
                    debug(f"文章 {raw_article_id} 没有进行中的任务")
                return status
                    
        except Exception as e:
            error(f"检查任务状态失败: {e}")
            return True, []  # 出错时保守处理，认为有任务
    
    def delete_tasks(self, task_ids: List[int]):
        try:
            # 确保数据库连接可用
            if not self.connection or not self.connection.open:
                self._init_db_connection()

            with self.connection.cursor() as cursor:
                sql = """DELETE FROM label_raw_article_task_result WHERE
                label_raw_article_task_id IN ({})
                """.format(','.join(['%s'] * len(task_ids)))
                cursor.execute(sql, task_ids)
                sql = """DELETE FROM label_raw_article_task_item WHERE
                label_raw_article_task_id IN ({})
                """.format(','.join(['%s'] * len(task_ids)))
                cursor.execute(sql, task_ids)
                sql = """DELETE FROM label_raw_article_task WHERE id IN ({})
                """.format(','.join(['%s'] * len(task_ids)))
                cursor.execute(sql, task_ids)

                self.connection.commit()
                info(f"删除 {len(task_ids)} 个任务")
        except Exception as e:
            error(f"删除任务失败: {e}")
            return False

    def cancel_historical_tasks(self, raw_article_id: int, classifier_ids: List[int]) -> int:
        """
        取消指定文章和分类器列表的所有历史任务（将状态改为已取消）

        Args:
            raw_article_id: 文章ID
            classifier_ids: 分类器ID列表

        Returns:
            取消的任务数量
        """
        if not classifier_ids:
            return 0

        try:
            # 确保数据库连接可用
            if not self.connection or not self.connection.open:
                self._init_db_connection()

            with self.connection.cursor() as cursor:
                # 先查询需要取消的任务ID
                sql = """
                SELECT DISTINCT lrat.id as task_id
                FROM label_raw_article_task lrat
                JOIN label_raw_article_task_item lrati ON lrat.id = lrati.label_raw_article_task_id
                WHERE lrat.raw_article_id = %s
                    AND lrat.status != %s
                    AND lrati.classifier_id IN ({})
                """.format(','.join(['%s'] * len(classifier_ids)))
                params = [raw_article_id, LabelRawArticleTaskStatus.CANCELLED.value] + classifier_ids
                cursor.execute(sql, params)
                results = cursor.fetchall()

                if not results:
                    debug(f"文章 {raw_article_id} 没有需要取消的历史任务")
                    return 0

                task_ids = [row['task_id'] for row in results]

                # 更新 label_raw_article_task_result 状态为已取消
                sql = """
                UPDATE label_raw_article_task_result
                SET status = %s, modified = NOW()
                WHERE label_raw_article_task_id IN ({})
                """.format(','.join(['%s'] * len(task_ids)))
                cursor.execute(sql, [LabelRawArticleTaskStatus.CANCELLED.value] + task_ids)

                # 更新 label_raw_article_task_item 状态为已取消（只更新指定分类器的）
                sql = """
                UPDATE label_raw_article_task_item
                SET status = %s, modified = NOW()
                WHERE label_raw_article_task_id IN ({})
                    AND classifier_id IN ({})
                """.format(
                    ','.join(['%s'] * len(task_ids)),
                    ','.join(['%s'] * len(classifier_ids))
                )
                cursor.execute(sql, [LabelRawArticleTaskStatus.CANCELLED.value] + task_ids + classifier_ids)

                # 更新 label_raw_article_task 状态为已取消
                sql = """
                UPDATE label_raw_article_task
                SET status = %s, modified = NOW()
                WHERE id IN ({})
                """.format(','.join(['%s'] * len(task_ids)))
                cursor.execute(sql, [LabelRawArticleTaskStatus.CANCELLED.value] + task_ids)

                self.connection.commit()
                info(f"已取消文章 {raw_article_id} 的 {len(task_ids)} 个历史任务")
                return len(task_ids)

        except Exception as e:
            error(f"取消历史任务失败: {e}")
            return 0


    
    def process_article(self, raw_article_id: int, classifier_group_id: int,
                       classifier_ids: List[int], retask_days: int = 30,
                       clear_history: bool = True) -> bool:
        """
        处理单篇文章的分类任务

        Args:
            raw_article_id: 文章ID
            classifier_group_id: 分类器组ID
            classifier_ids: 分类器ID列表
            retask_days: 检查已有任务的时间范围，默认为30天
            clear_history: 是否清除历史任务数据，默认为True

        Returns:
            是否成功
        """
        info(f"\n{'='*60}")
        info(f"开始处理文章 {raw_article_id}")

        # 检查是否已有任务
        tasks_status = self.check_existing_tasks(raw_article_id, classifier_ids, retask_days)

        if tasks_status.has_task:
            reason = f"已有分类器任务: {tasks_status.classifier_ids}"
            info(f"跳过文章 {raw_article_id}: {reason}")
            self.stats['skipped'].append({
                'raw_article_id': raw_article_id,
                'reason': reason
            })
            return False

        # 如果没有近期任务且需要清除历史任务，则取消历史任务
        if clear_history:
            self.cancel_historical_tasks(raw_article_id, classifier_ids)
        
        # 执行分类任务
        try:
            # 初始化分类器
            article_classifier = RawArticleClassifier(
                self.config,
                configuration.vector_db,
                configuration.embedding_model,
                configuration.academic_translator,
                env=self.env,
                collection_name=self.collection_name
            )
            
            # 执行分类
            result = article_classifier.classify_article(
                classifier_id=None,
                classifier_group_id=classifier_group_id,
                raw_article_id=raw_article_id
            )
            
            # 检查结果
            if result and result.get('success_count', 0) > 0:
                info(f"✅ 文章 {raw_article_id} 分类成功: {result['success_count']}/{result['total_classifiers']}")
                self.stats['success'].append({
                    'raw_article_id': raw_article_id,
                    'success_count': result['success_count'],
                    'total_count': result['total_classifiers'],
                    'task_id': result.get('task_id')
                })
                return True
            else:
                reason = "分类结果为空或所有分类器都失败"
                error(f"❌ 文章 {raw_article_id} 分类失败: {reason}")
                self.stats['failed'].append({
                    'raw_article_id': raw_article_id,
                    'reason': reason
                })
                return False
                
        except Exception as e:
            reason = f"执行异常: {str(e)}"
            error(f"❌ 文章 {raw_article_id} 处理失败: {reason}")
            self.stats['failed'].append({
                'raw_article_id': raw_article_id,
                'reason': reason
            })
            return False
    
    def batch_process(self, classifier_group_id: int, term_id: int,
                     dimension_id: int = 2, limit: int = 10, offset: int = 0,
                     retask_days: int = 30, clear_history: bool = True):
        """
        批量处理文章分类

        Args:
            classifier_group_id: 分类器组ID
            term_id: 词条ID
            dimension_id: 维度ID
            limit: 处理文章数量限制
            offset: 文章偏移量
            retask_days: 检查已有任务的时间范围
            clear_history: 是否清除历史任务数据，默认为True
        """
        start_time = time.time()
        
        color_print(f"{'='*80}")
        color_print("批量文章分类任务开始")
        color_print(f"{'='*80}")
        color_print(f"分类器组ID: {classifier_group_id}")
        color_print(f"词条ID: {term_id}")
        color_print(f"维度ID: {dimension_id}")
        color_print(f"处理数量: {limit}, 偏移量: {offset}")
        color_print(f"{'='*80}\n")
        
        # 获取分类器列表
        classifier_ids, group_name = self.get_classifier_ids_by_group(classifier_group_id)
        if not classifier_ids:
            error("无法获取分类器列表，任务终止")
            return
        
        info(f"分类器组: {group_name} (共 {len(classifier_ids)} 个分类器)")
        
        # 获取文章列表
        article_ids = self.get_articles_by_term(term_id, dimension_id, limit, offset)
        if not article_ids:
            error("未找到符合条件的文章，任务终止")
            return
        
        self.stats['total'] = len(article_ids)
        info(f"找到 {len(article_ids)} 篇待处理文章")
        
        # 逐个处理文章
        for idx, article_id in enumerate(article_ids, 1):
            color_print(f"[{idx}/{len(article_ids)}] 处理文章 {article_id}")
            self.process_article(article_id, classifier_group_id, classifier_ids, retask_days, clear_history)
            
            # 确保数据库连接在下次循环前可用
            if not self.connection or not self.connection.open:
                info("重新建立数据库连接...")
                self._init_db_connection()
            
            # 添加短暂延迟，避免对系统造成过大压力
            if idx < len(article_ids):
                time.sleep(1)
        
        # 输出统计信息
        self._print_statistics(start_time)
    
    def _print_statistics(self, start_time: float):
        """
        打印统计信息
        
        Args:
            start_time: 开始时间
        """
        elapsed_time = time.time() - start_time
        
        color_print(f"{'='*80}")
        color_print("批量分类任务完成")
        color_print(f"{'='*80}")
        color_print(f"总耗时: {elapsed_time:.2f} 秒")
        color_print(f"总文章数: {self.stats['total']}")
        color_print(f"成功: {len(self.stats['success'])}")
        color_print(f"跳过: {len(self.stats['skipped'])}")
        color_print(f"失败: {len(self.stats['failed'])}")
        color_print(f"{'='*80}\n")
        
        # 详细列出跳过的文章
        if self.stats['skipped']:
            color_print("跳过的文章:")
            for item in self.stats['skipped']:
                color_print(f"  - 文章ID {item['raw_article_id']}: {item['reason']}")
            color_print("")
        
        # 详细列出失败的文章
        if self.stats['failed']:
            color_print("失败的文章:")
            for item in self.stats['failed']:
                color_print(f"  - 文章ID {item['raw_article_id']}: {item['reason']}")
            color_print("")
        
        # 详细列出成功的文章
        if self.stats['success']:
            color_print("成功的文章:")
            for item in self.stats['success']:
                color_print(f"  - 文章ID {item['raw_article_id']}: "
                          f"{item['success_count']}/{item['total_count']} 个分类器成功, "
                          f"任务ID: {item['task_id']}")
            color_print("")
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量为符合条件的文章执行分类')
    parser.add_argument('-g', '--classifier-group-id', type=int, required=True, 
                       help='分类器组ID')
    parser.add_argument('-t', '--term-id', type=int, required=True, 
                       help='词条ID')
    parser.add_argument('-d', '--dimension-id', type=int, default=2, 
                       help='维度ID，默认为2')
    parser.add_argument('-l', '--limit', type=int, default=10, 
                       help='处理文章数量限制，默认为10')
    parser.add_argument('-o', '--offset', type=int, default=0, 
                       help='文章偏移量，默认为0')
    parser.add_argument('-e', '--env', type=str, default='dev', 
                       help='环境，默认为dev')
    parser.add_argument('-n', '--collection-name', type=str, default='classifier_value_entities', 
                       help='向量库集合名称，默认为classifier_value_entities')
    parser.add_argument('--retask-days', type=int, default=30,
                       help='检查已有任务的时间范围，默认为30天')
    parser.add_argument('--no-clear-history', dest='clear_history', action='store_false',
                       default=True, help='不清除历史任务数据（默认会清除历史任务）')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='显示详细信息')
    
    args = parser.parse_args()
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        debug(f"分类器组ID: {args.classifier_group_id}")
        debug(f"词条ID: {args.term_id}")
        debug(f"维度ID: {args.dimension_id}")
        debug(f"处理限制: {args.limit}")
        debug(f"偏移量: {args.offset}")
        debug(f"环境: {args.env}")
        debug(f"向量库集合名称: {args.collection_name}")
        debug(f"检查已有任务的时间范围: {args.retask_days} 天")
        debug(f"清除历史任务数据: {args.clear_history}")
        debug("-" * 50)
    
    # 初始化配置
    init_rbase_config()
    
    batch_classifier = None
    try:
        # 创建批量分类器
        batch_classifier = BatchArticleClassifier(
            configuration.config,
            env=args.env,
            collection_name=args.collection_name
        )
        
        # 执行批量处理
        batch_classifier.batch_process(
            classifier_group_id=args.classifier_group_id,
            term_id=args.term_id,
            dimension_id=args.dimension_id,
            limit=args.limit,
            offset=args.offset,
            retask_days=args.retask_days,
            clear_history=args.clear_history
        )
        
        return 0
        
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if batch_classifier:
            batch_classifier.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())

