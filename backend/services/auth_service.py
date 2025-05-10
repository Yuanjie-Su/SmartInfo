#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Authentication Service Module
Handles user registration and authentication logic.
"""

from typing import Optional
import logging

from db.repositories import UserRepository
from models import UserCreate, UserInDB
from core.security import get_password_hash, verify_password
from models.schemas.user import User

logger = logging.getLogger(__name__)


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

    async def change_password(
        self, user_id: int, current_password_str: str, new_password_str: str
    ) -> bool:
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            return False  # Should not happen if user_id comes from authenticated user

        if not verify_password(current_password_str, user.hashed_password):
            logger.warning(
                f"Password change attempt failed for user {user_id}: Incorrect current password."
            )
            return False

        new_hashed_password = get_password_hash(new_password_str)
        return await self.user_repo.update_password(user_id, new_hashed_password)

    async def change_username(
        self, user_id: int, new_username: str, current_password_str: str
    ) -> Optional[User]:
        user_in_db = await self.user_repo.get_user_by_id(user_id)
        if not user_in_db:
            return None

        if not verify_password(current_password_str, user_in_db.hashed_password):
            logger.warning(
                f"Username change attempt failed for user {user_id}: Incorrect current password."
            )
            return None  # Or raise specific exception

        # Check if new username is different from current
        if user_in_db.username == new_username:
            logger.info(
                f"User {user_id} attempted to change username to the same value ('{new_username}'). No change made."
            )
            # Return current user details as if successful, since no change was needed
            return User.model_validate(user_in_db)

        # Attempt to update username in repository (handles uniqueness check)
        success = await self.user_repo.update_username(user_id, new_username)
        if not success:
            # This implies username was likely taken, or DB error
            raise ValueError("Username already taken or update failed.")

        updated_user_in_db = await self.user_repo.get_user_by_id(user_id)
        if updated_user_in_db:
            return User.model_validate(
                updated_user_in_db
            )  # Convert to User for response
        return None
