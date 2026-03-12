#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
DiscussAgent 单元测试

测试 DiscussAgent 类的 intention_analysis 和 query_objects_analysis 方法
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import json
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.agent.discuss_agent import DiscussAgent, DiscussIntention
from deepsearcher.tools import log


class TestDiscussAgent(unittest.TestCase):
    """DiscussAgent 测试类"""
    
    def setUp(self):
        """
        测试前的初始化设置
        创建 mock 对象来模拟各种依赖组件
        """
        # 设置日志模式
        log.set_dev_mode(True)
        
        # 初始化配置
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.rbase.yaml")
        configuration.config = Configuration(config_path)
        init_config(configuration.config)
        
        # 创建 mock 对象
        self.mock_llm = Mock()
        self.mock_reasoning_llm = Mock()
        self.mock_translator = Mock()
        self.mock_embedding_model = Mock()
        self.mock_vector_db = Mock()
        
        # 创建 DiscussAgent 实例
        self.discuss_agent = DiscussAgent(
            llm=self.mock_llm,
            reasoning_llm=self.mock_reasoning_llm,
            translator=self.mock_translator,
            embedding_model=self.mock_embedding_model,
            vector_db=self.mock_vector_db,
            verbose=True
        )
    
    def test_intention_analysis_academic_question(self):
        """
        测试意图分析 - 学术提问场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "intention": "学术提问",
            "is_academic": True
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 100}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        user_action = "浏览学术论文"
        background = "用户正在研究人工智能领域"
        history = [
            {
                "content": "我想了解人工智能在医疗领域的应用",
                "role": "user",
            },
            {
                "content": "人工智能在医疗领域有多种应用...",
                "role": "assistant"
            }
        ]
        query = "于君教授在近期都有哪些学术成果?"
        
        # 执行测试
        result = self.discuss_agent.intention_analysis(user_action, background, history, query)
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertEqual(result["intention"], "学术提问")
        self.assertTrue(result["is_academic"])
        
        # 验证 LLM 调用
        self.mock_reasoning_llm.chat.assert_called_once()
        call_args = self.mock_reasoning_llm.chat.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0]["role"], "user")
        self.assertIn("于君教授在近期都有哪些学术成果?", call_args[0]["content"])
        
        # 测试 DiscussIntention 类
        intention = DiscussIntention(result)
        self.assertEqual(intention.intention, "学术提问")
        self.assertTrue(intention.is_academic)
        self.assertTrue(intention.should_response())
    
    def test_intention_analysis_non_academic_expression(self):
        """
        测试意图分析 - 非学术语气表达场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "intention": "语气表达",
            "is_academic": False
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 80}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        user_action = "浏览学术论文"
        background = ""
        history = []
        query = "哇，太厉害了！"
        
        # 执行测试
        result = self.discuss_agent.intention_analysis(user_action, background, history, query)
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertEqual(result["intention"], "语气表达")
        self.assertFalse(result["is_academic"])
        
        # 测试 DiscussIntention 类
        intention = DiscussIntention(result)
        self.assertEqual(intention.intention, "语气表达")
        self.assertFalse(intention.is_academic)
        self.assertFalse(intention.should_response())  # 非学术的语气表达不应该响应
    
    def test_intention_analysis_opinion_expression(self):
        """
        测试意图分析 - 发表观点场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "intention": "发表观点",
            "is_academic": True
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 120}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        user_action = "浏览学术论文"
        background = "学术讨论"
        history = []
        query = "我认为深度学习在医疗诊断中的应用还有很大提升空间"
        
        # 执行测试
        result = self.discuss_agent.intention_analysis(user_action, background, history, query)
        
        # 验证结果
        self.assertIsInstance(result, dict)
        self.assertEqual(result["intention"], "发表观点")
        self.assertTrue(result["is_academic"])
        
        # 测试 DiscussIntention 类
        intention = DiscussIntention(result)
        self.assertTrue(intention.should_response())  # 学术观点应该响应
    
    def test_intention_analysis_json_parse_error(self):
        """
        测试意图分析 - JSON解析错误场景
        """
        # 模拟 LLM 返回无效的 JSON
        mock_response = Mock()
        mock_response.content = "这不是一个有效的JSON格式"
        mock_response.usage.return_value = {"total_tokens": 50}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        user_action = "浏览学术论文"
        background = ""
        history = []
        query = "测试查询"
        
        # 验证抛出异常
        with self.assertRaises(ValueError):
            self.discuss_agent.intention_analysis(user_action, background, history, query)
    
    def test_query_objects_analysis_with_author_and_journal(self):
        """
        测试查询对象分析 - 包含作者和期刊信息
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "objects": [
                {"type": "作者", "value": "于君"},
                {"type": "时间范围", "value": "最近"}
            ]
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 90}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "于君教授在近期都有哪些学术成果?"
        
        # 执行测试
        result = self.discuss_agent.query_objects_analysis(query)
        
        # 验证结果
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        
        # 验证第一个对象（作者）
        author_obj = result[0]
        self.assertEqual(author_obj["type"], "作者")
        self.assertEqual(author_obj["value"], "于君")
        
        # 验证第二个对象（时间范围）
        time_obj = result[1]
        self.assertEqual(time_obj["type"], "时间范围")
        self.assertEqual(time_obj["value"], "最近")
        
        # 验证 LLM 调用
        self.mock_reasoning_llm.chat.assert_called_once()
        call_args = self.mock_reasoning_llm.chat.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0]["role"], "user")
        self.assertIn("于君教授在近期都有哪些学术成果?", call_args[0]["content"])
    
    def test_query_objects_analysis_with_impact_factor(self):
        """
        测试查询对象分析 - 包含影响因子信息
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "objects": [
                {"type": "影响因子", "value": "10", "operator": ">"},
                {"type": "时间范围", "value": "最近"}
            ]
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 85}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "请分析该领域影响因子大于10的最近的研究成果"
        
        # 执行测试
        result = self.discuss_agent.query_objects_analysis(query)
        
        # 验证结果
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        
        # 验证影响因子对象
        impact_factor_obj = result[0]
        self.assertEqual(impact_factor_obj["type"], "影响因子")
        self.assertEqual(impact_factor_obj["value"], "10")
        self.assertEqual(impact_factor_obj["operator"], ">")
    
    def test_query_objects_analysis_empty_result(self):
        """
        测试查询对象分析 - 空结果场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "objects": []
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 60}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "什么是人工智能？"
        
        # 执行测试
        result = self.discuss_agent.query_objects_analysis(query)
        
        # 验证结果
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)
    
    def test_query_objects_analysis_missing_objects_key(self):
        """
        测试查询对象分析 - 缺少objects键的场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "other_key": "some_value"
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 40}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "测试查询"
        
        # 执行测试
        result = self.discuss_agent.query_objects_analysis(query)
        
        # 验证结果 - 应该返回空列表
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)
    
    def test_query_objects_analysis_json_parse_error(self):
        """
        测试查询对象分析 - JSON解析错误场景
        """
        # 模拟 LLM 返回无效的 JSON
        mock_response = Mock()
        mock_response.content = "这不是一个有效的JSON格式"
        mock_response.usage.return_value = {"total_tokens": 30}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "测试查询"
        
        # 验证抛出异常
        with self.assertRaises(ValueError):
            self.discuss_agent.query_objects_analysis(query)
    
    def test_query_objects_analysis_complex_query(self):
        """
        测试查询对象分析 - 复杂查询场景
        """
        # 模拟 LLM 响应
        mock_response = Mock()
        mock_response.content = json.dumps({
            "objects": [
                {"type": "作者", "value": "王一"},
                {"type": "期刊", "value": "Cell"},
                {"type": "影响因子", "value": "5", "operator": ">="},
                {"type": "时间范围", "value": ">1724688000"}
            ]
        }, ensure_ascii=False)
        mock_response.usage.return_value = {"total_tokens": 150}
        self.mock_reasoning_llm.chat.return_value = mock_response
        
        # 测试数据
        query = "请分析王一教授在Cell期刊上发表的影响因子大于等于5的2024年以后的文章"
        
        # 执行测试
        result = self.discuss_agent.query_objects_analysis(query)
        
        # 验证结果
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)
        
        # 验证各个对象
        author_obj = next((obj for obj in result if obj["type"] == "作者"), None)
        self.assertIsNotNone(author_obj)
        self.assertEqual(author_obj["value"], "王一")
        
        journal_obj = next((obj for obj in result if obj["type"] == "期刊"), None)
        self.assertIsNotNone(journal_obj)
        self.assertEqual(journal_obj["value"], "Cell")
        
        impact_factor_obj = next((obj for obj in result if obj["type"] == "影响因子"), None)
        self.assertIsNotNone(impact_factor_obj)
        self.assertEqual(impact_factor_obj["value"], "5")
        self.assertEqual(impact_factor_obj["operator"], ">=")
        
        time_obj = next((obj for obj in result if obj["type"] == "时间范围"), None)
        self.assertIsNotNone(time_obj)
        self.assertEqual(time_obj["value"], ">1724688000")


class TestDiscussIntention(unittest.TestCase):
    """DiscussIntention 测试类"""
    
    def test_discuss_intention_initialization(self):
        """
        测试 DiscussIntention 类的初始化
        """
        # 测试完整数据初始化
        data = {
            "intention": "学术提问",
            "is_academic": True
        }
        intention = DiscussIntention(data)
        self.assertEqual(intention.intention, "学术提问")
        self.assertTrue(intention.is_academic)
    
    def test_discuss_intention_default_values(self):
        """
        测试 DiscussIntention 类的默认值
        """
        # 测试空数据初始化
        data = {}
        intention = DiscussIntention(data)
        self.assertEqual(intention.intention, "其他")
        self.assertTrue(intention.is_academic)  # 默认为 True
    
    def test_discuss_intention_strip_whitespace(self):
        """
        测试 DiscussIntention 类处理空白字符
        """
        # 测试带空白字符的数据
        data = {
            "intention": "  学术提问  ",
            "is_academic": True
        }
        intention = DiscussIntention(data)
        self.assertEqual(intention.intention, "学术提问")  # 应该去除空白字符
    
    def test_should_response_scenarios(self):
        """
        测试 should_response 方法的各种场景
        """
        # 场景1: 学术提问 - 应该响应
        intention1 = DiscussIntention({"intention": "学术提问", "is_academic": True})
        self.assertTrue(intention1.should_response())
        
        # 场景2: 非学术的语气表达 - 不应该响应
        intention2 = DiscussIntention({"intention": "语气表达", "is_academic": False})
        self.assertFalse(intention2.should_response())
        
        # 场景3: 学术的语气表达 - 应该响应
        intention3 = DiscussIntention({"intention": "语气表达", "is_academic": True})
        self.assertTrue(intention3.should_response())
        
        # 场景4: 非学术的其他意图 - 不应该响应
        intention4 = DiscussIntention({"intention": "其他", "is_academic": False})
        self.assertFalse(intention4.should_response())
        
        # 场景5: 学术的其他意图 - 应该响应
        intention5 = DiscussIntention({"intention": "其他", "is_academic": True})
        self.assertTrue(intention5.should_response())
        
        # 场景6: 发表观点 - 应该响应
        intention6 = DiscussIntention({"intention": "发表观点", "is_academic": True})
        self.assertTrue(intention6.should_response())
        
        # 场景7: 质疑 - 应该响应
        intention7 = DiscussIntention({"intention": "质疑", "is_academic": True})
        self.assertTrue(intention7.should_response())


if __name__ == "__main__":
    unittest.main()
