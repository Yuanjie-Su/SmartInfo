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
)

logger = logging.getLogger(__name__)


class ChatRepository(BaseRepository):
    """Repository for handling chat operations in the database."""

    async def add(self, title: str) -> Optional[int]:
        """
        Create a new chat in the database.

        Args:
            title: The title of the chat

        Returns:
            int: The ID of the newly created chat or None if creation failed
        """
        try:
            current_time = datetime.now(timezone.utc)

            query_str = f"""
                INSERT INTO {CHATS_TABLE} (
                    {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                ) VALUES ($1, $2, $3)
                RETURNING {CHAT_ID}
            """
            params = (title, current_time, current_time)

            # Use _fetchone for RETURNING id
            record = await self._fetchone(query_str, params)
            chat_id = record[0] if record else None

            if chat_id is not None:
                logger.info(f"Created chat with ID {chat_id} and title '{title}'")
            else:
                logger.warning(
                    f"Failed to create chat with title '{title}', no ID returned."
                )
            return chat_id

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to create chat: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating chat: {str(e)}")
            return None

    async def update(self, chat_id: int, title: Optional[str] = None) -> bool:
        """
        Update an existing chat.

        Args:
            chat_id: The ID of the chat to update
            title: New chat title (optional)

        Returns:
            bool: True if update was successful, False otherwise
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
                logger.warning("No update data provided for chat update")
                return False

            set_clause_str = ", ".join(
                f"{field} = {placeholder}" for field, placeholder in updates.items()
            )
            query_str = f"""
                UPDATE {CHATS_TABLE}
                SET {set_clause_str}
                WHERE {CHAT_ID} = ${param_index}
            """
            params.append(chat_id)

            status = await self._execute(query_str, tuple(params))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated chat with ID {chat_id}")
            else:
                logger.warning(
                    f"Update command for chat ID {chat_id} executed but status was '{status}'."
                )
            return updated

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to update chat {chat_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating chat {chat_id}: {str(e)}")
            return False

    async def delete(self, chat_id: int) -> bool:
        """
        Delete a chat by its ID.

        Args:
            chat_id: The ID of the chat to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {CHATS_TABLE} WHERE {CHAT_ID} = $1"

            status = await self._execute(query_str, (chat_id,))
            deleted = status is not None and status.startswith("DELETE 1")

            if deleted:
                logger.info(f"Deleted chat with ID {chat_id}")
            else:
                logger.warning(
                    f"Delete command for chat ID {chat_id} executed but status was '{status}'."
                )
            return deleted

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to delete chat {chat_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting chat {chat_id}: {str(e)}")
            return False

    async def get_by_id(self, chat_id: int) -> Optional[asyncpg.Record]:
        """
        Get a chat by its ID.

        Args:
            chat_id: The ID of the chat to retrieve

        Returns:
            Optional[asyncpg.Record]: An asyncpg.Record containing the chat information or None if not found
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                FROM {CHATS_TABLE} WHERE {CHAT_ID} = $1
            """
            return await self._fetchone(query_str, (chat_id,))

        except Exception as e:
            logger.error(f"Failed to get chat {chat_id}: {str(e)}")
            return None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[asyncpg.Record]:
        """
        Get all chats with pagination.

        Args:
            limit: Maximum number of chats to return (default: 100)
            offset: Number of chats to skip (default: 0)

        Returns:
            List[asyncpg.Record]: A list of asyncpg.Record objects containing chat information
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                FROM {CHATS_TABLE}
                ORDER BY {CHAT_UPDATED_AT} DESC
                LIMIT $1 OFFSET $2
            """
            return await self._fetchall(query_str, (limit, offset))

        except Exception as e:
            logger.error(f"Failed to get chats: {str(e)}")
            return []

    async def get_count(self) -> int:
        """
        Get the total number of chats.

        Returns:
            int: The number of chats in the database
        """
        try:
            query_str = f"SELECT COUNT(*) FROM {CHATS_TABLE}"
            # Use _fetchone
            record = await self._fetchone(query_str)
            count = record[0] if record else 0
            return count if count is not None else 0

        except Exception as e:
            logger.error(f"Failed to get chat count: {str(e)}")
            return 0
