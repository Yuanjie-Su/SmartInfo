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


# Additional properties to return via API
class User(UserInDBBase):
    model_config = ConfigDict(from_attributes=True)  # Adding model_config for User


# Additional properties stored in DB
class UserInDB(UserInDBBase):
    model_config = ConfigDict(from_attributes=True)  # Adding model_config for UserInDB
