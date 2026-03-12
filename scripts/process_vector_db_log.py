#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
向量数据库日志处理脚本

本脚本用于处理vector_db_data_log中的数据，筛选operation=1 AND status=0的记录，
然后在vector_db中查找对应的数据，可选择删除或仅展示摘要信息。

使用方法:
    python scripts/process_vector_db_log.py --delete
"""

import argparse
import os
import sys
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from tqdm import tqdm

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.tools import log
from deepsearcher.db.async_mysql_connection import get_mysql_pool


class VectorDbLogProcessor:
    """向量数据库日志处理器"""
    
    def __init__(self, config: Configuration):
        """
        初始化处理器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.vector_db = configuration.vector_db
        self.db_config = config.rbase_settings.get("database")
        self.summary = {
            "total_logs": 0,
            "matched_records": 0,
            "deleted_records": 0,
            "collections": {},
            "errors": []
        }
    
    async def get_pending_logs(self) -> List[Dict[str, Any]]:
        """
        获取待处理的日志记录
        
        Returns:
            待处理的日志记录列表
        """
        try:
            pool = await get_mysql_pool(self.db_config)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    sql = """
                    SELECT raw_article_id, collection, id_from, id_to, created, modified
                    FROM vector_db_data_log 
                    WHERE operation = 1 AND status = 0
                    ORDER BY created ASC
                    """
                    await cursor.execute(sql)
                    results = await cursor.fetchall()
                    
                    log.info(f"找到 {len(results)} 条待处理的日志记录")
                    return results
        except Exception as e:
            error_msg = f"获取待处理日志失败: {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
            return []
    
    def find_matching_records(self, raw_article_id: int, collection_name: str) -> List[Dict[str, Any]]:
        """
        在向量数据库中查找匹配的记录
        
        Args:
            raw_article_id: 原始文章ID
            
        Returns:
            匹配的记录列表
        """
        try:
            # 检查集合是否存在
            collections = self.vector_db.list_collections()
            collection_exists = any(col.collection_name == collection_name for col in collections)
            
            if not collection_exists:
                error_msg = f"集合 '{collection_name}' 不存在"
                log.error(error_msg)
                self.summary["errors"].append(error_msg)
                return []
            
            # 使用reference_id查询匹配的记录
            query_result = self.vector_db.client.query(
                collection_name=collection_name,
                filter=f"reference_id == {raw_article_id}",
                output_fields=[
                    "id",
                    "text",
                    "reference",
                    "reference_id",
                    "keywords",
                    "authors",
                    "author_ids",
                    "corresponding_authors",
                    "corresponding_author_ids",
                    "base_ids",
                    "impact_factor",
                    "rbase_factor",
                    "pubdate",
                    "metadata"
                ]
            )
            
            if query_result:
                log.debug(f"找到 {len(query_result)} 条匹配的记录 (raw_article_id: {raw_article_id})")
                return query_result
            else:
                log.debug(f"未找到匹配的记录 (raw_article_id: {raw_article_id})")
                return []
                
        except Exception as e:
            error_msg = f"查询向量数据库失败 (raw_article_id: {raw_article_id}): {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
            return []
    
    def delete_matching_records(self, raw_article_id: int, collection_name: str) -> int:
        """
        删除匹配的记录
        
        Args:
            raw_article_id: 原始文章ID
            
        Returns:
            删除的记录数量
        """
        try:
            # 使用reference_id删除匹配的记录
            delete_result = self.vector_db.delete_data(
                collection=collection_name,
                filter=f"reference_id == {raw_article_id}"
            )
            
            log.debug(f"删除了 {delete_result} 条记录 (raw_article_id: {raw_article_id})")
            return delete_result
            
        except Exception as e:
            error_msg = f"删除记录失败 (raw_article_id: {raw_article_id}): {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
            return 0
    
    def get_record_summary(self, records: List[Dict[str, Any]]) -> str:
        """
        获取记录摘要信息（用于tqdm描述）
        
        Args:
            records: 记录列表
            
        Returns:
            摘要信息字符串
        """
        if not records:
            return "无匹配记录"
        
        return f"找到{len(records)}条记录"
    
    async def process_logs(self, delete_mode: bool = False):
        """
        处理日志记录
        
        Args:
            delete_mode: 是否为删除模式
        """
        # 获取待处理的日志
        pending_logs = await self.get_pending_logs()
        self.summary["total_logs"] = len(pending_logs)
        
        if not pending_logs:
            log.info("没有待处理的日志记录")
            return
        
        log.info(f"开始处理 {len(pending_logs)} 条日志记录...")
        if delete_mode:
            log.warning("⚠️  删除模式已启用，将删除匹配的记录")
        
        # 使用tqdm显示处理进度
        with tqdm(total=len(pending_logs), desc="处理日志记录", unit="条") as pbar:
            # 处理每条日志
            for log_record in pending_logs:
                raw_article_id = log_record["raw_article_id"]
                collection = log_record["collection"]
                
                # 更新tqdm描述显示当前处理的raw_article_id
                pbar.set_description(f"处理: {raw_article_id}")
                
                # 查找匹配的记录
                matching_records = self.find_matching_records(raw_article_id, collection)
                
                if matching_records:
                    self.summary["matched_records"] += len(matching_records)
                    
                    # 更新集合统计
                    if collection not in self.summary["collections"]:
                        self.summary["collections"][collection] = {
                            "total_records": 0,
                            "deleted_records": 0
                        }
                    self.summary["collections"][collection]["total_records"] += len(matching_records)
                    
                    if delete_mode:
                        # 删除模式：删除匹配的记录
                        deleted_count = self.delete_matching_records(raw_article_id, collection)
                        self.summary["deleted_records"] += deleted_count
                        self.summary["collections"][collection]["deleted_records"] += deleted_count
                        
                        # 更新tqdm描述显示删除结果
                        pbar.set_postfix({
                            "匹配": len(matching_records),
                            "删除": deleted_count
                        })
                    else:
                        # 展示模式：更新tqdm描述显示匹配结果
                        pbar.set_postfix({
                            "匹配": len(matching_records)
                        })
                else:
                    # 更新tqdm描述显示无匹配
                    pbar.set_postfix({"匹配": 0})
                
                # 更新进度条
                pbar.update(1)
    
    def display_final_summary(self):
        """显示最终汇总信息"""
        log.color_print("=" * 80)
        log.color_print("📊 处理结果汇总")
        log.color_print("=" * 80)
        
        log.color_print(f"总日志记录数: {self.summary['total_logs']}")
        log.color_print(f"匹配的记录数: {self.summary['matched_records']}")
        
        if self.summary["deleted_records"] > 0:
            log.color_print(f"删除的记录数: {self.summary['deleted_records']}")
        
        if self.summary["collections"]:
            log.color_print("\n📁 各集合统计:")
            for collection, stats in self.summary["collections"].items():
                log.color_print(f"  {collection}:")
                log.color_print(f"    总记录数: {stats['total_records']}")
                if stats['deleted_records'] > 0:
                    log.color_print(f"    删除记录数: {stats['deleted_records']}")
        
        if self.summary["errors"]:
            log.color_print(f"\n❌ 错误信息 ({len(self.summary['errors'])} 个):")
            for i, error in enumerate(self.summary["errors"], 1):
                log.color_print(f"  {i}. {error}")
        
        log.color_print("=" * 80)


