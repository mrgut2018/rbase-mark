"""
Rbase Database Utilities

This package contains database utility functions for Rbase.
"""

from .ai_content import (
    get_response_by_request_hash,
    save_request_to_db,
    save_response_to_db,
)
from .discuss import (
    update_ai_content_to_discuss,
    update_discuss_thread_depth,
    get_discuss_thread_by_request_hash,
    is_thread_has_summary,
    get_discuss_thread_by_id,
    save_discuss_thread,
    update_discuss_status,
    get_discuss_thread_by_uuid,
    get_discuss_by_uuid,
    get_discuss_by_reply_uuid,
    save_discuss,
    get_discuss_in_thread,
    get_discuss_thread_history,
    list_discuss_in_thread,
    compose_discuss_thread_title, 
    compose_discuss_thread_title_by_discuss, 
    update_discuss_thread_title,
    check_discuss_thread_favoritable,
    favorite_discuss_threads,
    list_discuss_threads,
    check_discuss_thread_hideable,
    hide_discuss_threads,
)
from .sync.classify import (
    load_classifier_by_id,
    load_classifiers_by_ids,
    load_classifier_by_alias,
    load_classifier_value_by_id,
    load_classifier_values_by_entity_name,
    load_classifier_value_by_concept_id,
    load_classifier_value_by_vector_db,
    load_classifier_values_by_vector_db,
    load_classifier_value_route,
    extract_entity_context,
    list_classifier_values_by_classifier_id,
    list_classifier_values_by_value,
    list_classifier_results_by_article_id,
    check_classifier_prerequisite_values_in,
    check_classifier_prerequisite_status_in,
    create_label_raw_article_task,
    create_label_raw_article_task_item,
    update_task_item_status,
    save_classification_result,
    update_task_status,
)
from .sync.metadata import (
    load_terms_by_concept_id,
    load_concept_by_id,
    load_term_by_value,
    concept_i18n_data,
    term_i18n_data,
)
from .metadata import (
    get_term_tree_nodes,
    get_base_by_id,
    get_base_category_by_id,
)
from .utils import get_request_hash, load_article_full_text

__all__ = [
    # AI Content
    'get_response_by_request_hash',
    'save_request_to_db',
    'save_response_to_db',
    
    # Discuss
    'update_ai_content_to_discuss',
    'update_discuss_thread_depth',
    'get_discuss_thread_by_request_hash',
    'is_thread_has_summary',
    'get_discuss_thread_by_id',
    'save_discuss_thread',
    'get_discuss_thread_by_uuid',
    'get_discuss_by_uuid',
    'save_discuss',
    'get_discuss_in_thread',
    'get_discuss_thread_history',
    'list_discuss_in_thread',
    
    # Classify
    'load_classifier_by_id',
    'load_classifiers_by_ids',
    'load_classifier_by_alias',
    'load_classifier_value_by_id',
    'load_classifier_values_by_entity_name',
    'load_classifier_value_by_concept_id',
    'load_classifier_value_by_vector_db',
    'load_classifier_values_by_vector_db',
    'load_classifier_value_route',
    'extract_entity_context',
    'list_classifier_values_by_classifier_id',
    'list_classifier_values_by_value',
    'list_classifier_results_by_article_id',
    'check_classifier_prerequisite_values_in',
    'check_classifier_prerequisite_status_in',
    'create_label_raw_article_task',
    'create_label_raw_article_task_item',
    'update_task_item_status',
    'save_classification_result',
    'update_task_status',
    
    # Metadata
    'get_term_tree_nodes',
    'get_base_by_id',
    'get_base_category_by_id',
    'load_concept_by_id',
    'term_i18n_data',
    'concept_i18n_data',
    
    # Utils
    'get_request_hash',
    'load_article_full_text',

    # Terms
    'load_terms_by_concept_id',
    'load_term_by_value',
] 