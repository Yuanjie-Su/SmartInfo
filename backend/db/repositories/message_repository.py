#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Message Repository Module
Handles database operations for chat messages
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Union, Any
import asyncpg
from datetime import datetime, timezone

from db.repositories.base_repository import BaseRepository
from db.schema_constants import (
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
    ) -> Optional[asyncpg.Record]:
        """
        Add a new message to the database and return the created message data.

        Args:
            chat_id: The ID of the chat this message belongs to
            sender: The role of the message sender (user, assistant, system)
            content: The content of the message
            sequence_number: The sequence number of the message in the conversation

        Returns:
            Optional[asyncpg.Record]: An asyncpg.Record containing the newly created message's
                                     information (including db-generated id and timestamp)
                                     or None if creation failed.
        """
        try:
            if sequence_number is None:
                new_sequence_number = await self.get_next_sequence_number(chat_id)
                sequence_number = (
                    new_sequence_number
                    if new_sequence_number is not None
                    else DEFAULT_SEQUENCE_NUMBER
                )

            current_time = datetime.now(timezone.utc)

            query_str = f"""
                INSERT INTO {MESSAGES_TABLE} (
                    {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, {MESSAGE_CONTENT},
                    {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """
            params = (chat_id, sender, content, current_time, sequence_number)

            # Use _fetchone instead of conn.fetchrow
            new_message_record = await self._fetchone(query_str, params)

            if new_message_record:
                logger.info(
                    f"Added message with ID {new_message_record[MESSAGE_ID.lower()]} to chat {chat_id}"
                )
                return new_message_record
            else:
                logger.error(
                    f"Failed to add message for chat {chat_id}, no record returned."
                )
                return None

        except asyncpg.PostgresError as e:
            logger.error(
                f"Failed to add message for chat {chat_id}: {str(e)}", exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error adding message for chat {chat_id}: {str(e)}",
                exc_info=True,
            )
            return None

    async def update(
        self,
        message_id: int,
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
            updates = {}
            params = []
            param_index = 1

            if content is not None:
                updates[MESSAGE_CONTENT] = f"${param_index}"
                params.append(content)
                param_index += 1
            if sequence_number is not None:
                updates[MESSAGE_SEQUENCE_NUMBER] = f"${param_index}"
                params.append(sequence_number)
                param_index += 1

            if not updates:
                logger.warning("No update data provided for message update")
                return False

            set_clause_str = ", ".join(
                f"{field} = {placeholder}" for field, placeholder in updates.items()
            )
            query_str = f"""
                UPDATE {MESSAGES_TABLE}
                SET {set_clause_str}
                WHERE {MESSAGE_ID} = ${param_index}
            """
            params.append(message_id)

            status = await self._execute(query_str, tuple(params))
            updated = status is not None and status.startswith("UPDATE 1")
            if updated:
                logger.info(f"Updated message with ID {message_id}")
            else:
                logger.warning(
                    f"Update command for message ID {message_id} executed but status was '{status}'."
                )
            return updated

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to update message {message_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating message {message_id}: {str(e)}")
            return False

    async def delete(self, message_id: int) -> bool:
        """
        Delete a message by its ID.

        Args:
            message_id: The ID of the message to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {MESSAGES_TABLE} WHERE {MESSAGE_ID} = $1"

            status = await self._execute(query_str, (message_id,))
            deleted = status is not None and status.startswith("DELETE 1")

            if deleted:
                logger.info(f"Deleted message with ID {message_id}")
            else:
                logger.warning(
                    f"Delete command for message ID {message_id} executed but status was '{status}'."
                )
            return deleted

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to delete message {message_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting message {message_id}: {str(e)}")
            return False

    async def delete_by_chat_id(self, chat_id: int) -> bool:
        """
        Delete all messages associated with a chat.

        Args:
            chat_id: The ID of the chat whose messages should be deleted

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            query_str = f"DELETE FROM {MESSAGES_TABLE} WHERE {MESSAGE_CHAT_ID} = $1"

            status = await self._execute(query_str, (chat_id,))
            logger.info(
                f"Executed delete for messages in chat {chat_id}. Status: {status}"
            )
            return True

        except asyncpg.PostgresError as e:
            logger.error(f"Failed to delete messages for chat {chat_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting messages for chat {chat_id}: {str(e)}"
            )
            return False

    async def get_by_id(self, message_id: int) -> Optional[asyncpg.Record]:
        """
        Get a message by its ID.

        Args:
            message_id: The ID of the message to retrieve

        Returns:
            Optional[asyncpg.Record]: An asyncpg.Record containing the message information or None if not found
        """
        try:
            query_str = f"""
                SELECT {MESSAGE_ID}, {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, 
                       {MESSAGE_CONTENT}, {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                FROM {MESSAGES_TABLE} WHERE {MESSAGE_ID} = $1
            """
            return await self._fetchone(query_str, (message_id,))

        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {str(e)}")
            return None

    async def get_by_chat_id(self, chat_id: int) -> List[asyncpg.Record]:
        """
        Get all messages for a specific chat, ordered by sequence number.

        Args:
            chat_id: The ID of the chat whose messages to retrieve

        Returns:
            List[asyncpg.Record]: A list of asyncpg.Records, each containing a message's information
        """
        try:
            query_str = f"""
                SELECT {MESSAGE_ID}, {MESSAGE_CHAT_ID}, {MESSAGE_SENDER}, 
                       {MESSAGE_CONTENT}, {MESSAGE_TIMESTAMP}, {MESSAGE_SEQUENCE_NUMBER}
                FROM {MESSAGES_TABLE} 
                WHERE {MESSAGE_CHAT_ID} = $1
                ORDER BY {MESSAGE_SEQUENCE_NUMBER} ASC
            """
            return await self._fetchall(query_str, (chat_id,))

        except Exception as e:
            logger.error(f"Failed to get messages for chat {chat_id}: {str(e)}")
            return []

    async def get_chat_message_count(self, chat_id: int) -> int:
        """
        Get the count of messages in a specific chat.

        Args:
            chat_id: The ID of the chat whose message count to retrieve

        Returns:
            int: The number of messages in the chat
        """
        try:
            query_str = (
                f"SELECT COUNT(*) FROM {MESSAGES_TABLE} WHERE {MESSAGE_CHAT_ID} = $1"
            )
            # Use _fetchone
            record = await self._fetchone(query_str, (chat_id,))
            count = record[0] if record else 0
            return count if count is not None else 0

        except Exception as e:
            logger.error(f"Failed to get message count for chat {chat_id}: {str(e)}")
            return 0

    async def get_next_sequence_number(self, chat_id: int) -> int:
        """
        Get the next sequence number for a message in a specific chat.

        Args:
            chat_id: The ID of the chat

        Returns:
            int: The next sequence number (max existing + 1) or DEFAULT_SEQUENCE_NUMBER if no messages exist
        """
        try:
            query_str = f"SELECT MAX({MESSAGE_SEQUENCE_NUMBER}) FROM {MESSAGES_TABLE} WHERE {MESSAGE_CHAT_ID} = $1"
            # Use _fetchone
            record = await self._fetchone(query_str, (chat_id,))
            max_sequence = record[0] if record and record[0] is not None else None

            if max_sequence is None:
                return DEFAULT_SEQUENCE_NUMBER
            else:
                return (max_sequence or 0) + 1
        except Exception as e:
            logger.error(
                f"Failed to get next sequence number for chat {chat_id}: {str(e)}"
            )
            return DEFAULT_SEQUENCE_NUMBER
