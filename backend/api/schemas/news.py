# backend/api/schemas/news.py
"""
Pydantic schemas for news-related operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class NewsSource(BaseModel):
    """News source schema. Matches repository output."""
    id: int
    name: str
    url: str
    category_id: int
    category_name: str

    class Config:
        from_attributes = True # Use this for ORM mode in Pydantic v2


class NewsCategory(BaseModel):
    """News category schema."""
    id: int
    name: str

    class Config:
        from_attributes = True


class NewsCategoryWithCount(NewsCategory):
    """News category schema with source count."""
    source_count: int

    class Config:
        from_attributes = True


class NewsItem(BaseModel):
    """News item schema. Matches repository output."""
    id: int
    title: str
    link: str
    source_name: str
    category_name: str
    source_id: Optional[int] = None
    category_id: Optional[int] = None
    summary: Optional[str] = None
    analysis: Optional[str] = None
    date: Optional[str] = None # Stored as TEXT in DB

    class Config:
        from_attributes = True


class NewsSourceCreate(BaseModel):
    """Schema for creating a news source."""
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    category_name: str = Field(..., min_length=1)


class NewsSourceUpdate(BaseModel):
    """Schema for updating a news source."""
    name: Optional[str] = Field(None, min_length=1)
    url: Optional[str] = Field(None, min_length=1)
    category_name: Optional[str] = Field(None, min_length=1)


class NewsCategoryCreate(BaseModel):
    """Schema for creating a news category."""
    name: str = Field(..., min_length=1)


class NewsCategoryUpdate(BaseModel):
    """Schema for updating a news category."""
    name: str = Field(..., min_length=1)


class FetchNewsRequest(BaseModel):
    """Schema for fetch news request."""
    source_ids: Optional[List[int]] = None  # If None, fetch from all enabled sources


class NewsSearchRequest(BaseModel):
    """Schema for news search request (Placeholder)."""
    query: str
    category_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 20
    offset: int = 0


class NewsAnalysisRequest(BaseModel):
    """Schema for news analysis request (Placeholder)."""
    news_ids: List[int]
    analysis_type: str = "summary"  # summary, sentiment, keywords, etc.


class NewsProgressUpdate(BaseModel):
    """Schema for news processing progress updates via WebSocket."""
    url: str
    status: str  # e.g., "Crawling", "Crawled - Success", "Extracting (LLM)", "Saving", "Complete", "Error", "Skipped"
    details: str # e.g., "Checking token size (1234)", "Saved 5, Skipped 0", "Extraction Failed: API Error"

    class Config:
        from_attributes = True # Ensure it can be created from dict

class StreamChunkUpdate(BaseModel):
    """Schema for raw stream chunks via WebSocket."""
    type: str = "stream_chunk" # Differentiate from progress updates
    chunk: str

    class Config:
        from_attributes = True
