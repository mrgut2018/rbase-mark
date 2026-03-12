import json
from typing import List, Optional, Tuple
from datetime import datetime
from deepsearcher.rbase.ai_models import (
    Classifier, ClassifierValue, ClassifierStatus,
    ClassifyMethod, ClassifierValueIsLabel,
    LabelRawArticleTaskStatus
)
from deepsearcher.rbase.terms import Concept
from deepsearcher import configuration
from deepsearcher.db.mysql_connection import get_mysql_connection
from deepsearcher.vector_db.base import BaseVectorDB
from deepsearcher.embedding.base import BaseEmbedding
from deepsearcher.tools.log import debug
from deepsearcher.rbase.ai_models import LabelRawArticleTaskResult, LabelRawArticleTaskStatus

def load_classifier_by_id(classifier_id: int) -> Classifier:
    """
    Load classifier by id
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT id, name, alias, ver, level, base_id, parent_classifier_id, type, 
                classify_method, classify_params, prerequisite, term_tree_id, 
                term_tree_node_id, purpose, target, principle, criterion, 
                is_need_full_text, is_allow_other_value, is_multi, 
                multi_limit_min, multi_limit_max, is_include_sub_value, 
                status, created, modified
            FROM classifier 
            WHERE id = %s AND status = 1
            """
            cursor.execute(sql, (classifier_id,))
            result = cursor.fetchone()
            if result:
                result['classify_params'] = json.loads(result['classify_params']) if result['classify_params'] else None
                result['prerequisite'] = json.loads(result['prerequisite']) if result['prerequisite'] else None
                result['status'] = ClassifierStatus(result['status'])
                return Classifier(**result)
            else:
                return None
    except Exception as e:
        raise Exception(f"Failed to load classifier by id({classifier_id}): {e}")


def load_classifiers_by_ids(classifier_ids: List[int]) -> dict[int, Classifier]:
    """
    批量加载分类器

    Args:
        classifier_ids: 分类器ID列表

    Returns:
        dict[int, Classifier]: 分类器ID到Classifier对象的映射字典
    """
    if not classifier_ids:
        return {}

    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            placeholders = ','.join(['%s'] * len(classifier_ids))
            sql = f"""
            SELECT id, name, alias, ver, level, base_id, parent_classifier_id, type,
                classify_method, classify_params, prerequisite, term_tree_id,
                term_tree_node_id, purpose, target, principle, criterion,
                is_need_full_text, is_allow_other_value, is_multi,
                multi_limit_min, multi_limit_max, is_include_sub_value,
                status, created, modified
            FROM classifier
            WHERE id IN ({placeholders}) AND status = 1
            """
            cursor.execute(sql, classifier_ids)
            results = cursor.fetchall()

            classifiers = {}
            for result in results:
                result['classify_params'] = json.loads(result['classify_params']) if result['classify_params'] else None
                result['prerequisite'] = json.loads(result['prerequisite']) if result['prerequisite'] else None
                result['status'] = ClassifierStatus(result['status'])
                classifiers[result['id']] = Classifier(**result)

            return classifiers
    except Exception as e:
        raise Exception(f"Failed to load classifiers by ids({classifier_ids}): {e}")


def load_classifier_by_alias(classifier_alias: str) -> Classifier:
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT * FROM classifier WHERE alias = %s AND status = 1
            """
            cursor.execute(sql, (classifier_alias,))
            result = cursor.fetchone()
            if result:
                result['classify_params'] = json.loads(result['classify_params']) if result['classify_params'] else None
                result['prerequisite'] = json.loads(result['prerequisite']) if result['prerequisite'] else None
                result['status'] = ClassifierStatus(result['status'])
                return Classifier(**result)
            else:
                return None
    except Exception as e:
        raise Exception(f"Failed to load classifier by alias({classifier_alias}): {e}")

def list_classifier_values_by_classifier_id(classifier_id: int, offset: int = 0, limit: int = 0) -> list[ClassifierValue]:
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT id, classifier_id, value, value_i18n, value_clue, value_rule, code, alias, 
                   priority, parent_id, term_tree_node_id, concept_id, term_id, 
                   exclusive_with, is_label, status, remark, created, modified
            FROM classifier_value
            WHERE classifier_id = %s AND status = %s
            ORDER BY priority DESC, id ASC
            """
            if limit > 0:
                sql += " LIMIT %s, %s"
                params = (classifier_id, ClassifierStatus.NORMAL.value, offset, limit)
            else:
                params = (classifier_id, ClassifierStatus.NORMAL.value)
            cursor.execute(sql, params)
            results = cursor.fetchall()
            
            classifier_values = []
            for result in results:
                if result['value_i18n'] and isinstance(result['value_i18n'], str):
                    result['value_i18n'] = json.loads(result['value_i18n'])
                elif not result['value_i18n']:
                    result['value_i18n'] = {}
                
                classifier_values.append(ClassifierValue(**result))
            
            return classifier_values
    except Exception as e:
        raise Exception(f"Failed to load classifier values by classifier id({classifier_id}): {e}")

