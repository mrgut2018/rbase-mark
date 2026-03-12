import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from deepsearcher import configuration
from deepsearcher.api.models import (
    ExceptionResponse,
    BackendArticleTitlesRequest, BackendArticleTitlesResponse,
    RefreshArticleVectorDbRequest,
    VectorDbOperation,
    AiTranslateRequest, AiTranslateResponse, AiTranslateLang,
)
from deepsearcher.rbase_db_loading import (
    load_article_by_article_id, load_article_authors, load_article_vector_db_log,
    delete_article_in_vector_db, log_raw_article_deleted,
)
from deepsearcher.agent.article_title_agent import ArticleTitleAgent
from deepsearcher import configuration

router = APIRouter()

@router.post(
    "/ai_article_titles", 
    summary="Generate article title suggestions using AI", 
    description="""
    Get article title, authors, abstract, keywords, etc. 
    Based on article ID, generate article title suggestions using AI. 
    Users can provide additional requirements for titles and specify the number of recommendations.
    """
)
async def api_article_titles(request: BackendArticleTitlesRequest):
    """
    Generate article titles based on article ID
    """
    try:
        article = await load_article_by_article_id(request.article_id)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content=ExceptionResponse(code=400, message=f"Article query failed: {request.article_id}").model_dump()
        )

    try:
        authors = await load_article_authors(article.article_id)
        
        title_agent = ArticleTitleAgent(
            reasoning_llm=configuration.reasoning_llm,
            translator=configuration.academic_translator,
        )
        titles, _, _= title_agent.query(
            query=request.extend_requirement,
            article=article,
            authors=authors,
            title_count=request.count,
        )
        title_pattern = r'<title>(.*?)</title>'
        extracted_titles = re.findall(title_pattern, titles, re.DOTALL)
        if not extracted_titles:
            return JSONResponse(status_code=400, content=ExceptionResponse(
                code=400, message=f"Failed to parse titles, showing original output: {titles}").model_dump())
        else:
            return BackendArticleTitlesResponse(
                code=0, message="success", titles=extracted_titles)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )

    
@router.post(
    "/delete_article_vector_db_data", 
    summary="Delete article vector db data", 
    description="""
    Delete article vector db data.
    Based on article ID and raw article ID, delete article vector db data and log in vector_db_log table.
    """
)
async def api_refresh_article_vector_db(request: RefreshArticleVectorDbRequest):
    try:
        article = await load_article_by_article_id(request.article_id)
        if article.raw_article_id != request.raw_article_id:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"Article ID and raw article ID mismatch: {request.article_id} and {request.raw_article_id}").model_dump()
            )
        vlog = await load_article_vector_db_log(request.raw_article_id, VectorDbOperation.INSERT)
        if not vlog:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"Article is not processed, raw_article_id: {request.raw_article_id}").model_dump()
            )
        collection = vlog["collection"]
        rt = delete_article_in_vector_db(collection, request.article_id)
        if rt > 0:
            log_raw_article_deleted(configuration.config.rbase_settings, request.raw_article_id, collection)
            return JSONResponse(
                status_code=200,
                content=ExceptionResponse(code=0, message=f"Article in vector db is deleted, raw_article_id: {request.raw_article_id}").model_dump()
            )
        else:
            return JSONResponse(
                status_code=400,
                content=ExceptionResponse(code=400, message=f"Article in vector db is not deleted, raw_article_id: {request.raw_article_id}").model_dump()
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=f"Article query failed: {request.article_id}").model_dump()
        )

@router.post(
    "/ai_translate", 
    summary="Translate sentence using AcademicTranslator", 
    description="""
    Translate sentence using AcademicTranslator.
    Based on sentence, translate sentence using AcademicTranslator.
    """
)
async def api_ai_translate(request: AiTranslateRequest):
    try:
        translated = configuration.academic_translator.translate(
            request.sentence, request.target_lang.value)
        return AiTranslateResponse(
            code=0, 
            message="success", 
            translated=translated, 
            target_lang=request.target_lang
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump()
        )