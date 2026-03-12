"""
Discussion Routes

This module contains routes and functions for handling discussions.
"""

import json
import time
from typing import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from deepsearcher import configuration
from deepsearcher.api.models import (
    RelatedType, SortType,
    DiscussCreateRequest, DiscussCreateResponse,
    DiscussPostRequest, DiscussPostResponse,
    DiscussAIReplyRequest, CloseAIReplyResponse,
    DiscussListRequest, DiscussListResponse,
    DiscussListEntity, ExceptionResponse,
    RefreshThreadTitleRequest, RefreshThreadTitleResponse, UpdateThreadTitleRequest,
    FavoriteThreadRequest, FavoriteThreadResponse,
    HideThreadRequest, HideThreadResponse,
    HistoryDiscussThreadsRequest, HistoryDiscussThreadsResponse,
)
from deepsearcher.api.rbase_util import (
    get_discuss_thread_by_request_hash, get_discuss_thread_by_uuid, list_discuss_threads,
    save_discuss_thread,
    is_thread_has_summary,
    get_discuss_by_uuid, get_discuss_by_reply_uuid, get_discuss_in_thread, list_discuss_in_thread,
    save_discuss, update_discuss_status,
    update_discuss_thread_depth,
    get_discuss_thread_history,
    get_base_by_id, get_base_category_by_id,
    compose_discuss_thread_title, compose_discuss_thread_title_by_discuss, update_discuss_thread_title, 
    check_discuss_thread_favoritable, favorite_discuss_threads,
    check_discuss_thread_hideable, hide_discuss_threads,
)
from deepsearcher.api.rbase_util.ai_content import save_ai_log 
from deepsearcher.agent.discuss_agent import DiscussAgent, ProgressHint
from deepsearcher.rbase.ai_models import (
    Discuss,
    DiscussThread,
    DiscussRole,
    AIResponseStatus,
    initialize_discuss_thread,
)
from deepsearcher.rbase_db_loading import load_articles_by_article_ids

router = APIRouter()

