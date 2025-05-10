#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
User Repository Module
Handles database operations related to users.
"""

from typing import Optional
import asyncpg
import logging

from .base_repository import BaseRepository
from models import UserInDB  # Assuming UserInDB includes id, username, hashed_password
from db.schema_constants import Users

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):
    """
    Repository for user-related database operations.
    """

    async def add_user(self, username: str, hashed_password: str) -> Optional[UserInDB]:
        """
        Adds a new user to the database.

        Args:
            username: The username of the new user.
            hashed_password: The securely hashed password for the new user.

        Returns:
            The created user object (UserInDB) if successful, otherwise None.
        """
        query = f"""
            INSERT INTO {Users.TABLE_NAME} ({Users.USERNAME}, {Users.HASHED_PASSWORD})
            VALUES ($1, $2)
            RETURNING {Users.ID}, {Users.USERNAME}, {Users.HASHED_PASSWORD}
        """
        try:
            record = await self._fetchone(query, (username, hashed_password))
            return UserInDB(**dict(record)) if record else None
        except asyncpg.UniqueViolationError:
            logger.warning(f"Username '{username}' already exists.")
            return None
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return None

    async def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        """
        Retrieves a user by their username.

        Args:
            username: The username to search for.

        Returns:
            The user object (UserInDB) if found, otherwise None.
        """
        query = f"""
            SELECT {Users.ID}, {Users.USERNAME}, {Users.HASHED_PASSWORD}
            FROM {Users.TABLE_NAME}
            WHERE {Users.USERNAME} = $1
        """
        try:
            record = await self._fetchone(query, (username,))
            return UserInDB(**dict(record)) if record else None
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[UserInDB]:
        """
        Retrieves a user by their ID.

        Args:
            user_id: The ID of the user to search for.

        Returns:
            The user object (UserInDB) if found, otherwise None.
        """
        query = f"""
            SELECT {Users.ID}, {Users.USERNAME}, {Users.HASHED_PASSWORD}
            FROM {Users.TABLE_NAME}
            WHERE {Users.ID} = $1
        """
        try:
            record = await self._fetchone(query, (user_id,))
            return UserInDB(**dict(record)) if record else None
        except Exception as e:
            logger.error(f"Error getting user by id: {e}")
            return None

    async def update_username(self, user_id: int, new_username: str) -> bool:
        query = f"""
            UPDATE {Users.TABLE_NAME}
            SET {Users.USERNAME} = $1
            WHERE {Users.ID} = $2
        """
        try:
            status = await self._execute(query, (new_username, user_id))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(
                    f"Username updated for user ID {user_id} to '{new_username}'."
                )
            return updated
        except asyncpg.UniqueViolationError:
            logger.warning(
                f"Attempt to update to an already existing username: '{new_username}'"
            )
            return False  # Or raise a specific exception
        except Exception as e:
            logger.error(f"Error updating username for user ID {user_id}: {e}")
            return False

    async def update_password(self, user_id: int, new_hashed_password: str) -> bool:
        query = f"""
            UPDATE {Users.TABLE_NAME}
            SET {Users.HASHED_PASSWORD} = $1
            WHERE {Users.ID} = $2
        """
        try:
            status = await self._execute(query, (new_hashed_password, user_id))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Password updated for user ID {user_id}.")
            return updated
        except Exception as e:
            logger.error(f"Error updating password for user ID {user_id}: {e}")
            return False
