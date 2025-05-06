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


class ApiKeyFields(BaseModel):
    """Fields expected in API key create/update request payloads."""

    model: str = Field(..., description="Model identifier (e.g., 'deepseek-chat')")
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="The API key itself (sensitive data)")
    context: int = Field(..., description="Model context length (in tokens)")
    max_output_tokens: int = Field(..., description="Maximum output tokens")
    description: Optional[str] = Field(
        None, description="Optional description for the API key"
    )


class ApiKeyCreate(ApiKeyFields):
    """Schema for creating a new API key (request body)."""

    # Inherits fields from ApiKeyFields, does NOT include user_id
    pass


class ApiKeyUpdate(ApiKeyFields):
    """Schema for updating an existing API key (request body)."""

    # Inherits fields from ApiKeyFields, makes them optional for updates
    model: Optional[str] = Field(
        None, description="Model identifier (e.g., 'deepseek-chat')"
    )
    base_url: Optional[str] = Field(None, description="API base URL")
    api_key: Optional[str] = Field(
        None, description="The API key itself (sensitive data)"
    )
    context: Optional[int] = Field(None, description="Model context length (in tokens)")
    max_output_tokens: Optional[int] = Field(None, description="Maximum output tokens")
    description: Optional[str] = Field(
        None, description="Optional description for the API key"
    )


class ApiKey(ApiKeyFields):
    """Schema for representing a full API key object (response/database)."""

    id: int = Field(..., description="Unique identifier for the API key")
    user_id: int = Field(
        ..., description="ID of the user who owns this API key"
    )  # Keep user_id here
    created_date: Optional[datetime] = Field(
        None, description="Creation timestamp (ISO 8601 format)"
    )
    modified_date: Optional[datetime] = Field(
        None, description="Last modification timestamp (ISO 8601 format)"
    )


class ApiKeyResponse(BaseModel):
    """Schema for representing an API key in API responses (excludes user_id and api_key)."""

    id: int = Field(..., description="Unique identifier for the API key")
    model: str = Field(..., description="Model identifier (e.g., 'deepseek-chat')")
    base_url: str = Field(..., description="API base URL")
    context: int = Field(..., description="Model context length (in tokens)")
    max_output_tokens: int = Field(..., description="Maximum output tokens")
    description: Optional[str] = Field(
        None, description="Optional description for the API key"
    )
    created_date: Optional[datetime] = Field(
        None, description="Creation timestamp (ISO 8601 format)"
    )
    modified_date: Optional[datetime] = Field(
        None, description="Last modification timestamp (ISO 8601 format)"
    )
    model_config = ConfigDict(from_attributes=True)
