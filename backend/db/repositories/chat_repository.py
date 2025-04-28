#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Repository Module
Handles database operations for chat sessions
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Any

from backend.db.repositories.base_repository import BaseRepository
from backend.db.schema_constants import (
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
            current_time = int(time.time())

            query_str = f"""
                INSERT INTO {CHATS_TABLE} (
                    {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                ) VALUES (?, ?, ?)
            """

            cursor = await self._execute(
                query_str, (title, current_time, current_time), commit=True
            )
            chat_id = self._get_last_insert_id(cursor)

            if chat_id:
                logger.info(f"Created chat with ID {chat_id} and title '{title}'")
                return chat_id
            return None

        except Exception as e:
            logger.error(f"Failed to create chat: {str(e)}")
            return None

    async def update(self, chat_id: str, title: Optional[str] = None) -> bool:
        """
        Update an existing chat.

        Args:
            chat_id: The ID of the chat to update
            title: New chat title (optional)

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            # Get current chat data to ensure we have a newer timestamp
            current_chat = await self.get_by_id(chat_id)
            if not current_chat:
                logger.warning(f"Chat with ID {chat_id} not found for update")
                return False

            data = {}
            if title is not None:
                data[CHAT_TITLE] = title

            # Ensure updated_at is always newer than current
            current_time = int(time.time())
            data[CHAT_UPDATED_AT] = current_time

            if not data:
                logger.warning("No update data provided for chat update")
                return False

            # Build update query dynamically
            set_clauses = [f"{field} = ?" for field in data.keys()]
            set_clause_str = ", ".join(set_clauses)
            query_str = f"""
                UPDATE {CHATS_TABLE} 
                SET {set_clause_str}
                WHERE {CHAT_ID} = ?
            """

            # Execute update with all values plus the ID for WHERE clause
            values = list(data.values())
            values.append(chat_id)
            cursor = await self._execute(query_str, tuple(values), commit=True)

            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated chat with ID {chat_id}")
            return updated

        except Exception as e:
            logger.error(f"Failed to update chat {chat_id}: {str(e)}")
            return False

    async def delete(self, chat_id: str) -> bool:
        """
        Delete a chat by its ID.

        Args:
            chat_id: The ID of the chat to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {CHATS_TABLE} WHERE {CHAT_ID} = ?"

            cursor = await self._execute(query_str, (chat_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0

            if deleted:
                logger.info(f"Deleted chat with ID {chat_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete chat {chat_id}: {str(e)}")
            return False

    async def get_by_id(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chat by its ID.

        Args:
            chat_id: The ID of the chat to retrieve

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the chat information or None if not found
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                FROM {CHATS_TABLE} WHERE {CHAT_ID} = ?
            """

            return await self._fetchone_as_dict(query_str, (chat_id,))

        except Exception as e:
            logger.error(f"Failed to get chat {chat_id}: {str(e)}")
            return None

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all chats with pagination.

        Args:
            limit: Maximum number of chats to return (default: 100)
            offset: Number of chats to skip (default: 0)

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing chat information
        """
        try:
            query_str = f"""
                SELECT {CHAT_ID}, {CHAT_TITLE}, {CHAT_CREATED_AT}, {CHAT_UPDATED_AT}
                FROM {CHATS_TABLE}
                ORDER BY {CHAT_UPDATED_AT} DESC
                LIMIT ? OFFSET ?
            """

            return await self._fetch_as_dict(query_str, (limit, offset))

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

            row = await self._fetchone(query_str)
            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Failed to get chat count: {str(e)}")
            return 0

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """
        Convert a database row to a dictionary.

        Args:
            row: Database row as tuple

        Returns:
            Dict[str, Any]: Dictionary with chat data
        """
        return {
            CHAT_ID: row[0],
            CHAT_TITLE: row[1],
            CHAT_CREATED_AT: row[2],
            CHAT_UPDATED_AT: row[3],
        }
