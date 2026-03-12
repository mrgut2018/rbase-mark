#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据指定的classifier_id构造classifier下的所有classifier_value数据的脚本。

该脚本的执行流程：
1. 通过classifier_id读取classifier表中的分类器数据
2. 判断分类器数据中的term_tree_id和term_tree_node_id是否存在，如果不存在则直接返回，构建失败
3. 如果存在则读取该term_tree_node下的下一级子节点（term_tree_node.parent_node_id=term_tree_node_id）
4. 为每个子节点构造一个classifier_value

作者: AI Assistant
创建时间: 2025年9月20日
"""

import sys
import os
import logging
import json
import argparse
from typing import Optional, List, Dict, Any
from datetime import datetime
from deepsearcher.api.rbase_util.sync.metadata import load_concept_by_id
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from deepsearcher.api.rbase_util import load_classifier_by_id
from fix_incomplete_concepts import ConceptFixer

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from deepsearcher.rbase.ai_models import (
    Classifier, ClassifierStatus,
    ClassifyMethod, ClassifierValueIsLabel
)
from deepsearcher.rbase.terms import Concept

class ClassifierValueBuilder:
    """构造classifier_value数据的类"""
    
    def __init__(self, config: Configuration):
        """初始化数据库连接"""
        self.connection = None
        self.config = config
        self._init_db_connection()
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise
    
    def _ensure_db_connection(self):
        """确保数据库连接有效，如果断开则重连"""
        try:
            if self.connection:
                self.connection.ping(reconnect=True)
        except Exception as e:
            from deepsearcher.tools.log import warning
            warning(f"数据库连接失效，尝试重连: {e}")
            try:
                self._init_db_connection()
            except Exception as reconnect_error:
                error(f"数据库重连失败: {reconnect_error}")
                raise
    
    def get_classifier_by_id(self, classifier_id: int) -> Optional[Classifier]:
        """
        根据classifier_id获取分类器信息
        
        Args:
            classifier_id: 分类器ID
            
        Returns:
            Classifier对象，如果不存在返回None
        """
        try:
            classifier = load_classifier_by_id(classifier_id)
            if classifier:
                return classifier
            else:
                info(f"未找到ID为 {classifier_id} 的有效分类器")
                return None
        except Exception as e:
            error(f"获取分类器信息失败: {e}")
            return None
    
    def validate_term_tree_references(self, classifier: Classifier) -> bool:
        """
        验证分类器中的term_tree_id和term_tree_node_id是否存在
        
        Args:
            classifier: 分类器信息字典
            
        Returns:
            验证结果
        """
        term_tree_id = classifier.term_tree_id
        term_tree_node_id = classifier.term_tree_node_id
        
        if not term_tree_id or not term_tree_node_id:
            info(f"分类器缺少必要的term_tree_id或term_tree_node_id: "
                  f"term_tree_id={term_tree_id}, term_tree_node_id={term_tree_node_id}")
            return False
        
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                # 验证term_tree是否存在
                cursor.execute(
                    "SELECT id FROM term_tree WHERE id = %s AND status = 1",
                    (term_tree_id,)
                )
                if not cursor.fetchone():
                    info(f"term_tree_id {term_tree_id} 不存在或状态无效")
                    return False
                
                # 验证term_tree_node是否存在
                cursor.execute(
                    "SELECT id, tree_id FROM term_tree_node WHERE id = %s AND status = 1",
                    (term_tree_node_id,)
                )
                node_result = cursor.fetchone()
                if not node_result:
                    info(f"term_tree_node_id {term_tree_node_id} 不存在或状态无效")
                    return False
                
                # 验证节点是否属于指定的term_tree
                if node_result['tree_id'] != term_tree_id:
                    info(f"term_tree_node_id {term_tree_node_id} 不属于 term_tree_id {term_tree_id}")
                    return False
                
                info(f"term_tree_id和term_tree_node_id验证通过")
                return True
                
        except Exception as e:
            error(f"验证term_tree引用失败: {e}")
            return False
    
    def get_child_nodes(self, term_tree_node_id: int, allow_category_node: bool = False, is_include_sub_value = False) -> List[Dict[str, Any]]:
        """
        获取指定节点的所有子节点
        
        Args:
            term_tree_node_id: 父节点ID
            allow_category_node: 是否允许分类节点
        Returns:
            子节点列表
        """
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, tree_id, parent_node_id, node_concept_id, node_concept_name, 
                       intro, sequence, children_count, is_category_node, status
                FROM term_tree_node 
                WHERE parent_node_id = %s AND status = 1
                ORDER BY sequence ASC, id ASC
                """
                cursor.execute(sql, (term_tree_node_id,))
                results = []
                nodes = cursor.fetchall()
                for node in nodes:
                    if not allow_category_node and node['is_category_node']:
                        child_nodes = self.get_child_nodes(node['id'], allow_category_node, is_include_sub_value)
                        results.extend(child_nodes)
                    else:
                        results.append(node)
                        if is_include_sub_value:
                            child_nodes = self.get_child_nodes(node['id'], allow_category_node, False)
                            results.extend(child_nodes)
                
                debug(f"找到 {len(results)} 个子节点")
                return results
                
        except Exception as e:
            error(f"获取子节点失败: {e}")
            return []
    
    def get_concept_info(self, concept_id: int) -> Optional[Dict[str, Any]]:
        """
        获取概念信息
        
        Args:
            concept_id: 概念ID
            
        Returns:
            概念信息字典
        """
        if not concept_id:
            return None
            
        try:
            self._ensure_db_connection()
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, name, cname, abbr_name, abbr_cname, intro,
                    concept_term_id, concept_term_id2, concept_term_id3,
                    is_virtual, is_preferred_concept, preferred_concept_id,
                    concept_relation, status, related_article_count, widely_related_article_count,
                    created, modified
                FROM concept 
                WHERE id = %s AND status >= 1
                """
                cursor.execute(sql, (concept_id,))
                return cursor.fetchone()
                
        except Exception as e:
            print(f"获取概念信息失败: {e}")
            return None
    
    def create_classifier_value(self, classifier: Classifier, child_node: Dict[str, Any], 
                               parent_classifier_value_id: Optional[int] = None,
                               is_update: bool = False) -> Optional[int]:
        """
        为子节点创建classifier_value记录
        
        Args:
            classifier: 分类器信息
            child_node: 子节点信息
            parent_classifier_value_id: 父classifier_value的ID（递归模式下使用）
            is_update: 是否更新已存在的classifier_value
            
        Returns:
            创建成功返回classifier_value的ID，失败返回None
        """
        try:
            self._ensure_db_connection()
            fixer = ConceptFixer(self.config, configuration.academic_translator, 
                                 configuration.llm, configuration.reasoning_llm)
            
            # 获取概念信息
            concept = load_concept_by_id(child_node.get('node_concept_id'))
            if concept:
                if not concept.is_complete() or not fixer.is_concept_intro_useful(concept):
                    if fixer.fix_concept(concept.id, create_intro=True):
                        info(f"概念信息不完整，已修复: {concept.name} / {concept.cname}")
                    else:
                        error(f"概念信息不完整，修复失败: {concept.name} / {concept.cname}")
                        return None

                    concept = load_concept_by_id(concept.id)

                if classifier.classify_method == ClassifyMethod.GENERAL_CLASSIFICATION:
                    # 分类器优先使用中文名称，如果没有则使用英文名称
                    value = concept.cname or concept.name or child_node.get('node_concept_name', '')
                    alias = concept.name or concept.cname or ''
                elif classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING:
                    # 命名实体匹配优先使用英文名称，如果没有则使用中文名称
                    value = concept.name or concept.cname or child_node.get('node_concept_name', '')
                    alias = concept.name or concept.cname or ''
            else:
                value = child_node.get('node_concept_name', '')
                alias = value

            if not concept:
                raise ValueError(f"概念信息不存在: {child_node['node_concept_name']}")
            
            # 构造国际化取值
            value_i18n = self._build_value_i18n(concept, value)
            
            # 构造value_clue（分类依据）
            value_clue = ''
            if classifier.classify_method == ClassifyMethod.GENERAL_CLASSIFICATION:
                if child_node.get('intro'):
                    value_clue = child_node['intro'][:1000]
                elif concept and concept.intro:
                    value_clue = concept.intro[:1000]
            else:
                if concept and concept.intro:
                    value_clue = concept.intro[:1000]
                elif child_node.get('intro'):
                    value_clue = child_node['intro'][:1000]
            
            with self.connection.cursor() as cursor:
                # 检查是否已存在相同的classifier_value
                check_sql = """
                SELECT id FROM classifier_value 
                WHERE classifier_id = %s AND term_tree_node_id = %s
                """
                cursor.execute(check_sql, (classifier.id, child_node['id']))
                existing = cursor.fetchone()
                
                if existing:
                    if is_update:
                        sql, sql_params = self._update_classify_value_sql(existing['id'], concept, child_node, 
                                                                      value=value, value_i18n=value_i18n, value_clue=value_clue, 
                                                                      alias=alias, parent_id=parent_classifier_value_id)
                        cursor.execute(sql, sql_params)
                        self.connection.commit()
                        info(f"成功更新classifier_value: {value} (ID: {existing['id']}, 节点ID: {child_node['id']})")
                        return existing['id']
                    else:
                        info(f"classifier_value已存在，跳过节点: {child_node['node_concept_name']} (ID: {child_node['id']})")
                        return existing['id']
                
                sql, sql_params = self._insert_new_classify_value_sql(classifier, concept, child_node, 
                                                value=value, value_i18n=value_i18n, value_clue=value_clue, 
                                                alias=alias, parent_id=parent_classifier_value_id)
                cursor.execute(sql, sql_params)
                self.connection.commit()
                
                # 获取新插入记录的ID
                classifier_value_id = cursor.lastrowid
                
                parent_info = f"，父ID: {parent_classifier_value_id}" if parent_classifier_value_id else ""
                info(f"成功创建classifier_value: {value} (ID: {classifier_value_id}, 节点ID: {child_node['id']}{parent_info})")
                return classifier_value_id
                
        except Exception as e:
            error(f"创建classifier_value失败: {e}")
            try:
                if self.connection:
                    self.connection.rollback()
            except Exception as rollback_error:
                error(f"回滚失败: {rollback_error}")
            return None

    def _build_value_i18n(self, concept: Concept, value: str) -> dict:
        # 构造国际化取值
        value_i18n = {}
        if concept.name:
            value_i18n['en'] = concept.name
        if concept.cname:
            value_i18n['zh'] = concept.cname
        if concept.abbr_name:
            value_i18n['en_abbr'] = concept.abbr_name
        if concept.abbr_cname:
            value_i18n['zh_abbr'] = concept.abbr_cname

        if not value_i18n:
            value_i18n = {'default': value}
        return value_i18n
    
    def _insert_new_classify_value_sql(self, classifier: Classifier, concept: Concept, child_node: dict, value: str, value_i18n: dict, value_clue: str, alias: str, parent_id: Optional[int]) -> (str, list):
        # 插入新的classifier_value记录
        insert_sql = """
        INSERT INTO classifier_value (
            classifier_id, value, value_i18n, value_clue, value_rule, 
            code, alias, priority, parent_id, term_tree_node_id, 
            concept_id, term_id, exclusive_with, is_label, status, remark
        ) VALUES (
            %s, %s, %s, %s, %s, 
            %s, %s, %s, %s, %s, 
            %s, %s, %s, %s, %s, %s
        )
        """
        
        values = (
            classifier.id,                              # classifier_id
            value,                                      # value
            json.dumps(value_i18n, ensure_ascii=False), # value_i18n
            value_clue,                                 # value_clue
            '',                                         # value_rule
            None,                                       # code
            alias,                                      # alias
            0,                                          # priority
            parent_id,                                  # parent_id
            child_node.get('id', 0),                    # term_tree_node_id
            concept.id,                                 # concept_id
            concept.concept_term_id,                    # term_id
            '',                                         # exclusive_with
            ClassifierValueIsLabel.YES.value,           # is_label
            ClassifierStatus.NORMAL.value,              # status
            f"从term_tree_node自动生成，节点ID: {child_node['id']}"  # remark
        )
        
        return insert_sql, values

    def _update_classify_value_sql(self, classifier_value_id: int, concept: Concept, child_node: dict, value: str, value_i18n: dict, value_clue: str, alias: str, parent_id: Optional[int]) -> (str, list):
        # 更新classifier_value记录
        update_sql = """
        UPDATE classifier_value SET
            value = %s,
            value_i18n = %s,
            value_clue = %s,
            alias = %s,
            parent_id = %s,
            term_tree_node_id = %s,
            concept_id = %s,
            term_id = %s,
            remark = %s
        WHERE id = %s
        """
        values = (
            value,                                      # value
            json.dumps(value_i18n, ensure_ascii=False), # value_i18n
            value_clue,                                 # value_clue
            alias,                                      # alias
            parent_id,                                  # parent_id
            child_node.get('id', 0),                    # term_tree_node_id
            concept.id,                                 # concept_id
            concept.concept_term_id,                    # term_id
            f"从term_tree_node自动更新，节点ID: {child_node['id']}",  # remark
            classifier_value_id,                        # id
        )
        return update_sql, values
    
    def build_classifier_values_recursive(self, classifier: Classifier, parent_node_id: int, 
                                         success_count: List[int], total_count: List[int],
                                         parent_classifier_value_id: Optional[int] = None,
                                         is_update: bool = False) -> bool:
        """
        递归地为指定节点的所有后代节点创建classifier_value数据
        
        Args:
            classifier: 分类器信息
            parent_node_id: 父term_tree_node的ID
            success_count: 成功计数（使用列表以便在递归中修改）
            total_count: 总数计数（使用列表以便在递归中修改）
            parent_classifier_value_id: 父classifier_value的ID（用于建立父子关系）
            is_update: 是否更新已存在的classifier_value
            
        Returns:
            构建是否成功
        """
        # 获取子节点
        child_nodes = self.get_child_nodes(parent_node_id)
        if not child_nodes:
            return True
        
        # 为每个子节点创建classifier_value
        for child_node in child_nodes:
            total_count[0] += 1
            # 创建当前节点的classifier_value，并获取其ID
            current_classifier_value_id = self.create_classifier_value(
                classifier, 
                child_node, 
                parent_classifier_value_id,
                is_update
            )
            
            if current_classifier_value_id:
                success_count[0] += 1
                
                # 递归处理子节点的子节点，将当前classifier_value的ID作为parent_id传递
                self.build_classifier_values_recursive(
                    classifier, 
                    child_node['id'], 
                    success_count, 
                    total_count,
                    current_classifier_value_id, # 传递当前创建的classifier_value的ID
                    is_update=is_update
                )
        
        return True
    
    def build_classifier_values(self, classifier_id: int, recursive: bool = False, is_update: bool = False) -> bool:
        """
        为指定分类器构建所有classifier_value数据
        
        Args:
            classifier_id: 分类器ID
            recursive: 是否递归处理所有后代节点（直到叶节点）
            is_update: 是否更新已存在的classifier_value
            
        Returns:
            构建是否成功
        """
        color_print(f"开始为分类器 {classifier_id} 构建classifier_value数据...")
        if recursive:
            info("启用递归模式，将处理所有后代节点直到叶节点")
        
        # 1. 获取分类器信息
        classifier = self.get_classifier_by_id(classifier_id)
        if not classifier:
            return False
        
        # 2. 验证term_tree_id和term_tree_node_id
        if not self.validate_term_tree_references(classifier):
            return False
        
        # 3. 根据是否递归，选择不同的处理方式
        if recursive:
            # 递归模式：处理所有后代节点
            success_count = [0]  # 使用列表以便在递归中修改
            total_count = [0]
            
            self.build_classifier_values_recursive(
                classifier, 
                classifier.term_tree_node_id,
                success_count, 
                total_count,
                is_update=is_update
            )
            
            if total_count[0] == 0:
                info("未找到子节点，构建完成")
                return True
            
            info(f"构建完成: 成功 {success_count[0]}/{total_count[0]} 个classifier_value")
            return success_count[0] == total_count[0]
        else:
            # 非递归模式：只处理直接子节点
            child_nodes = self.get_child_nodes(classifier.term_tree_node_id, is_include_sub_value=classifier.is_include_sub_value)
            if not child_nodes:
                info("未找到子节点，构建完成")
                return True
            
            success_count = 0
            total_count = len(child_nodes)
            
            create_results = {}
            for child_node in child_nodes:
                # 非递归模式下，parent_id为None
                parent_id = create_results.get(f"{child_node['parent_node_id']}")
                classifier_value_id = self.create_classifier_value(classifier, child_node, parent_id, is_update)
                if classifier_value_id:
                    create_results[f"{child_node['id']}"] = classifier_value_id
                    success_count += 1
            
            info(f"构建完成: 成功 {success_count}/{total_count} 个classifier_value")
            return success_count == total_count
    
    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()
            debug("数据库连接已关闭")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='根据classifier_id构造classifier_value数据')
    parser.add_argument('-c', '--classifier_id', type=int, help='分类器ID')
    parser.add_argument('-r', '--recursive', action='store_true', 
                       help='递归处理所有后代节点直到叶节点（默认只处理直接子节点）')
    parser.add_argument('-u', '--update', action='store_true', help='更新已存在的classifier_value')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        debug(f"分类器ID: {args.classifier_id}")
        debug(f"递归模式: {args.recursive}")
        debug("-" * 50)

    # 初始化配置
    init_rbase_config()
    
    builder = None
    try:
        builder = ClassifierValueBuilder(configuration.config)
        success = builder.build_classifier_values(args.classifier_id, args.recursive, args.update)
        
        if success:
            color_print("\n✅ classifier_value构建成功!")
            return 0
        else:
            error("\n❌ classifier_value构建失败!")
            return 1
            
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        return 1
    finally:
        if builder:
            builder.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())
