# backend/api/schemas/settings.py
"""
Pydantic schemas for settings-related operations.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# Renamed from ApiKeyInfo for clarity when representing a key entry
class ApiKey(BaseModel):
    """API key representation (name and key value)."""
    api_name: str
    api_key: str # Expose the key value in specific GET? Or just info? Let's stick to info mostly.

    class Config:
        from_attributes = True

class ApiKeyInfo(BaseModel):
    """API key info schema (name and dates). Matches repo output."""
    api_name: str
    created_date: str
    modified_date: str

    class Config:
        from_attributes = True

class ApiKeyCreate(BaseModel):
    """Schema for creating/updating an API key."""
    api_name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)

# Use ApiKeyCreate for PUT as well, or define ApiKeyUpdate if fields differ
# class ApiKeyUpdate(BaseModel):
#    api_key: str = Field(..., min_length=1)


class SystemConfig(BaseModel):
    """System configuration schema. Matches repo/config structure."""
    config_key: str
    config_value: Any # Value can be parsed JSON or string

    class Config:
        from_attributes = True

# Schema for creating a new config (if needed, often same as update)
# class SystemConfigCreate(BaseModel):
#     config_key: str = Field(..., min_length=1)
#     config_value: Any

class SystemConfigUpdate(BaseModel):
    """Schema for updating a system configuration."""
    # Key is usually in path, only need value in body
    config_value: Any # Allow setting various types
