"""
Embedding Routes

This module contains routes for text-to-vector (embedding) conversion.
"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from deepsearcher import configuration
from deepsearcher.api.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingData,
    BatchEmbeddingRequest,
    BatchEmbeddingResponse,
    BatchEmbeddingResultItem,
    ExceptionResponse,
)
from deepsearcher.tools.log import info

router = APIRouter()

BATCH_SIZE = 16


@router.post("", summary="文本转向量", description="将单条文本转换为向量")
async def embed_text(request: EmbeddingRequest):
    try:
        embedding = await asyncio.to_thread(
            configuration.embedding_model.embed_query, request.text
        )
        dimension = configuration.embedding_model.dimension
        info(f"embed text, length={len(request.text)}, dimension={dimension}")
        return EmbeddingResponse(
            code=0,
            message="success",
            data=EmbeddingData(embedding=embedding, dimension=dimension),
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump(),
        )


@router.post("/batch", summary="批量文本转向量", description="将多条文本批量转换为向量")
async def batch_embed_texts(request: BatchEmbeddingRequest):
    try:
        if not request.items:
            return BatchEmbeddingResponse(
                code=0, message="success", data=[], dimension=0, count=0,
            )
        texts = [item.text for item in request.items]
        # 分批调用 embedding API，避免单次请求过大
        embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_embeddings = await asyncio.to_thread(
                configuration.embedding_model.embed_documents, batch
            )
            embeddings.extend(batch_embeddings)
        dimension = configuration.embedding_model.dimension
        data = [
            BatchEmbeddingResultItem(id=item.id, embedding=emb)
            for item, emb in zip(request.items, embeddings)
        ]
        info(f"batch embed texts, count={len(texts)}, dimension={dimension}")
        return BatchEmbeddingResponse(
            code=0,
            message="success",
            data=data,
            dimension=dimension,
            count=len(data),
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=ExceptionResponse(code=500, message=str(e)).model_dump(),
        )
