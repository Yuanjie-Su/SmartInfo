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

import logging
import json
import time
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from db.repositories.chat_repository import ChatRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.api_key_repository import (
    ApiKeyRepository,
)  # Import ApiKeyRepository
from core.llm.client import AsyncLLMClient  # Import AsyncLLMClient
from models import (  # Import models directly
    Chat,
    ChatCreate,
    Message,
    MessageCreate,
    ChatAnswer,
    User,  # Import User for type hinting
    ApiKey,  # Import ApiKey model
)

logger = logging.getLogger(__name__)


class ChatService:
    """Service for managing chat sessions and messages"""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
        api_key_repo: ApiKeyRepository,  # Add ApiKeyRepository dependency
    ):
        """Initialize the chat service"""
        self._chat_repo = chat_repo
        self._message_repo = message_repo
        self._api_key_repo = api_key_repo  # Store ApiKeyRepository

    # --- Chat Session Management (User-Aware) ---

    async def get_all_chats(self, user_id: int) -> List[Chat]:
        """Get all chat sessions for a specific user."""
        chats = await self._chat_repo.get_all(user_id=user_id)
        # Assuming Chat model now includes user_id
        return [
            Chat.model_validate(chat) for chat in chats
        ]  # Use model_validate for Pydantic v2

    async def get_chat_by_id(self, chat_id: int, user_id: int) -> Optional[Chat]:
        """Get a chat session by ID for a specific user."""
        chat_record = await self._chat_repo.get_by_id(chat_id=chat_id, user_id=user_id)
        if not chat_record:
            return None

        # Get messages for this chat (Message repo doesn't need user_id directly)
        messages = await self.get_messages_by_chat_id(chat_id)

        # Assuming Chat model includes user_id and messages
        chat_data = dict(chat_record)
        chat_data["messages"] = messages
        return Chat.model_validate(chat_data)  # Use model_validate

    async def create_chat(self, chat_data: ChatCreate, user_id: int) -> Chat:
        """Create a new chat session for a specific user."""
        # Ensure user_id from ChatCreate matches the authenticated user's ID
        if chat_data.user_id != user_id:
            raise ValueError("User ID in chat data does not match authenticated user.")

        chat_id = await self._chat_repo.add(title=chat_data.title, user_id=user_id)
        if chat_id is None:
            raise ValueError(f"Failed to create chat for user {user_id}")

        created_chat = await self.get_chat_by_id(chat_id=chat_id, user_id=user_id)
        if created_chat is None:
            raise ValueError(
                f"Failed to retrieve newly created chat {chat_id} for user {user_id}"
            )
        return created_chat

    async def update_chat(
        self, chat_id: int, chat_data: ChatCreate, user_id: int
    ) -> Optional[Chat]:
        """Update a chat session belonging to a specific user."""
        # Ensure user_id from ChatCreate matches the authenticated user's ID
        if chat_data.user_id != user_id:
            raise ValueError("User ID in chat data does not match authenticated user.")

        # The repository's update method now handles the user_id check
        success = await self._chat_repo.update(
            chat_id=chat_id, user_id=user_id, title=chat_data.title
        )

        if not success:
            return None

        return await self.get_chat_by_id(chat_id=chat_id, user_id=user_id)

    async def delete_chat(self, chat_id: int, user_id: int) -> bool:
        """Delete a chat session belonging to a specific user."""
        # The repository's delete method now handles the user_id check
        # Consider adding logic here to delete associated messages if needed
        # messages_deleted = await self._message_repo.delete_by_chat_id(chat_id)
        # if not messages_deleted: logger.warning(...)
        return await self._chat_repo.delete(chat_id=chat_id, user_id=user_id)

    # --- Message Management (Remains largely unchanged, user context applied via chat_id) ---

    async def get_messages_by_chat_id(self, chat_id: int) -> List[Message]:
        """Get all messages for a chat session"""
        messages = await self._message_repo.get_by_chat_id(chat_id)
        return [Message.model_validate(msg) for msg in messages]  # Use model_validate

    async def get_message_by_id(self, message_id: int) -> Optional[Message]:
        """Get a message by ID"""
        message = await self._message_repo.get_by_id(message_id)
        if not message:
            return None
        return Message.model_validate(message)  # Use model_validate

    async def create_message(self, message: MessageCreate) -> Message:
        """Create a new message. User context is implicit via chat_id ownership check in process_question."""
        # NOTE: We rely on process_question to verify chat_id ownership before calling this.
        # If create_message could be called directly from an endpoint, add user_id check here.
        created_message_data = await self._message_repo.add(
            chat_id=message.chat_id,
            sender=message.sender,
            content=message.content,
            sequence_number=message.sequence_number,
        )

        if created_message_data is None:
            error_msg = f"Failed to save message to database or retrieve it afterwards for chat {message.chat_id}."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Assuming add returns a dict or record convertible by model_validate
        return Message.model_validate(created_message_data)

    async def delete_message(self, message_id: int) -> bool:
        """Delete a message. Add user context check if needed."""
        # NOTE: Add user context check here if required.
        # E.g., Get message, check message.chat_id, check chat ownership via get_chat_by_id(chat_id, user_id)
        return await self._message_repo.delete(message_id)

    # --- LLM Interaction (User-Aware) ---

    async def process_question(
        self, content: str, user: User, chat_id: Optional[int] = None
    ) -> ChatAnswer:
        """
        Process a question for a specific user and get an answer from the LLM.

        Args:
            content: The question content.
            user: The authenticated user object.
            chat_id: Optional chat ID for context (must belong to the user).

        Returns:
            ChatAnswer object with the LLM's response.
        """
        messages = []
        chat_title = None
        user_id = user.id  # Get user ID from the authenticated user object

        if chat_id:
            # Get the chat, ensuring it belongs to the user
            chat = await self.get_chat_by_id(
                chat_id=chat_id, user_id=user_id
            )  # Use the service method
            if not chat:
                raise ValueError(
                    f"Chat ID {chat_id} not found or does not belong to user {user_id}"
                )

            chat_title = chat.title
            chat_messages = (
                chat.messages or []
            )  # Messages are already loaded by get_chat_by_id

            # Sort by timestamp and take last 10 (if messages exist)
            if chat_messages:
                chat_messages = sorted(chat_messages, key=lambda m: m.timestamp)[-10:]
                messages.extend(
                    [
                        {"role": msg.sender, "content": msg.content}
                        for msg in chat_messages
                    ]
                )

        messages.append({"role": "user", "content": content})

        # Create a new chat if needed (associating with the user)
        if not chat_id:
            chat_create_data = ChatCreate(
                title=content[:50] + "..." if len(content) > 50 else content,
                user_id=user_id,  # Pass user_id here
            )
            new_chat = await self.create_chat(
                chat_data=chat_create_data, user_id=user_id
            )
            chat_id = new_chat.id
            chat_title = new_chat.title

        # Add user's question as a message
        if chat_id is None:  # Should not happen if logic above is correct
            raise ValueError(
                "Failed to obtain a valid chat_id before creating message."
            )

        user_message_create = MessageCreate(
            chat_id=chat_id, sender="user", content=content
        )
        await self.create_message(user_message_create)

        # Get user-specific LLM client
        client = await self._get_user_llm_client(user_id)
        if client is None:
            error_msg = f"No valid LLM API key found for user {user_id}."
            logger.error(error_msg)
            # Add an assistant message indicating the error
            answer_content = "Sorry, I cannot process your request. No valid LLM API key is configured for your account."
            assistant_message_create = MessageCreate(
                chat_id=chat_id, sender="assistant", content=answer_content
            )
            await self.create_message(assistant_message_create)
            raise ValueError(error_msg)  # Or return a specific error response

        # Run inference with the LLM using the on-demand client
        system_message = {"role": "system", "content": "你是一个有帮助的AI助手。"}
        if not messages or messages[0]["role"] != "system":
            messages.insert(0, system_message)

        answer_content = None
        try:
            async with client as llm_client:
                answer_content = await llm_client.get_completion_content(
                    messages=messages
                )
        except Exception as e:
            error_msg = f"Error during LLM inference for user {user_id}: {e}"
            logger.error(error_msg, exc_info=True)
            answer_content = (
                "Sorry, I encountered an error communicating with the LLM service."
            )
            # Decide whether to save an error message or raise exception
            # Saving an error message might be better UX
            # raise ValueError(error_msg) # Option to raise

        if not answer_content:
            answer_content = "Sorry, I received an empty response from the LLM."
            logger.warning(f"Empty response from LLM for user {user_id}")

        # Add assistant's response as a message
        assistant_message_create = MessageCreate(
            chat_id=chat_id, sender="assistant", content=answer_content
        )
        assistant_message = await self.create_message(assistant_message_create)

        return ChatAnswer(
            chat_id=chat_id,
            message_id=assistant_message.id,
            content=answer_content,
        )

    async def _get_user_llm_client(self, user_id: int) -> Optional[AsyncLLMClient]:
        """
        Fetches user's API key configuration and instantiates an AsyncLLMClient.
        Returns None if no valid key is found.
        """
        api_keys_data = await self._api_key_repo.get_all(user_id)

        if not api_keys_data:
            logger.warning(f"No API keys found for user {user_id}.")
            return None

        # Use the first valid API key found
        for key_data in api_keys_data:
            try:
                api_key = ApiKey.model_validate(key_data)
                logger.info(
                    f"Using API key ID {api_key.id} for user {user_id} (Provider: {api_key.provider})."
                )
                # Instantiate AsyncLLMClient with user-specific config
                # Note: AsyncLLMClient expects base_url, api_key, model, etc.
                # These should come from the ApiKey model fields.
                # Assuming ApiKey model has fields like base_url, api_key, model, etc.
                # You might need to map ApiKey fields to AsyncLLMClient parameters
                # based on the specific LLM provider (api_key.provider).
                # For simplicity, assuming generic fields match AsyncLLMClient params.
                # You might need more complex logic here based on provider.
                return AsyncLLMClient(
                    base_url=api_key.base_url,
                    api_key=api_key.api_key,
                    model=api_key.model,
                    # Add other parameters if needed, e.g., context_window, max_output_tokens
                    # These might also come from the ApiKey model or user preferences
                )
            except Exception as e:
                logger.error(
                    f"Failed to validate or instantiate LLM client for API key data: {key_data}. Error: {e}",
                    exc_info=True,
                )
                continue  # Try the next key

        logger.warning(f"No valid API key configuration found for user {user_id}.")
        return None
