#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
示例程序：使用ArticleTitleAgent生成学术论文的新闻标题

本示例展示如何根据文章ID获取文章和作者信息，然后使用ArticleTitleAgent生成指定数量的新闻标题。
"""

import argparse
import asyncio
import logging
import os
import time
from typing import List

from deepsearcher import configuration
from deepsearcher.configuration import init_rbase_config
from deepsearcher.tools import log
from deepsearcher.agent.article_title_agent import ArticleTitleAgent
from deepsearcher.rbase.rbase_article import RbaseArticle, RbaseAuthor
from deepsearcher.rbase_db_loading import load_article_by_article_id, load_article_authors


async def get_article_and_authors(article_id: int, article_uuid: str = "") -> tuple[RbaseArticle, List[RbaseAuthor]]:
    """
    根据文章ID获取文章和作者信息
    
    Args:
        article_id: 文章ID
        
    Returns:
        tuple: (文章对象, 作者列表)
    """
    if article_id:
        log.color_print(f"正在获取文章ID {article_id} 的信息...")
    else:
        log.color_print(f"正在获取文章UUID {article_uuid} 的信息...")
    
    # 获取文章信息
    article = await load_article_by_article_id(article_id, article_uuid)
    log.color_print(f"成功获取文章: {article.title}")
    
    # 获取作者信息
    authors = await load_article_authors(article.article_id)
    log.color_print(f"成功获取 {len(authors)} 位作者信息")
    
    return article, authors


def main(
    article_id: int = 0,
    article_uuid: str = "",
    title_count: int = 3,
    query: str = "",
    output_file: str = None,
    verbose: bool = False,
):
    """
    使用ArticleTitleAgent生成新闻标题的主函数

    Args:
        article_id: 文章ID
        title_count: 生成标题数量
        query: 额外的查询提示
        output_file: 输出文件路径
        verbose: 是否启用详细输出
    """
    # 初始化配置
    init_rbase_config()
    config = configuration.config

    async def async_main():
        # 获取文章和作者信息
        article, authors = await get_article_and_authors(article_id, article_uuid)
        
        # 显示文章基本信息
        log.color_print(f"\n文章信息:")
        log.color_print(f"标题: {article.title}")
        log.color_print(f"期刊: {article.journal_name}")
        log.color_print(f"影响因子: {article.impact_factor}")
        
        log.color_print(f"\n作者信息:")
        for i, author in enumerate(authors, 1):
            if author.is_key_author:
                log.color_print(f"{i}. {author.description()}")
        
        # 创建ArticleTitleAgent实例
        title_agent = ArticleTitleAgent(
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
        )

        log.color_print(f"\n开始生成 {title_count} 个新闻标题...")
        start_time = time.time()

        # 调用ArticleTitleAgent生成标题
        titles, _, usage = title_agent.query(
            query=query,
            article=article,
            authors=authors,
            title_count=title_count,
            verbose=verbose,
        )

        # 计算处理时间
        end_time = time.time()
        time_spent = end_time - start_time

        # 显示统计信息
        log.color_print("\n新闻标题生成完成！")
        log.color_print(f"用时: {time_spent:.2f}秒")
        if hasattr(usage, 'total_tokens'):
            log.color_print(f"消耗tokens: {usage.total_tokens}")

        # 解析生成的标题
        import re
        title_pattern = r'<title>(.*?)</title>'
        extracted_titles = re.findall(title_pattern, titles, re.DOTALL)
        
        if not extracted_titles:
            log.color_print("警告: 未能解析到标题，显示原始输出:")
            log.color_print(titles)
        else:
            log.color_print(f"\n生成的 {len(extracted_titles)} 个新闻标题:")
            for i, title in enumerate(extracted_titles, 1):
                log.color_print(f"{i}. {title.strip()}")
        
        # 将结果保存到文件
        if output_file:
            final_output_file = output_file.replace("<article_id>", str(article.article_id))
            with open(final_output_file, "w", encoding="utf-8") as f:
                f.write(f"文章ID: {article_id}\n")
                f.write(f"文章标题: {article.title}\n")
                f.write(f"期刊: {article.journal_name}\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"用时: {time_spent:.2f}秒\n")
                f.write("\n生成的新闻标题:\n")
                if extracted_titles:
                    for i, title in enumerate(extracted_titles, 1):
                        f.write(f"{i}. {title.strip()}\n")
                else:
                    f.write(titles)
            
            log.color_print(f"\n结果已保存至: {final_output_file}")

    # 运行异步主函数
    asyncio.run(async_main())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="""Generate news titles using ArticleTitleAgent. 
Please provide either article_id or article_uuid for the article to be processed.""")
    parser.add_argument("--article_id", "-id", type=int, default=0, help="Article ID")
    parser.add_argument("--article_uuid", "-uuid", type=str, default="", help="Article UUID")
    parser.add_argument("--title_count", "-c", type=int, default=3, help="Number of titles to generate")
    parser.add_argument("--query", "-q", default="", help="Additional query prompt")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.article_id == 0 and args.article_uuid == "":
        parser.print_help()
        parser.exit(1)

    if args.verbose:
        log.set_dev_mode(True)
        log.set_level(logging.DEBUG)
    else:
        log.set_dev_mode(False)
        log.set_level(logging.INFO)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = (
        args.output
        if args.output
        else os.path.join(current_dir, "..", "outputs", f"article_title_<article_id>.txt")
    )
    
    main(
        article_id=args.article_id,
        article_uuid=args.article_uuid,
        title_count=args.title_count,
        query=args.query,
        output_file=output_file,
        verbose=args.verbose
    ) 