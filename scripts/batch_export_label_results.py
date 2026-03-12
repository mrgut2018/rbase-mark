#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导出符合条件的文章的标注结果到Excel文件。

该脚本的执行流程：
1. 接收term_id, dimension_id, limit, offset等参数
2. 根据SQL查询获取符合条件的raw_article_id列表
3. 对于每个raw_article_id：
   - 调用LabelTaskResultExporter的export_to_excel_by_article方法
   - 默认导出最近5个任务的标注结果
4. 输出统计信息

作者: AI Assistant
创建时间: 2025年11月15日
"""

import logging
import os
import sys
import time
import argparse
from typing import List
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from scripts.batch_classify_articles import BatchArticleClassifier
from scripts.export_label_task_result import LabelTaskResultExporter


class BatchLabelResultExporter:
    """批量标注结果导出器类"""
    
    def __init__(self, config: Configuration, **kwargs):
        """
        初始化批量标注结果导出器
        
        Args:
            config: 配置对象
            **kwargs: 其他参数
        """
        self.config = config
        self.env = kwargs.get('env', 'dev')
        self.collection_name = kwargs.get('collection_name', 'classifier_value_entities')
        self.task_limit = kwargs.get('task_limit', 5)  # 每个文章导出的任务数量
        
        # 初始化BatchArticleClassifier以使用其get_articles_by_term方法
        self.article_classifier = BatchArticleClassifier(
            config,
            env=self.env,
            collection_name=self.collection_name
        )
        
        # 初始化LabelTaskResultExporter
        self.result_exporter = LabelTaskResultExporter(config)
        
        # 统计信息
        self.stats = {
            'total': 0,
            'success': [],  # 成功导出的文章ID
            'failed': [],   # 失败的文章ID及原因
            'skipped': [],  # 跳过的文章ID及原因
        }
    
    def export_article(self, raw_article_id: int) -> bool:
        """
        导出单篇文章的标注结果
        
        Args:
            raw_article_id: 文章ID
            
        Returns:
            是否成功
        """
        info(f"\n{'='*60}")
        info(f"开始导出文章 {raw_article_id} 的标注结果")
        
        try:
            # 调用LabelTaskResultExporter的export_to_excel_by_article方法
            success = self.result_exporter.export_to_excel_by_article(
                raw_article_id=raw_article_id,
                limit=self.task_limit,
                output_file=None  # 使用默认路径
            )
            
            if success:
                info(f"✅ 文章 {raw_article_id} 导出成功")
                self.stats['success'].append(raw_article_id)
                return True
            else:
                reason = "导出失败（可能没有已完成的标注任务）"
                info(f"⚠️  文章 {raw_article_id} {reason}")
                self.stats['skipped'].append({
                    'raw_article_id': raw_article_id,
                    'reason': reason
                })
                return False
                
        except Exception as e:
            reason = f"执行异常: {str(e)}"
            error(f"❌ 文章 {raw_article_id} 导出失败: {reason}")
            self.stats['failed'].append({
                'raw_article_id': raw_article_id,
                'reason': reason
            })
            return False
    
    def batch_export(self, term_id: int, dimension_id: int = 2, 
                    limit: int = 10, offset: int = 0):
        """
        批量导出文章标注结果
        
        Args:
            term_id: 词条ID
            dimension_id: 维度ID
            limit: 处理文章数量限制
            offset: 文章偏移量
        """
        start_time = time.time()
        
        color_print(f"\n{'='*80}")
        color_print("批量导出标注结果任务开始")
        color_print(f"{'='*80}")
        color_print(f"词条ID: {term_id}")
        color_print(f"维度ID: {dimension_id}")
        color_print(f"处理数量: {limit}, 偏移量: {offset}")
        color_print(f"每篇文章导出任务数: {self.task_limit}")
        color_print(f"{'='*80}\n")
        
        # 获取文章列表
        article_ids = self.article_classifier.get_articles_by_term(
            term_id, dimension_id, limit, offset
        )
        
        if not article_ids:
            error("未找到符合条件的文章，任务终止")
            return
        
        self.stats['total'] = len(article_ids)
        info(f"找到 {len(article_ids)} 篇待处理文章\n")
        
        # 逐个导出文章
        for idx, article_id in enumerate(article_ids, 1):
            color_print(f"\n[{idx}/{len(article_ids)}] 导出文章 {article_id}")
            self.export_article(article_id)
        
        # 输出统计信息
        self._print_statistics(start_time)
    
    def _print_statistics(self, start_time: float):
        """
        打印统计信息
        
        Args:
            start_time: 开始时间
        """
        elapsed_time = time.time() - start_time
        
        color_print(f"\n{'='*80}")
        color_print("批量导出任务完成")
        color_print(f"{'='*80}")
        color_print(f"总耗时: {elapsed_time:.2f} 秒")
        color_print(f"总文章数: {self.stats['total']}")
        color_print(f"成功导出: {len(self.stats['success'])}")
        color_print(f"跳过: {len(self.stats['skipped'])}")
        color_print(f"失败: {len(self.stats['failed'])}")
        color_print(f"{'='*80}\n")
        
        # 详细列出成功导出的文章
        if self.stats['success']:
            color_print("成功导出的文章:")
            for article_id in self.stats['success']:
                color_print(f"  - 文章ID {article_id}")
            color_print("")
        
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
    
    def cleanup(self):
        """清理资源"""
        if self.article_classifier:
            self.article_classifier.cleanup()
        if self.result_exporter:
            self.result_exporter.cleanup()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='批量导出符合条件的文章的标注结果到Excel')
    parser.add_argument('-t', '--term-id', type=int, required=True, 
                       help='词条ID')
    parser.add_argument('-d', '--dimension-id', type=int, default=2, 
                       help='维度ID，默认为2')
    parser.add_argument('-l', '--limit', type=int, default=10, 
                       help='处理文章数量限制，默认为10')
    parser.add_argument('-o', '--offset', type=int, default=0, 
                       help='文章偏移量，默认为0')
    parser.add_argument('-n', '--task-limit', type=int, default=5,
                       help='每篇文章导出的任务数量，默认为5')
    parser.add_argument('-e', '--env', type=str, default='dev', 
                       help='环境，默认为dev')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='显示详细信息')
    
    args = parser.parse_args()
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        debug(f"词条ID: {args.term_id}")
        debug(f"维度ID: {args.dimension_id}")
        debug(f"处理限制: {args.limit}")
        debug(f"偏移量: {args.offset}")
        debug(f"每篇文章任务数: {args.task_limit}")
        debug("-" * 50)
    
    # 初始化配置
    init_rbase_config()
    
    batch_exporter = None
    try:
        # 创建批量导出器
        batch_exporter = BatchLabelResultExporter(
            configuration.config,
            env=args.env,
            task_limit=args.task_limit
        )
        
        # 执行批量导出
        batch_exporter.batch_export(
            term_id=args.term_id,
            dimension_id=args.dimension_id,
            limit=args.limit,
            offset=args.offset
        )
        
        return 0
        
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if batch_exporter:
            batch_exporter.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())

