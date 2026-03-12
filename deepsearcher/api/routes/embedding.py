"""
Embedding Routes

This module contains routes for text-to-vector (embedding) conversion.
"""

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


@router.post("", summary="文本转向量", description="将单条文本转换为向量")
async def embed_text(request: EmbeddingRequest):
    try:
        embedding = configuration.embedding_model.embed_query(request.text)
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
        embeddings = configuration.embedding_model.embed_documents(texts)
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