@router.post(
    "/discuss_create",
    summary="Discussion Topic Creation API",
    description="""
    Create a new discussion topic or return existing topic UUID.
    
    - Supports author, topic, and paper related types
    - Uses request_hash and user_hash to check for existing topics
    - Returns topic UUID
    """,
)
async def api_create_discuss_thread(request: DiscussCreateRequest):
    """
    Create a discussion topic or return existing topic UUID.

    Args:
        request (DiscussCreateRequest): Request parameters for creating discussion topic

    Returns:
        DiscussCreateResponse: Response containing topic UUID
    """
    try:
        discuss_thread = initialize_discuss_thread(request)
        active_days = configuration.config.rbase_settings.get("api", {}).get("discuss_thread_active_days", 30)
        if request.is_manually == 1:
            result = None
        else:
            result = await get_discuss_thread_by_request_hash(
                discuss_thread.request_hash, 
                discuss_thread.user_hash, 
                active_days=active_days)

        if result:
            # If exists, return history result directly
            has_summary = await is_thread_has_summary(result.id)
            if result.title == "":
                result.title = await compose_discuss_thread_title(result)
                await update_discuss_thread_title(result.uuid, result.title)
            return DiscussCreateResponse(
                code=0,
                message="success",
                thread_uuid=result.uuid,
                thread_title=result.title,
                depth=result.depth,
                has_summary=has_summary,
                is_title_modified=result.is_title_modified
            )
        else:
            # If not exists, create new thread
            if discuss_thread.title == "":
                discuss_thread.title = await compose_discuss_thread_title(discuss_thread)
            await save_discuss_thread(discuss_thread)
            return DiscussCreateResponse(
                code=0,
                message="success",
                thread_uuid=discuss_thread.uuid,
                thread_title=discuss_thread.title,
                depth=discuss_thread.depth,
                has_summary=False,
                is_title_modified=0
            )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.api_route(
    "/list_discuss",
    methods=["GET", "POST"],
    summary="List Discussion Topics API",
    description="""
    List discussion topics.
    
    - Supports author, topic, and paper related types
    - Optional cache usage
    - Supports streaming response
    - Supports both GET and POST methods
    """,
)
async def api_list_discuss(request: DiscussListRequest):
    """
    List discussion topics.

    Args:
        request (DiscussCreateRequest): Request parameters for listing discussion topics

    Returns:
        DiscussListResponse: Response containing discussion topics
    """
    try:
        # 1. 验证讨论话题是否存在
        thread = await get_discuss_thread_by_uuid(request.thread_uuid, 
                                                  user_hash=request.user_hash,
                                                  user_id=request.user_id)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"讨论话题不存在: {request.thread_uuid}"
                ).model_dump()
            )
        
        # 2. 获取讨论列表
        discuss_list = await list_discuss_in_thread(
            thread_uuid=request.thread_uuid,
            from_depth=request.from_depth,
            limit=request.limit,
            sort_asc=(request.sort == SortType.ASC)
        )
        
        # 3. 构建响应数据
        discuss_entities = []
        for discuss in discuss_list:
            entity = DiscussListEntity(
                uuid=discuss.uuid,
                depth=discuss.depth,
                content=discuss.content,
                created=int(discuss.created.timestamp()) if isinstance(discuss.created, datetime) else discuss.created,
                role=discuss.role.value,
                is_summary=discuss.is_summary,
                user_hash=request.user_hash,
                user_id=discuss.user_id if discuss.user_id else 0,
                user_name=discuss.user_name if hasattr(discuss, "user_name") else "",
                user_avatar=discuss.user_avatar if hasattr(discuss, "user_avatar") else "",
                status=discuss.status.value
            )
            discuss_entities.append(entity)
        
        # 4. 返回响应
        return DiscussListResponse(
            code=0,
            message="success",
            count=len(discuss_entities),
            discuss_entities=discuss_entities
        )
                
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/discuss_post",
    summary="Discussion Content Posting API",
    description="""
    Post discussion content to specified topic.
    
    - Specify topic UUID and reply UUID
    - User hash and ID must be provided
    - Returns success or failure status
    """,
)
async def api_post_discuss(request: DiscussPostRequest):
    """
    Post discussion content to specified topic.

    Args:
        request (DiscussPostRequest): Request parameters for posting discussion content

    Returns:
        DiscussPostResponse: Response containing posting result
    """
    try:
        # Verify if discussion topic exists
        thread = await get_discuss_thread_by_uuid(request.thread_uuid)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"讨论话题不存在: {request.thread_uuid}"
                ).model_dump()
            )
        
        # If reply UUID is specified, verify if reply object exists
        if request.reply_uuid and request.reply_uuid != "":
            reply_discuss = await get_discuss_by_uuid(request.reply_uuid)
            if not reply_discuss:
                return JSONResponse(
                    status_code=400,
                    content=ExceptionResponse(
                        code=400, 
                        message=f"回复对象不存在: {request.reply_uuid}"
                    ).model_dump()
                )
        else:
            reply_discuss = None
        
        # Create and save discussion content
        discuss = initialize_discuss_by_post_request(request, thread, reply_discuss)
        content_id = await save_discuss(discuss)
        if content_id:
            await update_discuss_thread_depth(thread.uuid, discuss.depth, discuss.uuid)
            return DiscussPostResponse(
                code=0,
                message="success",
                uuid=discuss.uuid,
                depth=discuss.depth
            )
        else:
            return JSONResponse(
                status_code=500,
                content=ExceptionResponse(code=500, message="保存讨论内容失败").model_dump()
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/ai_reply",
    summary="AI Discussion Reply API",
    description="""
    Automatically generate AI reply based on user discussion content.
    
    - Supports streaming output
    - Generates appropriate reply based on discussion topic and history
    - Returns generated reply content UUID
    """,
)
async def api_ai_reply_discuss(request: DiscussAIReplyRequest):
    """
    Generate AI reply for discussion content.

    Args:
        request (DiscussAIReplyRequest): AI reply discussion request

    Returns:
        StreamingResponse: Streaming response with AI generated reply content
    """
    try:
        # 1. Get discussion topic data
        thread = await get_discuss_thread_by_uuid(request.thread_uuid)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"讨论话题不存在: {request.thread_uuid}"
                ).model_dump()
            )
        
        # 2. Get discussion content to reply to
        reply_discuss = await get_discuss_by_uuid(request.reply_uuid)
        if not reply_discuss:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"回复对象不存在: {request.reply_uuid}"
                ).model_dump()
            )
        
        # Create AI reply discussion object
        ai_discuss = Discuss(
            uuid="",
            related_type=thread.related_type,
            thread_id=thread.id,
            thread_uuid=thread.uuid,
            reply_id=reply_discuss.id if reply_discuss else None,
            reply_uuid=reply_discuss.uuid if reply_discuss else None,
            depth=reply_discuss.depth + 1 if reply_discuss else 0,
            content="",  # Content will be updated during streaming generation
            role=DiscussRole.ASSISTANT,
            tokens={},
            usage={},
            status=AIResponseStatus.GENERATING,
            created=datetime.now(),
            modified=datetime.now(),
        )
        ai_discuss.create_uuid()
        
        # Save empty content, get ID, update content later
        discuss_id = await save_discuss(ai_discuss)
        ai_discuss.id = discuss_id
        
        # 3. Return streaming response
        return StreamingResponse(
            generate_ai_reply_stream(ai_discuss, thread, reply_discuss, request.further_question_count),
            media_type="text/event-stream"
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/close_ai_reply",
    summary="Close AI Discussion Reply API",
    description="""
    Close AI Discussion Reply.
    """,
)
async def api_close_ai_reply(request: DiscussAIReplyRequest):
    try:
        # 1. Get discussion topic data
        thread = await get_discuss_thread_by_uuid(request.thread_uuid)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"讨论话题不存在: {request.thread_uuid}"
                ).model_dump()
            )
        
        # 2. Get discussion content to reply to
        generating_discuss = await get_discuss_by_reply_uuid(request.reply_uuid, request.thread_uuid, request.user_hash, request.user_id)
        if not generating_discuss:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(
                    code=400, 
                    message=f"待回复讨论不存在: {request.reply_uuid}"
                ).model_dump()
            )
        if generating_discuss.status != AIResponseStatus.GENERATING:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"讨论不在生成中状态: {generating_discuss.uuid}").model_dump()
            )
        row = await update_discuss_status(generating_discuss.uuid, AIResponseStatus.MANUALLY_FINISHED)
        if row > 0:
            await update_discuss_thread_depth(thread.uuid, generating_discuss.depth, generating_discuss.uuid)
            return CloseAIReplyResponse(
                code=0,
                message="success",
                discuss_uuid=generating_discuss.uuid
            )
        else:
            return JSONResponse(
                status_code=500,
                content=ExceptionResponse(code=500, message="关闭回复讨论失败").model_dump()
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )
    
