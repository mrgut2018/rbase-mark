#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_prerequisite方法的单元测试
"""

import sys
import os
import unittest

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_classifiers import ClassifierImporter


class TestParsePrerequisite(unittest.TestCase):
    """测试前置条件解析方法"""
    
    def setUp(self):
        """测试前准备"""
        # 创建一个临时的ClassifierImporter实例，只用于测试parse_prerequisite方法
        # 不需要真正的数据库连接
        self.importer = None
        try:
            # 模拟一个简单的配置，不进行数据库连接
            class MockConfig:
                def __init__(self):
                    self.rbase_settings = {"database": {}}
            
            # 重写_init_db_connection方法，避免真正连接数据库
            original_init = ClassifierImporter._init_db_connection
            ClassifierImporter._init_db_connection = lambda self: None
            
            self.importer = ClassifierImporter(MockConfig(), False)
            
            # 恢复原方法
            ClassifierImporter._init_db_connection = original_init
        except Exception as e:
            print(f"初始化测试环境失败: {e}")
    
    def test_empty_prerequisite(self):
        """测试空前置条件"""
        result = self.importer.parse_prerequisite("")
        self.assertIsNone(result)
        
        result = self.importer.parse_prerequisite("   ")
        self.assertIsNone(result)
        
        result = self.importer.parse_prerequisite(None)
        self.assertIsNone(result)
    
    def test_simple_prerequisite(self):
        """测试简单的前置条件"""
        # 测试单个值
        result = self.importer.parse_prerequisite("original_research in [原创性研究]")
        expected = [{'classifier_alias': 'original_research', 'value_in': ['原创性研究']}]
        self.assertEqual(result, expected)
    
    def test_complex_prerequisite(self):
        """测试复杂的前置条件"""
        # 测试多个值（这是问题所在的测试用例）
        prerequisite_str = "article_type in [Article, Short Article, Symantic Review, Review, Perspective, Minireview]"
        result = self.importer.parse_prerequisite(prerequisite_str)
        
        expected = [{
            'classifier_alias': 'article_type', 
            'value_in': ['Article', 'Short Article', 'Symantic Review', 'Review', 'Perspective', 'Minireview']
        }]
        
        print(f"输入: {prerequisite_str}")
        print(f"实际结果: {result}")
        print(f"期望结果: {expected}")
        
        self.assertEqual(result, expected)
    
    def test_multiple_conditions(self):
        """测试多个条件（用逗号分隔）"""
        prerequisite_str = "article_type in [Article, Review], original_research in [原创性研究]"
        result = self.importer.parse_prerequisite(prerequisite_str)
        
        expected = [
            {'classifier_alias': 'article_type', 'value_in': ['Article', 'Review']},
            {'classifier_alias': 'original_research', 'value_in': ['原创性研究']}
        ]
        
        print(f"输入: {prerequisite_str}")
        print(f"实际结果: {result}")
        print(f"期望结果: {expected}")
        
        self.assertEqual(result, expected)
    
    def test_quoted_values(self):
        """测试带引号的值"""
        prerequisite_str = 'article_type in ["Article", "Short Article"]'
        result = self.importer.parse_prerequisite(prerequisite_str)
        
        expected = [{'classifier_alias': 'article_type', 'value_in': ['Article', 'Short Article']}]
        
        print(f"输入: {prerequisite_str}")
        print(f"实际结果: {result}")
        print(f"期望结果: {expected}")
        
        self.assertEqual(result, expected)
    
    def test_mixed_values(self):
        """测试混合格式的值（有引号和无引号）"""
        prerequisite_str = 'article_type in [Article, "Short Article", Review]'
        result = self.importer.parse_prerequisite(prerequisite_str)
        
        expected = [{'classifier_alias': 'article_type', 'value_in': ['Article', 'Short Article', 'Review']}]
        
        print(f"输入: {prerequisite_str}")
        print(f"实际结果: {result}")
        print(f"期望结果: {expected}")
        
        self.assertEqual(result, expected)
    
    def test_invalid_format(self):
        """测试无效格式"""
        result = self.importer.parse_prerequisite("invalid format")
        self.assertIsNone(result)
        
        result = self.importer.parse_prerequisite("article_type = [Article]")
        self.assertIsNone(result)
    
    def test_real_csv_examples(self):
        """测试CSV中的真实例子"""
        test_cases = [
            "article_type in [Article, Short Article, Symantic Review, Review, Perspective, Minireview]",
            "original_research in [原创性研究]",
            "research_method in [观察性研究]",
            "expirimental_method in [体内研究]",  # 注意这里有拼写错误
        ]
        
        for prerequisite_str in test_cases:
            print(f"\n测试用例: {prerequisite_str}")
            result = self.importer.parse_prerequisite(prerequisite_str)
            print(f"解析结果: {result}")
            self.assertIsNotNone(result)
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