def list_classifier_values_by_value(classifier_id: int, value: str, offset: int = 0, limit: int = 0) -> list[ClassifierValue]:
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT * FROM classifier_value WHERE classifier_id = %s AND value = %s AND status = %s
            ORDER BY priority DESC, id ASC
            """
            if limit > 0:
                sql += " LIMIT %s, %s"
                params = (classifier_id, value, ClassifierStatus.NORMAL.value, offset, limit)
            else:
                params = (classifier_id, value, ClassifierStatus.NORMAL.value)

            cursor.execute(sql, params)
            results = cursor.fetchall()
            classifier_values = []
            for result in results:
                if result['value_i18n'] and isinstance(result['value_i18n'], str):
                    result['value_i18n'] = json.loads(result['value_i18n'])
                elif not result['value_i18n']:
                    result['value_i18n'] = {}
                
                classifier_values.append(ClassifierValue(**result))
            
            return classifier_values
    except Exception as e:
        raise Exception(f"Failed to load classifier values by value({classifier_id}, {value}): {e}")

def check_classifier_prerequisite_values_in(raw_article_id: int, classifier_alias: str, value_in: List[str], task_id: Optional[int] = None) -> bool:
    """
    检查分类器单个前置条件是否满足
    
    通过联合查询直接检查指定别名的分类器是否有满足条件的标注结果
    
    Args:
        raw_article_id: 文章ID
        classifier_alias: 分类器别名
        value_in: 要求的取值列表
        
    Returns:
        bool: True表示条件满足，False表示不满足
    """
    try:
        if len(value_in) <= 0:
            return False
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT COUNT(*) as count FROM label_raw_article_task_result r
                JOIN label_raw_article_task_item i ON r.label_raw_article_task_item_id = i.id
                JOIN label_raw_article_task t ON r.label_raw_article_task_id = t.id
                JOIN classifier c ON i.classifier_id = c.id
            WHERE t.raw_article_id = %s 
              AND c.alias = %s 
              AND c.status = 1
              AND r.status IN (1, 10)
              AND r.label_item_value IN ({})
            """.format(','.join(['%s'] * len(value_in)))

            params = [raw_article_id, classifier_alias] + value_in

            if task_id and task_id > 0:
                sql += " AND t.id = %s"
                params.append(task_id)
            
            cursor.execute(sql, params)
            result = cursor.fetchone()
            
            return result['count'] > 0 if result else False
            
    except Exception as e:
        raise Exception(f"Failed to check prerequisite condition for classifier alias({classifier_alias}): {e}")

