"""
Discussion Database Operations

This module contains database operations for discussions.
"""

import json
from datetime import datetime, timedelta
from deepsearcher import configuration
from deepsearcher.api.models import HistoryDiscussTheadEntity
from deepsearcher.rbase_db_loading import load_article_by_article_id
from deepsearcher.db.async_mysql_connection import get_mysql_pool
from deepsearcher.tools import log
from deepsearcher.api.rbase_util.metadata import get_term_tree_nodes, get_base_by_id, get_base_category_by_id
from deepsearcher.rbase.ai_models import (
    DiscussThread,
    Discuss,
    DiscussRole,
    RelatedType,
    AIResponseStatus,
    AIContentResponse,
)

COMPOSE_DISCUSS_THREAD_TITLE_PROMPT = """
用户正在与AI进行讨论，我已知他们讨论的内容是：{title}。
请为这次讨论起一个中文标题，标题简洁扼要，长度尽可能不超过10个字。直接回复标题，不要提供任何辅助性内容。
"""

COMPOSE_DISCUSS_THREAD_TITLE_BY_DISCUSS_PROMPT = """
用户正在与AI进行讨论，用户询问的问题是：{question}。
请为这次讨论起一个中文标题，标题简洁扼要，长度尽可能不超过10个字。直接回复标题，不要提供任何辅助性内容。
"""

def _build_sql_by_user_hash_and_user_id(sql: str, sql_params: list, user_hash: str, user_id: int, **kwargs) -> tuple[str, list]:
    """
    Build SQL by user hash and user id for discuss related query
    """
    user_hash_key = kwargs.get("user_hash_key", "user_hash")
    user_id_key = kwargs.get("user_id_key", "user_id")
    params = sql_params.copy()
    if user_id and user_id > 0:
        if user_hash:
            sql += f" AND ({user_hash_key} = %s OR {user_id_key} = %s)"
            params.append(user_hash)
            params.append(user_id)
        else:
            sql += f" AND {user_id_key} = %s"
            params.append(user_id)
    elif user_hash:
        sql += f" AND {user_hash_key} = %s"
        params.append(user_hash)

    return sql, params

async def update_ai_content_to_discuss(response: AIContentResponse, thread_uuid: str, reply_uuid: str):
    """
    Update AI content to discuss

    Args:
        response: AIContentResponse object
        thread_uuid: Thread UUID
        reply_uuid: Reply UUID
    """
    if not thread_uuid:
        return

    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "SELECT * FROM discuss_thread WHERE uuid = %s"
                await cursor.execute(sql, (thread_uuid,))
                thread = await cursor.fetchone()
                if not thread:
                    raise Exception(f"Failed to get discuss thread by uuid: {thread_uuid}")
                if thread["depth"] > 0 and reply_uuid:
                    sql = "SELECT * FROM discuss WHERE uuid = %s"
                    await cursor.execute(sql, (reply_uuid,))
                    reply = await cursor.fetchone()
                    if not reply:
                        raise Exception(f"Failed to get discuss by uuid: {reply_uuid}")
                else:
                    reply = None

                discuss = Discuss(
                    related_type=RelatedType(thread["related_type"]),
                    thread_id=thread["id"],
                    thread_uuid=thread["uuid"],
                    reply_id=reply["id"] if reply else None,
                    reply_uuid=reply["uuid"] if reply else None,
                    depth=reply["depth"] + 1 if reply else thread["depth"] + 1,
                    content=response.content,
                    tokens=response.tokens,
                    usage=response.usage,
                    is_summary=1,
                    role=DiscussRole.ASSISTANT,
                    status=AIResponseStatus.FINISHED,
                    created=datetime.now(),
                    modified=datetime.now()
                )
                discuss.create_uuid()
                await save_discuss(discuss)
                await update_discuss_thread_depth(thread_uuid, discuss.depth, discuss.uuid)
    except Exception as e:
        raise Exception(f"Failed to update ai content to discuss: {e}")

