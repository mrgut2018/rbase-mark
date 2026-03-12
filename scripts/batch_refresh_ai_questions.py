"""
批量刷新AI问题脚本

该脚本用于批量生成AI推荐问题，支持指定term_tree_node_id及其子节点。

功能：
1. 接收外部参数：term_tree_node_id, base_id, tree_id, ver, question_count, limit, offset
2. 获取指定节点的子节点列表
3. 对每个节点调用AI问题生成接口
4. 显示进度并输出结果摘要
"""

import asyncio
import argparse
import logging
import sys
import os
from tqdm import tqdm
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_config
from deepsearcher.tools.log import set_dev_mode, set_level, color_print
from deepsearcher.api.models import QuestionRequest, RelatedType, DepressCache
from deepsearcher.api.routes.questions import api_generate_questions
from deepsearcher.rbase_db_loading import get_term_tree_node_children_ids


async def generate_questions_for_node(
    base_id: int,
    term_tree_node_id: int,
    ver: int,
    question_count: int
) -> dict:
    """
    为指定节点生成AI推荐问题
    
    Args:
        base_id: 基础ID
        term_tree_node_id: 术语树节点ID
        ver: 版本号
        question_count: 问题数量
        
    Returns:
        dict: 包含生成结果的字典
    """
    try:
        # 创建问题请求对象
        request = QuestionRequest(
            related_type=RelatedType.CHANNEL,
            related_id=base_id,
            term_tree_node_ids=[term_tree_node_id],
            ver=ver,
            depress_cache=DepressCache.ENABLE,  # 禁用缓存，强制重新生成
            count=question_count
        )
        
        # 调用AI问题生成接口
        response = await api_generate_questions(request)
        
        return {
            "node_id": term_tree_node_id,
            "success": True,
            "questions": response.questions if response.questions else [],
            "message": response.message
        }
        
    except Exception as e:
        return {
            "node_id": term_tree_node_id,
            "success": False,
            "questions": [],
            "message": str(e)
        }


async def batch_refresh_ai_questions(
    term_tree_node_id: int,
    base_id: int,
    tree_id: int = 0,
    ver: int = 1,
    question_count: int = 6,
    limit: int = 0,
    offset: int = 0,
    recursive_level: int = 1
) -> dict:
    """
    批量刷新AI问题
    
    Args:
        term_tree_node_id: 术语树节点ID（必传）
        base_id: 基础ID（必传）
        tree_id: 树ID（可选，默认为0）
        ver: 版本号（可选，默认为1）
        question_count: 问题数量（可选，默认为6）
        limit: 限制节点数量（可选，默认为0表示无限制）
        offset: 偏移量（可选，默认为0）
        
    Returns:
        dict: 包含批量处理结果的字典
    """
    color_print(f"开始批量刷新AI问题...")
    task_hint = """参数信息:
- term_tree_node_id: {term_tree_node_id}
- base_id: {base_id}
- tree_id: {tree_id}
- ver: {ver}
- question_count: {question_count}
- limit: {limit}
- offset: {offset}
- recursive_level: {recursive_level}"""
    color_print(task_hint.format(
        term_tree_node_id=term_tree_node_id,
        base_id=base_id,
        tree_id=tree_id,
        ver=ver,
        question_count=question_count,
        limit=limit,
        offset=offset,
        recursive_level=recursive_level))
    # 获取当前脚本所在目录，并构建配置文件的路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(current_dir, "..", "config.rbase.yaml")

    # 从YAML文件加载配置
    config = Configuration(yaml_file)

    # 应用配置，使其在全局生效
    init_config(config)
    configuration.config = config
    
    # 获取子节点列表
    color_print("正在获取子节点列表...")
    children_ids = await get_term_tree_node_children_ids(
        rbase_config=config.rbase_settings,
        term_tree_node_id=term_tree_node_id,
        tree_id=tree_id,
        offset=offset,
        limit=limit,
        include_self=True,  # 包含当前节点本身
        recursive_level=recursive_level
    )
    
    if not children_ids:
        color_print("未找到任何节点，退出处理")
        return {
            "total_nodes": 0,
            "success_count": 0,
            "failed_count": 0,
            "results": []
        }
    
    color_print(f"找到 {len(children_ids)} 个节点需要处理")
    color_print(f"节点ID列表: {children_ids}")
    
    # 批量处理节点
    results = []
    success_count = 0
    failed_count = 0
    
    # 使用tqdm显示进度
    with tqdm(total=len(children_ids), desc="生成AI问题", unit="节点") as pbar:
        for node_id in children_ids:
            # 生成问题
            result = await generate_questions_for_node(
                base_id=base_id,
                term_tree_node_id=node_id,
                ver=ver,
                question_count=question_count
            )
            
            results.append(result)
            
            if result["success"]:
                success_count += 1
                pbar.set_postfix({
                    "成功": success_count,
                    "失败": failed_count,
                    "当前节点": node_id
                })
            else:
                failed_count += 1
                pbar.set_postfix({
                    "成功": success_count,
                    "失败": failed_count,
                    "当前节点": node_id,
                    "错误": result["message"][:20] + "..." if len(result["message"]) > 20 else result["message"]
                })
            
            pbar.update(1)
    
    # 生成结果摘要
    summary = {
        "total_nodes": len(children_ids),
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": f"{success_count / len(children_ids) * 100:.2f}%" if len(children_ids) > 0 else "0%",
        "results": results
    }
    
    return summary


