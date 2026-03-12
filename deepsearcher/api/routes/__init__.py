"""
API Routes Package

This package contains all the route definitions for the Rbase API.
"""

from fastapi import APIRouter
from .summary import router as summary_router
from .questions import router as questions_router
from .discuss import router as discuss_router
from .backend import router as backend_router
from .embedding import router as embedding_router

# Create main router
router = APIRouter()

# Register all sub-routers
router.include_router(summary_router, prefix="/generate", tags=["generate"])
router.include_router(questions_router, prefix="/generate", tags=["generate"])
router.include_router(discuss_router, prefix="/generate", tags=["generate"])
router.include_router(backend_router, prefix="/backend", tags=["backend"])
router.include_router(embedding_router, prefix="/embedding", tags=["embedding"])