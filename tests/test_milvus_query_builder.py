#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MilvusQueryBuilder 单元测试

测试 MilvusQueryBuilder 类的各种查询条件构建功能
"""

import unittest
import time
from datetime import datetime
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from deepsearcher.tools.milvus_query_builder import MilvusQueryBuilder, create_query_builder
from deepsearcher.tools import log


class TestMilvusQueryBuilder(unittest.TestCase):
    """MilvusQueryBuilder 测试类"""
    
    def setUp(self):
        """
        测试前的初始化设置
        """
        # 设置日志模式
        log.set_dev_mode(True)
        
        # 创建查询构建器实例
        self.builder = create_query_builder()
    
    def test_empty_objects(self):
        """
        测试空对象列表
        """
        result = self.builder.build_filter_from_objects([])
        self.assertEqual(result, "")
    
    def test_single_author_condition(self):
        """
        测试单个作者条件
        """
        objects = [
            {"type": "作者", "value": "于君"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS(authors, "于君")'
        self.assertEqual(result, expected)
    
    def test_multiple_authors_condition(self):
        """
        测试多个作者条件（OR关系）
        """
        objects = [
            {"type": "作者", "value": "于君"},
            {"type": "作者", "value": "王一"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS_ANY(authors, ["于君", "王一"])'
        self.assertEqual(result, expected)
    
    def test_single_author_id_condition(self):
        """
        测试单个作者ID条件
        """
        objects = [
            {"type": "作者ID", "value": "12345"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS(author_ids, 12345)'
        self.assertEqual(result, expected)
    
    def test_multiple_author_ids_condition(self):
        """
        测试多个作者ID条件（OR关系）
        """
        objects = [
            {"type": "作者ID", "value": "12345"},
            {"type": "作者ID", "value": "67890"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS_ANY(author_ids, [12345, 67890])'
        self.assertEqual(result, expected)
    
    def test_invalid_author_id(self):
        """
        测试无效的作者ID
        """
        objects = [
            {"type": "作者ID", "value": "invalid"},
            {"type": "作者ID", "value": "12345"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS(author_ids, 12345)'
        self.assertEqual(result, expected)
    
    def test_single_journal_condition(self):
        """
        测试单个期刊条件
        """
        objects = [
            {"type": "期刊", "value": "Cell"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'reference LIKE "%Cell%"'
        self.assertEqual(result, expected)
    
    def test_multiple_journals_condition(self):
        """
        测试多个期刊条件（OR关系）
        """
        objects = [
            {"type": "期刊", "value": "Cell"},
            {"type": "期刊", "value": "Nature"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'reference LIKE "%Cell%" OR reference LIKE "%Nature%"'
        self.assertEqual(result, expected)
    
    def test_journal_id_condition(self):
        """
        测试期刊ID条件
        """
        objects = [
            {"type": "期刊ID", "value": "54321"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'reference_id == 54321'
        self.assertEqual(result, expected)
    
    def test_time_condition_recent(self):
        """
        测试最近时间条件
        """
        objects = [
            {"type": "时间范围", "value": "最近"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        
        # 验证结果包含pubdate >= 且后面跟着一个时间戳
        self.assertTrue(result.startswith('pubdate >= '))
        # 验证时间戳是一个数字
        timestamp_str = result.split('pubdate >= ')[1]
        self.assertTrue(timestamp_str.isdigit())
        
        # 验证时间戳大约是一年前（允许一些误差）
        timestamp = int(timestamp_str)
        current_timestamp = int(time.time())
        one_year_ago = current_timestamp - 365 * 24 * 3600
        self.assertAlmostEqual(timestamp, one_year_ago, delta=3600)  # 允许1小时误差
    
    def test_time_condition_timestamp_expression(self):
        """
        测试时间戳表达式
        """
        objects = [
            {"type": "时间范围", "value": ">1724688000"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'pubdate > 1724688000'
        self.assertEqual(result, expected)
    
    def test_time_condition_multiple_operators(self):
        """
        测试多种时间操作符
        """
        test_cases = [
            (">1724688000", "pubdate > 1724688000"),
            (">=1724688000", "pubdate >= 1724688000"),
            ("<1724688000", "pubdate < 1724688000"),
            ("<=1724688000", "pubdate <= 1724688000")
        ]
        
        for input_value, expected_output in test_cases:
            with self.subTest(input_value=input_value):
                objects = [{"type": "时间范围", "value": input_value}]
                result = self.builder.build_filter_from_objects(objects)
                self.assertEqual(result, expected_output)
    
    def test_impact_factor_condition_single(self):
        """
        测试单个影响因子条件
        """
        objects = [
            {"type": "影响因子", "value": "10", "operator": ">"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'impact_factor > 10.0'
        self.assertEqual(result, expected)
    
    def test_impact_factor_condition_multiple(self):
        """
        测试多个影响因子条件（AND关系）
        """
        objects = [
            {"type": "影响因子", "value": "5", "operator": ">="},
            {"type": "影响因子", "value": "15", "operator": "<="}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'impact_factor >= 5.0 AND impact_factor <= 15.0'
        self.assertEqual(result, expected)
    
    def test_impact_factor_default_operator(self):
        """
        测试影响因子默认操作符
        """
        objects = [
            {"type": "影响因子", "value": "8"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'impact_factor >= 8.0'
        self.assertEqual(result, expected)
    
    def test_invalid_impact_factor(self):
        """
        测试无效的影响因子值
        """
        objects = [
            {"type": "影响因子", "value": "invalid"},
            {"type": "影响因子", "value": "5", "operator": ">"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        expected = 'impact_factor > 5.0'
        self.assertEqual(result, expected)
    
    def test_complex_mixed_conditions(self):
        """
        测试复杂的混合条件
        """
        objects = [
            {"type": "作者", "value": "于君"},
            {"type": "作者", "value": "王一"},
            {"type": "期刊", "value": "Cell"},
            {"type": "时间范围", "value": ">1724688000"},
            {"type": "影响因子", "value": "10", "operator": ">"}
        ]
        result = self.builder.build_filter_from_objects(objects)
        
        # 验证结果包含所有预期的条件
        self.assertIn('ARRAY_CONTAINS_ANY(authors, ["于君", "王一"])', result)
        self.assertIn('reference LIKE "%Cell%"', result)
        self.assertIn('pubdate > 1724688000', result)
        self.assertIn('impact_factor > 10.0', result)
        
        # 验证条件之间用AND连接
        parts = result.split(' AND ')
        self.assertEqual(len(parts), 4)
    
    def test_custom_filter_authors_only(self):
        """
        测试自定义过滤器 - 仅作者条件
        """
        result = self.builder.build_custom_filter(authors=["于君", "王一"])
        expected = 'ARRAY_CONTAINS_ANY(authors, ["于君", "王一"])'
        self.assertEqual(result, expected)
    
    def test_custom_filter_single_author(self):
        """
        测试自定义过滤器 - 单个作者
        """
        result = self.builder.build_custom_filter(authors=["于君"])
        expected = 'ARRAY_CONTAINS(authors, "于君")'
        self.assertEqual(result, expected)
    
    def test_custom_filter_author_ids(self):
        """
        测试自定义过滤器 - 作者ID
        """
        result = self.builder.build_custom_filter(author_ids=[12345, 67890])
        expected = 'ARRAY_CONTAINS_ANY(author_ids, [12345, 67890])'
        self.assertEqual(result, expected)
    
    def test_custom_filter_journals(self):
        """
        测试自定义过滤器 - 期刊
        """
        result = self.builder.build_custom_filter(journals=["Cell", "Nature"])
        expected = '(reference LIKE "%Cell%" OR reference LIKE "%Nature%")'
        self.assertEqual(result, expected)
    
    def test_custom_filter_impact_factor_range(self):
        """
        测试自定义过滤器 - 影响因子范围
        """
        result = self.builder.build_custom_filter(min_impact_factor=5.0, max_impact_factor=15.0)
        expected = 'impact_factor >= 5.0 AND impact_factor <= 15.0'
        self.assertEqual(result, expected)
    
    def test_custom_filter_pubdate_range(self):
        """
        测试自定义过滤器 - 发布时间范围
        """
        result = self.builder.build_custom_filter(min_pubdate=1724688000, max_pubdate=1756224000)
        expected = 'pubdate >= 1724688000 AND pubdate <= 1756224000'
        self.assertEqual(result, expected)
    
    def test_custom_filter_complex_mixed(self):
        """
        测试自定义过滤器 - 复杂混合条件
        """
        result = self.builder.build_custom_filter(
            authors=["于君"],
            journals=["Cell", "Nature"],
            min_impact_factor=10.0,
            min_pubdate=1724688000,
            custom_conditions=['rbase_factor >= 5.0']
        )
        
        # 验证所有条件都存在
        self.assertIn('ARRAY_CONTAINS(authors, "于君")', result)
        self.assertIn('(reference LIKE "%Cell%" OR reference LIKE "%Nature%")', result)
        self.assertIn('impact_factor >= 10.0', result)
        self.assertIn('pubdate >= 1724688000', result)
        self.assertIn('rbase_factor >= 5.0', result)
        
        # 验证条件数量
        and_parts = result.split(' AND ')
        self.assertEqual(len(and_parts), 5)
    
    def test_custom_filter_empty_params(self):
        """
        测试自定义过滤器 - 空参数
        """
        result = self.builder.build_custom_filter()
        self.assertEqual(result, "")
    
    def test_custom_filter_ignore_empty_values(self):
        """
        测试自定义过滤器 - 忽略空值
        """
        result = self.builder.build_custom_filter(
            authors=["", "  ", "于君"],  # 包含空字符串和空白字符串
            author_ids=[0, -1, 12345],  # 包含无效ID
            journals=["", "Cell"],
            min_impact_factor=-1.0,  # 负值应被忽略
            min_pubdate=0  # 0值应被忽略
        )
        
        # 只有有效的条件应该被包含
        expected = 'ARRAY_CONTAINS(authors, "于君") AND ARRAY_CONTAINS(author_ids, 12345) AND reference LIKE "%Cell%"'
        self.assertEqual(result, expected)
    
    def test_create_query_builder_function(self):
        """
        测试创建查询构建器的工厂函数
        """
        builder = create_query_builder()
        self.assertIsInstance(builder, MilvusQueryBuilder)
        
        # 测试创建的构建器是否正常工作
        objects = [{"type": "作者", "value": "测试作者"}]
        result = builder.build_filter_from_objects(objects)
        expected = 'ARRAY_CONTAINS(authors, "测试作者")'
        self.assertEqual(result, expected)
    
    def test_edge_cases_whitespace_handling(self):
        """
        测试边界情况 - 空白字符处理
        """
        objects = [
            {"type": "作者", "value": "  于君  "},  # 包含前后空白
            {"type": "作者", "value": ""},  # 空字符串
            {"type": "作者", "value": "   "},  # 纯空白
            {"type": "期刊", "value": " Cell "},  # 期刊名包含空白
        ]
        result = self.builder.build_filter_from_objects(objects)
        
        # 应该正确处理空白字符
        self.assertIn('ARRAY_CONTAINS(authors, "于君")', result)
        self.assertIn('reference LIKE "%Cell%"', result)
        # 不应该包含空字符串条件
        self.assertNotIn('ARRAY_CONTAINS(authors, "")', result)
        self.assertNotIn('ARRAY_CONTAINS(authors, "   ")', result)


if __name__ == "__main__":
    unittest.main()
