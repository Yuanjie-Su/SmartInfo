# backend/models/api_key.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for API key related data.
"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

# --- API Key Models ---


class ApiKeyBase(BaseModel):
    """Base schema for API key data."""

    model: str = Field(..., description="Model identifier (e.g., 'deepseek-chat')")
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="The API key itself (sensitive data)")
    context: int = Field(..., description="Model context length (in tokens)")
    max_output_tokens: int = Field(..., description="Maximum output tokens")
    description: Optional[str] = Field(
        None, description="Optional description for the API key"
    )
    user_id: int = Field(..., description="ID of the user who owns this API key")


class ApiKeyCreate(ApiKeyBase):
    """Schema for creating a new API key."""

    # Inherits all fields from ApiKeyBase
    pass


class ApiKey(ApiKeyBase):
    """Schema for representing an API key, including database ID and timestamps."""

    id: int = Field(..., description="Unique identifier for the API key")
    created_date: Optional[datetime] = Field(
        None, description="Creation timestamp (ISO 8601 format)"
    )
    modified_date: Optional[datetime] = Field(
        None, description="Last modification timestamp (ISO 8601 format)"
    )

    model_config = ConfigDict(
        from_attributes=True  # Enable ORM mode if mapping directly from ORM objects later
        # Set from_attributes=False if mapping from raw tuples/dicts
    )
