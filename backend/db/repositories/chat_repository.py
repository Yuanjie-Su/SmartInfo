#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Repository Module
Handles database operations for chat sessions
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any
import asyncpg
from datetime import datetime, timezone

from db.repositories.base_repository import BaseRepository
from db.schema_constants import (
    CHATS_TABLE,
    CHAT_ID,
    CHAT_TITLE,
    CHAT_CREATED_AT,
    CHAT_UPDATED_AT,
    # CHAT_USER_ID, # Conceptually adding user_id
)

# Note: Assuming 'user_id' column exists conceptually in CHATS_TABLE
CHAT_USER_ID = "user_id"

logger = logging.getLogger(__name__)


class ChatRepository(BaseRepository):
    """Repository for handling chat operations in the database."""

    async def add(self, title: str, user_id: int) -> Optional[int]:
        """
        Create a new chat in the database for a specific user.

        Args:
            title: The title of the chat.
            user_id: The ID of the user creating the chat.

        Returns:
            int: The ID of the newly created chat or None if creation failed.
        """
        try:
            current_time = datetime.now(timezone.utc)

            query_str = f"""
                INSERT INTO {CHATS_TABLE} (
                    {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}, {CHAT_USER_ID}
                ) VALUES ($1, $2, $3, $4)
                RETURNING {CHAT_ID}
            """
            params = (title, current_time, current_time, user_id)

            record = await self._fetchone(query_str, params)
            chat_id = record[0] if record else None

            if chat_id is not None:
                logger.info(f"Created chat with ID {chat_id} for user {user_id}")
            else:
                logger.warning(
                    f"Failed to create chat for user {user_id}, no ID returned."
                )
            return chat_id

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to create chat for user {user_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating chat for user {user_id}: {str(e)}")
            return None

    async def update(
        self, chat_id: int, user_id: int, title: Optional[str] = None
    ) -> bool:
        """
        Update an existing chat belonging to a specific user.

        Args:
            chat_id: The ID of the chat to update.
            user_id: The ID of the user who owns the chat.
            title: New chat title (optional).

        Returns:
            bool: True if update was successful, False otherwise.
        """
        try:
            updates = {}
            params = []
            param_index = 1

            if title is not None:
                updates[CHAT_TITLE] = f"${param_index}"
                params.append(title)
                param_index += 1

            current_time = datetime.now(timezone.utc)
            updates[CHAT_UPDATED_AT] = f"${param_index}"
            params.append(current_time)
            param_index += 1

            if not updates:
                logger.warning(
                    f"No update data provided for chat update (ID: {chat_id}, User: {user_id})"
                )
                return False

            set_clause_str = ", ".join(
                f"{field} = {placeholder}" for field, placeholder in updates.items()
            )
            query_str = f"""
                UPDATE {CHATS_TABLE}
                SET {set_clause_str}
                WHERE {CHAT_ID} = ${param_index} AND {CHAT_USER_ID} = ${param_index + 1}
            """
            params.extend([chat_id, user_id])

            status = await self._execute(query_str, tuple(params))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated chat with ID {chat_id} for user {user_id}")
            else:
                # Check if the chat exists but belongs to another user or doesn't exist
                exists = await self.get_by_id(chat_id, user_id)  # Check ownership
                if exists:
                    logger.warning(
                        f"Update command for chat ID {chat_id} (User: {user_id}) executed but status was '{status}'."
                    )
                else:
                    logger.warning(
                        f"Attempted to update non-existent or unauthorized chat ID {chat_id} for user {user_id}."
                    )

            return updated

        except asyncpg.PostgresError as e:
            logger.error(
                f"Failed to update chat {chat_id} for user {user_id}: {str(e)}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error updating chat {chat_id} for user {user_id}: {str(e)}"
            )
            return False

    async def delete(self, chat_id: int, user_id: int) -> bool:
        """
        Delete a chat by its ID, ensuring it belongs to the specified user.

        Args:
            chat_id: The ID of the chat to delete.
            user_id: The ID of the user who owns the chat.

        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        try:
            query_str = f"DELETE FROM {CHATS_TABLE} WHERE {CHAT_ID} = $1 AND {CHAT_USER_ID} = $2"

            status = await self._execute(query_str, (chat_id, user_id))
            deleted = status is not None and status.startswith("DELETE 1")

            if deleted:
                logger.info(f"Deleted chat with ID {chat_id} for user {user_id}")
            else:
                logger.warning(
                    f"Delete command for chat ID {chat_id} (User: {user_id}) executed but status was '{status}'. Chat might not exist or belong to user."
                )
            return deleted

        except asyncpg.PostgresError as e:
            logger.error(
                f"Failed to delete chat {chat_id} for user {user_id}: {str(e)}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting chat {chat_id} for user {user_id}: {str(e)}"
            )
            return False

    async def get_by_id(self, chat_id: int, user_id: int) -> Optional[asyncpg.Record]:
        """
        Get a chat by its ID, ensuring it belongs to the specified user.

        Args:
            chat_id: The ID of the chat to retrieve.
            user_id: The ID of the user who owns the chat.

        Returns:
            Optional[asyncpg.Record]: An asyncpg.Record containing the chat information or None if not found or not owned by the user.
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}, {CHAT_USER_ID}
                FROM {CHATS_TABLE} WHERE {CHAT_ID} = $1 AND {CHAT_USER_ID} = $2
            """
            return await self._fetchone(query_str, (chat_id, user_id))

        except Exception as e:
            logger.error(f"Failed to get chat {chat_id} for user {user_id}: {str(e)}")
            return None

    async def get_all(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> List[asyncpg.Record]:
        """
        Get all chats for a specific user with pagination.

        Args:
            user_id: The ID of the user whose chats to retrieve.
            limit: Maximum number of chats to return (default: 100).
            offset: Number of chats to skip (default: 0).

        Returns:
            List[asyncpg.Record]: A list of asyncpg.Record objects containing chat information.
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}, {CHAT_USER_ID}
                FROM {CHATS_TABLE}
                WHERE {CHAT_USER_ID} = $1
                ORDER BY {CHAT_UPDATED_AT} DESC
                LIMIT $2 OFFSET $3
            """
            return await self._fetchall(query_str, (user_id, limit, offset))

        except Exception as e:
            logger.error(f"Failed to get chats for user {user_id}: {str(e)}")
            return []

    async def get_count(self, user_id: int) -> int:
        """
        Get the total number of chats for a specific user.

        Args:
            user_id: The ID of the user whose chat count to retrieve.

        Returns:
            int: The number of chats for the user in the database.
        """
        try:
            query_str = f"SELECT COUNT(*) FROM {CHATS_TABLE} WHERE {CHAT_USER_ID} = $1"
            record = await self._fetchone(query_str, (user_id,))
            count = record[0] if record else 0
            return count if count is not None else 0

        except Exception as e:
            logger.error(f"Failed to get chat count for user {user_id}: {str(e)}")
            return 0