def check_classifier_prerequisite_status_in(raw_article_id: int, classifier_alias: str, status_in: List[LabelRawArticleTaskStatus], task_id: Optional[int] = None) -> bool:
    """
    检查分类器单个前置条件是否满足

    通过联合查询直接检查指定别名的分类器是否有满足条件的标注结果

    Args:
        raw_article_id: 文章ID
        classifier_alias: 分类器别名
        status_in: 要求的取值列表

    Returns:
        bool: True表示条件满足，False表示不满足
    """
    try:
        if len(status_in) <= 0:
            return False
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT COUNT(*) as count FROM label_raw_article_task_item i
                JOIN label_raw_article_task t ON i.label_raw_article_task_id = t.id
                JOIN classifier c ON i.classifier_id = c.id
            WHERE t.raw_article_id = %s
              AND c.alias = %s
              AND c.status = 1
              AND i.status IN ({})
            """.format(','.join(['%s'] * len(status_in)))
            
            params = [raw_article_id, classifier_alias] + status_in

            if task_id and task_id > 0:
                sql += " AND t.id = %s"
                params.append(task_id)
            
            cursor.execute(sql, params)
            result = cursor.fetchone()
            
            return result['count'] > 0 if result else False
            
    except Exception as e:
        raise Exception(f"Failed to check prerequisite condition for classifier alias({classifier_alias}): {e}")

def create_label_raw_article_task(raw_article_id: int, base_id: Optional[int], desc: str) -> int:
    """
    创建标注文章任务
    
    Args:
        raw_article_id: 文章ID
        base_id: 用户库ID，可为None
        desc: 任务描述
        
    Returns:
        创建的任务ID
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO label_raw_article_task (
                raw_article_id, base_id, `desc`, status, created, modified
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            """
            
            now = datetime.now()
            values = (
                raw_article_id,
                base_id if base_id else None,
                desc,
                LabelRawArticleTaskStatus.PENDING.value,
                now,
                now
            )
            
            cursor.execute(sql, values)
            task_id = cursor.lastrowid
            connection.commit()
            
            return task_id
            
    except Exception as e:
        raise Exception(f"Failed to create label raw article task: {e}")

def create_label_raw_article_task_item(
    task_id: int, 
    classifier_id: int, 
    classifier_ver: str,
    label_item_key: str,
    term_tree_id: Optional[int] = None,
    term_tree_node_id: Optional[int] = None,
    script_params: Optional[dict] = None
) -> int:
    """
    创建标注文章任务项
    
    Args:
        task_id: 任务ID
        classifier_id: 分类器ID
        classifier_ver: 分类器版本
        label_item_key: 标注项名称
        term_tree_id: 术语树ID
        term_tree_node_id: 术语树节点ID
        
    Returns:
        创建的任务项ID
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO label_raw_article_task_item (
                label_raw_article_task_id, term_tree_id, term_tree_node_id,
                label_item_key, classifier_id, classifier_ver, script_params, status,
                created, modified
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            now = datetime.now()
            values = (
                task_id,
                term_tree_id,
                term_tree_node_id,
                label_item_key,
                classifier_id,
                classifier_ver,
                json.dumps(script_params) if script_params else None,
                LabelRawArticleTaskStatus.PENDING.value,
                now,
                now
            )
            
            cursor.execute(sql, values)
            task_item_id = cursor.lastrowid
            connection.commit()
            
            return task_item_id
            
    except Exception as e:
        raise Exception(f"Failed to create label raw article task item: {e}")

def update_task_item_status(task_item_id: int, status: LabelRawArticleTaskStatus, usage: Optional[dict] = None) -> None:
    """
    更新任务项状态
    
    Args:
        task_item_id: 任务项ID
        status: 新状态
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            if usage is not None:
                sql = """
                UPDATE label_raw_article_task_item SET status = %s, modified = %s, `usage` = %s
                WHERE id = %s
                """
                cursor.execute(sql, (status.value, datetime.now(), json.dumps(usage), task_item_id))
            else:
                sql = """
                UPDATE label_raw_article_task_item SET status = %s, modified = %s
                WHERE id = %s
                """
                cursor.execute(sql, (status.value, datetime.now(), task_item_id))
            connection.commit()
            
    except Exception as e:
        raise Exception(f"Failed to update task item status: {e}")

def save_classification_result(
    task_id: int,
    task_item_id: int,
    label_item_key: str,
    label_item_value: str,
    classify_method: ClassifyMethod,
    location: int = 0,
    term_tree_id: Optional[int] = None,
    term_tree_node_id: Optional[int] = None,
    concept_id: Optional[int] = None,
    term_id: Optional[int] = None,
    metadata: Optional[dict] = None
) -> int:
    """
    保存分类结果
    
    Args:
        task_id: 任务ID
        task_item_id: 任务项ID
        label_item_key: 标注项名称
        label_item_value: 标注项取值
        classify_method: 分类方法
        location: 位置
        term_tree_id: 术语树ID
        term_tree_node_id: 术语树节点ID
        concept_id: 概念ID
        term_id: 术语ID
        
    Returns:
        创建的结果ID
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO label_raw_article_task_result (
                label_item_key, label_raw_article_task_id, label_raw_article_task_item_id,
                classify_method, location, term_tree_id, term_tree_node_id,
                concept_id, term_id, label_item_value, metadata, status, created, modified
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            now = datetime.now()
            values = (
                label_item_key,
                task_id,
                task_item_id,
                classify_method.value,
                location,
                term_tree_id,
                term_tree_node_id,
                concept_id,
                term_id,
                label_item_value,
                json.dumps(metadata) if metadata else None,
                LabelRawArticleTaskStatus.PENDING.value,
                now,
                now
            )
            
            cursor.execute(sql, values)
            result_id = cursor.lastrowid
            connection.commit()
            
            return result_id
            
    except Exception as e:
        raise Exception(f"Failed to save classification result: {e}")

def update_task_status(task_id: int, status: LabelRawArticleTaskStatus, usage: Optional[dict] = None) -> None:
    """
    更新任务状态
    
    Args:
        task_id: 任务ID
        status: 新状态
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            if usage is not None:
                sql = """
                UPDATE label_raw_article_task SET status = %s, modified = %s, `usage` = %s 
                WHERE id = %s
                """
                cursor.execute(sql, (status.value, datetime.now(), json.dumps(usage), task_id))
            else:
                sql = """
                UPDATE label_raw_article_task SET status = %s, modified = %s 
                WHERE id = %s
                """
                cursor.execute(sql, (status.value, datetime.now(), task_id))
            connection.commit()
            
    except Exception as e:
        raise Exception(f"Failed to update task status: {e}")

def _parse_classify_value_result(result: dict) -> Optional[ClassifierValue]:
    if result:
        return ClassifierValue(
            id=result['id'],
            classifier_id=result['classifier_id'],
            value=result['value'],
            value_i18n=json.loads(result['value_i18n']) if result['value_i18n'] else {},
            value_clue=result['value_clue'] or "",
            value_rule=result['value_rule'] or "",
            code=result['code'],
            alias=result['alias'],
            priority=result['priority'] or 0,
            parent_id=result['parent_id'],
            term_tree_node_id=result['term_tree_node_id'],
            concept_id=result['concept_id'],
            term_id=result['term_id'],
            exclusive_with=result['exclusive_with'] or "",
            is_label=result['is_label'] or 1,
            status=result['status'],
            remark=result['remark'] or "",
            created=result['created'],
            modified=result['modified']
        )
    else:
        return None

def load_classifier_value_by_id(value_id: int) -> Optional[ClassifierValue]:
    """
    根据ID加载分类器值
    
    Args:
        value_id: 分类器值ID
        
    Returns:
        ClassifierValue: 分类器值对象，如果不存在则返回None
    """
    try:
        if not value_id:
            return None
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT * FROM classifier_value WHERE id = %s AND status = %s
            """
            cursor.execute(sql, (value_id, ClassifierStatus.NORMAL.value))
            result = cursor.fetchone()
            
            return _parse_classify_value_result(result)
    except Exception as e:
        raise Exception(f"Failed to load classifier value by id({value_id}): {e}")

def load_classifier_values_by_entity_name(entity_name: str, classifier_id: int, alternatives: Optional[list[str]] = None, search_all_terms: bool = False) -> Optional[list[ClassifierValue]]:
    """
    Load classifier values by entity name
    Args:
        entity_name: 实体名称
        classifier_id: 分类器ID
        alternatives: 可选的实体名称列表
        search_all_terms: 是否搜索所有术语，如果在分类词表中无法找到的话
    Returns:
        ClassifierValue: 分类器值对象，如果不存在则返回None
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """SELECT * FROM classifier_value 
            WHERE value = %s AND classifier_id = %s AND status = %s AND is_label = %s"""
            cursor.execute(sql, (entity_name, classifier_id, ClassifierStatus.NORMAL.value, ClassifierValueIsLabel.YES.value))
            results = cursor.fetchall()
            if results:
                return [_parse_classify_value_result(result) for result in results]
            else:
                if search_all_terms:
                    concept_id = search_entity_name_concept_by_terms(entity_name)
                    if concept_id:
                        results = load_classifier_value_by_concept_id(concept_id, classifier_id)
                
                if not results and alternatives is not None:
                    for alternative in alternatives:
                        values = load_classifier_values_by_entity_name(alternative, classifier_id, search_all_terms=search_all_terms)
                        if values:
                            results = values
                            break
                return results
    except Exception as e:
        raise Exception(f"Failed to load classifier value by entity name({entity_name}): {e}")

def search_entity_name_concept_by_terms(entity_name: str) -> Optional[int]:
    """
    Search entity name related concept id by all terms
    Args:
        entity_name: entity name
    Returns:
        concept_id: concept id if found, otherwise None
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """SELECT concept_id, id as term_id FROM term 
                     WHERE name = %s AND status = %s LIMIT 1"""
            cursor.execute(sql, (entity_name, 10))
            result = cursor.fetchone()
            if result:
                sql = """SELECT id, preferred_concept_id FROM concept 
                         WHERE id = %s AND status = %s LIMIT 1"""
                cursor.execute(sql, (result['concept_id'], 10))
                concept = cursor.fetchone()
                if concept:
                    if concept['preferred_concept_id'] is not None and concept['preferred_concept_id'] > 0:
                        return concept['preferred_concept_id']
                    else:
                        return concept['id']
                else:
                    return None
            else:
                return None
    except Exception as e:
        raise Exception(f"Failed to search entity in all terms({entity_name}): {e}")


def load_classifier_value_by_concept_id(concept_id: int, classifier_id: int) -> Optional[List[ClassifierValue]]:
    """
    Load classifier value by concept id
    Args:
        concept_id: concept ID
        classifier_id: classifier ID
    Returns:
        List[ClassifierValue]: list of classifier value objects, returns None if not found
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """SELECT * FROM classifier_value WHERE concept_id = %s AND classifier_id = %s AND status = %s AND is_label = %s"""
            cursor.execute(sql, (concept_id, classifier_id, ClassifierStatus.NORMAL.value, ClassifierValueIsLabel.YES.value))
            results = cursor.fetchall()
            if results:
                return [_parse_classify_value_result(result) for result in results]
            else:
                return None
    except Exception as e:
        raise Exception(f"Failed to load classifier value by concept id({concept_id}): {e}")

def load_classifier_value_by_vector_db(vector_db: BaseVectorDB, collection: str, embedding_model: BaseEmbedding, entity_query: str, classifier_id: int, entity_name: str, **kwargs) -> Tuple[Optional[ClassifierValue], bool, Optional[int]]:
    """
    Load classifier values by vector database.
    Args:
        vector_db (BaseVectorDB): vector db instance
        collection (str): vector db collection name
        embedding_model (BaseEmbedding): embedding model for generating entity query vector
        entity_query (str): entity query text
        classifier_id (int): classifier id
        entity_name (str): entity name for final confirmation matching
        **kwargs:
            top_k (int, optional): maximum number of results returned by vector search, default is 10
            confirm_score (float, optional): score threshold for confirming candidate results, default is 0.5
            valid_score (float, optional): score upper bound for valid results, below which they are considered valid matches, default is 3
            verbose (bool, optional): whether to print verbose output, default is False

    Returns:
        Tuple[Optional[ClassifierValue], bool, Optional[int]]:
            - matched classifier value object (None if not found)
            - whether to confirm matching to a specific entity (based on name and score)
            - matched term id (returns if found, otherwise None)
    """
    top_k = kwargs.get('top_k', 10)
    confirm_score = kwargs.get('confirm_score', 0.5)
    valid_score = kwargs.get('valid_score', 3)
    verbose = kwargs.get('verbose', False)
    if verbose:
        debug(f"searching value by vector db for entity: {entity_query} for classifier {classifier_id}")

    embedding = embedding_model.embed_query(entity_query)
    results = vector_db.search_data(collection, embedding, 
                                    filter=f"classifier_id=={classifier_id}", 
                                    top_k=top_k,
                                    schema_name="classify_value_entity")
    recommend = None
    is_confirm = False
    match_term_id = None
    if results:
        if verbose:
            for r in results:
                debug(f"vector result: {r.text} - {r.metadata['classifier_value_id']} - {r.score}")
        results.reverse()
        for result in results:
            if result.score >= valid_score:
                continue

            recommend = result.metadata['classifier_value_id']
            terms = result.metadata.get('terms', [])
            for term in terms:
                if entity_name.lower() == term.get('term', '').lower():
                    if verbose:
                        debug(f"term match: {term.get('term')} - {term.get('term_id')}")
                    is_confirm = True
                    match_term_id = term.get('term_id')
                    break 

            if match_term_id:
                break
            else:
                is_confirm = result.score <= confirm_score
        
        if recommend:
            return load_classifier_value_by_id(recommend), is_confirm, match_term_id
            
    return None, False, None

def load_classifier_values_by_vector_db(vector_db: BaseVectorDB, collection: str, embedding_model: BaseEmbedding,
                                        entity_query: str, classifier_id: int, entity_name: str, **kwargs) -> Tuple[List[Tuple[ClassifierValue, float, bool]], Optional[int]]:
    """
    Load multiple classifier value candidates by vector database.

    Args:
        vector_db (BaseVectorDB): vector db instance
        collection (str): vector db collection name
        embedding_model (BaseEmbedding): embedding model for generating entity query vector
        entity_query (str): entity query text
        classifier_id (int): classifier id
        entity_name (str): entity name for exact matching check
        **kwargs:
            top_k (int, optional): maximum number of results returned by vector search, default is 10
            max_candidates (int, optional): maximum number of candidates to return, default is 5
            valid_score (float, optional): score upper bound for valid results, default is 3
            verbose (bool, optional): whether to print verbose output, default is False

    Returns:
        Tuple[List[Tuple[ClassifierValue, float, bool]], Optional[int]]:
            - list of candidates: [(ClassifierValue, score, is_exact_match), ...]
            - exact match term id (if found, otherwise None)
    """
    top_k = kwargs.get('top_k', 10)
    max_candidates = kwargs.get('max_candidates', 5)
    valid_score = kwargs.get('valid_score', 3)
    verbose = kwargs.get('verbose', False)

    # 确保 top_k 不小于 max_candidates，否则可能无法返回足够的候选
    if top_k < max_candidates:
        top_k = max_candidates

    if verbose:
        debug(f"searching multiple candidates by vector db for entity: {entity_query} for classifier {classifier_id} (top_k={top_k}, max_candidates={max_candidates})")

    embedding = embedding_model.embed_query(entity_query)
    results = vector_db.search_data(collection, embedding,
                                    filter=f"classifier_id=={classifier_id}",
                                    top_k=top_k,
                                    schema_name="classify_value_entity")

    candidates = []
    exact_match_term_id = None
    seen_value_ids = set()  # 避免重复的classifier_value_id

    if results:
        if verbose:
            for r in results:
                debug(f"vector result: {r.text} - {r.metadata['classifier_value_id']} - {r.score}")

        for result in results:
            if result.score >= valid_score:
                continue

            value_id = result.metadata['classifier_value_id']
            if value_id in seen_value_ids:
                continue
            seen_value_ids.add(value_id)

            classifier_value = load_classifier_value_by_id(value_id)
            if not classifier_value:
                continue

            # 检查是否严格匹配
            is_exact = False
            terms = result.metadata.get('terms', [])
            for term in terms:
                if entity_name.lower() == term.get('term', '').lower():
                    is_exact = True
                    if exact_match_term_id is None:
                        exact_match_term_id = term.get('term_id')
                    if verbose:
                        debug(f"exact term match: {term.get('term')} - {term.get('term_id')}")
                    break

            candidates.append((classifier_value, result.score, is_exact))

            if len(candidates) >= max_candidates:
                break

    return candidates, exact_match_term_id

def load_classifier_value_route(classifier_value: ClassifierValue) -> List[ClassifierValue]:
    """
    Load classifier value route

    Args:
        classifier_value: classifier value object
    Returns:
        List[ClassifierValue]: list of classifier value objects from root to current node
    """
    try:
        if not classifier_value:
            return []
        parents = [classifier_value]
        while classifier_value and classifier_value.parent_id is not None:
            classifier_value = load_classifier_value_by_id(classifier_value.parent_id)
            if classifier_value:
                parents.append(classifier_value)
        parents.reverse()
        return parents
    except Exception as e:
        raise Exception(f"Failed to load classifier value route by classifier value id({classifier_value.id}): {e}")

def list_classifier_results_by_article_id(article_id: int, classifier: Classifier, status: Optional[LabelRawArticleTaskStatus] = None, unique_value: bool = False) -> List[LabelRawArticleTaskResult]:
    """
    List classifier results by article id
    Args:
        article_id: article id
        classifier: classifier
        status: status
    Returns:
        List[LabelRawArticleTaskResult]: list of classifier results
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """
            SELECT * FROM label_raw_article_task_result lr, label_raw_article_task_item li, label_raw_article_task task
            WHERE lr.label_raw_article_task_item_id = li.id AND li.label_raw_article_task_id = task.id 
                AND task.raw_article_id = %s AND li.classifier_id = %s 
            """
            params = [article_id, classifier.id]
            if status:
                sql += " AND lr.status = %s"
                params.append(status.value)
            else:
                sql += " AND lr.status <> %s"
                params.append(LabelRawArticleTaskStatus.CANCELLED.value)
            cursor.execute(sql, params)
            results = cursor.fetchall()
            if not unique_value:
                return [_parse_classifier_result(result) for result in results]
            else:
                values = {}
                for result in results:
                    values[result['label_item_value']] = _parse_classifier_result(result)
                
                return list(values.values())


    except Exception as e:
        raise Exception(f"Failed to list classifier results by article id({article_id}): {e}")

def _parse_classifier_result(result: dict) -> Optional[LabelRawArticleTaskResult]:
    if result:
        result['metadata'] = json.loads(result['metadata']) if result['metadata'] else None
        result['status'] = LabelRawArticleTaskStatus(result['status'])
        return LabelRawArticleTaskResult(**result)
    else:
        return None

def extract_entity_context(text: str, entity_name: str, context_chars: int = 250, max_contexts: int = 5) -> str:
    """
    从文本中提取实体名称出现的上下文片段。

    Args:
        text: 要搜索的文本（如文章标题+摘要或全文）
        entity_name: 要查找的实体名称
        context_chars: 每个匹配位置前后提取的字符数，默认250
        max_contexts: 最多返回的上下文片段数，默认5

    Returns:
        str: 编号格式的上下文片段，如果没有找到则返回空字符串
    """
    if not text or not entity_name:
        return ""

    contexts = []
    lower_text = text.lower()
    lower_entity = entity_name.lower()

    start = 0
    while len(contexts) < max_contexts:
        pos = lower_text.find(lower_entity, start)
        if pos == -1:
            break

        # 提取前后各 context_chars 个字符
        ctx_start = max(0, pos - context_chars)
        ctx_end = min(len(text), pos + len(entity_name) + context_chars)

        # 尝试扩展到句子边界（向前找句号/换行，向后找句号/换行）
        # 向前查找句子开始
        if ctx_start > 0:
            for i in range(ctx_start, max(0, ctx_start - 50), -1):
                if text[i] in '.。\n':
                    ctx_start = i + 1
                    break

        # 向后查找句子结束
        if ctx_end < len(text):
            for i in range(ctx_end, min(len(text), ctx_end + 50)):
                if text[i] in '.。\n':
                    ctx_end = i + 1
                    break

        context_text = text[ctx_start:ctx_end].strip()
        if context_text:
            contexts.append(context_text)

        start = pos + len(entity_name)

    if not contexts:
        return ""

    # 只有一个上下文时，直接返回
    if len(contexts) == 1:
        return contexts[0]

    # 多个上下文时，用编号格式
    result = []
    for i, ctx in enumerate(contexts, 1):
        result.append(f"[{i}] {ctx}")

    return "\n".join(result)