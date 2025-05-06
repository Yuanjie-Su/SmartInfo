#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Authentication API Router
Handles user registration, login (token generation), and user info endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from pydantic import BaseModel

from models import (
    User,
    UserCreate,
)
from services import AuthService
from core.security import create_access_token

# Import dependency functions from dependencies.py
from api.dependencies.dependencies import (
    get_current_active_user,
    get_auth_service,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# Pydantic model for the token response
class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Register a new user.
    """
    user = await auth_service.register_user(user_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered or registration failed",
        )
    # Return the created user details (excluding password)
    return user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Authenticate user and return JWT access token.
    Uses OAuth2PasswordRequestForm for standard form data input (username, password).
    """
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Data to include in the JWT payload (subject: user identifier)
    access_token_data = {"sub": str(user.id)}  # Use user ID as subject
    access_token = create_access_token(data=access_token_data)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=User)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Get current logged-in user's details.
    Requires authentication via JWT Bearer token.
    """
    # The dependency get_current_active_user already validates the token
    # and returns the user object.
    return current_user
