#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
User Pydantic Schemas
"""

from pydantic import BaseModel, Field, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


# Additional properties to return via API (excludes sensitive fields)
class User(UserBase):
    id: int = Field(..., description="Unique identifier for the user")
    # Excludes hashed_password

    model_config = ConfigDict(from_attributes=True)


# Additional properties stored in DB (includes sensitive fields)
class UserInDB(UserInDBBase):
    model_config = ConfigDict(from_attributes=True)
