# backend/models/chat.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pydantic models for chat related data (sessions and messages).
"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

# --- Message Models ---


class MessageBase(BaseModel):
    """Base schema for message data."""

    chat_id: int = Field(
        ..., description="ID of the chat session this message belongs to"
    )
    sender: str = Field(
        ..., description="Sender of the message ('user' or 'assistant')"
    )
    content: str = Field(..., description="Content of the message")


class MessageCreate(MessageBase):
    """Schema for creating a new message."""

    # sequence_number can be automatically determined by the service if not provided
    sequence_number: Optional[int] = Field(
        None,
        description="Order of the message within the chat (optional, service assigns if None)",
    )


class Message(MessageBase):
    """Schema for representing a message, including database ID and timestamps."""

    id: int = Field(..., description="Unique identifier for the message")
    timestamp: Optional[datetime] = Field(
        None, description="Timestamp when the message was created (ISO 8601 format)"
    )
    sequence_number: int = Field(
        ..., description="Order of the message within the chat"
    )

    model_config = ConfigDict(from_attributes=True)


# --- Chat Session Models ---


class ChatBase(BaseModel):
    """Base schema for chat session data."""

    title: str = Field(..., max_length=255, description="Title of the chat session")
    user_id: int = Field(..., description="ID of the user who owns this chat")


class ChatCreate(ChatBase):
    """Schema for creating a new chat session."""

    pass


class Chat(ChatBase):
    """Schema for representing a chat session, including database ID and messages."""

    id: int = Field(..., description="Unique identifier for the chat session")
    created_at: Optional[datetime] = Field(
        None, description="Creation timestamp (ISO 8601 format)"
    )
    updated_at: Optional[datetime] = Field(
        None, description="Last modification timestamp (ISO 8601 format)"
    )
    messages: Optional[List[Message]] = Field(
        None,
        description="List of messages in the chat session (optional, loaded on demand)",
    )

    model_config = ConfigDict(from_attributes=True)


# --- Chat Interaction Models ---


class ChatAnswer(BaseModel):
    """Schema for an LLM chat answer."""

    chat_id: int = Field(..., description="ID of the chat session")
    message_id: Optional[int] = Field(
        None,
        description="ID of the assistant's message created in the database (if saved)",
    )
    content: str = Field(..., description="Content of the assistant's response")


class Question(BaseModel):
    """Schema for a user question submitted to the chat endpoint."""

    content: str = Field(..., description="The question content from the user")
    chat_id: Optional[int] = Field(
        None, description="Optional chat ID to provide conversation context"
    )
