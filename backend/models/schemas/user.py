#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
User Pydantic Schemas
"""

from pydantic import BaseModel, Field


# Shared properties
class UserBase(BaseModel):
    username: str = Field(..., description="Unique username for the user")


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(..., description="User's password")


# Properties stored in DB
class UserInDBBase(UserBase):
    id: int
    hashed_password: str

    class Config:
        from_attributes = True  # Replaces orm_mode = True in Pydantic v2


# Additional properties to return via API
class User(UserInDBBase):
    pass  # No extra fields needed for now


# Additional properties stored in DB
class UserInDB(UserInDBBase):
    pass  # No extra fields needed for now
