#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MilvusQueryBuilder 演示程序

展示如何使用 MilvusQueryBuilder 根据 query_objects_analysis 的结果构建 Milvus 查询条件
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from deepsearcher.tools.milvus_query_builder import create_query_builder
from deepsearcher.tools import log


def demo_basic_usage():
    """
    演示基本使用方法
    """
    print("=" * 60)
    print("MilvusQueryBuilder 基本使用演示")
    print("=" * 60)
    
    # 创建查询构建器
    builder = create_query_builder()
    
    # 模拟 query_objects_analysis 的结果
    objects = [
        {"type": "作者", "value": "于君"},
        {"type": "作者", "value": "王一"},
        {"type": "期刊", "value": "Cell"},
        {"type": "时间范围", "value": "最近"},
        {"type": "影响因子", "value": "10", "operator": ">"}
    ]
    
    print("输入对象:")
    for obj in objects:
        print(f"  - {obj}")
    
    # 构建过滤条件
    filter_condition = builder.build_filter_from_objects(objects)
    
    print(f"\n生成的Milvus过滤条件:")
    print(f"  {filter_condition}")
    print()


def demo_individual_conditions():
    """
    演示各种单独条件的构建
    """
    print("=" * 60)
    print("各种条件类型演示")
    print("=" * 60)
    
    builder = create_query_builder()
    
    # 作者条件
    print("1. 作者条件:")
    objects = [{"type": "作者", "value": "于君"}, {"type": "作者", "value": "王一"}]
    result = builder.build_filter_from_objects(objects)
    print(f"   输入: {objects}")
    print(f"   输出: {result}")
    print()
    
    # 作者ID条件
    print("2. 作者ID条件:")
    objects = [{"type": "作者ID", "value": "12345"}, {"type": "作者ID", "value": "67890"}]
    result = builder.build_filter_from_objects(objects)
    print(f"   输入: {objects}")
    print(f"   输出: {result}")
    print()
    
    # 期刊条件
    print("3. 期刊条件:")
    objects = [{"type": "期刊", "value": "Nature"}, {"type": "期刊", "value": "Science"}]
    result = builder.build_filter_from_objects(objects)
    print(f"   输入: {objects}")
    print(f"   输出: {result}")
    print()
    
    # 时间范围条件
    print("4. 时间范围条件:")
    time_examples = [
        [{"type": "时间范围", "value": "最近"}],
        [{"type": "时间范围", "value": ">1724688000"}],
        [{"type": "时间范围", "value": ">=1724688000"}],
    ]
    
    for objects in time_examples:
        result = builder.build_filter_from_objects(objects)
        print(f"   输入: {objects}")
        print(f"   输出: {result}")
    print()
    
    # 影响因子条件
    print("5. 影响因子条件:")
    impact_examples = [
        [{"type": "影响因子", "value": "10", "operator": ">"}],
        [{"type": "影响因子", "value": "5", "operator": ">="}, {"type": "影响因子", "value": "15", "operator": "<="}],
    ]
    
    for objects in impact_examples:
        result = builder.build_filter_from_objects(objects)
        print(f"   输入: {objects}")
        print(f"   输出: {result}")
    print()


def demo_custom_filter():
    """
    演示自定义过滤器API
    """
    print("=" * 60)
    print("自定义过滤器API演示")
    print("=" * 60)
    
    builder = create_query_builder()
    
    # 示例1: 只指定作者
    print("1. 只指定作者:")
    result = builder.build_custom_filter(authors=["于君", "王一"])
    print(f"   authors=['于君', '王一']")
    print(f"   输出: {result}")
    print()
    
    # 示例2: 指定影响因子范围
    print("2. 指定影响因子范围:")
    result = builder.build_custom_filter(min_impact_factor=5.0, max_impact_factor=15.0)
    print(f"   min_impact_factor=5.0, max_impact_factor=15.0")
    print(f"   输出: {result}")
    print()
    
    # 示例3: 复杂条件组合
    print("3. 复杂条件组合:")
    result = builder.build_custom_filter(
        authors=["于君"],
        journals=["Cell", "Nature"],
        min_impact_factor=10.0,
        min_pubdate=1724688000,
        custom_conditions=['rbase_factor >= 5.0']
    )
    print(f"   authors=['于君']")
    print(f"   journals=['Cell', 'Nature']")
    print(f"   min_impact_factor=10.0")
    print(f"   min_pubdate=1724688000")
    print(f"   custom_conditions=['rbase_factor >= 5.0']")
    print(f"   输出: {result}")
    print()


