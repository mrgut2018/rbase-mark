from typing import Optional, List
from deepsearcher.rbase.terms import Term, Concept
from deepsearcher import configuration
from deepsearcher.db.mysql_connection import get_mysql_connection

def load_terms_by_concept_id(concept_id: int, except_term_id: Optional[int] = None) -> List[Term]:
    """
    Load classifier by id
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            if except_term_id:
                sql = """SELECT * FROM term 
                WHERE concept_id = %s AND status = 10 AND id != %s
                """
                cursor.execute(sql, (concept_id, except_term_id))
            else:
                sql = "SELECT * FROM term WHERE concept_id = %s AND status = 10"
                cursor.execute(sql, (concept_id,))
            results = cursor.fetchall()
            return [Term(**result) for result in results]
    except Exception as e:
        raise Exception(f"Failed to load terms by concept id({concept_id}): {e}")

def load_term_by_value(term_value: str) -> Optional[Term]:
    """
    Load term by value
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = "SELECT * FROM term WHERE name = %s AND status = 10"
            cursor.execute(sql, (term_value,))
            result = cursor.fetchone()
            if result:
                return Term(**result)
            return None
    except Exception as e:
        raise Exception(f"Failed to load term by value({term_value}): {e}")

def concept_i18n_data(concept_id: int) -> dict:
    """
    Load concept i18n data
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = "SELECT id, name, cname FROM concept WHERE id = %s AND status = 10"
            cursor.execute(sql, (concept_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'en': result['name'],
                    'zh': result['cname']
                }
            else:
                return {}
    except Exception as e:
        raise Exception(f"Failed to load concept i18n data for concept id({concept_id}): {e}")

def term_i18n_data(term_id: int) -> dict:
    """
    Load term i18n data
    """
    try:
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = "SELECT id, name, concept_id FROM term WHERE id = %s AND status = 10"
            cursor.execute(sql, (term_id,))
            result = cursor.fetchone()
            if result:
                if result['concept_id']:
                    return concept_i18n_data(result['concept_id'])
            return {}
    except Exception as e:
        raise Exception(f"Failed to load term i18n data for term id({term_id}): {e}")

def load_concept_by_id(concept_id: int) -> Optional[Concept]:
    """
    Load concept by id

    Args:
        concept_id: concept ID

    Returns:
        Concept: concept object, returns None if not found
    """
    try:
        from deepsearcher.rbase.terms import Concept
        connection = get_mysql_connection(configuration.config.rbase_settings.get("database"))
        with connection.cursor() as cursor:
            sql = """SELECT id, name, cname, abbr_name, abbr_cname, intro,
                              concept_term_id, concept_term_id2, concept_term_id3,
                              is_virtual, is_preferred_concept, preferred_concept_id,
                              concept_relation, status, related_article_count,
                              widely_related_article_count, created, modified
                       FROM concept WHERE id = %s"""
            cursor.execute(sql, (concept_id,))
            result = cursor.fetchone()
            if result:
                result['name'] = result['name'] or ""
                return Concept(**result)
            return None
    except Exception as e:
        raise Exception(f"Failed to load concept by id({concept_id}): {e}")