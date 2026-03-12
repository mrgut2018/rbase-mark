#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
示例程序：使用DiscussAgent进行学术对话

本示例展示如何使用DiscussAgent进行学术讨论，包括意图判断和知识检索功能。
"""

import argparse
import logging
import os
import time
import json
from typing import List, Dict

from deepsearcher import configuration
from deepsearcher.configuration import init_rbase_config
from deepsearcher.tools import log
from deepsearcher.agent.discuss_agent import DiscussAgent, DiscussIntention

def main(
    query: str,
    output_file: str,
    background: str = "",
    verbose: bool = False,
):
    """
    使用DiscussAgent进行学术对话的主函数

    Args:
        query: 用户问题
        output_file: 输出文件路径
        background: 对话背景信息
        verbose: 是否启用详细输出
    """
    log.color_print("=" * 60)
    log.color_print("开始执行完整学术对话演示...")
    overall_start_time = time.time()
    
    try:
        # 创建DiscussAgent实例
        log.color_print("正在初始化DiscussAgent...")
        init_start_time = time.time()
        
        discuss_agent = DiscussAgent(
            llm=configuration.writing_llm,
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
            embedding_model=configuration.embedding_model,
            vector_db=configuration.vector_db,
            verbose=verbose
        )
        
        init_end_time = time.time()
        init_time = init_end_time - init_start_time
        log.color_print(f"DiscussAgent初始化完成！用时: {init_time:.3f}秒")
        
        # 模拟对话历史
        history = [
            {
                "content": "我想了解人工智能在医疗领域的应用",
                "role": "user",
            },
            {
                "content": "人工智能在医疗领域有多种应用，包括疾病诊断、医学影像分析、药物研发和个性化治疗方案等。具体来说，AI可以分析大量医学数据以识别疾病模式，提高诊断准确性；通过计算机视觉技术分析X光、CT和MRI等医学影像；加速药物筛选和设计过程；根据患者的基因组数据和病史制定个性化治疗方案。",
                "role": "assistant"
            },
        ]

        # 设置请求参数（用于过滤检索结果）
        request_params = {
            "pubdate": int(time.time()) - 5 * 365 * 24 * 3600,  # 5年内的文献
            "impact_factor": 3.0  # 影响因子大于3的文献
        }

        log.color_print(f"开始处理用户问题: '{query}'")
        query_start_time = time.time()

        # 调用DiscussAgent处理用户问题
        answer, retrieval_results, usage = discuss_agent.query(
            query=query,
            background=background,
            history=history,
            request_params=request_params,
            verbose=verbose
        )

        # 计算处理时间
        query_end_time = time.time()
        query_time = query_end_time - query_start_time

        # 显示统计信息
        log.color_print("\n" + "=" * 40)
        log.color_print("学术对话处理完成！")
        log.color_print("=" * 40)
        log.color_print(f"问题处理时间: {query_time:.3f}秒")
        log.color_print(f"总执行时间: {(query_end_time - overall_start_time):.3f}秒")
        
        if isinstance(usage, dict):
            if "total_tokens" in usage:
                log.color_print(f"总消耗tokens: {usage['total_tokens']}")
            if "prompt_tokens" in usage:
                log.color_print(f"输入tokens: {usage['prompt_tokens']}")
            if "completion_tokens" in usage:
                log.color_print(f"输出tokens: {usage['completion_tokens']}")

        # 显示检索结果统计
        log.color_print(f"检索到的文献数量: {len(retrieval_results)}")
        
        # 保存结果
        log.color_print("正在保存结果...")
        save_start_time = time.time()
        
        result = {
            "query": query,
            "answer": answer,
            "retrieval_count": len(retrieval_results),
            "retrieval_ids": [r.metadata.get("reference_id", "") for r in retrieval_results],
            "time_spent": query_time,
            "total_time": query_end_time - overall_start_time,
            "init_time": init_time,
            "usage": usage,
            "timestamp": int(time.time())
        }
        
        # 将结果保存到文件
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        save_end_time = time.time()
        save_time = save_end_time - save_start_time
        log.color_print(f"结果保存完成！用时: {save_time:.3f}秒")
        log.color_print(f"结果已保存至: {output_file}")
        
        # 输出回答内容
        log.color_print("\n" + "=" * 40)
        log.color_print("回答内容:")
        log.color_print("=" * 40)
        log.color_print(answer)
        
        # 总结统计
        overall_end_time = time.time()
        overall_time = overall_end_time - overall_start_time
        log.color_print("\n" + "=" * 40)
        log.color_print("执行时间统计:")
        log.color_print("=" * 40)
        log.color_print(f"初始化时间: {init_time:.3f}秒 ({(init_time/overall_time*100):.1f}%)")
        log.color_print(f"问题处理时间: {query_time:.3f}秒 ({(query_time/overall_time*100):.1f}%)")
        log.color_print(f"结果保存时间: {save_time:.3f}秒 ({(save_time/overall_time*100):.1f}%)")
        log.color_print(f"总执行时间: {overall_time:.3f}秒")
        
    except Exception as e:
        overall_end_time = time.time()
        overall_time = overall_end_time - overall_start_time
        log.error(f"学术对话执行失败: {e}")
        log.color_print(f"总执行时间: {overall_time:.3f}秒")
        raise
    
    log.color_print("=" * 60)

def intention_analysis_demo(
    query: str,
    background: str = "",
    verbose: bool = False,
):
    """
    意图分析演示函数
    
    Args:
        query: 用户问题
        background: 对话背景信息
        verbose: 是否启用详细输出
    """
    log.color_print("=" * 50)
    log.color_print("开始执行意图分析演示...")
    start_time = time.time()
    
    try:
        # 创建DiscussAgent实例
        discuss_agent = DiscussAgent(
            llm=configuration.writing_llm,
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
            embedding_model=configuration.embedding_model,
            vector_db=configuration.vector_db,
            verbose=verbose
        )

        # 模拟对话历史
        history = [
            {
                "content": "我想了解人工智能在医疗领域的应用",
                "role": "user",
            },
            {
                "content": "人工智能在医疗领域有多种应用，包括疾病诊断、医学影像分析、药物研发和个性化治疗方案等。具体来说，AI可以分析大量医学数据以识别疾病模式，提高诊断准确性；通过计算机视觉技术分析X光、CT和MRI等医学影像；加速药物筛选和设计过程；根据患者的基因组数据和病史制定个性化治疗方案。",
                "role": "assistant"
            },
        ]

        # 执行意图分析
        log.color_print(f"正在分析问题: '{query}'")
        intention_result = discuss_agent.intention_analysis(background, history, query)
        intention = DiscussIntention(intention_result)
        
        # 显示结果
        if verbose:
            log.debug(intention_result)
        log.color_print("意图分析结果:")
        log.color_print(f"  - Intention: {intention.intention}")
        log.color_print(f"  - Is academic: {intention.is_academic}")
        log.color_print(f"  - Should response: {intention.should_response()}")
        
        # 计算并显示执行时间
        end_time = time.time()
        execution_time = end_time - start_time
        log.color_print(f"意图分析完成！执行时间: {execution_time:.3f}秒")
        
    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        log.error(f"意图分析执行失败: {e}")
        log.color_print(f"执行时间: {execution_time:.3f}秒")
        raise
    
    log.color_print("=" * 50)

def query_objects_analysis_demo(
    query: str,
    verbose: bool = False,
):
    """
    查询对象分析演示函数
    
    Args:
        query: 用户问题
        verbose: 是否启用详细输出
    """
    log.color_print("=" * 50)
    log.color_print("开始执行查询对象分析演示...")
    start_time = time.time()
    
    try:
        # 创建DiscussAgent实例
        discuss_agent = DiscussAgent(
            llm=configuration.writing_llm,
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
            embedding_model=configuration.embedding_model,
            vector_db=configuration.vector_db,
            verbose=verbose
        )

        # 模拟对话历史
        history = [
            {
                "content": "我想了解人工智能在医疗领域的应用",
                "role": "user",
            },
            {
                "content": "人工智能在医疗领域有多种应用，包括疾病诊断、医学影像分析、药物研发和个性化治疗方案等。具体来说，AI可以分析大量医学数据以识别疾病模式，提高诊断准确性；通过计算机视觉技术分析X光、CT和MRI等医学影像；加速药物筛选和设计过程；根据患者的基因组数据和病史制定个性化治疗方案。",
                "role": "assistant"
            },
        ]

        # 执行查询对象分析
        log.color_print(f"正在分析问题中的查询对象: '{query}'")
        query_objects = discuss_agent.query_objects_analysis(query)
        
        # 显示结果
        if verbose:
            log.debug(query_objects)
        
        log.color_print("查询对象分析结果:")
        if query_objects:
            for i, obj in enumerate(query_objects, 1):
                log.color_print(f"  {i}. {obj}")
        else:
            log.color_print("  未检测到特定的查询对象")
        
        # 计算并显示执行时间
        end_time = time.time()
        execution_time = end_time - start_time
        log.color_print(f"查询对象分析完成！执行时间: {execution_time:.3f}秒")
        log.color_print(f"共检测到 {len(query_objects)} 个查询对象")
        
    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        log.error(f"查询对象分析执行失败: {e}")
        log.color_print(f"执行时间: {execution_time:.3f}秒")
        raise
    
    log.color_print("=" * 50)

def create_search_query_demo(
    query: str,
    user_action: str = "浏览学术论文",
    background: str = "",
    verbose: bool = False,
):
    """
    创建查询语句演示函数
    """
    log.color_print("=" * 50)
    log.color_print("开始执行创建查询语句演示...")
    start_time = time.time()
    
    try:
        # 创建DiscussAgent实例
        discuss_agent = DiscussAgent(
            llm=configuration.writing_llm,
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
            embedding_model=configuration.embedding_model,
            vector_db=configuration.vector_db,
            verbose=verbose
        )
        
        # 模拟对话历史
        history = [
            {
                "content": "我想了解人工智能在医疗领域的应用",
                "role": "user",
            },
            {
                "content": "人工智能在医疗领域有多种应用，包括疾病诊断、医学影像分析、药物研发和个性化治疗方案等。具体来说，AI可以分析大量医学数据以识别疾病模式，提高诊断准确性；通过计算机视觉技术分析X光、CT和MRI等医学影像；加速药物筛选和设计过程；根据患者的基因组数据和病史制定个性化治疗方案。",
                "role": "assistant"
            },
        ]

        # 执行创建查询语句
        log.color_print(f"正在创建查询语句: '{query}'")
        search_query = discuss_agent.create_search_query(background, history, query)
        
        # 显示结果
        log.color_print("查询语句:")
        log.color_print(search_query)
        
        # 计算并显示执行时间
        end_time = time.time()
        execution_time = end_time - start_time
        log.color_print(f"创建查询语句完成！执行时间: {execution_time:.3f}秒")
        
    except Exception as e:
        end_time = time.time()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="学术对话代理演示")
    parser.add_argument("--verbose", "-v", action="store_true", help="启用详细输出")
    parser.add_argument("--query", "-q", help="用户问题")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--user_action", "-a", default="浏览学术论文", help="用户当前行为")
    parser.add_argument("--background", "-b", default="", help="对话背景信息")
    parser.add_argument("--intention", "-i", action="store_true", help="分析意图")
    parser.add_argument("--query_objects", "-qo", action="store_true", help="分析查询对象")
    parser.add_argument("--create_search_query", "-cq", action="store_true", help="创建查询语句")
    parser.add_argument("--skip_answer", "-sa", action="store_true", help="跳过回答")
    args = parser.parse_args()

    if args.verbose:
        log.set_dev_mode(True)
        log.set_level(logging.DEBUG)
    else:
        log.set_dev_mode(False)
        log.set_level(logging.INFO)

    query = args.query if args.query else "最新的深度学习技术在医疗诊断中有哪些突破性应用？能否给出一些具体例子？"
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = (
        args.output
        if args.output
        else os.path.join(current_dir, "..", "outputs", "discuss_result.json")
    )

    # 初始化配置
    init_rbase_config()

    if args.intention:
        intention_analysis_demo(query=query, background=args.background, verbose=args.verbose)
    if args.query_objects:
        query_objects_analysis_demo(query=query, verbose=args.verbose)
    if args.create_search_query:
        create_search_query_demo(query=query, background=args.background, verbose=args.verbose)
    if not args.skip_answer:
        main(
            query=query, 
            output_file=output_file, 
            background=args.background,
            verbose=args.verbose
        ) 