@router.post(
    "/refresh_discuss_thread_title",
    summary="Refresh Discussion Thread Title API",
    description="""
    Refresh discussion thread title.
    
    - Generates appropriate title based on discussion content
    - Returns generated title
    """,
)
async def api_refresh_discuss_thread_title(request: RefreshThreadTitleRequest):
    try:
        thread = await get_discuss_thread_by_uuid(request.thread_uuid, user_hash=request.user_hash, user_id=request.user_id)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"讨论话题不存在: {request.thread_uuid}").model_dump()
            )
        discuss = await get_discuss_by_uuid(request.discuss_uuid)
        if not discuss:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"讨论不存在: {request.discuss_uuid}").model_dump()
            )
        if discuss.thread_uuid != request.thread_uuid:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"讨论与话题不匹配: {request.thread_uuid}").model_dump()
            )
        title = await compose_discuss_thread_title_by_discuss(discuss)
        await update_discuss_thread_title(thread.uuid, title)
        return RefreshThreadTitleResponse(
            code=0,
            message="success",
            title=title
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/update_discuss_thread_title",
    summary="Refresh Discussion Thread Title API",
    description="""
    Refresh discussion thread title.
    
    - Generates appropriate title based on discussion content
    - Returns generated title
    """,
)
async def api_update_discuss_thread_title(request: UpdateThreadTitleRequest):
    try:
        if request.title == "":
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message="话题标题不能为空").model_dump()
            )

        thread = await get_discuss_thread_by_uuid(request.thread_uuid, user_hash=request.user_hash, user_id=request.user_id)
        if not thread:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"讨论话题不存在: {request.thread_uuid}").model_dump()
            )
        await update_discuss_thread_title(thread.uuid, request.title)
        return RefreshThreadTitleResponse(
            code=0,
            message="success",
            title=request.title
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/favorite_discuss_thread",
    summary="Favorite Discussion Thread API",
    description="""
    Favorite or cancel favorite discussion thread.
    
    - Favorite or cancel favorite discussion thread.
    - Returns favorite thread count
    """,
)
async def api_favorite_discuss_thread(request: FavoriteThreadRequest):
    try:
        if request.is_cancel == 0:
            thread_uuids = await check_discuss_thread_favoritable(request.discuss_thread_uuid_list, request.user_hash, request.user_id)
        else:
            thread_uuids = request.discuss_thread_uuid_list
        count = await favorite_discuss_threads(thread_uuids, request.user_hash, request.user_id, request.is_cancel)
        if count > 0:
            return FavoriteThreadResponse(
                code=0,
                message="success",
                discuss_thread_uuid_list=thread_uuids,
                count=count
            )
        else:
            return FavoriteThreadResponse(
                code=400,
                message="收藏失败，收藏数量达到上限",
                discuss_thread_uuid_list=[],
                count=0
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/history_discuss_threads",
    summary="History Discussion Threads API",
    description="""
    History discussion threads.
    """,
)
async def api_history_discuss_threads(request: HistoryDiscussThreadsRequest):
    limit = min(max(0, request.limit), 20)
    offset = max(0, request.offset)
    try:
        discuss_threads, total = await list_discuss_threads(request.user_hash, request.user_id, limit, offset, request.is_favorite)
        return HistoryDiscussThreadsResponse(
            code=0,
            message="success",
            discuss_threads=discuss_threads,
            limit=limit,
            offset=offset,
            total=total,
            count=len(discuss_threads)
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

@router.post(
    "/hide_discuss_thread",
    summary="Hide Discussion Thread API",
    description="""
    Hide discussion thread.
    
    - Hide discussion thread.
    - Returns hide thread count
    """,
)
async def api_hide_discuss_thread(request: HideThreadRequest):
    try:
        thread_uuids = await check_discuss_thread_hideable(request.discuss_thread_uuid_list, request.user_hash, request.user_id)
        count = await hide_discuss_threads(thread_uuids, request.user_hash, request.user_id)
        if count > 0:
            return HideThreadResponse(
                code=0,
                message="success",
                discuss_thread_uuid_list=thread_uuids,
                count=count
            )
        else:
            return HideThreadResponse(
                code=400,
                message="操作失败，请检查请求参数",
                discuss_thread_uuid_list=[],
                count=0
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

def initialize_discuss_by_post_request(request: DiscussPostRequest, thread: DiscussThread, replyDiscuss: Discuss) -> Discuss:
    """
    Initialize a discuss object based on the post request.
    """
    discuss = Discuss(
        uuid="",
        related_type=thread.related_type,
        thread_id=thread.id,
        thread_uuid=thread.uuid,
        reply_id=replyDiscuss.id if replyDiscuss else None,
        reply_uuid=replyDiscuss.uuid if replyDiscuss else None,
        depth=replyDiscuss.depth + 1 if replyDiscuss else thread.depth + 1,
        content=request.content,
        role=DiscussRole.USER,
        tokens={},
        usage={},
        is_summary=0,
        status=AIResponseStatus.FINISHED,
        user_id=request.user_id if request.user_id else None,
        created=datetime.now(),
        modified=datetime.now(),
    )
    discuss.create_uuid()
    return discuss

async def generate_ai_reply_stream(ai_discuss: Discuss, thread: DiscussThread, reply_discuss: Discuss, further_question_count: int = 3) -> AsyncGenerator[bytes, None]:
    """
    Generate streaming response for AI reply discussion content.

    Args:
        ai_discuss: AI reply discussion object
        thread: Discussion topic
        reply_discuss: Discussion content to reply to

    Yields:
        bytes: Streamed content chunks
    """
    try:
        # Create DiscussAgent instance
        discuss_agent = DiscussAgent(
            llm=configuration.writing_llm,
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
            embedding_model=configuration.embedding_model,
            vector_db=configuration.vector_db,
            verbose=configuration.config.rbase_settings.get("verbose", False)
        )
        
        # Send role message
        yield discuss_agent.build_role_json_str(ai_discuss.id)
        yield discuss_agent.build_progress_json_str(ProgressHint["LOAD_BACKGROUND"], ai_discuss.id)

        # Get discussion background information
        background = await get_thread_background(thread)
        # Get history records (last 10)
        history = await get_discuss_thread_history(thread.id, reply_discuss.id, limit=5, role=DiscussRole.USER)
        
        # Update AI discussion status
        ai_discuss.tokens["generating"] = []
        await save_discuss(ai_discuss)
        
        # Extract user query content
        query = reply_discuss.content
        
        chunk_cnt = configuration.config.rbase_settings.get("api", {}).get("discuss_chunk_cnt", 5)
        start_time = time.time()
        show_reasoning_content = configuration.config.rbase_settings.get("api", {}).get("show_reasoning_content", False)
        # Call DiscussAgent to generate reply
        async for chunk in discuss_agent.query_generator(
            query=query,
            background=background,
            history=history,
            top_k_per_section=chunk_cnt,
            discuss_uuid=ai_discuss.uuid,
            further_question_count=further_question_count
        ):
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                stop = chunk.choices[0].finish_reason == "stop"

                content_chunk = {
                    "id": f"chatcmpl-{ai_discuss.id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "rbase-discuss-agent",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": None if not stop else "stop"
                    }]
                }
                
                if hasattr(delta, "content") and delta.content is not None:
                    # Update content
                    ai_discuss.content += delta.content
                    ai_discuss.tokens["generating"].append(delta.content)
                    await save_discuss(ai_discuss, status_in=AIResponseStatus.GENERATING)
                    # Build response chunk
                    content_chunk["choices"][0]["delta"]["content"] = delta.content
                
                if show_reasoning_content and hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                    content_chunk["choices"][0]["delta"]["reasoning_content"] = delta.reasoning_content
                
                if hasattr(delta, "progress") and delta.progress is not None:
                    content_chunk["choices"][0]["delta"]["progress"] = delta.progress

                yield f"data: {json.dumps(content_chunk)}\n\n".encode('utf-8')

            if hasattr(chunk, "usage") and chunk.usage:
                discuss_agent.usage["total_tokens"] += chunk.usage.total_tokens
                discuss_agent.usage["prompt_tokens"] += chunk.usage.prompt_tokens
                discuss_agent.usage["completion_tokens"] += chunk.usage.completion_tokens

        # Update final status
        ai_discuss.tokens["generating"] = []
        if ai_discuss.content == "":
            ai_discuss.status = AIResponseStatus.DEPRECATED
        else:
            ai_discuss.status = AIResponseStatus.FINISHED

        if hasattr(discuss_agent, "usage"):
            ai_discuss.usage = discuss_agent.usage
        await save_discuss(ai_discuss, status_in=AIResponseStatus.GENERATING)

        if ai_discuss.status == AIResponseStatus.FINISHED:
            await update_discuss_thread_depth(thread.uuid, ai_discuss.depth, ai_discuss.uuid)
        
        # Send completion marker
        yield "data: [DONE]\n\n".encode('utf-8')

        if discuss_agent.ai_log is not None and discuss_agent.ai_log.is_valid():
            discuss_agent.ai_log.total_duration = int(time.time() - start_time)
            await save_ai_log(discuss_agent.ai_log)
        
    except Exception as e:
        # Error handling
        ai_discuss.content += f"\n\n生成回复时发生错误: {str(e)}"
        ai_discuss.status = AIResponseStatus.ERROR
        await save_discuss(ai_discuss)
        
        error_chunk = {
            "id": f"chatcmpl-{ai_discuss.id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "rbase-discuss-agent",
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\n生成回复时发生错误: {str(e)}"},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')
        yield "data: [DONE]\n\n".encode('utf-8')

async def get_thread_background(thread: DiscussThread) -> str:
    """
    Get background information for discussion thread.
    
    Get corresponding background information based on thread related type (channel, column, article).
    
    Args:
        thread: Discussion thread object
        
    Returns:
        str: Background information text
    """
    # If preset background exists, return directly
    if hasattr(thread, "background") and thread.background:
        return thread.background
    
    # Get background information based on related type
    try:
        if thread.related_type == RelatedType.CHANNEL:
            channel_id = thread.params.get("channel_id", 0)
            if channel_id:
                # Get channel basic information directly from database
                base = await get_base_by_id(channel_id)
                if base:
                   return f"用户正在访问频道: {base.name}"
        elif thread.related_type == RelatedType.COLUMN:
            column_id = thread.params.get("column_id", 0)
            if column_id:
                # Get column basic information directly from database
                base_category = await get_base_category_by_id(column_id)
                if base_category:
                   return f"用户正在访问栏目: {base_category.name}"
        elif thread.related_type == RelatedType.ARTICLE:
            article_id = thread.params.get("article_id", 0)
            if article_id:
                articles = await load_articles_by_article_ids([article_id])
                if len(articles) > 0:
                    article = articles[0]
                    return (
                        f"用户正在阅读文章, 标题: {article.title}\n\n"
                        f"作者: {', '.join(article.authors)}\n\n"
                        f"期刊: {article.journal_name} ({article.pubdate.year})\n\n"
                        f"摘要: {article.abstract}"
                    )
    except Exception as e:
        raise Exception(f"获取讨论背景信息失败: {e}")
    
    # Return empty background by default
    return "" 
