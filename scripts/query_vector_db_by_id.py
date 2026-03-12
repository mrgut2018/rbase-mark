#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
向量数据库按ID查询脚本

本脚本用于初始化config.rbase.yaml配置后，通过vector_db对象读取指定collection中指定ID的数据，
并展示其每一个字段的详细信息。

使用方法:
    python scripts/query_vector_db_by_id.py --collection <collection_name> --id <record_id>
    python scripts/query_vector_db_by_id.py --collection "dev_rbase_bge_base_en_v1_5_1" --id 12345
"""

import argparse
import json
import os
import sys
from typing import Dict, Any, Optional

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.tools import log


def format_field_value(field_name: str, value: Any) -> str:
    """
    格式化字段值的显示
    
    Args:
        field_name: 字段名称
        value: 字段值
        
    Returns:
        格式化后的字符串
    """
    if value is None:
        return f"{field_name}: None"
    
    if field_name == "embedding":
        # 向量字段只显示前5个和后5个值
        if isinstance(value, list) and len(value) > 10:
            return f"{field_name}: [{', '.join(map(str, value[:5]))} ... {', '.join(map(str, value[-5:]))}] (维度: {len(value)})"
        else:
            return f"{field_name}: {value} (维度: {len(value) if isinstance(value, list) else 'N/A'})"
    
    elif field_name == "text":
        # 文本字段限制显示长度
        if isinstance(value, str) and len(value) > 200:
            return f"{field_name}: {value[:200]}... (总长度: {len(value)}字符)"
        else:
            return f"{field_name}: {value}"
    
    elif isinstance(value, list):
        # 数组字段限制显示元素数量
        if len(value) > 10:
            return f"{field_name}: {value[:10]} ... (共{len(value)}个元素)"
        else:
            return f"{field_name}: {value}"
    
    elif isinstance(value, dict):
        # 字典字段格式化为JSON
        return f"{field_name}: {json.dumps(value, ensure_ascii=False, indent=2)}"
    
    else:
        return f"{field_name}: {value}"


def query_vector_db_by_id(collection_name: str, record_id: int, reference_id: int = None) -> Optional[Dict[str, Any]]:
    """
    通过ID或reference_id查询向量数据库中的记录
    
    Args:
        collection_name: 集合名称
        record_id: 记录ID
        reference_id: 引用ID，当record_id为0时使用此字段查询
        
    Returns:
        查询结果字典，如果未找到则返回None
    """
    try:
        # 获取vector_db实例
        vector_db = configuration.vector_db
        
        # 检查集合是否存在
        collections = vector_db.list_collections()
        collection_exists = any(col.collection_name == collection_name for col in collections)
        
        if not collection_exists:
            log.error(f"集合 '{collection_name}' 不存在")
            log.info("可用的集合:")
            for col in collections:
                log.info(f"  - {col.collection_name}: {col.description}")
            return None
        
        # 确定查询条件
        if record_id == 0 and reference_id is not None:
            # 当id为0时，使用reference_id查询
            filter_condition = f"reference_id == {reference_id}"
            log.info(f"使用reference_id查询: {reference_id}")
        else:
            # 使用id查询
            filter_condition = f"id == {record_id}"
            log.info(f"使用id查询: {record_id}")
        
        # 使用MilvusClient的query方法查询
        # 根据Milvus的schema，我们需要查询所有字段
        query_result = vector_db.client.query(
            collection_name=collection_name,
            filter=filter_condition,
            output_fields=[
                "id",
                "embedding", 
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
        
        if not query_result:
            if record_id == 0 and reference_id is not None:
                log.error(f"在集合 '{collection_name}' 中未找到reference_id为 {reference_id} 的记录")
            else:
                log.error(f"在集合 '{collection_name}' 中未找到ID为 {record_id} 的记录")
            return None
        
        # 返回第一条记录（ID查询应该只有一条）
        return query_result[0]
        
    except Exception as e:
        log.error(f"查询向量数据库时发生错误: {e}")
        return None


def display_record_info(record: Dict[str, Any], collection_name: str, record_id: int):
    """
    显示记录的详细信息
    
    Args:
        record: 记录数据
        collection_name: 集合名称
        record_id: 记录ID
    """
    log.color_print("=" * 80)
    log.color_print(f"向量数据库记录详情")
    log.color_print("=" * 80)
    log.color_print(f"集合名称: {collection_name}")
    log.color_print(f"记录ID: {record_id}")
    log.color_print("-" * 80)
    
    # 定义字段显示顺序
    field_order = [
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
        "metadata",
        "embedding"
    ]
    
    # 按顺序显示字段
    for field_name in field_order:
        if field_name in record:
            formatted_value = format_field_value(field_name, record[field_name])
            log.color_print(formatted_value)
            log.color_print("-" * 40)
    
    # 显示其他可能存在的字段
    other_fields = [field for field in record.keys() if field not in field_order]
    if other_fields:
        log.color_print("其他字段:")
        for field_name in other_fields:
            formatted_value = format_field_value(field_name, record[field_name])
            log.color_print(formatted_value)
            log.color_print("-" * 40)


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(
        description="查询向量数据库中指定ID的记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/query_vector_db_by_id.py --collection "dev_rbase_bge_base_en_v1_5_1" --id 12345
  python scripts/query_vector_db_by_id.py -c "test_collection" -i 100
        """
    )
    
    parser.add_argument(
        "-c", "--collection",
        required=True,
        help="向量数据库集合名称"
    )
    
    parser.add_argument(
        "-i", "--id", 
        type=int,
        required=True,
        help="要查询的记录ID (当为0时，将使用reference_id查询)"
    )
    
    parser.add_argument(
        "-r", "--reference_id",
        type=int,
        help="引用ID，当id为0时使用此字段查询"
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
        log.info(f"查询集合: {args.collection}")
        log.info(f"查询ID: {args.id}")
        if args.reference_id is not None:
            log.info(f"引用ID: {args.reference_id}")
        
        # 查询记录
        record = query_vector_db_by_id(args.collection, args.id, args.reference_id)
        
        if record:
            display_record_info(record, args.collection, args.id)
        else:
            log.error("未找到指定记录")
            sys.exit(1)
            
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