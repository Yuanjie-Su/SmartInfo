#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Authentication Service Module
Handles user registration and authentication logic.
"""

from typing import Optional
import asyncpg

from db.repositories import UserRepository
from models import UserCreate, UserInDB
from core.security import get_password_hash, verify_password


class AuthService:
    """
    Service layer for authentication operations.
    """

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def register_user(self, user_create: UserCreate) -> Optional[UserInDB]:
        """
        Registers a new user.

        Args:
            user_create: Pydantic model containing username and password.

        Returns:
            The created user object (UserInDB) if registration is successful,
            otherwise None (e.g., if username already exists).
        """
        # Check if user already exists
        existing_user = await self.user_repo.get_user_by_username(user_create.username)
        if existing_user:
            # Consider raising a specific exception (e.g., HTTPException) here
            # for the API layer to handle, instead of just returning None.
            print(
                f"Registration failed: Username '{user_create.username}' already exists."
            )
            return None

        # Hash the password
        hashed_password = get_password_hash(user_create.password)

        # Add user to the database
        try:
            new_user = await self.user_repo.add_user(
                username=user_create.username, hashed_password=hashed_password
            )
            return new_user
        except Exception as e:
            # Log the error appropriately
            print(f"Error during user registration: {e}")
            return None

    async def authenticate_user(
        self, username: str, password: str
    ) -> Optional[UserInDB]:
        """
        Authenticates a user based on username and password.

        Args:
            username: The username provided by the user.
            password: The password provided by the user.

        Returns:
            The user object (UserInDB) if authentication is successful,
            otherwise None.
        """
        user = await self.user_repo.get_user_by_username(username)
        if not user:
            return None  # User not found
        if not verify_password(password, user.hashed_password):
            return None  # Incorrect password

        return user