async def update_discuss_thread_depth(thread_uuid: str, depth: int, discuss_uuid: str = None):
    """
    Update discuss thread depth
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await conn.begin()
                try:
                    # Update discuss thread depth
                    sql = "UPDATE discuss_thread SET depth = %s WHERE uuid = %s"
                    await cursor.execute(sql, (depth, thread_uuid))
                    
                    # If discuss_uuid is provided, update other discuss content status to deprecated
                    if discuss_uuid:
                        sql = "UPDATE discuss SET status = %s WHERE uuid <> %s AND thread_uuid = %s AND depth = %s"
                        await cursor.execute(sql, (AIResponseStatus.DEPRECATED.value, discuss_uuid, thread_uuid, depth))
                    
                    await conn.commit()
                except Exception as e:
                    # Rollback transaction on error
                    await conn.rollback()
                    raise e
    except Exception as e:
        raise Exception(f"Failed to update discuss thread depth: {e}")

async def get_discuss_thread_by_request_hash(request_hash: str, user_hash: str, **kwargs) -> DiscussThread:
    """
    Get discussion thread by request hash and user hash

    Args:
        request_hash: Request hash value
        user_hash: User hash value

    Returns:
        DiscussThread: Discussion thread object, returns None if not found
    """
    try:
        active_days = kwargs.get("active_days", 0)
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                SELECT * FROM discuss_thread WHERE request_hash = %s AND user_hash = %s AND is_hidden = 0
                """
                params = [request_hash, user_hash]
                if active_days > 0:
                    sql += " AND modified > %s"
                    params.append(datetime.now() - timedelta(days=active_days))
                sql += " ORDER BY modified DESC LIMIT 1"
                await cursor.execute(sql, params)
                result = await cursor.fetchone()
                if not result:
                    return None
                result["params"] = json.loads(result["params"]) if result["params"] else {}
                result["related_type"] = RelatedType(result["related_type"])
                return DiscussThread(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss thread by request hash: {e}")

async def is_thread_has_summary(thread_id: int) -> bool:
    """
    Check if the discussion thread has a summary
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                SELECT COUNT(*) as cnt FROM discuss WHERE thread_id = %s AND is_summary = 1
                """
                await cursor.execute(sql, (thread_id,))
                result = await cursor.fetchone()
                return result["cnt"] > 0
    except Exception as e:
        raise Exception(f"Failed to check if thread has summary: {e}")

async def get_discuss_thread_by_id(thread_id: int) -> DiscussThread:
    """
    Get discussion thread by ID

    Args:
        thread_id: Discussion thread ID

    Returns:
        DiscussThread: Discussion thread object, returns None if not found
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                SELECT * FROM discuss_thread WHERE id = %s AND is_hidden = 0
                """
                await cursor.execute(sql, (thread_id,))
                result = await cursor.fetchone()
                if not result:
                    return None
                result["params"] = json.loads(result["params"]) if result["params"] else {}
                result["related_type"] = RelatedType(result["related_type"])
                return DiscussThread(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss thread by id: {e}")

async def save_discuss_thread(discuss_thread: DiscussThread) -> int:
    """
    Save discussion thread to database

    Args:
        discuss_thread: DiscussThread object

    Returns:
        int: Inserted record ID
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                if discuss_thread.id == 0:
                    sql = """
                    INSERT INTO discuss_thread (uuid, title, related_type, params, request_hash, user_hash, user_id, depth, background, is_hidden, created, modified)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    await cursor.execute(sql, (
                        discuss_thread.uuid,
                        discuss_thread.title,
                        discuss_thread.related_type.value,
                        json.dumps(discuss_thread.params),
                        discuss_thread.request_hash,
                        discuss_thread.user_hash,
                        discuss_thread.user_id,
                        discuss_thread.depth,
                        discuss_thread.background,
                        discuss_thread.is_hidden,
                        discuss_thread.created,
                        discuss_thread.modified
                    ))
                    return cursor.lastrowid
                else:
                    sql = """
                    UPDATE discuss_thread SET
                        title = %s,
                        relate_type = %s,
                        params = %s,
                        request_hash = %s,
                        user_hash = %s,
                        user_id = %s,
                        depth = %s,
                        background = %s,
                        is_hidden = %s,
                    WHERE id = %s
                    """
                    await cursor.execute(sql, (
                        discuss_thread.title,
                        discuss_thread.relate_type.value,
                        json.dumps(discuss_thread.params),
                        discuss_thread.request_hash,
                        discuss_thread.user_hash,
                        discuss_thread.user_id,
                        discuss_thread.depth,
                        discuss_thread.background,
                        discuss_thread.is_hidden,
                        discuss_thread.id
                    ))
                    return discuss_thread.id
    except Exception as e:
        raise Exception(f"Failed to save discuss thread to db: {e}")

async def get_discuss_thread_by_uuid(thread_uuid: str, **kwargs) -> DiscussThread:
    """
    Get discussion thread by topic UUID
    
    Args:
        thread_uuid: Topic UUID
        
    Returns:
        DiscussThread: Discussion thread object, returns None if not found
    """
    user_hash = kwargs.get("user_hash", None)
    user_id = kwargs.get("user_id", None)
    active_days = kwargs.get("active_days", 0)
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                params = [thread_uuid]
                sql = """
                SELECT * FROM discuss_thread WHERE uuid = %s AND is_hidden = 0
                """
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                if active_days > 0:
                    sql += " AND modified > %s"
                    params.append(datetime.now() - timedelta(days=active_days))
                await cursor.execute(sql, params)
                result = await cursor.fetchone()
                if not result:
                    return None
                result["related_type"] = RelatedType(result["related_type"])
                result["params"] = json.loads(result["params"]) if result["params"] else {}
                return DiscussThread(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss thread: {e}")

async def get_discuss_by_uuid(uuid: str) -> Discuss:
    """
    Get discussion content by content UUID
    
    Args:
        content_uuid: Content UUID
        
    Returns:
        DiscussContent: Discussion content object, returns None if not found
    """
    if not uuid:
        return None
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                SELECT * FROM discuss WHERE uuid = %s AND is_hidden = 0 AND status = %s
                """
                await cursor.execute(sql, (uuid, AIResponseStatus.FINISHED.value))
                result = await cursor.fetchone()
                if not result:
                    return None
                result["related_type"] = RelatedType(result["related_type"])
                result["tokens"] = json.loads(result["tokens"]) if result["tokens"] else {}
                result["usage"] = json.loads(result["usage"]) if result["usage"] else {}
                result["role"] = DiscussRole(result["role"])
                result["status"] = AIResponseStatus(result["status"])
                return Discuss(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss content: {e}")

async def get_discuss_by_reply_uuid(reply_uuid: str, thread_uuid: str, user_hash: str, user_id: int) -> Discuss:
    """
    Get discussion content by reply UUID
    
    Args:
        reply_uuid: Reply UUID
        thread_uuid: Thread UUID
        user_hash: User hash
        user_id: User ID
        
    Returns:
        DiscussContent: Discussion content object, returns None if not found
    """
    if not reply_uuid or not thread_uuid:
        return None
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                SELECT d.* FROM discuss d, discuss_thread t WHERE d.thread_id=t.id AND 
                  d.reply_uuid = %s AND t.uuid = %s AND d.is_hidden = 0 AND d.status <> 0
                """
                params = [reply_uuid, thread_uuid]
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id, user_hash_key="t.user_hash", user_id_key="t.user_id")
                sql += " ORDER BY `status` ASC, `modified` DESC"
                await cursor.execute(sql, params)
                result = await cursor.fetchone()
                if not result:
                    return None
                result["related_type"] = RelatedType(result["related_type"])
                result["tokens"] = json.loads(result["tokens"]) if result["tokens"] else {}
                result["usage"] = json.loads(result["usage"]) if result["usage"] else {}
                result["role"] = DiscussRole(result["role"])
                result["status"] = AIResponseStatus(result["status"])
                return Discuss(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss content: {e}")

async def save_discuss(discuss: Discuss, status_in: AIResponseStatus = None) -> int:
    """
    Save discussion content to database
    
    Args:
        discuss_content: Discussion content object
        status_in: Discussion status must be in the given status, when update data.
        
    Returns:
        int: Inserted record ID
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                if discuss.id == 0:
                    sql = """
                    INSERT INTO discuss (
                        uuid, related_type, thread_id, thread_uuid, reply_id, reply_uuid, depth, 
                        content, role, tokens, `usage`, user_id, is_hidden, `like`, trample, 
                        is_summary, status, created, modified
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, 
                        %s, %s, %s, %s, %s, %s, %s, %s, 
                        %s, %s, %s, %s
                    )
                    """
                    await cursor.execute(sql, (
                        discuss.uuid,
                        discuss.related_type.value,
                        discuss.thread_id,
                        discuss.thread_uuid,
                        discuss.reply_id,
                        discuss.reply_uuid,
                        discuss.depth,
                        discuss.content,
                        discuss.role.value,
                        json.dumps(discuss.tokens),
                        json.dumps(discuss.usage),
                        discuss.user_id,
                        discuss.is_hidden,
                        discuss.like,
                        discuss.trample,
                        discuss.is_summary,
                        discuss.status.value,
                        discuss.created,
                        discuss.modified
                    ))
                    return cursor.lastrowid
                else:
                    sql = """
                    UPDATE discuss SET
                        content = %s,
                        role = %s,
                        tokens = %s,
                        `usage` = %s,
                        is_hidden = %s,
                        `like` = %s,
                        trample = %s,
                        is_summary = %s,
                        status = %s
                    WHERE id = %s
                    """
                    params = [
                        discuss.content,
                        discuss.role.value,
                        json.dumps(discuss.tokens),
                        json.dumps(discuss.usage),
                        discuss.is_hidden,
                        discuss.like,
                        discuss.trample,
                        discuss.is_summary,
                        discuss.status.value,
                        discuss.id
                    ]
                    if status_in:
                        sql += " AND status = %s"
                        params.append(status_in.value)
                    await cursor.execute(sql, params)
                    return discuss.id
    except Exception as e:
        raise Exception(f"Failed to save discuss content: {e}")

async def update_discuss_status(discuss_uuid: str, status: AIResponseStatus) -> int:
    """
    Update discussion content status
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "UPDATE discuss SET status = %s WHERE uuid = %s"
                await cursor.execute(sql, (status.value, discuss_uuid))
                return cursor.rowcount
    except Exception as e:
        raise Exception(f"Failed to update discuss status: {e}")

async def get_discuss_in_thread(thread_uuid: str, discuss_uuid: str = None, **kwargs) -> Discuss:
    """
    Get discussion record by discuss UUID within the thread of thread_uuid.
    If is_summary is True, get the summary record. 
    If discuss_uuid is not None, get the specific record.
    
    Args:
        thread_uuid: Topic UUID
        discuss_uuid: Discussion UUID
        is_summary: Whether to get the summary record
    Returns:
        Discuss: Discussion content object, returns None if not found
    """
    if not kwargs and not discuss_uuid:
        return None
    
    is_summary = kwargs.get("is_summary", 0)
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "SELECT * FROM discuss WHERE thread_uuid = %s AND is_hidden = 0 AND status = %s "
                params = [thread_uuid, AIResponseStatus.FINISHED.value]
                if is_summary:
                    sql += "AND is_summary = 1"
                if discuss_uuid:
                    sql += "AND uuid = %s"
                    params.append(discuss_uuid)
                await cursor.execute(sql, params)
                result = await cursor.fetchone()
                if not result:
                    return None
                result["tokens"] = json.loads(result["tokens"]) if result["tokens"] else {}
                result["usage"] = json.loads(result["usage"]) if result["usage"] else {}
                result["status"] = AIResponseStatus(result["status"])
                return Discuss(**result)
    except Exception as e:
        raise Exception(f"Failed to get discuss content list: {e}")

async def get_discuss_thread_history(thread_id: int, reply_id: int, limit: int = 10, **kwargs) -> list:
    """
    Get discussion history records
    
    Args:
        thread_id: Discussion topic ID
        reply_id: Current reply ID
        limit: Limit on number of history records to retrieve
        
    Returns:
        list: History records list, sorted by time in ascending order, format as [{"role": "user|assistant", "content": "content"}]
    """
    role = kwargs.get("role", None)
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Get history records before current discussion node
                params = [thread_id, AIResponseStatus.FINISHED.value]
                sql = """
                SELECT id, role, content FROM discuss 
                WHERE thread_id = %s AND is_hidden = 0 AND status = %s
                """
                if reply_id > 0:
                    sql += " AND id <= %s"
                    params.append(reply_id)
                if role:
                    sql += " AND role = %s"
                    params.append(role.value)

                sql += "\nORDER BY id DESC LIMIT %s"
                params.append(limit)
                await cursor.execute(sql, params)
                results = await cursor.fetchall()
                
                # Convert format and sort by time
                history = []
                for result in sorted(results, key=lambda x: x["id"]):
                    history.append({
                        "role": result["role"],
                        "content": result["content"]
                    })
                
                return history
    except Exception as e:
        log.error(f"Failed to get discussion history records: {e}")
        return []

async def list_discuss_in_thread(thread_uuid: str, from_depth: int, limit: int, sort_asc: bool = True) -> list[Discuss]:
    """
    获取指定讨论主题中的讨论内容列表
    
    Args:
        thread_uuid: 讨论主题UUID
        from_depth: 起始深度
        limit: 获取条数
        sort_asc: 是否按深度升序排序
        
    Returns:
        list[Discuss]: 讨论内容列表
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 构建SQL查询
                sql = """
                SELECT * FROM discuss 
                WHERE thread_uuid = %s AND is_hidden = 0 AND status in (%s, %s)
                """
                params = [thread_uuid, AIResponseStatus.FINISHED.value, AIResponseStatus.MANUALLY_FINISHED.value]
                
                # 添加深度和排序条件
                if sort_asc:
                    sql += " AND depth >= %s ORDER BY depth ASC, created ASC LIMIT %s"
                else:
                    sql += " AND depth <= %s ORDER BY depth DESC, created DESC LIMIT %s"

                params.extend([from_depth, limit])
                
                # 执行查询
                await cursor.execute(sql, params)
                results = await cursor.fetchall()
                
                # 转换结果
                discuss_list = []
                for result in results:
                    result["tokens"] = json.loads(result["tokens"]) if result["tokens"] else {}
                    result["usage"] = json.loads(result["usage"]) if result["usage"] else {}
                    result["role"] = DiscussRole(result["role"])
                    result["status"] = AIResponseStatus(result["status"])
                    discuss_list.append(Discuss(**result))
                
                return discuss_list
    except Exception as e:
        raise Exception(f"Failed to list discuss in thread: {e}") 


async def compose_discuss_thread_title(thread: DiscussThread) -> str:
    """
    Compose discuss thread title with thread params

    Args:
        thread: DiscussThread object

    Returns:
        str: Composed title
    """
    title = ""
    term_tree_node_ids = thread.params.get("term_tree_node_ids", [])
    if len(term_tree_node_ids) > 0:
        nodes = await get_term_tree_nodes(term_tree_node_ids[:1])
        if nodes:
            title = f"关于{nodes[0].node_concept_name}的讨论"
    else:
        if thread.related_type == RelatedType.CHANNEL:
            channel_id = thread.params.get("channel_id", 0)
            if channel_id > 0:
                channel = await get_base_by_id(channel_id)
                if channel:
                    title = f"关于{channel.name}的讨论"
        elif thread.related_type == RelatedType.COLUMN:
            column_id = thread.params.get("column_id", 0)
            if column_id > 0:
                column = await get_base_category_by_id(column_id)
                if column:
                    title = f"关于{column.name}的讨论"
        elif thread.related_type == RelatedType.ARTICLE:
            article_id = thread.params.get("article_id", 0)
            if article_id > 0:
                article = await load_article_by_article_id(article_id)
                if article:
                    title = f"关于{article.title}的讨论"

    if not title:
        title = "新的Rbase讨论"
    else:
        response = configuration.llm.chat([{
            "role": "user", 
            "content": COMPOSE_DISCUSS_THREAD_TITLE_PROMPT.format(title=title),
        }])
        title = response.content

    return title

async def compose_discuss_thread_title_by_discuss(discuss: Discuss) -> str:
    """
    Compose discuss thread title by discuss content

    Args:
        discuss: Discuss object

    Returns:
        str: Composed title
    """
    if discuss.content == "":
        return ""
    response = configuration.llm.chat(
        [{
            "role": "user",
            "content": COMPOSE_DISCUSS_THREAD_TITLE_BY_DISCUSS_PROMPT.format(question=discuss.content),
        }]
    )
    return response.content

async def update_discuss_thread_title(thread_uuid: str, title: str):
    """
    Update discuss thread title
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "UPDATE discuss_thread SET title = %s, is_title_modified = 1 WHERE uuid = %s"
                await cursor.execute(sql, (title, thread_uuid))
    except Exception as e:
        raise Exception(f"Failed to update discuss thread title: {e}")

async def user_favorite_thread_count(user_hash: str, user_id: int) -> int:
    """
    Get user favorite thread count
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "SELECT COUNT(*) AS cnt FROM discuss_thread WHERE is_favorite=1 "
                params = []
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                await cursor.execute(sql, params)
                result = await cursor.fetchone()
                return result["cnt"] if result else 0
    except Exception as e:
        raise Exception(f"Failed to get user favorite thread count: {e}")

async def check_discuss_thread_favoritable(thread_uuids: list[str], user_hash: str, user_id: int) -> list[str]:
    """
    Check if the discuss thread is favoritable
    """
    try:
        if len(thread_uuids) == 0:
            return []
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                has_favorite_count = await user_favorite_thread_count(user_hash, user_id)
                can_favorite_count = configuration.config.rbase_settings.get("discuss_thread_favorite_limit", 3) - has_favorite_count
                if can_favorite_count <= 0:
                    return []
                can_favorite_count = min(can_favorite_count, len(thread_uuids))
                placeholders = ','.join(['%s'] * can_favorite_count)
                sql = f"SELECT uuid FROM discuss_thread WHERE uuid IN ({placeholders}) "
                params = thread_uuids[:can_favorite_count]
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                sql += " LIMIT %s"
                params.append(can_favorite_count)
                await cursor.execute(sql, params)
                results = await cursor.fetchall()
                return [result["uuid"] for result in results]
    except Exception as e:
        raise Exception(f"Failed to check discuss thread favoritable: {e}")

async def favorite_discuss_threads(thread_uuids: list[str], user_hash: str, user_id: int, is_cancel: bool = False) -> int:
    """
    Favorite discuss threads

    Args:
        thread_uuids: List of thread UUIDs
        user_hash: User hash
        user_id: User ID
        is_cancel: Whether to cancel favorite

    Returns:
        int: Number of threads favorited
    """
    try:
        if len(thread_uuids) == 0:
            return 0
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                is_favorite_value = 1 if not is_cancel else 0
                placeholders = ','.join(['%s'] * len(thread_uuids))
                sql = f"UPDATE discuss_thread SET is_favorite = %s, user_id = %s WHERE uuid IN ({placeholders})"
                params = [is_favorite_value, user_id] + thread_uuids
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                await cursor.execute(sql, params)
                return cursor.rowcount
    except Exception as e:
        raise Exception(f"Failed to favorite discuss threads: {e}")

async def check_discuss_thread_hideable(thread_uuids: list[str], user_hash: str, user_id: int) -> list[str]:
    """
    Check if the discuss thread is hideable
    """
    try:
        if len(thread_uuids) == 0:
            return []
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(thread_uuids))
                sql = f"SELECT uuid FROM discuss_thread WHERE uuid IN ({placeholders}) AND is_hidden=0 "
                params = thread_uuids
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                await cursor.execute(sql, params)
                results = await cursor.fetchall()
                return [result["uuid"] for result in results]
    except Exception as e:
        raise Exception(f"Failed to check discuss thread hideable: {e}")

async def hide_discuss_threads(thread_uuids: list[str], user_hash: str, user_id: int) -> int:
    """
    Hide discuss threads
    """
    try:
        if len(thread_uuids) == 0:
            return 0
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(thread_uuids))
                sql = f"UPDATE discuss_thread SET is_hidden = 1, is_favorite = 0 WHERE uuid IN ({placeholders})"
                params = thread_uuids.copy()  
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                await cursor.execute(sql, params)
                return cursor.rowcount
    except Exception as e:
        raise Exception(f"Failed to hide discuss threads: {e}")

async def list_discuss_threads(user_hash: str, user_id: int, limit: int, offset: int, is_favorite: int) -> tuple[list[HistoryDiscussTheadEntity], int]:
    """
    List discuss threads
    """
    try:
        pool = await get_mysql_pool(configuration.config.rbase_settings.get("database"))
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "SELECT uuid, depth, title, params, user_hash, user_id, is_favorite, is_title_modified, created, modified FROM discuss_thread WHERE is_hidden = 0 AND is_favorite = %s"
                sql_total = "SELECT COUNT(*) AS total FROM discuss_thread WHERE is_hidden = 0 AND is_favorite = %s"
                params = [is_favorite]
                sql, params = _build_sql_by_user_hash_and_user_id(sql, params, user_hash, user_id)
                sql_total, _ = _build_sql_by_user_hash_and_user_id(sql_total, params, user_hash, user_id)
                sql += " ORDER BY created DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                await cursor.execute(sql, params)
                results = await cursor.fetchall()
                result_list = []
                for result in results:
                    if result["params"]:
                        result_params = json.loads(result["params"])
                    else:
                        result_params = {}
                    result_list.append(HistoryDiscussTheadEntity(
                        uuid=result["uuid"],
                        depth=result["depth"],
                        title=result["title"],
                        created=int(result["created"].timestamp()) if isinstance(result["created"], datetime) else result["created"],
                        modified=int(result["modified"].timestamp()) if isinstance(result["modified"], datetime) else result["modified"],
                        user_hash=result["user_hash"],
                        user_id=result["user_id"],
                        is_favorite=result["is_favorite"],
                        is_title_modified=result["is_title_modified"],
                        article_count=result_params.get("article_count", 0),
                        sub_title=result_params.get("sub_title", ""),
                        params=result_params
                    ))

                await cursor.execute(sql_total, params[0:-2])
                total_result = await cursor.fetchone()
                total = total_result["total"] if total_result else 0
                return result_list, total
    except Exception as e:
        raise Exception(f"Failed to list discuss threads: {e}")
