"""
向量数据库完整性检查脚本

本脚本用于检查Milvus collection中的数据是否在MySQL的vector_db_data_log表中有对应的记录。
正常的情况下，每条数据的ID应当在vector_db_data_log表中有一个status=1且operation等于1或4的记录，
满足该记录的id_from <= ID <= id_to。

使用方法:
    python scripts/check_vector_db_integrity.py --collection <collection_name> --output <output_file.csv>
    python scripts/check_vector_db_integrity.py -c "dev_rbase_bge_base_en_v1_5_1" -o "integrity_check_result.csv"
    python scripts/check_vector_db_integrity.py -c "my_collection" -o "result.csv" --delete
"""

import argparse
import csv
import os
import sys
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from tqdm import tqdm

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.tools import log
from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection


class VectorDbIntegrityChecker:
    """向量数据库完整性检查器"""
    
    def __init__(self, config: Configuration):
        """
        初始化检查器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.vector_db = configuration.vector_db
        self.db_config = config.rbase_settings.get("database")
        self.summary = {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "deleted_records": 0,
            "errors": []
        }
        
        # 缓存系统：存储已查询的日志记录范围
        # 格式: {collection_name: {id_from: (id_to, log_record_info)}}
        self.log_cache = {}
        
        # 缓存统计信息
        self.cache_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "db_queries": 0
        }
    
    def get_collection_stats(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        获取集合的统计信息
        
        Args:
            collection_name: 集合名称
            
        Returns:
            统计信息字典，包含记录总数等
        """
        try:
            # 检查集合是否存在
            collections = self.vector_db.list_collections()
            collection_exists = any(col.collection_name == collection_name for col in collections)
            
            if not collection_exists:
                log.error(f"集合 '{collection_name}' 不存在")
                return None
            
            # 获取集合统计信息
            stats = self.vector_db.client.get_collection_stats(collection_name)
            return stats
            
        except Exception as e:
            log.error(f"获取集合统计信息时发生错误: {e}")
            return None
    
    def check_collection_integrity_with_iterator(
        self, 
        collection_name: str, 
        batch_size: int = 1000,
        preload_cache: bool = True,
        auto_delete: bool = False
    ) -> List[Dict[str, Any]]:
        """
        使用迭代器方式检查集合的完整性，一边遍历一边检查，控制内存使用
        
        Args:
            collection_name: 集合名称
            batch_size: 每批处理的记录数
            preload_cache: 是否预加载缓存
            auto_delete: 是否自动删除无效记录
            
        Returns:
            有问题的记录列表
        """
        try:
            # 检查集合是否存在
            collections = self.vector_db.list_collections()
            collection_exists = any(col.collection_name == collection_name for col in collections)
            
            if not collection_exists:
                log.error(f"集合 '{collection_name}' 不存在")
                return []
            
            log.info(f"开始使用迭代器方式检查集合 '{collection_name}' 的完整性...")
            
            # 获取集合统计信息
            stats = self.get_collection_stats(collection_name)
            if stats:
                log.info(f"集合统计信息: {stats}")
            
            # 预加载日志记录范围到缓存（可选）
            if preload_cache:
                self._load_log_ranges_to_cache(collection_name)
            else:
                log.info("跳过预加载缓存，将使用动态缓存策略")
            
            # 使用query_iterator进行遍历
            iterator = self.vector_db.client.query_iterator(
                collection_name=collection_name,
                batch_size=batch_size,
                filter="",  # 空filter表示查询所有记录
                output_fields=[
                    "id",
                    "reference_id",
                    "reference",
                ]
            )
            
            invalid_records = []
            total_processed = 0
            
            # 使用tqdm显示检查进度（由于无法预知总数，使用动态进度条）
            with tqdm(desc="检查记录完整性", unit="条") as pbar:
                while True:
                    # 获取下一批数据
                    batch_result = iterator.next()
                    
                    if not batch_result:
                        # 没有更多数据了
                        iterator.close()
                        break
                    
                    batch_count = len(batch_result)
                    total_processed += batch_count
                    
                    # 更新进度条
                    pbar.total = total_processed
                    pbar.update(batch_count)
                    
                    # 处理这一批数据
                    for record in batch_result:
                        record_id = record.get("id")
                        reference_id = record.get("reference_id")
                        
                        if record_id is None:
                            log.warning(f"记录缺少ID字段: {record}")
                            continue
                        
                        # 检查记录是否在日志表中有对应记录
                        log_record = self.check_record_in_log(record_id, collection_name)
                        
                        if log_record:
                            # 记录在日志表中存在，检查是否有效
                            self.summary["valid_records"] += 1
                        else:
                            # 记录在日志表中不存在，标记为无效
                            self.summary["invalid_records"] += 1
                            
                            # 构建无效记录信息
                            invalid_record = {
                                "id": record_id,
                                "reference_id": reference_id,
                                "reference": record.get("reference", ""),
                                "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "error_type": "missing_log_record"
                            }
                            
                            # 如果启用自动删除，则删除无效记录
                            if auto_delete:
                                if self.delete_record_by_id(collection_name, record_id):
                                    self.summary["deleted_records"] += 1
                                    log.info(f"已删除无效记录: ID={record_id}, reference_id={reference_id}")
                                    # 删除成功的不再添加到无效记录列表中
                                    continue
                                else:
                                    log.error(f"删除无效记录失败: ID={record_id}, reference_id={reference_id}")
                            
                            invalid_records.append(invalid_record)
                            
                            # 打印无效记录信息
                            log.warning(f"发现无效记录: ID={record_id}, reference_id={reference_id}")
                        
                        # 更新进度条描述
                        pbar.set_postfix({
                            "有效": self.summary["valid_records"], 
                            "无效": self.summary["invalid_records"],
                            "已删除": self.summary["deleted_records"],
                            "总数": total_processed
                        })
                    
                    # 每处理一批数据后，更新总记录数
                    self.summary["total_records"] = total_processed
                    
                    # 定期输出进度信息
                    if total_processed % (batch_size * 10) == 0:
                        log.debug(f"已处理 {total_processed} 条记录，有效: {self.summary['valid_records']}, 无效: {self.summary['invalid_records']}, 已删除: {self.summary['deleted_records']}")
            
            log.info(f"迭代器遍历完成，总共处理了 {total_processed} 条记录")
            return invalid_records
            
        except Exception as e:
            log.error(f"使用迭代器遍历集合数据时发生错误: {e}")
            return []
    
    def check_record_in_log(self, record_id: int, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        检查记录是否在vector_db_data_log表中有对应的记录
        优先使用缓存，缓存未命中时才查询数据库
        
        Args:
            record_id: 记录ID
            collection_name: 集合名称
            
        Returns:
            如果找到匹配的日志记录则返回日志信息，否则返回None
        """
        # 首先检查缓存
        cached_result = self._check_cache_for_record(record_id, collection_name)
        if cached_result is not None:
            return cached_result
        
        # 缓存未命中，查询数据库
        self.cache_stats["db_queries"] += 1
        try:
            # 获取MySQL连接
            conn = get_mysql_connection(self.db_config)
            
            with conn.cursor() as cursor:
                # 查询vector_db_data_log表中是否有对应的记录
                # 条件：status=1 AND (operation=1 OR operation=4) AND id_from <= record_id <= id_to
                sql = """
                SELECT id, id_from, id_to 
                FROM vector_db_data_log 
                WHERE status = 1 
                AND (operation = 1 OR operation = 4)
                AND collection = %s
                AND id_from <= %s AND id_to >= %s
                ORDER BY id DESC
                LIMIT 1
                """
                cursor.execute(sql, (collection_name, record_id, record_id))
                result = cursor.fetchone()
                
                # 如果找到结果，添加到缓存中
                if result:
                    self._add_to_cache(result, collection_name)
                
                return result
                
        except Exception as e:
            error_msg = f"检查记录 {record_id} 在日志表中的状态时发生错误: {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
            return None
        finally:
            close_mysql_connection()
    
    def delete_record_by_id(self, collection_name: str, record_id: int) -> bool:
        """
        根据ID删除向量数据库中的记录
        
        Args:
            collection_name: 集合名称
            record_id: 记录ID
            
        Returns:
            删除是否成功
        """
        try:
            # 执行删除操作
            result = self.vector_db.client.delete(
                collection_name=collection_name,
                ids=record_id
            )

            # 检查删除结果
            if result.get("delete_count", 0) > 0:
                return True
            else:
                log.warning(f"删除记录 {record_id} 时遇到错误: {result}")
                return False
                
        except Exception as e:
            error_msg = f"删除记录 {record_id} 时发生错误: {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
            return False
    
    def _check_cache_for_record(self, record_id: int, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        在缓存中查找记录ID是否在某个日志记录范围内
        
        Args:
            record_id: 记录ID
            collection_name: 集合名称
            
        Returns:
            如果找到匹配的日志记录则返回日志信息，否则返回None
        """
        if collection_name not in self.log_cache:
            return None
        
        collection_cache = self.log_cache[collection_name]
        
        # 遍历缓存中的范围，查找包含该record_id的范围
        for id_from, (id_to, log_record) in collection_cache.items():
            if id_from <= record_id <= id_to:
                self.cache_stats["cache_hits"] += 1
                return log_record
        
        self.cache_stats["cache_misses"] += 1
        return None
    
    def _add_to_cache(self, log_record: Dict[str, Any], collection_name: str) -> None:
        """
        将日志记录添加到缓存中
        
        Args:
            log_record: 日志记录
            collection_name: 集合名称
        """
        if collection_name not in self.log_cache:
            self.log_cache[collection_name] = {}
        
        id_from = log_record["id_from"]
        id_to = log_record["id_to"]
        
        # 存储到缓存中，使用id_from作为key，存储(id_to, log_record)作为value
        self.log_cache[collection_name][id_from] = (id_to, log_record)
    
    def _load_log_ranges_to_cache(self, collection_name: str) -> None:
        """
        预加载所有日志记录范围到缓存中
        
        Args:
            collection_name: 集合名称
        """
        try:
            log.info(f"预加载集合 '{collection_name}' 的日志记录范围到缓存...")
            
            # 获取MySQL连接
            conn = get_mysql_connection(self.db_config)
            
            with conn.cursor() as cursor:
                # 查询所有有效的日志记录范围
                sql = """
                SELECT id, id_from, id_to 
                FROM vector_db_data_log 
                WHERE status = 1 
                AND (operation = 1 OR operation = 4)
                AND collection = %s
                ORDER BY id_from ASC
                """
                cursor.execute(sql, (collection_name,))
                results = cursor.fetchall()
                
                if results:
                    for result in results:
                        self._add_to_cache(result, collection_name)
                    
                    log.info(f"成功加载 {len(results)} 个日志记录范围到缓存")
                else:
                    log.warning(f"集合 '{collection_name}' 没有找到有效的日志记录")
                
        except Exception as e:
            error_msg = f"预加载日志记录范围到缓存时发生错误: {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
        finally:
            close_mysql_connection()
    
    def save_invalid_records_to_csv(self, invalid_records: List[Dict[str, Any]], output_file: str) -> None:
        """
        将有问题的记录保存到CSV文件
        
        Args:
            invalid_records: 无效记录列表
            output_file: 输出文件路径
        """
        if not invalid_records:
            log.info("没有无效记录需要保存")
            return
        
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 定义CSV字段
            fieldnames = [
                "id",
                "reference_id", 
                "reference",
                "check_time",
                "error_type"
            ]
            
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for record in invalid_records:
                    # 处理列表字段，转换为字符串
                    csv_record = record.copy()
                    writer.writerow(csv_record)
            
            log.info(f"已将 {len(invalid_records)} 条无效记录保存到文件: {output_file}")
            
        except Exception as e:
            error_msg = f"保存CSV文件时发生错误: {e}"
            log.error(error_msg)
            self.summary["errors"].append(error_msg)
    
    def display_summary(self) -> None:
        """显示检查结果汇总"""
        log.color_print("=" * 80)
        log.color_print("📊 向量数据库完整性检查结果汇总")
        log.color_print("=" * 80)
        
        log.color_print(f"总记录数: {self.summary['total_records']}")
        log.color_print(f"有效记录数: {self.summary['valid_records']}")
        log.color_print(f"无效记录数: {self.summary['invalid_records']}")
        log.color_print(f"已删除记录数: {self.summary['deleted_records']}")
        
        if self.summary["total_records"] > 0:
            valid_rate = (self.summary["valid_records"] / self.summary["total_records"]) * 100
            log.color_print(f"数据完整性: {valid_rate:.2f}%")
        
        # 显示缓存统计信息
        log.color_print(f"\n📊 缓存性能统计:")
        log.color_print(f"缓存命中次数: {self.cache_stats['cache_hits']}")
        log.color_print(f"缓存未命中次数: {self.cache_stats['cache_misses']}")
        log.color_print(f"数据库查询次数: {self.cache_stats['db_queries']}")
        
        total_cache_operations = self.cache_stats['cache_hits'] + self.cache_stats['cache_misses']
        if total_cache_operations > 0:
            cache_hit_rate = (self.cache_stats['cache_hits'] / total_cache_operations) * 100
            log.color_print(f"缓存命中率: {cache_hit_rate:.2f}%")
        
        # 显示缓存大小信息
        total_cached_ranges = sum(len(cache) for cache in self.log_cache.values())
        log.color_print(f"缓存中的记录范围数: {total_cached_ranges}")
        
        if self.summary["errors"]:
            log.color_print(f"\n❌ 错误信息 ({len(self.summary['errors'])} 个):")
            for i, error in enumerate(self.summary["errors"], 1):
                log.color_print(f"  {i}. {error}")
        
        log.color_print("=" * 80)


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(
        description="检查Milvus集合中的数据完整性",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/check_vector_db_integrity.py --collection "dev_rbase_bge_base_en_v1_5_1" --output "integrity_check_result.csv"
  python scripts/check_vector_db_integrity.py -c "test_collection" -o "test_result.csv" --batch-size 500
  python scripts/check_vector_db_integrity.py -c "my_collection" -o "result.csv" -v
  python scripts/check_vector_db_integrity.py -c "large_collection" -o "result.csv" --no-preload-cache
  python scripts/check_vector_db_integrity.py -c "my_collection" -o "result.csv" --delete
        """
    )
    
    parser.add_argument(
        "-c", "--collection",
        required=True,
        help="向量数据库集合名称"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="outputs/integrity_check_result.csv",
        help="输出CSV文件路径"
    )
    
    parser.add_argument(
        "-b", "--batch-size",
        type=int,
        default=1000,
        help="每批查询的记录数 (默认: 1000)"
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
    
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="仅显示集合统计信息，不进行完整性检查"
    )
    
    parser.add_argument(
        "--no-preload-cache",
        action="store_true",
        help="不预加载缓存，使用动态缓存策略（适用于内存受限的环境）"
    )
    
    parser.add_argument(
        "--delete",
        action="store_true",
        help="自动删除发现的无效记录（谨慎使用，此操作不可逆）"
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
        log.info(f"目标集合: {args.collection}")
        log.info(f"输出文件: {args.output}")
        log.info(f"批次大小: {args.batch_size}")
        if args.delete:
            log.warning("⚠️  已启用自动删除模式，发现的无效记录将被自动删除！")
        
        # 创建完整性检查器
        checker = VectorDbIntegrityChecker(config)
        
        # 显示集合统计信息
        stats = checker.get_collection_stats(args.collection)
        if stats:
            log.info(f"集合统计信息: {stats}")
        
        if args.stats_only:
            log.info("仅显示统计信息，退出")
            return
        
        # 执行完整性检查（使用迭代器方式）
        preload_cache = not args.no_preload_cache
        invalid_records = checker.check_collection_integrity_with_iterator(
            args.collection, 
            args.batch_size,
            preload_cache,
            args.delete
        )
        
        # 保存无效记录到CSV文件
        checker.save_invalid_records_to_csv(invalid_records, args.output)
        
        # 显示检查结果汇总
        checker.display_summary()
        
        # 如果有无效记录，返回非零退出码
        if invalid_records:
            log.warning(f"发现 {len(invalid_records)} 条无效记录，请检查CSV文件")
            sys.exit(1)
        else:
            log.info("所有记录都通过了完整性检查！")
            
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
    main() 