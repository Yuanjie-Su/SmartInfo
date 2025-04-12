"""
API Dependencies for the SmartInfo application.

This module provides dependency injection functions for FastAPI routes.
"""

from fastapi import Depends, Request

from backend.services.news_service import NewsService
from backend.services.qa_service import QAService
from backend.services.setting_service import SettingService
from backend.services.llm_client import LLMClient


async def get_news_service(request: Request) -> NewsService:
    """
    Dependency to get the NewsService instance.
    """
    return request.app.state.services["news_service"]


async def get_qa_service(request: Request) -> QAService:
    """
    Dependency to get the QAService instance.
    """
    return request.app.state.services["qa_service"]


async def get_setting_service(request: Request) -> SettingService:
    """
    Dependency to get the SettingService instance.
    """
    return request.app.state.services["setting_service"]


async def get_llm_client(request: Request) -> LLMClient:
    """
    Dependency to get the LLMClient instance.
    """
    return request.app.state.services["llm_client"] 