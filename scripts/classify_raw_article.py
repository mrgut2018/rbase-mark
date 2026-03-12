#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为指定的raw_article执行分类的脚本。

该脚本的执行流程：
1. 接收classifier_id和raw_article_id参数
2. 初始化配置和数据库连接
3. 从数据库加载raw_article数据
4. 初始化ClassifyAgent
5. 执行分类并打印结果

作者: AI Assistant
创建时间: 2025年9月23日
"""

import inflect
import logging
import os
import sys
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from deepsearcher.tools.log import color_print, info, debug, error, set_dev_mode, set_level
from deepsearcher.tools.json_util import safe_json_loads
from deepsearcher.tools import load_rbase_txt_file
from deepsearcher import configuration
from deepsearcher.configuration import Configuration, init_rbase_config
from deepsearcher.vector_db.base import BaseVectorDB
from deepsearcher.embedding.base import BaseEmbedding
from deepsearcher.agent.academic_translator import AcademicTranslator

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepsearcher.db.mysql_connection import get_mysql_connection, close_mysql_connection
from deepsearcher.rbase.raw_article import RawArticle
from deepsearcher.agent.classify_agent import ClassifyAgent, ClassifierPrerequisiteNotMetError, ClassifierConditions
from deepsearcher.rbase.ai_models import LabelRawArticleTaskStatus, ClassifyMethod, ClassifierValue, Classifier
from deepsearcher.api.rbase_util import (
    list_classifier_values_by_value,
    load_classifiers_by_ids,
    load_classifier_value_by_id,
    load_classifier_values_by_entity_name,
    load_classifier_value_by_concept_id,
    load_classifier_value_by_vector_db,
    load_classifier_values_by_vector_db,
    load_classifier_value_route,
    extract_entity_context,
    create_label_raw_article_task,
    create_label_raw_article_task_item,
    update_task_item_status,
    save_classification_result,
    update_task_status,
    concept_i18n_data,
    term_i18n_data,
    load_term_by_value,
    load_concept_by_id,
    check_classifier_prerequisite_values_in,
    check_classifier_prerequisite_status_in,
)


class RawArticleClassifier:
    """文章分类器类"""
    
    def __init__(self, config: Configuration, vector_db: BaseVectorDB, embedding_model: BaseEmbedding, translator: AcademicTranslator, **kwargs):
        """初始化"""
        self.config = config
        self.connection = None
        self.vector_db = vector_db
        self.embedding_model = embedding_model
        self.translator = translator
        self.inflect_engine = inflect.engine()
        self.input_token_price = kwargs.get('input_token_price', 0)
        self.output_token_price = kwargs.get('output_token_price', 0)

        self.env = config.rbase_settings.get('env')
        if self.env is None:
            self.env = kwargs.get('env', 'dev')
        if self.env != 'dev' and self.env != 'prod':
            error(f"环境 {self.env} 不支持")
            raise ValueError(f"环境 {self.env} 不支持")

        self.collection = kwargs.get('collection_name', 'classifier_value_entities')
        self.collection = f"{self.env}_{self.collection}"
        self._init_db_connection()
        self.classifier_result_cache = {}
        self.allow_use_cache = kwargs.get('allow_use_cache', True)
        # 全文缓存，避免重复加载
        self._article_full_text_cache = {}  # raw_article_id -> full_text
        # 实体名称DB匹配缓存，避免同一entity_name重复查询DB
        # key: (entity_name, classifier_id), value: list[ClassifierValue] or None
        self._entity_match_cache = {}
        # i18n翻译缓存，避免同一entity_name重复翻译
        # key: (entity_name, lang), value: Dict[str, str]
        self._i18n_cache = {}
        # 并行处理配置
        self._max_workers = kwargs.get('max_workers', 8)
        self._parallel = kwargs.get('parallel', True)
        self._cache_lock = threading.Lock()
    
    def _init_db_connection(self):
        """初始化数据库连接"""
        try:
            rbase_db_config = self.config.rbase_settings.get("database", {})
            self.connection = get_mysql_connection(rbase_db_config)
            info("数据库连接成功")
        except Exception as e:
            error(f"数据库连接失败: {e}")
            raise

    def _get_article_full_text(self, raw_article: RawArticle, classify_agent: ClassifyAgent) -> str:
        """
        获取文章全文，带缓存功能。

        Args:
            raw_article: 文章对象
            classify_agent: 分类代理（用于获取 file_loader 和 oss 配置）

        Returns:
            文章全文，如果无法加载则返回空字符串
        """
        if raw_article.id in self._article_full_text_cache:
            return self._article_full_text_cache[raw_article.id]

        full_text = ""
        if raw_article.txt_file and classify_agent.file_loader:
            try:
                oss_config = classify_agent.rbase_settings.get("oss", {})
                docs = load_rbase_txt_file(oss_config, raw_article.txt_file, classify_agent.file_loader,
                                           include_references=False,
                                           save_downloaded_file=True)
                full_text = "\n\n".join([doc.page_content for doc in docs])
                debug(f"已加载文章全文，长度: {len(full_text)}")
            except Exception as e:
                debug(f"加载文章全文失败: {e}")

        self._article_full_text_cache[raw_article.id] = full_text
        return full_text

    def _get_article_text_for_context(self, raw_article: RawArticle, classify_agent: ClassifyAgent) -> str:
        """
        获取用于上下文提取的文章文本。优先使用全文，其次使用标题+摘要。

        Args:
            raw_article: 文章对象
            classify_agent: 分类代理

        Returns:
            文章文本
        """
        full_text = self._get_article_full_text(raw_article, classify_agent)
        if full_text:
            return full_text
        return f"{raw_article.title or ''} {raw_article.summary or ''}"

    def _build_entity_query(self, entity_name: str, entity_full_name: Optional[str],
                            entity_type: Optional[str], entity_context: str) -> str:
        """
        构建用于向量搜索的 entity query。

        Args:
            entity_name: 实体名称
            entity_full_name: 实体全名（可选）
            entity_type: 实体类型（可选）
            entity_context: 实体上下文

        Returns:
            构建好的 query 字符串
        """
        # 判断 entity_type 是否有意义（包含 keywords 的类型没有实际意义）
        use_entity_type = entity_type and "keyword" not in entity_type.lower()

        # 构建实体名称部分
        if entity_full_name and entity_full_name.strip() and entity_full_name != entity_name:
            name_part = f"{entity_name} ({entity_full_name})"
        else:
            name_part = entity_name

        # 根据是否有上下文和类型构建 query
        if entity_context:
            if use_entity_type:
                return f"{name_part}, {entity_type}: {entity_context}"
            else:
                return f"{name_part}: {entity_context}"
        else:
            if use_entity_type:
                return f"{name_part}, which is a named entity in type of {entity_type}"
            else:
                return name_part

    def estimate_cost(self, usage: dict, classify_agent: ClassifyAgent) -> float:
        prompt_tokens = usage.get('prompt_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0)

        if self.input_token_price > 0 or self.output_token_price > 0:
            return prompt_tokens / 1000 * self.input_token_price \
                + completion_tokens / 1000 * self.output_token_price

        if hasattr(classify_agent.reasoning_llm, 'input_token_price') and hasattr(classify_agent.reasoning_llm, 'output_token_price'):
            return classify_agent.reasoning_llm.input_token_price * prompt_tokens / 1000 \
                + classify_agent.reasoning_llm.output_token_price * completion_tokens / 1000
        
        return 0

    def usage_with_cost(self, classify_agent: ClassifyAgent, cost_total: bool = False) -> dict:
        usage = classify_agent.totalUsage if cost_total else classify_agent.usage
        cost = self.estimate_cost(usage, classify_agent)
        return {
            "total_tokens": usage.get('total_tokens', 0),
            "prompt_tokens": usage.get('prompt_tokens', 0),
            "completion_tokens": usage.get('completion_tokens', 0),
            "cost": cost,
        }
    
    def load_raw_article_by_id(self, raw_article_id: int) -> Optional[RawArticle]:
        """
        根据raw_article_id从数据库加载文章数据
        
        Args:
            raw_article_id: 文章ID
            
        Returns:
            RawArticle对象，如果不存在返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                SELECT id, uuid, doi, pmid, pmcid, title, summary, journal_id, journal_name, 
                       impact_factor, pubdate, source_type, type, volume, issue, startpage,
                       source_keywords, mesh_keywords, authors, first_authors, corresponding_authors,
                       ctitle, csummary, summarize, keywords, human_keywords, categories,
                       pdf_file, txt_file, source_url, is_open_access, has_zhiku, 
                       chosen_count, status, created, modified
                FROM raw_article 
                WHERE id = %s AND status <> 0
                """
                cursor.execute(sql, (raw_article_id,))
                result = cursor.fetchone()
                
                if result:
                    info(f"找到文章: {result['title'][:50]}... (ID: {result['id']})")
                    # 将数据库结果转换为RawArticle对象
                    raw_article = RawArticle(
                        raw_article_data=result
                    )
                    return raw_article
                else:
                    error(f"未找到ID为 {raw_article_id} 的文章")
                    return None
                    
        except Exception as e:
            error(f"加载文章信息失败: {e}")
            return None
    
    def load_classifier_ids_by_group(self, classifier_group_id: int) -> Tuple[List[int], Dict[int, List[int]], str]:
        """
        根据classifier_group_id从数据库加载分类器ID列表
        
        Args:
            classifier_group_id: 分类器分组ID
            
        Returns:
            分类器ID列表，分类器组名称
        """
        try:
            with self.connection.cursor() as cursor:
                # 首先验证分组是否存在
                cursor.execute(
                    "SELECT id, name, `desc`, `status` FROM classifier_group WHERE id = %s AND status <> 0",
                    (classifier_group_id,)
                )
                group_result = cursor.fetchone()
                if not group_result:
                    error(f"分类器分组ID {classifier_group_id} 不存在或状态无效")
                    return [], {}, ""
                
                debug(f"找到分类器分组: {group_result['name']}(状态{group_result['status']}) - {group_result['desc']}")
                
                # 加载分组中的分类器，按seq升序、id升序排列
                sql = """SELECT cgr.classifier_id, cgr.seq, cgr.merge_with_classifier_id, c.name, c.alias
                FROM classifier_group_relation cgr
                    INNER JOIN classifier c ON cgr.classifier_id = c.id
                WHERE cgr.classifier_group_id = %s AND c.status = 1
                ORDER BY cgr.seq ASC, cgr.classifier_id ASC
                """
                cursor.execute(sql, (classifier_group_id,))
                results = cursor.fetchall()
                
                if not results:
                    error(f"分类器分组 {classifier_group_id} 中没有有效的分类器")
                    return [], {}, group_result['name']
                
                classifier_ids = []
                sub_classifiers = {}
                debug(f"分组中包含 {len(results)} 个分类器:")
                for result in results:
                    classifier_ids.append(result['classifier_id'])
                    if result['merge_with_classifier_id'] is not None:
                        if result['merge_with_classifier_id'] not in sub_classifiers:
                            sub_classifiers[result['merge_with_classifier_id']] = []
                        sub_classifiers[result['merge_with_classifier_id']].append(result['classifier_id'])
                        debug(f"  - ID: {result['classifier_id']}, 名称: {result['name']} ({result['alias']}, 合并到分类器:{result['merge_with_classifier_id']})")
                
                return classifier_ids, sub_classifiers, group_result['name']
                
        except Exception as e:
            error(f"加载分类器分组失败: {e}")
            return [], {}, ""
    
    def init_classify_agent(self) -> ClassifyAgent:
        """
        初始化分类代理
        
        Returns:
            ClassifyAgent对象
        """
        try:
            # 使用全局配置初始化的组件
            classify_agent = ClassifyAgent(
                llm=configuration.writing_llm,
                reasoning_llm=configuration.reasoning_llm,
                embedding_model=configuration.embedding_model,
                vector_db=configuration.vector_db,
                file_loader=configuration.file_loader,
                rbase_settings=self.config.rbase_settings
            )
            info("分类代理初始化成功")
            return classify_agent
        except Exception as e:
            error(f"分类代理初始化失败: {e}")
            raise
    
    def invoke_classify_agent_classify(self, classifier_id: int, raw_article: RawArticle, classify_agent: ClassifyAgent, sub_classifier_ids: Optional[List[int]] = None, task_id: Optional[int] = None) -> str:
        """
        为文章执行单个分类器的分类
        
        Args:
            classifier_id: 分类器ID
            raw_article: 文章对象
            classify_agent: 分类代理
            
        Returns:
            分类结果
        """
        if sub_classifier_ids is None:
            info(f"开始分类 classifier_id={classifier_id}, raw_article_id={raw_article.id} ")
            result = classify_agent.classify(classifier_id, 
                                             raw_article, 
                                             result_cache=self.classifier_result_cache, 
                                             allow_use_cache=self.allow_use_cache, 
                                             task_id=task_id)
            info(f"分类完成 classifier_id={classifier_id}, raw_article_id={raw_article.id} ")
        else:
            info(f"开始合并分类 classifier_id={classifier_id} 合并ID: {sub_classifier_ids}")
            result = classify_agent.merged_classsify([classifier_id] + sub_classifier_ids, 
                                                     raw_article, 
                                                     task_id=task_id)
            info(f"合并分类完成 classifier_id={classifier_id}, raw_article_id={raw_article.id} ")
        return result

    def invoke_classify_agent_recheck(self, classifier_id: int, raw_article: RawArticle, classifier_values: List[ClassifierValue], classify_agent: ClassifyAgent, location: int) -> str:
        """
        旧版 recheck 方法（保留兼容性）

        Args:
            classifier_values: 分类器值列表
            classify_agent: 分类代理

        Returns:
            分类结果
        """
        if len(classifier_values) <= 0:
            return "[]"

        routes = []
        for classifier_value in classifier_values:
            route = load_classifier_value_route(classifier_value)
            routes.append(route)
        info(f"开始执行分类器 {classifier_id} 的分类重新检查...")
        result = classify_agent.classify(classifier_id, raw_article,
                                         classifier_value=classifier_values[0],
                                         entity_recheck=True,
                                         value_routes=routes,
                                         is_need_full_text=location==1)
        info(f"分类器 {classifier_id} 分类重新检查完成！")
        return result

    def invoke_classify_agent_recheck_with_candidates(self, classifier_id: int, raw_article: RawArticle,
                                                       candidates: list, entity_name: str,
                                                       classify_agent: ClassifyAgent) -> str:
        """
        新版 recheck 方法：基于多候选和上下文进行 recheck

        Args:
            classifier_id: 分类器 ID
            raw_article: 文章对象
            candidates: 候选列表 [(ClassifierValue, score, is_exact), ...]
            entity_name: 提取的实体名称
            classify_agent: 分类代理

        Returns:
            JSON 格式的分类结果
        """
        if not candidates:
            return "[]"

        info(f"开始执行分类器 {classifier_id} 的多候选重新检查（{len(candidates)}个候选）...")
        # 上下文提取已移至 classify_agent 内部，会尝试从全文中提取
        result = classify_agent.classify(classifier_id, raw_article,
                                         entity_recheck=True,
                                         candidates=candidates,
                                         entity_name=entity_name)
        info(f"分类器 {classifier_id} 多候选重新检查完成！")
        return result

    def _create_task_items(
        self,
        task_id: int,
        classifier_ids: List[int],
        classifiers_cache: Dict[int, Classifier],
        classify_agent: ClassifyAgent
    ) -> Dict[int, int]:
        """
        为每个分类器批量创建任务项

        Args:
            task_id: 任务ID
            classifier_ids: 分类器ID列表
            classifiers_cache: 分类器缓存字典
            classify_agent: 分类代理

        Returns:
            Dict[int, int]: classifier_id -> task_item_id 的映射
        """
        if not classifier_ids:
            return {}

        import json as _json

        # 准备批量插入数据
        now = datetime.now()
        rows = []  # (cid, values_tuple)
        for cid in classifier_ids:
            classifier = classifiers_cache.get(cid)
            if not classifier:
                continue

            if classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING:
                reasoning_llm = configuration.lctx_reasoning_llm
            else:
                reasoning_llm = configuration.reasoning_llm

            script_params = {
                "reasoning_llm_model": reasoning_llm.model,
                "reasoning_llm_enable_thinking": reasoning_llm.enable_thinking,
                "reasoning_llm_verbose": reasoning_llm.verbose,
                "reasoning_llm_max_tokens": reasoning_llm.max_tokens,
                "reasoning_llm_input_token_price": reasoning_llm.input_token_price,
                "reasoning_llm_output_token_price": reasoning_llm.output_token_price,
            }

            rows.append((cid, (
                task_id,
                classifier.term_tree_id,
                classifier.term_tree_node_id,
                classifier.name,
                cid,
                classifier.ver,
                _json.dumps(script_params),
                LabelRawArticleTaskStatus.PENDING.value,
                now,
                now,
            )))

        if not rows:
            return {}

        # 批量插入（需要逐条execute以获取每行lastrowid，但共享连接和单次commit）
        task_items = {}
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        try:
            with connection.cursor() as cursor:
                sql = """
                INSERT INTO label_raw_article_task_item (
                    label_raw_article_task_id, term_tree_id, term_tree_node_id,
                    label_item_key, classifier_id, classifier_ver, script_params, status,
                    created, modified
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                for cid, values in rows:
                    cursor.execute(sql, values)
                    task_items[cid] = cursor.lastrowid
                    debug(f"创建任务项: 分类器{cid} -> 任务项{task_items[cid]}")
                connection.commit()
        except Exception as e:
            connection.rollback()
            raise Exception(f"Failed to batch create task items: {e}")

        return task_items

    def _batch_create_cancelled_task_items(
        self,
        task_id: int,
        skipped_ids: List[int],
        classifiers_cache: Dict[int, Classifier],
    ) -> Dict[int, int]:
        """
        为跳过的分类器批量创建CANCELLED状态的任务项

        Args:
            task_id: 任务ID
            skipped_ids: 被跳过的分类器ID列表
            classifiers_cache: 分类器缓存

        Returns:
            Dict[int, int]: classifier_id -> task_item_id 的映射
        """
        if not skipped_ids:
            return {}

        task_items = {}
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        try:
            with connection.cursor() as cursor:
                now = datetime.now()
                sql = """
                INSERT INTO label_raw_article_task_item (
                    label_raw_article_task_id, term_tree_id, term_tree_node_id,
                    label_item_key, classifier_id, classifier_ver, script_params, status,
                    created, modified
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                for cid in skipped_ids:
                    classifier = classifiers_cache.get(cid)
                    if not classifier:
                        continue
                    values = (
                        task_id,
                        classifier.term_tree_id,
                        classifier.term_tree_node_id,
                        classifier.name,
                        cid,
                        classifier.ver,
                        None,
                        LabelRawArticleTaskStatus.CANCELLED.value,
                        now,
                        now,
                    )
                    cursor.execute(sql, values)
                    task_items[cid] = cursor.lastrowid
                    debug(f"创建跳过任务项: 分类器{cid} -> 任务项{task_items[cid]} (CANCELLED)")
                connection.commit()
        except Exception as e:
            connection.rollback()
            error(f"批量创建CANCELLED任务项失败: {e}")

        return task_items

    def _pre_filter_classifiers(
        self,
        classifier_ids: List[int],
        classifiers_cache: Dict[int, Classifier],
        raw_article_id: int,
        task_id: Optional[int] = None,
    ) -> Tuple[List[int], List[int]]:
        """
        在主循环前批量检查前置条件，将不满足条件的分类器预先排除。

        对于前置条件中引用同组内分类器的规则，跳过检查（运行时会满足）。
        只检查引用组外分类器的规则。

        Args:
            classifier_ids: 分类器ID列表
            classifiers_cache: 分类器缓存
            raw_article_id: 文章ID
            task_id: 任务ID（可选）

        Returns:
            Tuple[List[int], List[int]]: (eligible_ids, skipped_ids)
        """
        # 构建组内分类器alias集合
        group_aliases = set()
        for cid in classifier_ids:
            classifier = classifiers_cache.get(cid)
            if classifier:
                group_aliases.add(classifier.alias)

        eligible_ids = []
        skipped_ids = []

        for cid in classifier_ids:
            classifier = classifiers_cache.get(cid)
            if not classifier:
                skipped_ids.append(cid)
                continue

            if not classifier.prerequisite:
                eligible_ids.append(cid)
                continue

            # 检查每个前置条件规则
            is_eligible = True
            for rule in classifier.prerequisite:
                classifier_alias = rule.get('classifier_alias', '')
                value_in = rule.get('value_in', None)
                status_in = rule.get('status_in', None)

                if not classifier_alias or (not value_in and not status_in):
                    is_eligible = False
                    break

                # 如果前置条件引用的是组内分类器，跳过检查（运行时会处理）
                if classifier_alias in group_aliases:
                    continue

                # 检查组外前置条件
                if value_in and not check_classifier_prerequisite_values_in(
                    raw_article_id, classifier_alias, value_in, task_id
                ):
                    is_eligible = False
                    break

                if status_in and not check_classifier_prerequisite_status_in(
                    raw_article_id, classifier_alias, status_in, task_id
                ):
                    is_eligible = False
                    break

            if is_eligible:
                eligible_ids.append(cid)
            else:
                skipped_ids.append(cid)
                debug(f"预过滤: 分类器 {cid}({classifier.alias}) 前置条件不满足，跳过")

        info(f"前置条件预过滤: {len(eligible_ids)}/{len(classifier_ids)} 通过, "
             f"{len(skipped_ids)} 跳过")
        return eligible_ids, skipped_ids

    def _dynamic_merge_general_classifiers(
        self,
        eligible_ids: List[int],
        classifiers_cache: Dict[int, Classifier],
        sub_classifiers: Dict[int, List[int]],
        raw_article: RawArticle,
        classify_agent: ClassifyAgent,
        task_id: int,
    ) -> None:
        """
        找出独立的 GENERAL_CLASSIFICATION 分类器，动态合并为一次 LLM 调用。

        合并结果会写入 classifier_result_cache，后续主循环中这些分类器
        会从缓存读取结果，跳过 LLM 调用。

        条件：
        - classify_method == GENERAL_CLASSIFICATION
        - 不是已有合并组的子分类器（不在 sub_classifiers 的 values 中）
        - 不是已有合并组的父分类器（不在 sub_classifiers 的 keys 中）

        Args:
            eligible_ids: 通过预过滤的分类器ID列表
            classifiers_cache: 分类器缓存
            sub_classifiers: 已有的合并关系映射
            raw_article: 文章对象
            classify_agent: 分类代理
            task_id: 任务ID
        """
        # 收集已在合并组中的分类器ID
        already_merged = set(sub_classifiers.keys())
        for children in sub_classifiers.values():
            already_merged.update(children)

        # 构建组内分类器alias集合（用于排除有组内前置条件的分类器）
        group_aliases = set()
        for cid in eligible_ids:
            classifier = classifiers_cache.get(cid)
            if classifier:
                group_aliases.add(classifier.alias)

        # 找出可动态合并的候选
        # 排除：已在合并组中的、非GENERAL_CLASSIFICATION的、有组内前置条件的
        merge_candidates = []
        for cid in eligible_ids:
            if cid in already_merged:
                continue
            classifier = classifiers_cache.get(cid)
            if not classifier or classifier.classify_method != ClassifyMethod.GENERAL_CLASSIFICATION:
                continue
            # 有组内前置条件的分类器不能在主循环前合并（依赖的结果还不存在）
            if classifier.prerequisite:
                has_intra_group_dep = False
                for rule in classifier.prerequisite:
                    dep_alias = rule.get('classifier_alias', '')
                    if dep_alias in group_aliases:
                        has_intra_group_dep = True
                        break
                if has_intra_group_dep:
                    continue
            merge_candidates.append(cid)

        if len(merge_candidates) < 2:
            return

        info(f"动态合并 {len(merge_candidates)} 个独立 GENERAL_CLASSIFICATION 分类器: {merge_candidates}")

        try:
            classify_agent.setReasoningLLM(configuration.reasoning_llm)
            result = classify_agent.merged_classsify(
                merge_candidates, raw_article, task_id=task_id, skip_prerequisite=True)
            if result:
                result_items = safe_json_loads(result)
                if isinstance(result_items, list):
                    for item in result_items:
                        alias = item.get('classifier_alias', '')
                        if alias:
                            if alias not in self.classifier_result_cache:
                                self.classifier_result_cache[alias] = []
                            self.classifier_result_cache[alias].append(item)
                    info(f"动态合并完成，缓存了 {len(result_items)} 条结果")
                else:
                    error(f"动态合并结果格式异常: {result}")
        except Exception as e:
            error(f"动态合并执行失败，将回退到逐个执行: {e}")

    def _process_classification_results(
        self,
        task_id: int,
        task_item_id: int,
        classifier: Classifier,
        result: str,
        classify_agent: ClassifyAgent,
        raw_article: RawArticle
    ) -> bool:
        """
        处理并保存分类结果

        Args:
            task_id: 任务ID
            task_item_id: 任务项ID
            classifier: 分类器
            result: 分类结果JSON字符串
            classify_agent: 分类代理
            raw_article: 文章对象

        Returns:
            bool: 处理是否成功
        """
        try:
            classification_results = safe_json_loads(result)
            if not isinstance(classification_results, list):
                classification_results = [classification_results]

            # 过滤已缓存的结果
            items_to_process = []
            for result_item in classification_results:
                if not self._add_classifier_result_cache(classifier, result_item):
                    items_to_process.append(result_item)

            if not items_to_process:
                return True

            if self._parallel and len(items_to_process) > 1:
                # 预加载全文缓存，避免多线程同时加载同一文件
                self._get_article_text_for_context(raw_article, classify_agent)
                self._process_items_parallel(
                    items_to_process, task_id, task_item_id,
                    classifier, classify_agent, raw_article)
            else:
                self._process_items_serial(
                    items_to_process, task_id, task_item_id,
                    classifier, classify_agent, raw_article)

            return True
        except Exception as e:
            error(f"解析分类结果失败: {e}, 原始结果: {result}")
            raise e

    def _process_single_item(
        self, result_item: Dict[str, Any], task_id: int, task_item_id: int,
        classifier: Classifier, classify_agent: ClassifyAgent,
        raw_article: RawArticle
    ) -> None:
        """处理单个分类结果项（解析+保存），可在线程中安全调用"""
        label_item_key, classifier_value, classifier_values, location, \
            entity_name, entity_full_name, language, result_metadata = \
            self._parse_classify_result(
                classifier, result_item, classify_agent, raw_article)

        saved = self._save_classification_result(
            task_id, task_item_id=task_item_id,
            label_item_key=label_item_key,
            classifier=classifier,
            classifier_value=classifier_value,
            classifier_values=classifier_values,
            location=location,
            entity_name=entity_name,
            entity_full_name=entity_full_name,
            language=language,
            classify_agent=classify_agent,
            result_metadata=result_metadata)

        if saved:
            if len(classifier_values) > 0:
                for cv in classifier_values:
                    info(f"保存词表结果成功: {label_item_key} -> {cv.value}")
            else:
                if classifier_value:
                    info(f"保存词表结果成功: {label_item_key} -> {classifier_value.value}")
                else:
                    info(f"未匹配词表保存实体结果成功: {label_item_key} -> {entity_name}")
        else:
            error(f"跳过无法获取有效的classify_value: {result_item}")

    def _process_items_serial(
        self, items: List[Dict[str, Any]], task_id: int, task_item_id: int,
        classifier: Classifier, classify_agent: ClassifyAgent,
        raw_article: RawArticle
    ) -> None:
        """串行处理分类结果项"""
        for result_item in items:
            self._process_single_item(
                result_item, task_id, task_item_id,
                classifier, classify_agent, raw_article)

    def _process_items_parallel(
        self, items: List[Dict[str, Any]], task_id: int, task_item_id: int,
        classifier: Classifier, classify_agent: ClassifyAgent,
        raw_article: RawArticle
    ) -> None:
        """并行处理分类结果项（ThreadPoolExecutor）"""
        workers = min(self._max_workers, len(items))
        info(f"并行处理 {len(items)} 个实体结果，workers={workers}")
        errors = []
        errors_lock = threading.Lock()

        def _worker(result_item: Dict[str, Any]) -> None:
            try:
                self._process_single_item(
                    result_item, task_id, task_item_id,
                    classifier, classify_agent, raw_article)
            except Exception as e:
                entity = result_item.get('entity_name', 'unknown')
                error(f"并行处理实体 {entity} 失败: {e}")
                with errors_lock:
                    errors.append((entity, e))
            finally:
                close_mysql_connection()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_worker, item) for item in items]
            for future in as_completed(futures):
                future.result()  # 触发异常传播（已在_worker内捕获）

        if errors:
            error(f"并行处理完成，{len(errors)}/{len(items)} 个实体处理失败")

    def _execute_single_classifier(
        self,
        cid: int,
        idx: int,
        total_count: int,
        raw_article: RawArticle,
        classify_agent: ClassifyAgent,
        classifiers_cache: Dict[int, Classifier],
        sub_classifiers: Dict[int, Any],
        task_id: int,
        task_items: Dict[int, int],
        cancel_history_results: bool,
        classifier_group_id: Optional[int]
    ) -> Dict[str, Any]:
        """
        执行单个分类器的分类

        Args:
            cid: 分类器ID
            idx: 当前索引
            total_count: 总数
            raw_article: 文章对象
            classify_agent: 分类代理
            classifiers_cache: 分类器缓存
            sub_classifiers: 子分类器映射
            task_id: 任务ID
            task_items: 任务项映射
            cancel_history_results: 是否取消历史结果
            classifier_group_id: 分类器组ID

        Returns:
            Dict[str, Any]: 包含 result, status, success 的结果字典
        """
        color_print(f"[{idx}/{total_count}] 执行分类器 {cid}")

        # 根据分类器类型切换 reasoning LLM
        classifier = classifiers_cache.get(cid)
        if classifier:
            if classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING:
                classify_agent.setReasoningLLM(configuration.lctx_reasoning_llm)
            else:
                classify_agent.setReasoningLLM(configuration.reasoning_llm)

        if cancel_history_results:
            self.cancel_history_results(cid, raw_article.id)

        if cid in task_items:
            update_task_item_status(task_items[cid], LabelRawArticleTaskStatus.RUNNING)

        try:
            result = self.invoke_classify_agent_classify(
                cid, raw_article, classify_agent, sub_classifiers.get(cid, None), task_id)

            if result:
                result_dict = {
                    "classifier_id": cid,
                    "result": result,
                    "status": "success",
                    "usage": classify_agent.usage,
                    "success": True
                }

                if cid in task_items:
                    classifier = classifiers_cache.get(cid)
                    if classifier:
                        self._process_classification_results(
                            task_id, task_items[cid], classifier, result, classify_agent, raw_article)
                        update_task_item_status(
                            task_items[cid], LabelRawArticleTaskStatus.COMPLETED,
                            self.usage_with_cost(classify_agent))

                return result_dict
            else:
                if cid in task_items:
                    update_task_item_status(task_items[cid], LabelRawArticleTaskStatus.UNEXPECTED_ERROR)
                return {
                    "classifier_id": cid,
                    "result": "",
                    "status": "failed",
                    "error": "分类结果为空",
                    "success": False
                }

        except ClassifierPrerequisiteNotMetError as e:
            info(f"分类器 {cid} 前置条件不满足，跳过执行。")
            if cid in task_items:
                update_task_item_status(task_items[cid], LabelRawArticleTaskStatus.CANCELLED)
            return {
                "classifier_id": cid,
                "result": "",
                "status": "skipped",
                "error": f"前置条件不满足: {str(e)}",
                "success": False
            }

        except Exception as e:
            error(f"分类器 {cid} 执行异常: {e}")
            if classifier_group_id and cid in task_items:
                update_task_item_status(task_items[cid], LabelRawArticleTaskStatus.UNEXPECTED_ERROR)
            return {
                "classifier_id": cid,
                "result": "",
                "status": "error",
                "error": str(e),
                "success": False
            }

    def classify_article(self, classifier_id: Optional[int], classifier_group_id: Optional[int], raw_article_id: int, base_id: Optional[int] = None, cancel_history_results: bool = False) -> Dict[str, Any]:
        """
        为文章执行分类

        Args:
            classifier_id: 分类器ID（可选）
            classifier_group_id: 分类器分组ID（可选）
            raw_article_id: 文章ID
            base_id: 用户库ID（可选）
            cancel_history_results: 是否取消历史结果

        Returns:
            分类结果字典
        """
        if classifier_group_id:
            info(f"开始为文章 {raw_article_id} 执行分类器分组 {classifier_group_id} 的批量分类...")
        else:
            info(f"开始为文章 {raw_article_id} 执行分类器 {classifier_id} 的分类...")

        self._clear_classisifer_result_cache()

        # 1. 加载文章数据
        raw_article = self.load_raw_article_by_id(raw_article_id)
        if not raw_article:
            error("文章加载失败")
            return {}

        # 2. 初始化分类代理
        classify_agent = self.init_classify_agent()

        # 3. 确定要执行的分类器列表
        if classifier_group_id:
            classifier_ids, sub_classifiers, classifier_group_name = self.load_classifier_ids_by_group(classifier_group_id)
            if not classifier_ids:
                error("无法加载分类器分组")
                return {}
        else:
            classifier_ids = [classifier_id]
            sub_classifiers = {}
            classifier_group_name = ""

        # 3.1 批量加载所有分类器（避免N+1查询）
        classifiers_cache = load_classifiers_by_ids(classifier_ids)
        if not classifiers_cache:
            error("无法加载分类器")
            return {}

        # 3.2 前置条件预过滤（仅分组模式，单分类器模式跳过）
        skipped_ids = []
        if classifier_group_id and len(classifier_ids) > 1:
            eligible_ids, skipped_ids = self._pre_filter_classifiers(
                classifier_ids, classifiers_cache, raw_article_id)
        else:
            eligible_ids = list(classifier_ids)

        # 4. 创建标注任务和任务项
        if classifier_group_id:
            task_desc = f"文章{raw_article_id}的分类器组{classifier_group_id}({classifier_group_name})批量任务"
        else:
            task_desc = f"文章{raw_article_id}的分类器{classifier_id}的分类任务"

        task_id = create_label_raw_article_task(raw_article_id, base_id, task_desc)
        debug(f"创建标注任务: {task_id} ({task_desc})")

        # 为通过预过滤的分类器创建任务项
        task_items = self._create_task_items(task_id, eligible_ids, classifiers_cache, classify_agent)

        # 为跳过的分类器批量创建CANCELLED任务项
        if skipped_ids:
            skipped_task_items = self._batch_create_cancelled_task_items(
                task_id, skipped_ids, classifiers_cache)
            task_items.update(skipped_task_items)

        update_task_status(task_id, LabelRawArticleTaskStatus.RUNNING)

        # 4.5 动态合并独立的 GENERAL_CLASSIFICATION 分类器（仅分组模式）
        if classifier_group_id and len(eligible_ids) > 1:
            self._dynamic_merge_general_classifiers(
                eligible_ids, classifiers_cache, sub_classifiers,
                raw_article, classify_agent, task_id)

        # 5. 逐一执行分类（仅通过预过滤的分类器）
        results = {}
        success_count = 0
        total_count = len(classifier_ids)

        # 记录跳过的分类器结果
        for cid in skipped_ids:
            classifier = classifiers_cache.get(cid)
            results[f"classifier_{cid}"] = {
                "classifier_id": cid,
                "result": "",
                "status": "skipped",
                "error": f"前置条件不满足(预过滤): {classifier.alias if classifier else cid}",
            }

        for idx, cid in enumerate(eligible_ids, 1):
            result_dict = self._execute_single_classifier(
                cid, idx, len(eligible_ids), raw_article, classify_agent,
                classifiers_cache, sub_classifiers, task_id, task_items,
                cancel_history_results, classifier_group_id)

            results[f"classifier_{cid}"] = {
                k: v for k, v in result_dict.items() if k != "success"
            }
            if result_dict.get("success"):
                success_count += 1

        # 6. 更新整个任务状态为完成
        if task_id:
            update_task_status(
                task_id, LabelRawArticleTaskStatus.COMPLETED,
                self.usage_with_cost(classify_agent, cost_total=True))

        # 7. 输出汇总信息
        info(f"\n批量分类完成: 成功 {success_count}/{total_count} 个分类器")

        return {
            "raw_article_id": raw_article_id,
            "classifier_group_id": classifier_group_id,
            "single_classifier_id": classifier_id if not classifier_group_id else None,
            "total_classifiers": total_count,
            "success_count": success_count,
            "task_id": task_id,
            "results": results,
            "usage": classify_agent.totalUsage,
        }
    
    def _parse_classify_result(self, classifier: Classifier, result_item: Dict[str, Any], classify_agent: ClassifyAgent, raw_article: RawArticle) -> Tuple[str, Optional[ClassifierValue], List[ClassifierValue], int, Optional[str], Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        解析分类结果
        
        Returns:
            Tuple包含: (label_item_key, classifier_value, classifier_values, location, 
                       entity_name, entity_full_name, language, metadata)
        """
        # 提取result_item中的metadata字段
        result_metadata = result_item.get('metadata', None)
        
        if classifier.classify_method == ClassifyMethod.GENERAL_CLASSIFICATION:
            value_id = result_item.get('value_id', 0)
            label_item_key = classifier.name
            classifier_value = load_classifier_value_by_id(value_id)
            classifier_values = []
            location = 0
            entity_name = None
            entity_full_name = None
            language = None
        elif classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING:
            if 'entity_name' not in result_item:
                if 'logs' in result_item:
                    debug(f"自检日志: {result_item['logs']}")
                return (None, None, [], 0, None, None, None, None)
            entity_name = result_item.get('entity_name')
            entity_type = result_item.get('entity_type', 'OTHER')
            entity_full_name = result_item.get('entity_full_name', '')
            location = result_item.get('location', 0)
            language = result_item.get('language')
            concept_id = result_item.get('concept_id')
            label_item_key = entity_type
            classifier_impl = classify_agent.get_classifier_agent_impl(classifier)
            classifier_value = None
            classifier_values = []

            if classifier_impl.check(ClassifierConditions.NEED_MATCH_TERM_TREE):
                if concept_id is not None:
                    classifier_values = load_classifier_value_by_concept_id(concept_id, classifier.id)
                if not classifier_values or len(classifier_values) <= 0:
                    # 使用缓存避免同一entity_name重复查询DB（double-check locking）
                    cache_key = (entity_name, classifier.id)
                    with self._cache_lock:
                        cached = self._entity_match_cache.get(cache_key)
                    if cached is not None:
                        classifier_values = cached
                        if classifier_values:
                            debug(f"命名实体匹配(缓存命中): {entity_name}")
                    else:
                        classifier_values = load_classifier_values_by_entity_name(
                            entity_name, classifier.id,
                            self._get_alternatives(entity_name, entity_full_name), True)
                        with self._cache_lock:
                            if cache_key not in self._entity_match_cache:
                                self._entity_match_cache[cache_key] = classifier_values
                            else:
                                classifier_values = self._entity_match_cache[cache_key]

                if classifier_values:
                    for cv in classifier_values:
                        debug(f"命名实体完全匹配: {entity_name} -> {cv.value}({cv.id})")
            if (classifier_values is None or len(classifier_values) <= 0) and classifier_impl.check(ClassifierConditions.NEED_SEARCH_VECTOR_DB, entity_type=entity_type, metadata=result_metadata):
                # 从全文（或标题+摘要）中提取上下文，用于构建更准确的 query
                article_text = self._get_article_text_for_context(raw_article, classify_agent)
                entity_context = extract_entity_context(article_text, entity_name, context_chars=150, max_contexts=3)

                # 构建 entity query
                entity_query = self._build_entity_query(entity_name, entity_full_name, entity_type, entity_context)

                if not classifier_impl.check(ClassifierConditions.CLASSIFIER_LANGUAGE_MATCH, value_lang=language):
                    entity_query = self.translator.translate(entity_query, classifier.classify_params.get("language", "en"))

                vector_db_params = {}
                if classifier.classify_params:
                    collection_name = classifier.classify_params.get("vector_db_collection_name", self.collection)
                    if classifier.classify_params.get("vector_db_valid_score"):
                        vector_db_params['valid_score'] = classifier.classify_params.get("vector_db_valid_score")
                    if classifier.classify_params.get("vector_db_top_k"):
                        vector_db_params['top_k'] = classifier.classify_params.get("vector_db_top_k")
                    if classifier.classify_params.get("vector_db_max_candidates"):
                        vector_db_params['max_candidates'] = classifier.classify_params.get("vector_db_max_candidates")
                else:
                    collection_name = self.collection

                # 使用多候选查询
                candidates, exact_match_term_id = load_classifier_values_by_vector_db(
                    self.vector_db, collection_name, self.embedding_model,
                    entity_query, classifier.id, entity_name, **vector_db_params)

                if candidates:
                    # 检查是否有严格匹配的候选
                    exact_matches = [(cv, score, is_exact) for cv, score, is_exact in candidates if is_exact]

                    if exact_matches:
                        # 有严格匹配，直接使用第一个严格匹配的结果
                        exact_cv, exact_score, _ = exact_matches[0]
                        debug(f"命名实体向量库严格匹配: {entity_name} -> {exact_cv.value}, term_id: {exact_match_term_id}, score: {exact_score:.3f} ")
                        classifier_values = list_classifier_values_by_value(classifier.id, exact_cv.value)
                    elif classifier_impl.check(ClassifierConditions.RECHECK_VECTOR_DB_UNEXACT_MATCH):
                        # 没有严格匹配，对候选进行recheck, 如果classfier支持RECHECK_VECTOR_DB_UNEXACT_MATCH
                        debug(f"命名实体向量库近似匹配: {entity_name} -> {len(candidates)}个候选")
                        for cv, score, _ in candidates:
                            debug(f"  候选: {cv.value} (score: {score:.3f})")

                        try:
                            recheck_results = self.invoke_classify_agent_recheck_with_candidates(
                                classifier.id, raw_article, candidates, entity_name, classify_agent)
                            classification_results = safe_json_loads(recheck_results)
                            classifier_values = []
                            for result_item in classification_results:
                                if not isinstance(result_item, dict):
                                    error(f"Recheck结果格式错误：期望dict，实际为{type(result_item)}，跳过该项")
                                    continue

                                if 'classifier_value_id' not in result_item:
                                    error(f"Recheck结果缺少classifier_value_id字段，跳过该项: {result_item}")
                                    continue

                                value_id = result_item.get('classifier_value_id', 0)
                                v = load_classifier_value_by_id(value_id)
                                if v:
                                    classifier_values.append(v)
                        except Exception as recheck_e:
                            error(f"Recheck过程异常: {recheck_e}，将清空匹配结果")
                            classifier_values = []

        return (label_item_key, classifier_value, 
                classifier_values if classifier_values else [],
                location, entity_name, entity_full_name, language, result_metadata)

    def _save_classification_result(self, task_id: int, task_item_id: int, label_item_key: str, 
                                    classifier: Classifier, classifier_value: Optional[ClassifierValue], classifier_values: List[ClassifierValue], 
                                    location: int, entity_name: Optional[str], entity_full_name: Optional[str], language: Optional[str],
                                    classify_agent: ClassifyAgent, result_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存分类结果
        
        Args:
            result_metadata: 从result_item中提取的metadata，会与初始化的metadata合并
        """
        # 初始化基础metadata
        metadata = {
            "entity_name": entity_name,
            "entity_full_name": entity_full_name,
            "language": language,
            "classify_values": [],
            "concept_ids": []
        }
        
        # 合并result_metadata到metadata中
        if result_metadata is not None and isinstance(result_metadata, dict):
            metadata.update(result_metadata)

        if classifier_values is not None and len(classifier_values) > 0:
            metadata['entity_matched'] = True
            entity_name_matched = False
            entity_full_name_matched = False
            for classifier_value in classifier_values:
                if classifier_value.value.lower() == entity_name.lower():
                    entity_name_matched = True
                if entity_full_name and classifier_value.value.lower() == entity_full_name.lower():
                    entity_full_name_matched = True
                metadata["classify_values"].append(classifier_value.value)
                if classifier_value.concept_id:
                    metadata["concept_ids"].append(classifier_value.concept_id)
                    metadata['i18n'] = concept_i18n_data(classifier_value.concept_id)
                else:
                    metadata['i18n'] = term_i18n_data(classifier_value.term_id)
                save_classification_result(
                    task_id=task_id,
                    task_item_id=task_item_id,
                    label_item_key=label_item_key,
                    label_item_value=classifier_value.value,  # 使用classifier_value的value
                    classify_method=classifier.classify_method,  # 从classifier获取
                    location=location,
                    term_tree_id=classifier.term_tree_id,
                    term_tree_node_id=classifier_value.term_tree_node_id,
                    concept_id=classifier_value.concept_id,
                    term_id=classifier_value.term_id,
                    metadata=metadata
                )
            if not entity_name_matched: # no concept_id and term_id data
                term = load_term_by_value(entity_name)
                if term:
                    concept = load_concept_by_id(term.concept_id)
                else: 
                    concept = None

                if concept:
                    metadata['i18n'] = concept_i18n_data(concept.id)
                else:
                    metadata['i18n'] = self.build_i18n_data_for_entity(entity_name, language)

                save_classification_result(
                    task_id=task_id,
                    task_item_id=task_item_id,
                    label_item_key=label_item_key,
                    label_item_value=entity_name,
                    classify_method=classifier.classify_method,
                    location=location,
                    term_tree_id=None,
                    term_tree_node_id=None,
                    concept_id=concept.id if concept else None,
                    term_id=term.id if term else None,
                    metadata=metadata,
                )
            if entity_full_name and not entity_full_name_matched:
                term = load_term_by_value(entity_full_name)
                if term:
                    concept = load_concept_by_id(term.concept_id)
                else: 
                    concept = None

                if concept:
                    metadata['i18n'] = concept_i18n_data(concept.id)
                else:
                    metadata['i18n'] = self.build_i18n_data_for_entity(entity_full_name, language)
                save_classification_result(
                    task_id=task_id,
                    task_item_id=task_item_id,
                    label_item_key=label_item_key,
                    label_item_value=entity_full_name,
                    classify_method=classifier.classify_method,
                    location=location,
                    term_tree_id=None,
                    term_tree_node_id=None,
                    concept_id=concept.id if concept else None,
                    term_id=term.id if term else None,
                    metadata=metadata,
                )
            return True
        elif classifier_value is not None:
            metadata['entity_matched'] = True
            metadata["classify_values"].append(classifier_value.value)
            if classifier_value.concept_id:
                metadata["concept_ids"].append(classifier_value.concept_id)
                metadata['i18n'] = concept_i18n_data(classifier_value.concept_id)
            else:
                metadata['i18n'] = term_i18n_data(classifier_value.term_id)
            save_classification_result(
                task_id=task_id,
                task_item_id=task_item_id,
                label_item_key=label_item_key,
                label_item_value=classifier_value.value,  # 使用classifier_value的value
                classify_method=classifier.classify_method,  # 从classifier获取
                location=location,
                term_tree_id=classifier.term_tree_id,
                term_tree_node_id=classifier_value.term_tree_node_id,
                concept_id=classifier_value.concept_id,
                term_id=classifier_value.term_id,
                metadata=metadata,
            )
            return True
        else:
            if label_item_key is None or entity_name is None:
                return False
            metadata['entity_matched'] = False
            classifier_impl = classify_agent.get_classifier_agent_impl(classifier)
            if classifier.classify_method == ClassifyMethod.NAMED_ENTITY_MATCHING and classifier_impl.check(ClassifierConditions.ALLOW_NO_MATCHING_RESULTS):
                value = entity_full_name or entity_name
                term = load_term_by_value(value)
                if term:
                    concept = load_concept_by_id(term.concept_id)
                else: 
                    concept = None

                if concept:
                    metadata['i18n'] = concept_i18n_data(concept.id)
                else:
                    metadata['i18n'] = self.build_i18n_data_for_entity(entity_name, language)
                save_classification_result(
                    task_id=task_id,
                    task_item_id=task_item_id,
                    label_item_key=label_item_key,
                    label_item_value=value,
                    classify_method=classifier.classify_method,
                    location=location,
                    term_tree_id=None,
                    term_tree_node_id=None,
                    concept_id=concept.id if concept else None,
                    term_id=term.id if term else None,
                    metadata=metadata
                )
                return True
            else:
                return False
    
    def _get_alternatives(self, entity_name: str, entity_full_name: Optional[str] = None) -> list[str]:
        """
        获取实体名称的替代形式（复数/单数）
        
        Args:
            entity_name: 实体名称
            
        Returns:
            替代形式列表
        """
        alternatives = []

        has_full_name = False
        if entity_full_name and entity_full_name.strip() != "" and entity_full_name != entity_name:
            alternatives.append(entity_full_name)
            has_full_name = True
        
        # 尝试生成复数形式
        try:
            plural = self.inflect_engine.plural(entity_name)
            if plural and plural != entity_name:
                alternatives.append(plural)
        except (IndexError, AttributeError, Exception) as e:
            debug(f"无法生成 '{entity_name}' 的复数形式: {e}")

        
        # 尝试生成单数形式
        try:
            single = self.inflect_engine.singular_noun(entity_name)
            if single and single != entity_name:
                alternatives.append(single)
        except (IndexError, AttributeError, Exception) as e:
            debug(f"无法生成 '{entity_name}' 的单数形式: {e}")

        # 尝试生成全名形式的复数和单数形式
        if has_full_name:
            try:
                plural_full_name = self.inflect_engine.plural(entity_full_name)
                if plural_full_name and plural_full_name != entity_full_name:
                    alternatives.append(plural_full_name)
            except (IndexError, AttributeError, Exception) as e:
                debug(f"无法生成 '{entity_full_name}' 的复数形式: {e}")

            try:
                single_full_name = self.inflect_engine.singular_noun(entity_full_name)
                if single_full_name and single_full_name != entity_full_name:
                    alternatives.append(single_full_name)
            except (IndexError, AttributeError, Exception) as e:
                debug(f"无法生成 '{entity_full_name}' 的单数形式: {e}")
        
        return alternatives
    
    def _add_classifier_result_cache(self, classifier: Classifier, result_item: Dict[str, Any]):
        classifier_alias = result_item.get('classifier_alias', None)
        if classifier_alias is None or classifier_alias == "" or classifier_alias == classifier.alias:
            return False
        if classifier_alias not in self.classifier_result_cache:
            self.classifier_result_cache[classifier_alias] = []
        self.classifier_result_cache[classifier_alias].append(result_item)
        return True

    def _clear_classisifer_result_cache(self, classifier_id: Optional[int] = None):
        if classifier_id is None:
            self.classifier_result_cache.clear()
            self._entity_match_cache.clear()
            self._i18n_cache.clear()
            return

        if classifier_id in self.classifier_result_cache:
            self.classifier_result_cache[classifier_id] = []

    def cancel_history_results(self, classifier_id: int, raw_article_id: int):
        try:
            with self.connection.cursor() as cursor:
                sql = """
                UPDATE label_raw_article_task_result SET status = %s WHERE label_raw_article_task_item_id IN
                    (SELECT li.id FROM label_raw_article_task_item li, label_raw_article_task task WHERE 
                    li.classifier_id = %s AND task.raw_article_id = %s AND task.id = li.label_raw_article_task_id);
                """
                cursor.execute(sql, (LabelRawArticleTaskStatus.CANCELLED.value, classifier_id, raw_article_id,))
                sql = """
                UPDATE label_raw_article_task_item SET status=%s WHERE classifier_id=%s 
                    AND label_raw_article_task_id IN (SELECT id FROM label_raw_article_task WHERE raw_article_id=%s)
                """
                cursor.execute(sql, (LabelRawArticleTaskStatus.CANCELLED.value, classifier_id, raw_article_id,))
                self.connection.commit()
                info(f"取消历史结果成功: {classifier_id} -> {raw_article_id}")
        except Exception as e:
            error(f"取消历史结果失败: {e}")

    def build_i18n_data_for_entity(self, entity_name: str, lang: str) -> Dict[str, str]:
        """为实体构建国际化数据，带缓存避免重复翻译（线程安全）"""
        cache_key = (entity_name, lang)
        with self._cache_lock:
            cached = self._i18n_cache.get(cache_key)
        if cached is not None:
            debug(f"i18n缓存命中: {entity_name}")
            return cached

        i18n_data = {lang: entity_name}
        target_languages = ['en', 'zh']
        extra_info = (
            "If a word has multiple meanings, we prefer the meaning in the biomedical field."
            " If a word belongs to a specific abbreviation, number, code, or resource term"
            " (domain name, fund code, etc.), then there is no need to translate it;"
            " simply return the original word."
        )

        try:
            for target_lang in target_languages:
                if target_lang in i18n_data:
                    continue
                translated = self.translator.translate(
                    entity_name, target_lang, extra_info=extra_info)
                debug(f"i18n: [{lang}] {entity_name} -> [{target_lang}] {translated}")
                i18n_data[target_lang] = translated
        except Exception as e:
            error(f"构建实体国际化数据失败: {e}")

        with self._cache_lock:
            if cache_key not in self._i18n_cache:
                self._i18n_cache[cache_key] = i18n_data
            else:
                i18n_data = self._i18n_cache[cache_key]
        return i18n_data

    def cleanup(self):
        """清理资源"""
        if self.connection:
            close_mysql_connection()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='为raw_article执行分类')
    parser.add_argument('-c', '--classifier-id', type=int, help='分类器ID')
    parser.add_argument('-g', '--classifier-group-id', type=int, help='分类器分组ID')
    parser.add_argument('-a', '--raw-article-id', type=int, required=True, help='文章ID')
    parser.add_argument('-ip', '--input-token-price', type=float, help='输入token价格', default=0) 
    parser.add_argument('-op', '--output-token-price', type=float, help='输出token价格', default=0) 
    parser.add_argument('-e', '--env', type=str, default='dev', help='环境，默认为dev')
    parser.add_argument('-n', '--collection-name', type=str, default='classifier_value_entities', help='向量库集合名称，默认为classifier_value_entities')
    parser.add_argument('-r', '--cancel-history-results', action='store_true', help='取消历史结果')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')

    args = parser.parse_args()

    # 参数验证：classifier_id和classifier_group_id必须提供其中一个，且不能同时提供
    if not args.classifier_id and not args.classifier_group_id:
        error("必须提供 --classifier_id 或 --classifier_group_id 参数之一")
        return 1
        
    if args.classifier_id and args.classifier_group_id:
        error("--classifier_id 和 --classifier_group_id 参数不能同时提供")
        return 1

    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
        debug(f"开始时间: {datetime.now()}")
        if args.classifier_id:
            debug(f"分类器ID: {args.classifier_id}")
        if args.classifier_group_id:
            debug(f"分类器分组ID: {args.classifier_group_id}")
        debug(f"原始素材ID: {args.raw_article_id}")
        debug("-" * 50)

    # 初始化配置
    init_rbase_config()
    
    start = time.time()
    classifier = None
    try:
        classifier = RawArticleClassifier(configuration.config, 
                                          configuration.vector_db, 
                                          configuration.embedding_model, 
                                          configuration.academic_translator,
                                          input_token_price=args.input_token_price,
                                          output_token_price=args.output_token_price,
                                          env=args.env,
                                          collection_name=args.collection_name)
        result = classifier.classify_article(args.classifier_id, args.classifier_group_id, args.raw_article_id, cancel_history_results=args.cancel_history_results)
        
        if result and result.get('results'):
            color_print("="*60)
            color_print("分类结果:")
            
            # 输出详细结果
            color_print(f"文章ID: {result['raw_article_id']}")
            if result.get('classifier_group_id'):
                color_print(f"分类器分组ID: {result['classifier_group_id']}")
            else:
                color_print(f"单个分类器ID: {result['single_classifier_id']}")
            color_print(f"总分类器数: {result['total_classifiers']}")
            color_print(f"成功数: {result['success_count']}")
            color_print(f"总消耗tokens: {result['usage']['total_tokens']}")
            color_print(f"输入tokens: {result['usage']['prompt_tokens']}")
            color_print(f"输出tokens: {result['usage']['completion_tokens']}")
            color_print(f"总耗时: {time.time() - start}秒")
            color_print("="*60)

            # 输出每个分类器的结果
            for key, classifier_result in result['results'].items():
                debug(f"[分类器 {classifier_result['classifier_id']}]")
                debug(f"状态: {classifier_result['status']}")
                if classifier_result['status'] == 'success':
                    debug(f"结果: {classifier_result['result']}")
                    debug(f"消耗tokens: {classifier_result['usage']['total_tokens']}")
                else:
                    debug(f"错误: {classifier_result.get('error', '未知错误')}")
                debug("-" * 40)
            
            if result['success_count'] == result['total_classifiers']:
                color_print("✅ 所有分类器执行成功!")
            elif result['success_count'] > 0:
                color_print(f"⚠️ 部分分类器执行成功 ({result['success_count']}/{result['total_classifiers']})")
            else:
                color_print("❌ 所有分类器执行失败!")
            return 0
        else:
            error("\n❌ 文章分类失败!")
            return 1
            
    except Exception as e:
        error(f"\n❌ 程序执行出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if classifier:
            classifier.cleanup()
        if args.verbose:
            debug(f"结束时间: {datetime.now()}")


if __name__ == "__main__":
    sys.exit(main())
