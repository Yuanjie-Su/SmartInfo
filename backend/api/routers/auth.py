#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Authentication API Router
Handles user registration, login (token generation), and user info endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated
from models.schemas.user import PasswordChangeRequest, UsernameChangeRequest
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

router = APIRouter()


# Pydantic model for the token response
class Token(BaseModel):
    access_token: str
    token_type: str


# Define a new response model including the user
class TokenWithUser(Token):
    user: User


@router.post(
    "/register", response_model=TokenWithUser, status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_data: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Register a new user and return JWT access token and user details.
    """
    new_user = await auth_service.register_user(user_data)
    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered or registration failed",
        )

    # Create access token for the new user
    access_token_data = {"sub": str(new_user.id)}
    access_token = create_access_token(data=access_token_data)

    # Return both the access token and the new user object
    return TokenWithUser(
        access_token=access_token,
        token_type="bearer",
        user=new_user,  # Ensure new_user is of type User (Pydantic model for response)
    )


@router.post("/token", response_model=TokenWithUser)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    Authenticate user and return JWT access token and user details.
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
    # Return both the access token and the user object
    return {"access_token": access_token, "token_type": "bearer", "user": user}


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


@router.put("/users/me/password", status_code=status.HTTP_200_OK)
async def change_current_user_password(
    password_data: PasswordChangeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    success = await auth_service.change_password(
        user_id=current_user.id,
        current_password_str=password_data.current_password,
        new_password_str=password_data.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to change password. Incorrect current password or invalid new password.",
        )
    return {"message": "Password updated successfully"}


@router.put("/users/me/username", response_model=User)
async def change_current_user_username(
    username_data: UsernameChangeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        updated_user = await auth_service.change_username(
            user_id=current_user.id,
            new_username=username_data.new_username,
            current_password_str=username_data.current_password,
        )
        if not updated_user:
            # This case might be if password was wrong, or some other unexpected issue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to change username. Incorrect password or other error.",
            )
        return updated_user
    except ValueError as ve:  # Catch "Username already taken"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(ve),
        )
