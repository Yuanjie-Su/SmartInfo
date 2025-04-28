#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Message Repository Module
Handles database operations for chat messages
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Union, Any

from backend.db.repositories.base_repository import BaseRepository
from backend.db.schema_constants import (
    MESSAGES_TABLE,
    MESSAGE_ID,
    MESSAGE_CHAT_ID,
    MESSAGE_SENDER,
    MESSAGE_CONTENT,
    MESSAGE_TIMESTAMP,
    MESSAGE_SEQUENCE_NUMBER,
    DEFAULT_SEQUENCE_NUMBER,
)

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository):
    """Repository for handling chat message operations in the database."""

    async def add(
        self,
        chat_id: int,
        sender: str,
        content: str,
        sequence_number: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Add a new message to the database and return the created message data.

        Args:
            chat_id: The ID of the chat this message belongs to
            sender: The role of the message sender (user, assistant, system)
            content: The content of the message
            sequence_number: The sequence number of the message in the conversation

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the newly created message's
                                     information (including db-generated id and timestamp)
                                     or None if creation failed.
        """
        try:
            if sequence_number is None:
                new_sequence_number = await self.get_next_sequence_number(chat_id)
                if new_sequence_number is None:
                    sequence_number = DEFAULT_SEQUENCE_NUMBER
                else:
                    sequence_number = new_sequence_number

            current_time = int(time.time())

            query_str = f"""
                INSERT INTO {MESSAGES_TABLE} (
                    {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, {MESSAGE_CONTENT},
                    {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                ) VALUES (?, ?, ?, ?, ?)
            """

            cursor = await self._execute(
                query_str,
                (chat_id, sender, content, current_time, sequence_number),
                commit=True,
            )

            message_id = self._get_last_insert_id(cursor)
            if message_id:
                logger.info(f"Added message with ID {message_id} to chat {chat_id}")
                # After successful insert, fetch the complete row using get_by_id
                # get_by_id already returns a dictionary or None
                return await self.get_by_id(message_id)
            else:
                # Insert failed (e.g., constraint violation caught by DB before execute finished?)
                logger.error(
                    f"Failed to get last insert ID after attempting to add message for chat {chat_id}"
                )
                return None

        except Exception as e:
            # Catch specific DB errors if possible, e.g., IntegrityError
            logger.error(
                f"Failed to add message for chat {chat_id}: {str(e)}", exc_info=True
            )
            return None

    async def update(
        self,
        message_id: str,
        content: Optional[str] = None,
        sequence_number: Optional[int] = None,
    ) -> bool:
        """
        Update an existing message.

        Args:
            message_id: The ID of the message to update
            content: The new content of the message (optional)
            sequence_number: The new sequence number (optional)

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            data = {}
            if content is not None:
                data[MESSAGE_CONTENT] = content
            if sequence_number is not None:
                data[MESSAGE_SEQUENCE_NUMBER] = sequence_number

            if not data:
                logger.warning("No update data provided for message update")
                return False

            # Build update query dynamically
            set_clauses = [f"{field} = ?" for field in data.keys()]
            set_clause_str = ", ".join(set_clauses)
            query_str = f"""
                UPDATE {MESSAGES_TABLE} 
                SET {set_clause_str}
                WHERE {MESSAGE_ID} = ?
            """

            # Execute update with all values plus the ID for WHERE clause
            values = list(data.values())
            values.append(message_id)
            cursor = await self._execute(query_str, tuple(values), commit=True)

            updated = self._get_rows_affected(cursor) > 0
            if updated:
                logger.info(f"Updated message with ID {message_id}")
            return updated

        except Exception as e:
            logger.error(f"Failed to update message {message_id}: {str(e)}")
            return False

    async def delete(self, message_id: str) -> bool:
        """
        Delete a message by its ID.

        Args:
            message_id: The ID of the message to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {MESSAGES_TABLE} WHERE {MESSAGE_ID} = ?"

            cursor = await self._execute(query_str, (message_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0

            if deleted:
                logger.info(f"Deleted message with ID {message_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete message {message_id}: {str(e)}")
            return False

    async def delete_by_chat_id(self, chat_id: str) -> bool:
        """
        Delete all messages associated with a chat.

        Args:
            chat_id: The ID of the chat whose messages should be deleted

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {MESSAGES_TABLE} WHERE {MESSAGE_CHAT_ID} = ?"

            cursor = await self._execute(query_str, (chat_id,), commit=True)
            deleted = self._get_rows_affected(cursor) > 0

            if deleted:
                logger.info(f"Deleted all messages for chat ID {chat_id}")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete messages for chat {chat_id}: {str(e)}")
            return False

    async def get_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a message by its ID.

        Args:
            message_id: The ID of the message to retrieve

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the message information or None if not found
        """
        try:
            query_str = f"""
                SELECT {MESSAGE_ID}, {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, 
                       {MESSAGE_CONTENT}, {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                FROM {MESSAGES_TABLE} WHERE {MESSAGE_ID} = ?
            """

            return await self._fetchone_as_dict(query_str, (message_id,))

        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {str(e)}")
            return None

    async def get_by_chat_id(self, chat_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a specific chat, ordered by sequence number.

        Args:
            chat_id: The ID of the chat whose messages to retrieve

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing a message's information
        """
        try:
            query_str = f"""
                SELECT {MESSAGE_ID}, {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, 
                       {MESSAGE_CONTENT}, {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                FROM {MESSAGES_TABLE} 
                WHERE {MESSAGE_CHAT_ID} = ?
                ORDER BY {MESSAGE_SEQUENCE_NUMBER} ASC
            """

            return await self._fetch_as_dict(query_str, (chat_id,))

        except Exception as e:
            logger.error(f"Failed to get messages for chat {chat_id}: {str(e)}")
            return []

    async def get_chat_message_count(self, chat_id: str) -> int:
        """
        Get the count of messages in a specific chat.

        Args:
            chat_id: The ID of the chat whose message count to retrieve

        Returns:
            int: The number of messages in the chat
        """
        try:
            query_str = f"""
                SELECT COUNT(*)
                FROM {MESSAGES_TABLE} 
                WHERE {MESSAGE_CHAT_ID} = ?
            """

            row = await self._fetchone(query_str, (chat_id,))
            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Failed to get message count for chat {chat_id}: {str(e)}")
            return 0

    async def get_next_sequence_number(self, chat_id: str) -> int:
        """
        Get the next sequence number for a message in a specific chat.

        Args:
            chat_id: The ID of the chat

        Returns:
            int: The next sequence number (max existing + 1) or DEFAULT_SEQUENCE_NUMBER if no messages exist
        """
        try:
            query_str = f"""
                SELECT MAX({MESSAGE_SEQUENCE_NUMBER})
                FROM {MESSAGES_TABLE} 
                WHERE {MESSAGE_CHAT_ID} = ?
            """

            row = await self._fetchone(query_str, (chat_id,))
            if row and row[0] is not None:
                return row[0] + 1
            return DEFAULT_SEQUENCE_NUMBER

        except Exception as e:
            logger.error(
                f"Failed to get next sequence number for chat {chat_id}: {str(e)}"
            )
            return DEFAULT_SEQUENCE_NUMBER

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """
        Convert a database row to a dictionary.

        Args:
            row: A database row containing message data

        Returns:
            Dict[str, Any]: A dictionary with message fields
        """
        return {
            MESSAGE_ID: row[0],
            MESSAGE_CHAT_ID: row[1],
            MESSAGE_SENDER: row[2],
            MESSAGE_CONTENT: row[3],
            MESSAGE_TIMESTAMP: row[4],
            MESSAGE_SEQUENCE_NUMBER: row[5],
        }
