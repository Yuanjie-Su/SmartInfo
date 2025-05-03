#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat service for managing chat sessions and processing messages
"""

import logging
import json
import time
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from db.repositories.chat_repository import ChatRepository
from db.repositories.message_repository import MessageRepository
from core.llm import LLMClientPool
from models.schemas.chat import (
    Chat,
    ChatCreate,
    Message,
    MessageCreate,
    ChatAnswer,
)

logger = logging.getLogger(__name__)

# Default LLM model for Q&A
DEFAULT_MODEL = "deepseek-v3-250324"


class ChatService:
    """Service for managing chat sessions and messages"""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
    ):
        """Initialize the chat service"""
        self._chat_repo = chat_repo
        self._message_repo = message_repo
        self._llm_pool: Optional[LLMClientPool] = None

    def set_llm_pool(self, llm_pool: LLMClientPool) -> None:
        """Set the LLM client pool"""
        self._llm_pool = llm_pool
        logger.info("LLM client pool set for ChatService")

    # --- Chat Session Management ---

    async def get_all_chats(self) -> List[Chat]:
        """Get all chat sessions"""
        chats = await self._chat_repo.get_all()
        return [
            Chat(
                id=chat["id"],
                title=chat["title"],
                created_at=chat["created_at"],
                updated_at=chat["updated_at"],
            )
            for chat in chats
        ]

    async def get_chat_by_id(self, chat_id: int) -> Optional[Chat]:
        """Get a chat session by ID"""
        chat = await self._chat_repo.get_by_id(chat_id)
        if not chat:
            return None

        # Get messages for this chat
        messages = await self.get_messages_by_chat_id(chat_id)

        return Chat(
            id=chat["id"],
            title=chat["title"],
            created_at=chat["created_at"],
            updated_at=chat["updated_at"],
            messages=messages,
        )

    async def create_chat(self, chat: ChatCreate) -> Chat:
        """Create a new chat session"""
        chat_dict = chat.model_dump()  # Use model_dump
        chat_id = await self._chat_repo.add(title=chat_dict["title"])

        return await self.get_chat_by_id(chat_id)

    async def update_chat(self, chat_id: int, chat: ChatCreate) -> Optional[Chat]:
        """Update a chat session"""
        # First check if the chat exists
        existing_chat = await self._chat_repo.get_by_id(chat_id)
        if not existing_chat:
            return None

        chat_dict = chat.model_dump()  # Use model_dump
        success = await self._chat_repo.update(
            chat_id=chat_id, title=chat_dict["title"]
        )

        if not success:
            return None

        return await self.get_chat_by_id(chat_id)

    async def delete_chat(self, chat_id: int) -> bool:
        """Delete a chat session"""
        return await self._chat_repo.delete(chat_id)

    # --- Message Management ---

    async def get_messages_by_chat_id(self, chat_id: int) -> List[Message]:
        """Get all messages for a chat session"""
        messages = await self._message_repo.get_by_chat_id(chat_id)
        return [
            Message(
                id=msg["id"],
                chat_id=msg["chat_id"],
                sender=msg["sender"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                sequence_number=msg["sequence_number"],
            )
            for msg in messages
        ]

    async def get_message_by_id(self, message_id: int) -> Optional[Message]:
        """Get a message by ID"""
        message = await self._message_repo.get_by_id(message_id)
        if not message:
            return None

        return Message(
            id=message["id"],
            chat_id=message["chat_id"],
            sender=message["sender"],
            content=message["content"],
            timestamp=message["timestamp"],
            sequence_number=message["sequence_number"],
        )

    async def create_message(self, message: MessageCreate) -> Message:
        msg_dict = message.model_dump()  # Use model_dump

        # Attempt to add the message to the database
        # The repository's add method now returns the full message data as a dict or None
        created_message_data = await self._message_repo.add(
            chat_id=msg_dict["chat_id"],
            sender=msg_dict["sender"],
            content=msg_dict["content"],
            sequence_number=msg_dict.get("sequence_number"),
        )

        # Check if the database insertion and retrieval were successful
        if created_message_data is None:
            error_msg = f"Failed to save message to database or retrieve it afterwards for chat {msg_dict['chat_id']}."
            logger.error(error_msg)
            raise ValueError(error_msg)

        return Message(**created_message_data)

    async def delete_message(self, message_id: int) -> bool:
        """Delete a message"""
        return await self._message_repo.delete(message_id)

    # --- LLM Interaction ---

    async def process_question(
        self, content: str, chat_id: Optional[int] = None
    ) -> ChatAnswer:
        """
        Process a question and get an answer from the LLM

        Args:
            content: The question content
            chat_id: Optional chat ID for context

        Returns:
            ChatAnswer object with the LLM's response
        """
        if not self._llm_pool:
            raise ValueError("LLM client pool not set")

        # Create context from existing messages if chat_id is provided
        messages = []
        chat_title = None
        chat_messages = []

        if chat_id:
            # Get the chat
            chat = await self._chat_repo.get_by_id(chat_id)
            if chat:
                chat_title = chat["title"]

                # Get recent messages (last 10) for context
                chat_messages_data = await self._message_repo.get_by_chat_id(chat_id)
                chat_messages = []

                # 转换消息数据格式
                for msg in chat_messages_data:
                    chat_messages.append(
                        Message(
                            id=msg["id"],
                            chat_id=msg["chat_id"],
                            sender=msg["sender"],
                            content=msg["content"],
                            timestamp=msg["timestamp"],
                            sequence_number=msg["sequence_number"],
                        )
                    )

                chat_messages = sorted(chat_messages, key=lambda m: m.timestamp)[
                    -10:
                ]  # Sort by timestamp

                # Add to context - convert 'sender' to 'role' for the LLM API
                messages.extend(
                    [
                        {"role": msg.sender, "content": msg.content}
                        for msg in chat_messages
                    ]
                )

        # Add the question
        messages.append({"role": "user", "content": content})

        # Create a new chat if needed
        if not chat_id:
            chat_create = ChatCreate(
                title=content[:50] + "..." if len(content) > 50 else content
            )
            new_chat = await self.create_chat(chat_create)
            chat_id = new_chat.id
            chat_title = new_chat.title

        # Add user's question as a message
        user_message_create = MessageCreate(
            chat_id=chat_id, sender="user", content=content
        )
        await self.create_message(user_message_create)

        # Run inference with the LLM
        system_message = {"role": "system", "content": "你是一个有帮助的AI助手。"}
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, system_message)

        answer = await self._llm_pool.get_completion_content(
            messages=messages, model=DEFAULT_MODEL
        )

        if not answer:
            error_msg = "Failed to get response from LLM"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Add assistant's response as a message
        assistant_message_create = MessageCreate(
            chat_id=chat_id, sender="assistant", content=answer
        )
        assistant_message = await self.create_message(assistant_message_create)

        return ChatAnswer(
            chat_id=chat_id,
            message_id=assistant_message.id,
            content=answer,
        )
