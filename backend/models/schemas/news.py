# backend/models/news.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for news related data (sources, categories, items, requests).
"""

from pydantic import BaseModel, Field, AnyHttpUrl, ConfigDict
from typing import List, Optional, Dict, Any

# --- News Category Models ---


class NewsCategoryFields(BaseModel):
    """Fields expected in news category create/update request payloads."""

    name: str = Field(..., max_length=100, description="Name of the news category")


class NewsCategoryCreate(NewsCategoryFields):
    """Schema for creating a new news category (request body)."""

    pass  # Inherits name, does NOT include user_id


class NewsCategoryUpdate(NewsCategoryFields):
    """Schema for updating a news category (request body)."""

    pass  # Inherits name, does NOT include user_id


class NewsCategory(NewsCategoryFields):
    """Schema for representing a full news category object (response/database)."""

    id: int = Field(..., description="Unique identifier for the news category")
    user_id: int = Field(
        ..., description="ID of the user who owns this category"
    )  # Keep user_id here
    source_count: Optional[int] = Field(
        None,
        description="Number of news sources associated with this category (optional)",
    )
    model_config = ConfigDict(from_attributes=True)


# --- Response Models ---


class NewsCategoryResponse(BaseModel):
    """Schema for representing a news category in API responses (excludes user_id)."""

    id: int = Field(..., description="Unique identifier for the news category")
    name: str = Field(..., max_length=100, description="Name of the news category")
    source_count: Optional[int] = Field(
        None,
        description="Number of news sources associated with this category (optional)",
    )
    model_config = ConfigDict(from_attributes=True)


# --- News Source Models ---


class NewsSourceFields(BaseModel):
    """Fields expected in news source create/update request payloads."""

    name: str = Field(..., max_length=100, description="Name of the news source")
    url: AnyHttpUrl = Field(
        ..., description="URL of the news source (e.g., homepage, RSS feed)"
    )
    category_id: int = Field(
        ..., description="ID of the category this source belongs to"
    )


class NewsSourceCreate(NewsSourceFields):
    """Schema for creating a new news source (request body)."""

    pass  # Inherits fields, does NOT include user_id


class NewsSourceUpdate(NewsSourceFields):
    """Schema for updating a news source (request body)."""

    # Inherits fields, makes them optional for updates
    name: Optional[str] = Field(
        None, max_length=100, description="New name of the news source"
    )
    url: Optional[AnyHttpUrl] = Field(None, description="New URL of the news source")
    category_id: Optional[int] = Field(
        None, description="New category ID for the source"
    )


class NewsSource(NewsSourceFields):
    """Schema for representing a full news source object (response/database)."""

    id: int = Field(..., description="Unique identifier for the news source")
    user_id: int = Field(
        ..., description="ID of the user who owns this source"
    )  # Keep user_id here
    category_name: Optional[str] = Field(
        None,
        description="Name of the category this source belongs to (for convenience)",
    )
    model_config = ConfigDict(from_attributes=True)


class NewsSourceResponse(BaseModel):
    """Schema for representing a news source in API responses (excludes user_id)."""

    id: int = Field(..., description="Unique identifier for the news source")
    name: str = Field(..., max_length=100, description="Name of the news source")
    url: AnyHttpUrl = Field(
        ..., description="URL of the news source (e.g., homepage, RSS feed)"
    )
    category_id: int = Field(
        ..., description="ID of the category this source belongs to"
    )
    category_name: Optional[str] = Field(
        None,
        description="Name of the category this source belongs to (for convenience)",
    )
    model_config = ConfigDict(from_attributes=True)


# --- News Item Models ---


class NewsItemFields(BaseModel):
    """Fields expected in news item create/update request payloads."""

    title: str = Field(..., description="Title of the news item")
    url: Optional[AnyHttpUrl] = Field(
        None, description="URL of the original news article"
    )
    source_id: Optional[int] = Field(
        None, description="ID of the source this news item came from"
    )
    category_id: Optional[int] = Field(
        None, description="ID of the category this news item belongs to"
    )
    summary: Optional[str] = Field(None, description="A brief summary of the news item")
    content: Optional[str] = Field(
        None, description="Full content of the news item (potentially large)"
    )
    analysis: Optional[str] = Field(
        None, description="LLM-generated analysis or structured summary of the content"
    )
    date: Optional[str] = Field(
        None,
        description="Publication date of the news item (as a string, e.g., 'YYYY-MM-DD HH:MM:SS' or ISO format)",
    )
    # Include source_name and category_name for easier handling in create/update
    source_name: Optional[str] = Field(None, description="Name of the news source")
    category_name: Optional[str] = Field(None, description="Name of the news category")


class NewsItemCreate(NewsItemFields):
    """Schema for creating a new news item (request body)."""

    # Override title and url to be required for creation
    title: str = Field(..., description="Title of the news item")
    url: AnyHttpUrl = Field(..., description="URL of the original news article")
    # Does NOT include user_id


class NewsItemUpdate(NewsItemFields):
    """Schema for updating an existing news item (request body)."""

    # Inherits fields, makes them optional for updates
    title: Optional[str] = Field(None, description="New title of the news item")
    url: Optional[AnyHttpUrl] = Field(
        None, description="New URL of the original news article"
    )  # URL can be updated? Check backend logic. Assuming it can be for now.
    source_id: Optional[int] = Field(
        None, description="New source ID for the news item"
    )
    category_id: Optional[int] = Field(
        None, description="New category ID for the news item"
    )
    summary: Optional[str] = Field(None, description="Updated summary")
    content: Optional[str] = Field(None, description="Updated full content")
    analysis: Optional[str] = Field(None, description="Updated analysis")
    date: Optional[str] = Field(None, description="Updated publication date")
    source_name: Optional[str] = Field(None, description="New name of the news source")
    category_name: Optional[str] = Field(
        None, description="New name of the news category"
    )
    # Does NOT include user_id


class NewsItem(NewsItemFields):
    """Schema for representing a full news item object (response/database)."""

    id: int = Field(..., description="Unique identifier for the news item")
    user_id: int = Field(
        ..., description="ID of the user who owns this news item"
    )  # Keep user_id here
    # source_name and category_name inherited from Fields for convenience

    model_config = ConfigDict(from_attributes=True)


class NewsResponse(BaseModel):
    """Schema for representing a news item in API responses (excludes user_id and content)."""

    id: int = Field(..., description="Unique identifier for the news item")
    title: str = Field(..., description="Title of the news item")
    url: Optional[AnyHttpUrl] = Field(
        None, description="URL of the original news article"
    )
    source_id: Optional[int] = Field(
        None, description="ID of the source this news item came from"
    )
    category_id: Optional[int] = Field(
        None, description="ID of the category this news item belongs to"
    )
    summary: Optional[str] = Field(None, description="A brief summary of the news item")
    analysis: Optional[str] = Field(
        None, description="LLM-generated analysis or structured summary of the content"
    )
    date: Optional[str] = Field(
        None,
        description="Publication date of the news item (as a string, e.g., 'YYYY-MM-DD HH:MM:SS' or ISO format)",
    )
    source_name: Optional[str] = Field(None, description="Name of the news source")
    category_name: Optional[str] = Field(None, description="Name of the news category")
    model_config = ConfigDict(from_attributes=True)


# --- Request/Response Models for News Operations ---


class FetchSourceRequest(BaseModel):
    """Schema for requesting fetching from a specific source."""

    source_id: int = Field(..., description="ID of the news source to fetch")


class FetchSourceBatchRequest(BaseModel):
    """Schema for requesting batch fetching from multiple sources."""

    source_ids: List[int] = Field(..., description="List of news source IDs to fetch")


class FetchUrlRequest(BaseModel):
    """Schema for requesting crawling and processing of a single URL."""

    url: AnyHttpUrl = Field(..., description="URL to crawl and process")


class TaskResponse(BaseModel):
    """Schema for responses to task initiation requests."""

    task_group_id: str = Field(..., description="Unique identifier for the task group")
    message: str = Field(..., description="Informational message about the task")


class AnalyzeRequest(BaseModel):
    """Schema for requesting analysis of news items."""

    news_ids: Optional[List[int]] = Field(
        None,
        description="List of news item IDs to analyze. If empty or None, analyze all unanalyzed.",
    )
    force: bool = Field(
        False, description="If True, force re-analysis even if analysis already exists."
    )


class AnalyzeContentRequest(BaseModel):
    """Schema for requesting analysis of arbitrary content."""

    content: str = Field(..., description="The content to be analyzed")
    instructions: str = Field(
        ...,
        description="Specific instructions for the LLM on how to perform the analysis",
    )


class AnalysisResult(BaseModel):
    """Schema for the result of content analysis."""

    analysis: str = Field(
        ...,
        description="The analysis result (can be Markdown, plain text, or other format as requested)",
    )


class UpdateAnalysisRequest(BaseModel):
    """Schema for updating the analysis field of a news item."""

    analysis: str = Field(
        ..., description="The new analysis text to store for the news item"
    )


# --- Request/Response Models for News Operations ---


class FetchSourceRequest(BaseModel):
    """Schema for requesting fetching from a specific source."""

    source_id: int = Field(..., description="ID of the news source to fetch")


class FetchSourceBatchRequest(BaseModel):
    """Schema for requesting batch fetching from multiple sources."""

    source_ids: List[int] = Field(..., description="List of news source IDs to fetch")


class FetchUrlRequest(BaseModel):
    """Schema for requesting crawling and processing of a single URL."""

    url: AnyHttpUrl = Field(..., description="URL to crawl and process")


class TaskResponse(BaseModel):
    """Schema for responses to task initiation requests."""

    task_group_id: str = Field(..., description="Unique identifier for the task group")
    message: str = Field(..., description="Informational message about the task")


class AnalyzeRequest(BaseModel):
    """Schema for requesting analysis of news items."""

    news_ids: Optional[List[int]] = Field(
        None,
        description="List of news item IDs to analyze. If empty or None, analyze all unanalyzed.",
    )
    force: bool = Field(
        False, description="If True, force re-analysis even if analysis already exists."
    )


class AnalyzeContentRequest(BaseModel):
    """Schema for requesting analysis of arbitrary content."""

    content: str = Field(..., description="The content to be analyzed")
    instructions: str = Field(
        ...,
        description="Specific instructions for the LLM on how to perform the analysis",
    )


class AnalysisResult(BaseModel):
    """Schema for the result of content analysis."""

    analysis: str = Field(
        ...,
        description="The analysis result (can be Markdown, plain text, or other format as requested)",
    )


class UpdateAnalysisRequest(BaseModel):
    """Schema for updating the analysis field of a news item."""

    analysis: str = Field(
        ..., description="The new analysis text to store for the news item"
    )