def demo_real_world_examples():
    """
    演示真实世界的查询示例
    """
    print("=" * 60)
    print("真实查询场景演示")
    print("=" * 60)
    
    builder = create_query_builder()
    
    # 场景1: 查找特定作者的近期高影响因子论文
    print("场景1: 查找于君教授近期影响因子大于10的论文")
    objects = [
        {"type": "作者", "value": "于君"},
        {"type": "时间范围", "value": "最近"},
        {"type": "影响因子", "value": "10", "operator": ">"}
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   查询条件: {result}")
    print()
    
    # 场景2: 查找多个作者在顶级期刊的论文
    print("场景2: 查找于君或王一在Cell或Nature期刊的论文")
    objects = [
        {"type": "作者", "value": "于君"},
        {"type": "作者", "value": "王一"},
        {"type": "期刊", "value": "Cell"},
        {"type": "期刊", "value": "Nature"}
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   查询条件: {result}")
    print()
    
    # 场景3: 按时间戳范围和影响因子范围查询
    print("场景3: 查找2024年后影响因子在5-15之间的论文")
    objects = [
        {"type": "时间范围", "value": ">1704067200"},  # 2024年1月1日
        {"type": "影响因子", "value": "5", "operator": ">="},
        {"type": "影响因子", "value": "15", "operator": "<="}
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   查询条件: {result}")
    print()
    
    # 场景4: 复杂的多条件查询
    print("场景4: 复杂多条件查询 - 指定作者ID、期刊、时间和影响因子")
    objects = [
        {"type": "作者ID", "value": "12345"},
        {"type": "作者ID", "value": "67890"},
        {"type": "期刊", "value": "Science"},
        {"type": "时间范围", "value": ">=1672531200"},  # 2023年1月1日
        {"type": "影响因子", "value": "8", "operator": ">"}
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   查询条件: {result}")
    print()


def demo_error_handling():
    """
    演示错误处理和边界情况
    """
    print("=" * 60)
    print("错误处理和边界情况演示")
    print("=" * 60)
    
    builder = create_query_builder()
    
    # 空对象列表
    print("1. 空对象列表:")
    result = builder.build_filter_from_objects([])
    print(f"   输入: []")
    print(f"   输出: '{result}'")
    print()
    
    # 包含无效值的对象
    print("2. 包含无效值的对象:")
    objects = [
        {"type": "作者", "value": ""},  # 空作者名
        {"type": "作者", "value": "   "},  # 空白作者名
        {"type": "作者", "value": "有效作者"},
        {"type": "作者ID", "value": "invalid"},  # 无效ID
        {"type": "作者ID", "value": "12345"},  # 有效ID
        {"type": "影响因子", "value": "invalid"},  # 无效影响因子
        {"type": "影响因子", "value": "10", "operator": ">"}  # 有效影响因子
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   输入包含多个无效值")
    print(f"   输出: {result}")
    print("   注意: 只有有效的条件被包含在结果中")
    print()
    
    # 未知对象类型
    print("3. 未知对象类型:")
    objects = [
        {"type": "未知类型", "value": "某个值"},
        {"type": "作者", "value": "于君"}
    ]
    result = builder.build_filter_from_objects(objects)
    print(f"   输入包含未知类型")
    print(f"   输出: {result}")
    print("   注意: 未知类型被忽略，只处理已知类型")
    print()


def main():
    """
    主函数
    """
    # 设置日志
    log.set_dev_mode(True)
    
    print("MilvusQueryBuilder 演示程序")
    print("根据 query_objects_analysis 结果构建 Milvus 查询条件")
    print()
    
    # 运行各种演示
    demo_basic_usage()
    demo_individual_conditions()
    demo_custom_filter()
    demo_real_world_examples()
    demo_error_handling()
    
    print("=" * 60)
    print("演示完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
