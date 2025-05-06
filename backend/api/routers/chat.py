# backend/api/routers/chat.py
# -*- coding: utf-8 -*-
"""
API router for chat functionalities (Version 1).
Handles chat session management, message operations, and interaction with the LLM.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, status
from typing import List, Dict, Any, Optional, Annotated  # Import Annotated

# Import dependencies from the centralized dependencies module
from api.dependencies import (
    get_chat_service,
    get_current_active_user,
)  # Import user dependency

# Import schemas from the main models package
from models.schemas.chat import (
    Chat,  # Keep for internal use if needed
    ChatCreate,
    Message,  # Keep for internal use if needed
    MessageCreate,
    ChatAnswer,
    Question,
    # Import Chat Response Schemas
    MessageResponse,
    ChatResponse,
    ChatListResponseItem,
)

from models.schemas.user import User

# Import the service class type hint
from services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Chat Session Endpoints (User-Aware) ---


@router.get(
    "/", response_model=List[ChatListResponseItem], summary="List user's chat sessions"
)  # Updated response model
async def get_all_chats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Retrieve a list of all chat sessions belonging to the current user.
    """
    try:
        chats = await chat_service.get_all_chats(user_id=current_user.id)
        return chats
    except Exception as e:
        logger.exception("Failed to retrieve user chats", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving chats.",
        )


from models.schemas.chat import (
    Chat,  # Keep for internal use if needed
    ChatCreate,
    Message,  # Keep for internal use if needed
    MessageCreate,
    ChatAnswer,
    Question,
    # Import Chat Response Schemas
    MessageResponse,
    ChatResponse,
    ChatListResponseItem,
)

from models.schemas.user import User

# Import the service class type hint
from services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Chat Session Endpoints (User-Aware) ---


@router.get(
    "/", response_model=List[ChatListResponseItem], summary="List user's chat sessions"
)  # Updated response model
async def get_all_chats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Retrieve a list of all chat sessions belonging to the current user.
    """
    try:
        chats = await chat_service.get_all_chats(user_id=current_user.id)
        return chats
    except Exception as e:
        logger.exception("Failed to retrieve user chats", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving chats.",
        )


@router.get(
    "/{chat_id}", response_model=ChatResponse, summary="Get a specific chat session"
)  # Updated response model
async def get_chat_by_id(
    chat_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Retrieve a specific chat session by its ID, ensuring it belongs to the current user.
    Includes messages.
    """
    chat = await chat_service.get_chat_by_id(chat_id=chat_id, user_id=current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found or not owned by user.",
        )
    return chat


@router.post(
    "/",
    response_model=ChatResponse,  # Updated response model
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
async def create_chat(
    chat_data: ChatCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Create a new chat session for the current user.
    The user_id from the token will override any user_id in chat_data.
    """
    # Ensure the chat data is associated with the current user
    chat_data_with_user = chat_data.model_copy(update={"user_id": current_user.id})

    try:
        new_chat = await chat_service.create_chat(
            chat_data=chat_data_with_user, user_id=current_user.id
        )
        # Service layer now returns the full Chat object or raises error
        return new_chat
    except ValueError as ve:  # Catch potential validation errors from service
        logger.error(f"Chat creation validation error: {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception("Failed to create chat", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the chat.",
        )


@router.put(
    "/{chat_id}", response_model=ChatResponse, summary="Update a chat session title"
)  # Updated response model
async def update_chat(
    chat_id: int,
    chat_data: ChatCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Update the title of an existing chat session belonging to the current user.
    """
    # Ensure the chat data is associated with the current user for update check
    chat_data_with_user = chat_data.model_copy(update={"user_id": current_user.id})

    updated_chat = await chat_service.update_chat(
        chat_id=chat_id, chat_data=chat_data_with_user, user_id=current_user.id
    )
    if not updated_chat:
        # Service handles the check if chat exists and belongs to user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found or not owned by user.",
        )
    return updated_chat


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
)
async def delete_chat(
    chat_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Delete a chat session belonging to the current user.
    """
    success = await chat_service.delete_chat(chat_id=chat_id, user_id=current_user.id)
    if not success:
        # Service handles the check if chat exists and belongs to user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found or not owned by user.",
        )
    return None


# --- Message Endpoints (User context checked via chat ownership) ---


@router.get(
    "/{chat_id}/messages",
    response_model=List[MessageResponse],  # Updated response model
    summary="List messages in a chat",
)
async def get_messages_by_chat_id(
    chat_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Retrieve all messages for a specific chat session, ensuring the chat belongs to the current user.
    """
    # Check chat ownership first
    chat = await chat_service.get_chat_by_id(chat_id=chat_id, user_id=current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session with ID {chat_id} not found or not owned by user.",
        )
    # Messages are already loaded in the chat object by the service method
    return chat.messages or []


@router.get(
    "/messages/{message_id}",
    response_model=MessageResponse,
    summary="Get a specific message",  # Updated response model
)
async def get_message_by_id(
    message_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Retrieve a specific message by its ID, ensuring its chat belongs to the current user.
    """
    message = await chat_service.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message with ID {message_id} not found.",
        )
    # Verify chat ownership
    chat = await chat_service.get_chat_by_id(
        chat_id=message.chat_id, user_id=current_user.id
    )
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,  # Or 404 if we hide existence
            detail=f"Access denied to message {message_id}.",
        )
    return message


@router.post(
    "/messages",
    response_model=MessageResponse,  # Updated response model
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a chat",
)
async def create_message(
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Add a new message to a chat session, ensuring the chat belongs to the current user.
    """
    # Verify chat ownership before adding message
    chat = await chat_service.get_chat_by_id(
        chat_id=message_data.chat_id, user_id=current_user.id
    )
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,  # Or 403 Forbidden
            detail=f"Chat session with ID {message_data.chat_id} not found or not owned by user.",
        )
    try:
        # Service create_message doesn't need user_id directly, relies on prior check
        new_message = await chat_service.create_message(message_data)
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
    message_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Delete a specific message by its ID, ensuring its chat belongs to the current user.
    """
    # Get message to find chat_id
    message = await chat_service.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message with ID {message_id} not found.",
        )
    # Verify chat ownership
    chat = await chat_service.get_chat_by_id(
        chat_id=message.chat_id, user_id=current_user.id
    )
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,  # Or 404
            detail=f"Access denied to delete message {message_id}.",
        )

    # Proceed with deletion
    success = await chat_service.delete_message(message_id)
    if not success:
        # This might happen if the message was deleted between checks, or DB error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete message {message_id}.",
        )
    return None


# --- LLM Interaction Endpoint (User-Aware) ---


@router.post("/ask", response_model=ChatAnswer, summary="Ask a question to the LLM")
async def ask_question(
    question_data: Question,
    current_user: Annotated[User, Depends(get_current_active_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """
    Ask a question to the LLM for the current user.

    If chat_id is provided, it must belong to the user.
    If no chat_id is provided, a new chat will be created for the user.
    """
    try:
        # Service method now handles chat_id validation and user association
        response = await chat_service.process_question(
            content=question_data.content,
            user=current_user,  # Pass the authenticated user object
            chat_id=question_data.chat_id,
        )
        return response

    except ValueError as ve:
        logger.error(f"Validation error during /ask: {str(ve)}")
        # Check if the error is about chat ownership to return 404/403
        if "not found or does not belong to user" in str(ve):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.exception("Error processing question", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your question.",
        )
