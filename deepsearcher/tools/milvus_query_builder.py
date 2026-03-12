#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Milvus查询构建器

根据query_objects_analysis分析出的对象结果构建符合Milvus过滤规则的查询条件
"""

from typing import List, Dict, Any, Optional
import time
from datetime import datetime
from deepsearcher.tools import log
from deepsearcher.rbase_db_loading import get_authors_by_name


class MilvusQueryBuilder:
    """
    Milvus查询构建器类
    
    用于根据query_objects_analysis的结果构建符合Milvus语法的过滤条件
    支持作者、期刊、发布时间、影响因子等多种查询条件的组合
    """
    
    def __init__(self):
        """
        初始化查询构建器
        """
        self.conditions = []
        
    async def build_filter_from_objects(self, objects: List[Dict[str, Any]]) -> str:
        """
        根据query_objects_analysis的结果构建过滤条件
        
        Args:
            objects: query_objects_analysis返回的对象列表
            
        Returns:
            符合Milvus语法的过滤条件字符串
        """
        if not objects:
            return ""
        
        # 按类型分组处理对象
        author_objects = []
        author_id_objects = []
        journal_objects = []
        journal_id_objects = []
        time_objects = []
        impact_factor_objects = []
        
        for obj in objects:
            obj_type = obj.get("type", "")
            if obj_type == "作者":
                author_objects.append(obj)
            elif obj_type == "作者ID":
                author_id_objects.append(obj)
            elif obj_type == "期刊":
                journal_objects.append(obj)
            elif obj_type == "期刊ID":
                journal_id_objects.append(obj)
            elif obj_type == "时间范围":
                time_objects.append(obj)
            elif obj_type == "影响因子":
                impact_factor_objects.append(obj)
        
        # 构建各类条件
        conditions = []

        if author_objects and not author_id_objects:
            for author in author_objects:
                author_ids = await get_authors_by_name(author.get("value", ""))
                author_id_objects.append({
                    "type": "作者ID",
                    "value": author_ids[0]
                })
        
        if author_id_objects:
            author_id_condition = self._build_author_id_condition(author_id_objects)
            if author_id_condition:
                conditions.append(author_id_condition)
        elif author_objects:
            author_condition = self._build_author_condition(author_objects)
            if author_condition:
                conditions.append(author_condition)
        
        # 构建期刊条件（OR关系）
        if False and journal_objects:
            journal_condition = self._build_journal_condition(journal_objects)
            if journal_condition:
                conditions.append(journal_condition)
        
        # 构建期刊ID条件（OR关系）
        if False and journal_id_objects:
            journal_id_condition = self._build_journal_id_condition(journal_id_objects)
            if journal_id_condition:
                conditions.append(journal_id_condition)
        
        # 构建时间范围条件
        if time_objects:
            time_condition = self._build_time_condition(time_objects)
            if time_condition:
                conditions.append(time_condition)
        
        # 构建影响因子条件（AND关系）
        if impact_factor_objects:
            impact_factor_condition = self._build_impact_factor_condition(impact_factor_objects)
            if impact_factor_condition:
                conditions.append(impact_factor_condition)
        
        # 使用AND连接所有条件
        if not conditions:
            return ""
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return " AND ".join(f"({condition})" for condition in conditions)
    
    def _build_author_condition(self, author_objects: List[Dict[str, Any]]) -> str:
        """
        构建作者查询条件（OR关系）
        
        Args:
            author_objects: 作者对象列表
            
        Returns:
            作者查询条件字符串
        """
        if not author_objects:
            return ""
        
        # 收集所有有效的作者名称
        author_names = []
        for obj in author_objects:
            author_name = obj.get("value", "").strip()
            if author_name:
                author_names.append(author_name)
        
        if not author_names:
            return ""
        elif len(author_names) == 1:
            # 单个作者使用 ARRAY_CONTAINS
            return f'ARRAY_CONTAINS(authors, "{author_names[0]}")'
        else:
            # 多个作者使用 ARRAY_CONTAINS_ANY
            author_list = ', '.join(f'"{name}"' for name in author_names)
            return f'ARRAY_CONTAINS_ANY(authors, [{author_list}])'
    
    def _build_author_id_condition(self, author_id_objects: List[Dict[str, Any]]) -> str:
        """
        构建作者ID查询条件（OR关系）
        
        Args:
            author_id_objects: 作者ID对象列表
            
        Returns:
            作者ID查询条件字符串
        """
        if not author_id_objects:
            return ""
        
        # 收集所有有效的作者ID
        author_ids = []
        for obj in author_id_objects:
            try:
                author_id = int(obj.get("value", 0))
                if author_id > 0:
                    author_ids.append(author_id)
            except (ValueError, TypeError):
                log.warning(f"无效的作者ID: {obj.get('value')}")
                continue
        
        if not author_ids:
            return ""
        elif len(author_ids) == 1:
            # 单个作者ID使用 ARRAY_CONTAINS
            return f'ARRAY_CONTAINS(author_ids, {author_ids[0]})'
        else:
            # 多个作者ID使用 ARRAY_CONTAINS_ANY
            author_id_list = ', '.join(str(aid) for aid in author_ids)
            return f'ARRAY_CONTAINS_ANY(author_ids, [{author_id_list}])'
    
    def _build_journal_condition(self, journal_objects: List[Dict[str, Any]]) -> str:
        """
        构建期刊查询条件（OR关系）
        
        Args:
            journal_objects: 期刊对象列表
            
        Returns:
            期刊查询条件字符串
        """
        if not journal_objects:
            return ""
        
        journal_conditions = []
        for obj in journal_objects:
            journal_name = obj.get("value", "").strip()
            if journal_name:
                # 使用LIKE进行期刊名称匹配
                journal_conditions.append(f'reference LIKE "%{journal_name}%"')
        
        if not journal_conditions:
            return ""
        elif len(journal_conditions) == 1:
            return journal_conditions[0]
        else:
            return " OR ".join(journal_conditions)
    
    def _build_journal_id_condition(self, journal_id_objects: List[Dict[str, Any]]) -> str:
        """
        构建期刊ID查询条件（OR关系）
        
        Args:
            journal_id_objects: 期刊ID对象列表
            
        Returns:
            期刊ID查询条件字符串
        """
        if not journal_id_objects:
            return ""
        
        journal_id_conditions = []
        for obj in journal_id_objects:
            try:
                journal_id = int(obj.get("value", 0))
                if journal_id > 0:
                    # 假设期刊ID存储在metadata中或者reference_id字段中
                    journal_id_conditions.append(f'reference_id == {journal_id}')
            except (ValueError, TypeError):
                log.warning(f"无效的期刊ID: {obj.get('value')}")
                continue
        
        if not journal_id_conditions:
            return ""
        elif len(journal_id_conditions) == 1:
            return journal_id_conditions[0]
        else:
            return " OR ".join(journal_id_conditions)
    
    def _build_time_condition(self, time_objects: List[Dict[str, Any]]) -> str:
        """
        构建时间范围查询条件
        
        Args:
            time_objects: 时间对象列表
            
        Returns:
            时间查询条件字符串
        """
        if not time_objects:
            return ""
        
        time_conditions = []
        current_timestamp = int(time.time())
        
        for obj in time_objects:
            value = obj.get("value", "").strip()
            operator = obj.get("operator", "").strip()
            
            if not value:
                continue
            
            # 处理相对时间表达
            if value == "最近":
                # 默认为最近一年
                one_year_ago = current_timestamp - 365 * 24 * 3600
                time_conditions.append(f'pubdate >= {one_year_ago}')
            elif value == "近期":
                # 默认为最近半年
                six_months_ago = current_timestamp - 180 * 24 * 3600
                time_conditions.append(f'pubdate >= {six_months_ago}')
            elif value == "近年来":
                # 默认为最近三年
                three_years_ago = current_timestamp - 3 * 365 * 24 * 3600
                time_conditions.append(f'pubdate >= {three_years_ago}')
            elif value.startswith(">") or value.startswith("<") or value.startswith(">=") or value.startswith("<="):
                # 处理时间戳表达式，如 ">1724688000"
                try:
                    if value.startswith(">="):
                        timestamp = int(value[2:])
                        time_conditions.append(f'pubdate >= {timestamp}')
                    elif value.startswith("<="):
                        timestamp = int(value[2:])
                        time_conditions.append(f'pubdate <= {timestamp}')
                    elif value.startswith(">"):
                        timestamp = int(value[1:])
                        time_conditions.append(f'pubdate > {timestamp}')
                    elif value.startswith("<"):
                        timestamp = int(value[1:])
                        time_conditions.append(f'pubdate < {timestamp}')
                except (ValueError, TypeError):
                    log.warning(f"无效的时间戳表达式: {value}")
                    continue
            else:
                # 尝试解析为时间戳
                try:
                    timestamp = int(value)
                    if operator:
                        time_conditions.append(f'pubdate {operator} {timestamp}')
                    else:
                        # 默认为大于等于该时间戳
                        time_conditions.append(f'pubdate >= {timestamp}')
                except (ValueError, TypeError):
                    # 尝试解析为日期格式
                    try:
                        # 支持常见的日期格式
                        for date_format in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
                            try:
                                dt = datetime.strptime(value, date_format)
                                timestamp = int(dt.timestamp())
                                if operator:
                                    time_conditions.append(f'pubdate {operator} {timestamp}')
                                else:
                                    time_conditions.append(f'pubdate >= {timestamp}')
                                break
                            except ValueError:
                                continue
                        else:
                            log.warning(f"无法解析的时间格式: {value}")
                            continue
                    except Exception as e:
                        log.warning(f"时间解析错误: {value}, 错误: {e}")
                        continue
        
        if not time_conditions:
            return ""
        elif len(time_conditions) == 1:
            return time_conditions[0]
        else:
            # 时间条件使用AND连接（需要同时满足所有时间条件）
            return " AND ".join(time_conditions)
    
    def _build_impact_factor_condition(self, impact_factor_objects: List[Dict[str, Any]]) -> str:
        """
        构建影响因子查询条件（AND关系）
        
        Args:
            impact_factor_objects: 影响因子对象列表
            
        Returns:
            影响因子查询条件字符串
        """
        if not impact_factor_objects:
            return ""
        
        impact_factor_conditions = []
        for obj in impact_factor_objects:
            try:
                value = float(obj.get("value", 0))
                operator = obj.get("operator", ">=").strip()
                
                # 验证操作符
                if operator not in [">=", "<=", ">", "<", "==", "!="]:
                    operator = ">="  # 默认操作符
                
                if value >= 0:
                    impact_factor_conditions.append(f'impact_factor {operator} {value}')
            except (ValueError, TypeError):
                log.warning(f"无效的影响因子值: {obj.get('value')}")
                continue
        
        if not impact_factor_conditions:
            return ""
        elif len(impact_factor_conditions) == 1:
            return impact_factor_conditions[0]
        else:
            # 影响因子条件使用AND连接（需要同时满足所有条件）
            return " AND ".join(impact_factor_conditions)
    
    def build_custom_filter(
        self, 
        authors: Optional[List[str]] = None,
        author_ids: Optional[List[int]] = None,
        journals: Optional[List[str]] = None,
        journal_ids: Optional[List[int]] = None,
        min_impact_factor: Optional[float] = None,
        max_impact_factor: Optional[float] = None,
        min_pubdate: Optional[int] = None,
        max_pubdate: Optional[int] = None,
        custom_conditions: Optional[List[str]] = None
    ) -> str:
        """
        构建自定义过滤条件（提供更灵活的API）
        
        Args:
            authors: 作者列表（OR关系）
            author_ids: 作者ID列表（OR关系）
            journals: 期刊列表（OR关系）
            journal_ids: 期刊ID列表（OR关系）
            min_impact_factor: 最小影响因子
            max_impact_factor: 最大影响因子
            min_pubdate: 最早发布时间戳
            max_pubdate: 最晚发布时间戳
            custom_conditions: 自定义条件列表
            
        Returns:
            符合Milvus语法的过滤条件字符串
        """
        conditions = []
        
        # 作者条件
        if authors:
            valid_authors = [author.strip() for author in authors if author.strip()]
            if valid_authors:
                if len(valid_authors) == 1:
                    conditions.append(f'ARRAY_CONTAINS(authors, "{valid_authors[0]}")')
                else:
                    author_list = ', '.join(f'"{author}"' for author in valid_authors)
                    conditions.append(f'ARRAY_CONTAINS_ANY(authors, [{author_list}])')
        
        # 作者ID条件
        if author_ids:
            valid_author_ids = [author_id for author_id in author_ids if author_id > 0]
            if valid_author_ids:
                if len(valid_author_ids) == 1:
                    conditions.append(f'ARRAY_CONTAINS(author_ids, {valid_author_ids[0]})')
                else:
                    author_id_list = ', '.join(str(aid) for aid in valid_author_ids)
                    conditions.append(f'ARRAY_CONTAINS_ANY(author_ids, [{author_id_list}])')
        
        # 期刊条件
        if False and journals:
            journal_conditions = [f'reference LIKE "%{journal}%"' for journal in journals if journal.strip()]
            if journal_conditions:
                if len(journal_conditions) == 1:
                    conditions.append(journal_conditions[0])
                else:
                    conditions.append(f"({' OR '.join(journal_conditions)})")
        
        # 期刊ID条件
        if False and journal_ids:
            journal_id_conditions = [f'reference_id == {journal_id}' for journal_id in journal_ids if journal_id > 0]
            if journal_id_conditions:
                if len(journal_id_conditions) == 1:
                    conditions.append(journal_id_conditions[0])
                else:
                    conditions.append(f"({' OR '.join(journal_id_conditions)})")
        
        # 影响因子条件
        if min_impact_factor is not None and min_impact_factor >= 0:
            conditions.append(f'impact_factor >= {min_impact_factor}')
        
        if max_impact_factor is not None and max_impact_factor >= 0:
            conditions.append(f'impact_factor <= {max_impact_factor}')
        
        # 发布时间条件
        if min_pubdate is not None and min_pubdate > 0:
            conditions.append(f'pubdate >= {min_pubdate}')
        
        if max_pubdate is not None and max_pubdate > 0:
            conditions.append(f'pubdate <= {max_pubdate}')
        
        # 自定义条件
        if custom_conditions:
            conditions.extend([condition for condition in custom_conditions if condition.strip()])
        
        # 使用AND连接所有条件
        if not conditions:
            return ""
        elif len(conditions) == 1:
            return conditions[0]
        else:
            return " AND ".join(f"({condition})" if " OR " in condition and not condition.startswith("(") else condition for condition in conditions)


def create_query_builder() -> MilvusQueryBuilder:
    """
    创建一个新的查询构建器实例
    
    Returns:
        MilvusQueryBuilder实例
    """
    return MilvusQueryBuilder()
