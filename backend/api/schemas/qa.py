# backend/api/schemas/qa.py
"""
Pydantic schemas for QA-related operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class QAHistory(BaseModel):
    """QA history schema. Matches repository output."""
    id: int
    question: str
    answer: str
    context_ids: Optional[str] = None # Stored as TEXT in DB
    created_date: str # Stored as TEXT in DB

    class Config:
        from_attributes = True


class QARequest(BaseModel):
    """Schema for QA request."""
    question: str = Field(..., min_length=1)
    # Add fields if needed for non-streaming endpoint, e.g.:
    # context_ids: Optional[List[int]] = None
    # use_history: bool = False


class QAResponse(BaseModel):
    """Schema for QA response (non-streaming)."""
    # Corresponds to the Dict returned by qa_service.answer_question
    answer: str
    error: Optional[str] = None # Include potential errors


class QAProgressUpdate(BaseModel):
    """Schema for QA processing progress updates via WebSocket."""
    operation: str = "qa"
    status: str  # "in_progress", "completed", "failed"
    message: Optional[str] = None
    partial_answer: Optional[str] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True