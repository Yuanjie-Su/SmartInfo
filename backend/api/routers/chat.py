# backend/api/routers/chat.py
# -*- coding: utf-8 -*-
"""
API router for chat functionalities (Version 1).
Handles chat session management, message operations, and interaction with the LLM.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any, Optional

# Import dependencies from the centralized dependencies module
from api.dependencies import get_chat_service

# Import schemas from the main models package
from models.schemas.chat import (
    Chat,
    ChatCreate,
    Message,
    MessageCreate,
    ChatAnswer,
    Question,
)

# Import the service class type hint
from services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Chat Session Endpoints ---


@router.get("/", response_model=List[Chat], summary="List all chat sessions")
async def get_all_chats(chat_service: ChatService = Depends(get_chat_service)):
    """
    Retrieve a list of all existing chat sessions, ordered by last update time.
    """
    try:
        chats = await chat_service.get_all_chats()
        return chats
    except Exception as e:
        logger.exception("Failed to retrieve all chats", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving chats.",
        )


@router.get("/{chat_id}", response_model=Chat, summary="Get a specific chat session")
async def get_chat_by_id(
    chat_id: int, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Retrieve a specific chat session by its unique ID, including its messages.
    """
    chat = await chat_service.get_chat_by_id(chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found.",
        )
    return chat


@router.post(
    "/",
    response_model=Chat,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
async def create_chat(
    chat_data: ChatCreate, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Create a new chat session with the provided title.
    """
    try:
        new_chat = await chat_service.create_chat(chat_data)
        if not new_chat:
            # This might occur if DB insertion fails unexpectedly
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create chat session.",
            )
        return new_chat
    except Exception as e:
        logger.exception("Failed to create chat", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the chat.",
        )


@router.put("/{chat_id}", response_model=Chat, summary="Update a chat session title")
async def update_chat(
    chat_id: int,
    chat_data: ChatCreate,  # Re-using ChatCreate schema for title update
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Update the title of an existing chat session.
    """
    updated_chat = await chat_service.update_chat(chat_id, chat_data)
    if not updated_chat:
        # Check if the chat originally existed
        if await chat_service.get_chat_by_id(chat_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session with ID {chat_id} not found.",
            )
        else:
            # Update failed for other reasons (e.g., DB error)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update chat session.",
            )
    return updated_chat


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
)
async def delete_chat(
    chat_id: int, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Delete a chat session and all its associated messages by its ID.
    """
    success = await chat_service.delete_chat(chat_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found or deletion failed.",
        )
    # No content to return on successful deletion
    return None


# --- Message Endpoints ---


@router.get(
    "/{chat_id}/messages",
    response_model=List[Message],
    summary="List messages in a chat",
)
async def get_messages_by_chat_id(
    chat_id: int, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Retrieve all messages for a specific chat session, ordered by timestamp.
    """
    # First, check if chat exists to provide a better error message
    if await chat_service.get_chat_by_id(chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found.",
        )
    try:
        messages = await chat_service.get_messages_by_chat_id(chat_id)
        return messages
    except Exception as e:
        logger.exception(
            f"Failed to retrieve messages for chat {chat_id}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving messages.",
        )


@router.get(
    "/messages/{message_id}", response_model=Message, summary="Get a specific message"
)
async def get_message_by_id(
    message_id: int, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Retrieve a specific message by its unique ID.
    """
    message = await chat_service.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message with ID {message_id} not found.",
        )
    return message


@router.post(
    "/messages",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a chat",
)
async def create_message(
    message_data: MessageCreate, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Add a new message (typically from the user or assistant) to an existing chat session.
    """
    # Validate that the chat_id exists
    if await chat_service.get_chat_by_id(message_data.chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # Or 400 Bad Request
            detail=f"Chat session with ID {message_data.chat_id} not found.",
        )
    try:
        new_message = await chat_service.create_message(message_data)
        if not new_message:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create message.",
            )
        return new_message
    except Exception as e:
        logger.exception("Failed to create message", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the message.",
        )


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a message",
)
async def delete_message(
    message_id: int, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Delete a specific message by its ID.
    """
    success = await chat_service.delete_message(message_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message with ID {message_id} not found or deletion failed.",
        )
    # No content to return on successful deletion
    return None


# --- LLM Interaction Endpoint ---


@router.post("/ask", response_model=ChatAnswer, summary="Ask a question to the LLM")
async def ask_question(
    question_data: Question, chat_service: ChatService = Depends(get_chat_service)
):
    """
    Ask a question to the LLM and get a response, optionally in the context of an existing chat.

    If chat_id is provided, the question and response will be added to that chat's history.
    If no chat_id is provided, a new chat will be created with the question as the title.
    """
    try:
        # If a chat ID is provided, check if it exists
        if (
            question_data.chat_id
            and await chat_service.get_chat_by_id(question_data.chat_id) is None
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session with ID {question_data.chat_id} not found.",
            )

        # Process the question through the service
        response = await chat_service.process_question(
            content=question_data.content,
            chat_id=question_data.chat_id,
        )

        return response

    except ValueError as ve:
        # Handle service-level validation errors
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        # Handle unexpected errors
        logger.exception("Error processing question", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your question.",
        )
