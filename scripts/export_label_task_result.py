#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出label_raw_article_task的标注结果到Excel文件。

该脚本的执行流程：
1. 接收raw_article_id参数
2. 查询该文章最近的N个任务（默认N=5，可通过--limit参数调整）
3. 筛选出包含已完成标注项（status=10）的任务
4. 为每个有效任务创建一个Excel sheet，sheet名称使用任务的desc字段
5. 每个sheet包含：
   - 上半部分：文章基本信息（raw_article_id, title, doi, task_id）
   - 下半部分：所有标注结果（id, label_item_key, label_item_value, concept_id, term_tree_node_id, value路径）

作者: AI Assistant
创建时间: 2025年10月28日
更新时间: 2025年11月3日
"""

import argparse
import json
import logging
import os
import sys
import xlwt
from typing import Optional, List, Dict, Any
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.rbase.ai_models import LabelRawArticleTaskStatus
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from deepsearcher.api.rbase_util import (
    load_classifier_value_by_id,
    load_classifier_value_route,
)
from deepsearcher.api.rbase_util.sync.metadata import load_concept_by_id


class LabelTaskResultExporter:
    """标注任务结果导出器"""
    
    def __init__(self, config: Configuration):
        """初始化
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.connection = None
        self._init_db_connection()
        self.classifier_value_route_cache = {}
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise
    
    def load_task_info(self, task_id: int) -> Optional[Dict[str, Any]]:
        """加载任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息字典，如果不存在返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, raw_article_id, base_id, `desc`, status, created, modified
                FROM label_raw_article_task
                WHERE id = %s
                """
                cursor.execute(sql, (task_id,))
                result = cursor.fetchone()
                
                if result:
                    info(f"找到任务: {result['desc']} (ID: {result['id']})")
                    return result
                else:
                    error(f"未找到ID为 {task_id} 的任务")
                    return None
        except Exception as e:
            error(f"加载任务信息失败: {e}")
            return None
    
    def load_tasks_by_article(self, raw_article_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """根据raw_article_id加载最近的N个任务
        
        Args:
            raw_article_id: 文章ID
            limit: 返回的任务数量限制
            
        Returns:
            任务信息列表
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, raw_article_id, base_id, `desc`, status, created, modified
                FROM label_raw_article_task
                WHERE raw_article_id = %s AND status = %s
                ORDER BY created DESC
                LIMIT %s
                """
                cursor.execute(sql, (raw_article_id, LabelRawArticleTaskStatus.COMPLETED.value, limit))
                results = cursor.fetchall()
                
                info(f"找到 {len(results)} 个任务")
                return results
        except Exception as e:
            error(f"加载任务列表失败: {e}")
            return []
    
    def has_completed_task_items(self, task_id: int) -> bool:
        """检查任务是否有状态为10（已完成）的task_item
        
        Args:
            task_id: 任务ID
            
        Returns:
            如果有已完成的task_item返回True，否则返回False
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT COUNT(*) as count
                FROM label_raw_article_task_item
                WHERE label_raw_article_task_id = %s AND status = 10
                """
                cursor.execute(sql, (task_id,))
                result = cursor.fetchone()
                
                count = result['count'] if result else 0
                debug(f"任务 {task_id} 有 {count} 个已完成的task_item")
                return count > 0
        except Exception as e:
            error(f"检查任务完成状态失败: {e}")
            return False
    
    def load_raw_article_info(self, raw_article_id: int) -> Optional[Dict[str, Any]]:
        """加载文章基本信息
        
        Args:
            raw_article_id: 文章ID
            
        Returns:
            文章信息字典，如果不存在返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, doi, title
                FROM raw_article
                WHERE id = %s AND status = 1
                """
                cursor.execute(sql, (raw_article_id,))
                result = cursor.fetchone()
                
                if result:
                    info(f"找到文章: {result['title'][:50]}... (ID: {result['id']})")
                    return result
                else:
                    error(f"未找到ID为 {raw_article_id} 的文章")
                    return None
        except Exception as e:
            error(f"加载文章信息失败: {e}")
            return None
    
    def load_task_results(self, task_id: int) -> List[Dict[str, Any]]:
        """加载任务的所有标注结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            标注结果列表
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT r.id, r.label_item_key, r.label_item_value, r.location, 
                       r.concept_id, r.term_tree_node_id, r.label_raw_article_task_item_id,
                       r.metadata, i.classifier_id, i.classifier_ver, i.script_params as params, i.`usage` as `usage`
                FROM label_raw_article_task_result r, label_raw_article_task_item i
                WHERE r.label_raw_article_task_item_id = i.id AND i.label_raw_article_task_id = %s
                ORDER BY r.id ASC
                """
                cursor.execute(sql, (task_id,))
                results = cursor.fetchall()
                
                info(f"找到 {len(results)} 条标注结果")
                return results
        except Exception as e:
            error(f"加载标注结果失败: {e}")
            return []
    
    def get_classifier_id_from_task_item(self, task_item_id: int) -> Optional[int]:
        """从任务项中获取分类器ID
        
        Args:
            task_item_id: 任务项ID
            
        Returns:
            分类器ID，如果不存在返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT classifier_id
                FROM label_raw_article_task_item
                WHERE id = %s
                """
                cursor.execute(sql, (task_item_id,))
                result = cursor.fetchone()
                
                if result:
                    return result['classifier_id']
                else:
                    return None
        except Exception as e:
            error(f"获取分类器ID失败: {e}")
            return None
    
    def get_classifier_value_id(self, classifier_id: int, term_tree_node_id: int) -> Optional[int]:
        """根据classifier_id和term_tree_node_id获取classifier_value_id
        
        Args:
            classifier_id: 分类器ID
            term_tree_node_id: 术语树节点ID
            
        Returns:
            classifier_value_id，如果不存在返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id
                FROM classifier_value
                WHERE classifier_id = %s AND term_tree_node_id = %s AND status = 1
                LIMIT 1
                """
                cursor.execute(sql, (classifier_id, term_tree_node_id))
                result = cursor.fetchone()
                
                if result:
                    return result['id']
                else:
                    return None
        except Exception as e:
            error(f"获取classifier_value_id失败: {e}")
            return None
    
    def get_value_path(self, task_item_id: int, term_tree_node_id: Optional[int], lang: Optional[str] = 'en') -> str:
        """获取value路径
        
        Args:
            task_item_id: 任务项ID
            term_tree_node_id: 术语树节点ID
            
        Returns:
            路径字符串，用 " -> " 连接
        """
        # 如果term_tree_node_id为None，返回空字符串
        if term_tree_node_id is None:
            return ""
        
        try:
            # 获取classifier_id
            classifier_id = self.get_classifier_id_from_task_item(task_item_id)
            if classifier_id is None:
                debug(f"无法获取task_item_id={task_item_id}的classifier_id")
                return ""
            
            # 获取classifier_value_id
            classifier_value_id = self.get_classifier_value_id(classifier_id, term_tree_node_id)
            if classifier_value_id is None:
                debug(f"无法找到classifier_id={classifier_id}, term_tree_node_id={term_tree_node_id}的classifier_value")
                return ""

            cache_result = self.get_classifier_value_route_cache(classifier_value_id)
            if cache_result is not None:
                return cache_result
            
            # 加载classifier_value
            classifier_value = load_classifier_value_by_id(classifier_value_id)
            if classifier_value is None:
                debug(f"无法加载classifier_value_id={classifier_value_id}")
                return ""
            
            # 获取路径
            route = load_classifier_value_route(classifier_value)
            if not route:
                return ""
            
            # 连接路径
            values = []
            for cv in route:
                concept_id = cv.concept_id
                concept = load_concept_by_id(concept_id)
                if lang == 'en':
                    values.append(concept.name)
                else:
                    values.append(concept.cname)
            result = " -> ".join(values)
            self.set_classifier_value_route_cache(classifier_value_id, result)
            return result
            
        except Exception as e:
            error(f"获取value路径失败: {e}")
            return ""

    def set_classifier_value_route_cache(self, classifier_value_id: int, result: str):
        self.classifier_value_route_cache[classifier_value_id] = result

    def get_classifier_value_route_cache(self, classifier_value_id: int) -> Optional[str]:
        if classifier_value_id in self.classifier_value_route_cache:
            debug(f"获取classifier_value_route_cache: {classifier_value_id} -> {self.classifier_value_route_cache[classifier_value_id]}")
        return self.classifier_value_route_cache.get(classifier_value_id)

    def clear_classifier_value_route_cache(self):
        self.classifier_value_route_cache.clear()
    
    def format_metadata(self, metadata_str: Optional[str]) -> str:
        """格式化metadata字段，只提取seq和parts字段
        
        Args:
            metadata_str: metadata的JSON字符串
            
        Returns:
            格式化后的字符串，例如 "seq=1; parts=Result"，如果没有seq或parts则返回空字符串
        """
        if not metadata_str:
            return ""
        
        try:
            metadata = json.loads(metadata_str)
            if not isinstance(metadata, dict):
                return ""
            
            parts = []
            if 'seq' in metadata:
                parts.append(f"seq={metadata['seq']}")
            if 'parts' in metadata:
                parts.append(f"parts={metadata['parts']}")
            if 'entity_matched' in metadata:
                parts.append(f"entity_matched={metadata['entity_matched']}")
            
            if parts:
                return "; ".join(parts)
            else:
                return ""
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            debug(f"解析metadata失败: {e}, metadata_str: {metadata_str}")
            return ""
    
    def _write_task_sheet(self, workbook, task_info: Dict[str, Any], raw_article_info: Dict[str, Any]):
        """在workbook中为指定task创建一个sheet并写入数据
        
        Args:
            workbook: Excel工作簿对象
            task_info: 任务信息
            raw_article_info: 文章信息
        """
        # 使用task的desc作为sheet名称，但需要处理特殊字符
        if task_info['desc']:
            desc = str(task_info['desc'])
            id_str = str(task_info['id'])
            max_len = 31
            # +1 for the underscore
            max_desc_len = max_len - len(id_str) - 1
            if len(desc) + len(id_str) + 1 > max_len:
                desc = desc[:max_desc_len]
            sheet_name = f"{desc}_{id_str}"
        else:
            sheet_name = f"Task_{task_info['id']}"
        # Excel sheet名称限制：不能超过31个字符，不能包含: \ / ? * [ ]
        sheet_name = sheet_name[:31]
        for char in [':', '\\', '/', '?', '*', '[', ']']:
            sheet_name = sheet_name.replace(char, '_')
        
        worksheet = workbook.add_sheet(sheet_name)
        
        # 设置样式
        header_style = xlwt.XFStyle()
        header_font = xlwt.Font()
        header_font.bold = True
        header_font.height = 240  # 12pt
        header_style.font = header_font
        
        # 设置对齐
        alignment = xlwt.Alignment()
        alignment.horz = xlwt.Alignment.HORZ_LEFT
        alignment.vert = xlwt.Alignment.VERT_TOP
        header_style.alignment = alignment
        
        normal_style = xlwt.XFStyle()
        normal_style.alignment = alignment
        
        # 写入文章基本信息
        row = 0
        worksheet.write(row, 0, '文章基本信息', header_style)
        row += 1
        
        worksheet.write(row, 0, 'raw_article_id', header_style)
        worksheet.write(row, 1, raw_article_info['id'], normal_style)
        row += 1
        
        worksheet.write(row, 0, 'title', header_style)
        worksheet.write(row, 1, raw_article_info['title'] or '', normal_style)
        row += 1
        
        worksheet.write(row, 0, 'doi', header_style)
        worksheet.write(row, 1, raw_article_info['doi'] or '', normal_style)
        row += 1
        
        worksheet.write(row, 0, 'task_id', header_style)
        worksheet.write(row, 1, task_info['id'], normal_style)
        row += 2  # 空一行
        
        # 加载标注结果
        results = self.load_task_results(task_info['id'])
        
        # 写入标注结果
        worksheet.write(row, 0, '标注结果列表', header_style)
        row += 1
        
        # 写入表头
        headers = ['id', 'label_item_key', 'label_item_value', 'location', 'concept_id', 'term_tree_node_id', 'value路径', 'value路径(英文)', 'metadata', 'classifier_id', 'classifier_ver', 'llm', 'cost']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_style)
        row += 1
        
        # 写入数据
        for result in results:
            # 获取value路径
            value_path_en = self.get_value_path(
                result['label_raw_article_task_item_id'],
                result['term_tree_node_id']
            )
            value_path_cn = self.get_value_path(
                result['label_raw_article_task_item_id'],
                result['term_tree_node_id'],
                lang='cn'
            )
            
            worksheet.write(row, 0, result['id'], normal_style)
            worksheet.write(row, 1, result['label_item_key'] or '', normal_style)
            worksheet.write(row, 2, result['label_item_value'] or '', normal_style)
            worksheet.write(row, 3, result['location'] or '', normal_style)
            worksheet.write(row, 4, result['concept_id'] or '', normal_style)
            worksheet.write(row, 5, result['term_tree_node_id'] or '', normal_style)
            worksheet.write(row, 6, value_path_cn, normal_style)
            worksheet.write(row, 7, value_path_en, normal_style)
            # 格式化并写入metadata（在classifier_id前面）
            metadata_str = self.format_metadata(result.get('metadata'))
            worksheet.write(row, 8, metadata_str, normal_style)
            worksheet.write(row, 9, result['classifier_id'] or '', normal_style)
            worksheet.write(row, 10, result['classifier_ver'] or '', normal_style)
            if result['params']:
                try:
                    params = json.loads(result['params'])
                    llm = params.get('reasoning_llm_model', '')
                except Exception as e:
                    llm = ''
            if result['usage']:
                try:
                    usage = json.loads(result['usage'])
                    cost = usage.get('cost', 0)
                except Exception as e:
                    cost = 0
            worksheet.write(row, 11, llm, normal_style)
            worksheet.write(row, 12, cost, normal_style)
            row += 1
        
        # 设置列宽
        worksheet.col(0).width = 3000   # id
        worksheet.col(1).width = 6000   # label_item_key
        worksheet.col(2).width = 8000   # label_item_value
        worksheet.col(3).width = 4000   # location
        worksheet.col(4).width = 4000   # concept_id
        worksheet.col(5).width = 5000   # term_tree_node_id
        worksheet.col(6).width = 15000  # value路径
        worksheet.col(7).width = 15000  # value路径(英文)
        worksheet.col(8).width = 6000   # metadata
        
        info(f"Sheet '{sheet_name}' 已创建，共 {len(results)} 条标注结果")

    def export_to_excel(self, task_id: int, output_file: Optional[str] = None) -> bool:
        """导出标注结果到Excel文件（单个任务）
        
        Args:
            task_id: 任务ID
            output_file: 输出文件路径，如果为None则使用默认路径
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 1. 加载任务信息
            task_info = self.load_task_info(task_id)
            if not task_info:
                error("任务信息加载失败")
                return False
            
            # 2. 加载文章信息
            raw_article_info = self.load_raw_article_info(task_info['raw_article_id'])
            if not raw_article_info:
                error("文章信息加载失败")
                return False
            
            # 3. 确定输出文件路径
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                excel_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "database", "excel"
                )
                os.makedirs(excel_dir, exist_ok=True)
                output_file = os.path.join(
                    excel_dir, 
                    f"label_raw_article_task_{raw_article_info['id']}_{task_id}_{timestamp}.xls"
                )
            
            # 4. 创建Excel工作簿
            workbook = xlwt.Workbook(encoding='utf-8')
            
            # 5. 写入任务sheet
            self._write_task_sheet(workbook, task_info, raw_article_info)
            
            # 6. 保存文件
            workbook.save(output_file)
            
            color_print(f"✅ Excel文件已成功导出到: {output_file}")
            return True
            
        except Exception as e:
            error(f"导出Excel失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def export_to_excel_by_article(self, raw_article_id: int, limit: int = 5, output_file: Optional[str] = None) -> bool:
        """按raw_article_id导出标注结果到Excel文件（可能包含多个任务的多个sheet）
        
        Args:
            raw_article_id: 文章ID
            limit: 查询的任务数量限制
            output_file: 输出文件路径，如果为None则使用默认路径
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 1. 加载文章信息
            raw_article_info = self.load_raw_article_info(raw_article_id)
            if not raw_article_info:
                error("文章信息加载失败")
                return False
            
            # 2. 加载最近的N个任务
            tasks = self.load_tasks_by_article(raw_article_id, limit)
            if not tasks:
                error(f"未找到raw_article_id={raw_article_id}的任务")
                return False
            
            # 3. 筛选出有已完成task_item的任务
            valid_tasks = []
            for task in tasks:
                if self.has_completed_task_items(task['id']):
                    valid_tasks.append(task)
                    info(f"任务 {task['id']} ({task['desc']}) 有已完成的标注项")
                else:
                    debug(f"跳过任务 {task['id']} ({task['desc']})，无已完成的标注项")
            
            if not valid_tasks:
                error("没有找到包含已完成标注项的任务")
                return False
            
            info(f"共找到 {len(valid_tasks)} 个有效任务")
            
            # 4. 确定输出文件路径
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                excel_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "database", "excel"
                )
                os.makedirs(excel_dir, exist_ok=True)
                output_file = os.path.join(
                    excel_dir, 
                    f"label_raw_article_{raw_article_id}_{timestamp}.xls"
                )
            
            # 5. 创建Excel工作簿
            workbook = xlwt.Workbook(encoding='utf-8')
            
            # 6. 为每个有效任务创建一个sheet
            for task in valid_tasks:
                self._write_task_sheet(workbook, task, raw_article_info)
            
            # 7. 保存文件
            workbook.save(output_file)
            
            color_print(f"✅ Excel文件已成功导出到: {output_file}")
            info(f"共导出 {len(valid_tasks)} 个任务的标注结果")
            return True
            
        except Exception as e:
            error(f"导出Excel失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='导出label_raw_article_task的标注结果到Excel')
    parser.add_argument('-a', '--article_id', type=int, required=True, help='文章ID (raw_article_id)')
    parser.add_argument('-n', '--limit', type=int, default=5, help='查询的任务数量限制（默认5）')
    parser.add_argument('-o', '--output', type=str, help='输出文件路径（可选）')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        debug(f"文章ID: {args.article_id}")
        debug(f"查询任务数量限制: {args.limit}")
        if args.output:
            debug(f"输出文件: {args.output}")
        debug("-" * 50)
    
    # 初始化配置
    init_rbase_config()
    
    exporter = None
    try:
        exporter = LabelTaskResultExporter(configuration.config)
        success = exporter.export_to_excel_by_article(args.article_id, args.limit, args.output)
        
        if success:
            color_print("\n✅ 导出成功!")
            return 0
        else:
            error("\n❌ 导出失败!")
            return 1
            
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if exporter:
            exporter.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())