async def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(
        description="处理向量数据库日志，筛选并操作相关记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/process_vector_db_log.py --collection "prod_rbase_bge_base_en_v1_5_1"
  python scripts/process_vector_db_log.py -c "test_collection" --delete
  python scripts/process_vector_db_log.py -c "my_collection" -v
        """
    )
    
    parser.add_argument(
        "--delete",
        action="store_true",
        help="删除模式：删除匹配的记录（默认仅展示）"
    )
    
    parser.add_argument(
        "--config",
        default="config.rbase.yaml",
        help="配置文件路径 (默认: config.rbase.yaml)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="启用详细输出"
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        log.set_dev_mode(True)
        log.set_level(log.logging.DEBUG)
    
    try:
        # 获取当前脚本所在目录，并构建配置文件的路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "..", args.config)
        
        # 检查配置文件是否存在
        if not os.path.exists(config_path):
            log.error(f"配置文件不存在: {config_path}")
            sys.exit(1)
        
        log.info(f"加载配置文件: {config_path}")
        
        # 从YAML文件加载配置
        config = Configuration(config_path)
        
        # 应用配置，使其在全局生效
        configuration.config = config
        init_config(config)
        
        log.info("配置初始化完成")
        log.info(f"操作模式: {'删除' if args.delete else '展示'}")
        
        # 创建处理器并执行
        processor = VectorDbLogProcessor(config)
        await processor.process_logs(args.delete)
        processor.display_final_summary()
        
        # 检查是否有错误
        if processor.summary["errors"]:
            log.warning(f"处理过程中出现 {len(processor.summary['errors'])} 个错误")
            sys.exit(1)
        else:
            log.info("处理完成")
            
    except KeyboardInterrupt:
        log.info("用户中断操作")
        sys.exit(0)
    except Exception as e:
        log.error(f"程序执行出错: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 