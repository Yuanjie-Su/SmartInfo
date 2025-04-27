# backend/models/news.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for news related data (sources, categories, items, requests).
"""

from pydantic import BaseModel, Field, AnyHttpUrl, ConfigDict
from typing import List, Optional, Dict, Any

# --- News Category Models ---


class NewsCategoryBase(BaseModel):
    """Base schema for news category data."""

    name: str = Field(..., max_length=100, description="Name of the news category")


class NewsCategoryCreate(NewsCategoryBase):
    """Schema for creating a new news category."""

    pass


class NewsCategoryUpdate(NewsCategoryBase):
    """Schema for updating a news category."""

    pass


class NewsCategory(NewsCategoryBase):
    """Schema for representing a news category, including ID and source count."""

    id: int = Field(..., description="Unique identifier for the news category")
    source_count: Optional[int] = Field(
        None,
        description="Number of news sources associated with this category (optional)",
    )

    model_config = ConfigDict(from_attributes=True)


# --- News Source Models ---


class NewsSourceBase(BaseModel):
    """Base schema for news source data."""

    name: str = Field(..., max_length=100, description="Name of the news source")
    url: AnyHttpUrl = Field(
        ..., description="URL of the news source (e.g., homepage, RSS feed)"
    )
    category_id: int = Field(
        ..., description="ID of the category this source belongs to"
    )


class NewsSourceCreate(NewsSourceBase):
    """Schema for creating a new news source."""

    # For creation, we might accept category_name instead of category_id
    # but the current schema uses category_id. The API layer handles mapping.
    pass


class NewsSourceUpdate(BaseModel):
    """Schema for updating a news source (allows partial updates)."""

    name: Optional[str] = Field(
        None, max_length=100, description="New name of the news source"
    )
    url: Optional[AnyHttpUrl] = Field(None, description="New URL of the news source")
    category_id: Optional[int] = Field(
        None, description="New category ID for the source"
    )


class NewsSource(NewsSourceBase):
    """Schema for representing a news source, including ID and category name."""

    id: int = Field(..., description="Unique identifier for the news source")
    category_name: Optional[str] = Field(
        None,
        description="Name of the category this source belongs to (for convenience)",
    )

    model_config = ConfigDict(from_attributes=True)


# --- News Item Models ---


class NewsItemBase(BaseModel):
    """Base schema for news item data."""

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


class NewsItemCreate(NewsItemBase):
    """Schema for creating a new news item."""

    # Title and URL are essential for creation, others optional
    title: str = Field(..., description="Title of the news item")
    url: AnyHttpUrl = Field(..., description="URL of the original news article")


class NewsItemUpdate(BaseModel):
    """Schema for updating an existing news item (allows partial updates)."""

    title: Optional[str] = Field(None, description="New title of the news item")
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
    # Note: URL is typically not updated after creation


class NewsItem(NewsItemBase):
    """Schema for representing a news item, including its database ID."""

    id: int = Field(..., description="Unique identifier for the news item")
    # source_name and category_name inherited from Base for convenience

    model_config = ConfigDict(from_attributes=True)


# --- Request/Response Models for News Operations ---


class FetchSourceRequest(BaseModel):
    """Schema for requesting fetching from a specific source."""

    source_id: int = Field(..., description="ID of the news source to fetch")


class FetchUrlRequest(BaseModel):
    """Schema for requesting crawling and processing of a single URL."""

    url: AnyHttpUrl = Field(..., description="URL to crawl and process")


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