def print_summary(summary: dict):
    """
    打印结果摘要
    
    Args:
        summary: 结果摘要字典
    """
    color_print("="*60)
    color_print("批量刷新AI问题 - 结果摘要")
    color_print("="*60)
    color_print(f"总节点数: {summary['total_nodes']}")
    color_print(f"成功数量: {summary['success_count']}")
    color_print(f"失败数量: {summary['failed_count']}")
    color_print(f"成功率: {summary['success_rate']}")
    
    if summary['failed_count'] > 0:
        color_print("失败详情:")
        for result in summary['results']:
            if not result['success']:
                color_print(f"  - 节点 {result['node_id']}: {result['message']}")
    
    color_print("成功生成的节点:")
    for result in summary['results']:
        if result['success']:
            question_count = len(result['questions'])
            question_results = f"  - 节点 {result['node_id']}: 生成了 {question_count} 个问题"
            # 显示前6个问题作为示例
            for i, question in enumerate(result['questions'][:6]):
                question_results += f"\n    {i+1}. {question}"
            if len(result['questions']) > 6:
                question_results += f"    ... 还有 {len(result['questions']) - 6} 个问题"
            color_print(question_results)


async def main():
    """
    主函数
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="批量刷新AI问题脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python batch_refresh_ai_questions.py -tn 123 -b 1
  python batch_refresh_ai_questions.py -tn 123 -b 1 --tree_id 2 -c 8
  python batch_refresh_ai_questions.py -tn 123 -b 1 -l 10 -o 5 -c 8
        """
    )
    
    parser.add_argument(
        "--term_tree_node_id",
        "-tn",
        type=int,
        required=True, 
        help="术语树节点ID（必传）"
    )
    
    parser.add_argument(
        "--base_id",
        "-b",
        type=int,
        required=True,
        help="基本库ID（必传）"
    )
    
    parser.add_argument(
        "--tree_id",
        type=int,
        default=0,
        help="术语树ID（可选，默认为0）"
    )
    
    parser.add_argument(
        "--ver",
        type=int,
        default=1,
        help="版本号（可选，默认为1）"
    )
    
    parser.add_argument(
        "--question_count",
        "-c",
        type=int,
        default=6,
        help="问题数量（可选，默认为6）"
    )
    
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=0,
        help="限制节点数量（可选，默认为0表示无限制）"
    )
    
    parser.add_argument(
        "--offset",
        "-o",
        type=int,
        default=0,
        help="偏移量（可选，默认为0）"
    )

    parser.add_argument(
        "--recursive_level",
        "-r",
        type=int,
        default=1,
        help="递归层级（可选，默认为1）"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="是否打印详细信息，默认为False"
    )
    
    args = parser.parse_args()

    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    
    try:
        # 执行批量刷新
        summary = await batch_refresh_ai_questions(
            term_tree_node_id=args.term_tree_node_id,
            base_id=args.base_id,
            tree_id=args.tree_id,
            ver=args.ver,
            question_count=args.question_count,
            limit=args.limit,
            offset=args.offset,
            recursive_level=args.recursive_level
        )
        
        # 打印结果摘要
        print_summary(summary)
        
        # 返回退出码
        if summary['failed_count'] > 0:
            color_print(f"警告: 有 {summary['failed_count']} 个节点处理失败")
            sys.exit(1)
        else:
            color_print("所有节点处理成功！")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"脚本执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main()) 