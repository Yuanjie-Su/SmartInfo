# backend/api/__init__.py
# -*- coding: utf-8 -*-
"""
API package for FastAPI routers and dependencies.
This module assembles the main API router by including routers directly.
"""

from fastapi import APIRouter

# Import the routers from the new location
from backend.api.routers.chat import router as chat_router
from backend.api.routers.news import router as news_router
from backend.api.routers.settings import router as settings_router
from backend.api.routers.tasks import router as tasks_router

# Create the main API router instance
api_router = APIRouter()

# Include the routers directly without version prefix
api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(news_router, prefix="/news", tags=["News"])
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])

__all__ = ["api_router"]
