#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Service Module
Implements chat functionality using the new database structure.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from src.db.repositories import ChatRepository, MessageRepository

logger = logging.getLogger(__name__)

DEFAULT_QA_MODEL = "deepseek-v3-250324"


class ChatService:
    """Chat Service Class"""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
    ):
        self._chat_repo = chat_repo
        self._message_repo = message_repo
        self._llm_pool = None  # Will be set after initialization
        self._qa_repo = None  # For backward compatibility

    def set_llm_pool(self, llm_pool):
        """Set the LLM client pool after initialization"""
        self._llm_pool = llm_pool
        logger.info("LLM client pool assigned to ChatService")

    # --- Chat Management ---

    def create_chat(self, title: str = "New Chat") -> Optional[Dict[str, Any]]:
        """
        Create a new chat session.

        Args:
            title: Chat title, default is "New Chat"

        Returns:
            A dictionary containing the information of the newly created chat, or None if creation fails
        """
        chat_id = self._chat_repo.create_chat(title)
        if chat_id is not None:
            return self._chat_repo.get_chat(chat_id)
        return None

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chat information for the specified ID, including message content.

        Args:
            chat_id: Chat ID

        Returns:
            A dictionary containing chat information and message content, or None if it does not exist
        """
        chat = self._chat_repo.get_chat(chat_id)
        if not chat:
            return None

        # Get all messages in the chat
        messages = self._message_repo.get_messages(chat_id)
        chat["messages"] = messages

        return chat

    def update_chat_title(self, chat_id: int, title: str) -> bool:
        """
        Update the chat title.

        Args:
            chat_id: Chat ID
            title: New title

        Returns:
            Whether the update was successful
        """
        return self._chat_repo.update_chat_title(chat_id, title)

    def delete_chat(self, chat_id: int) -> bool:
        """
        Delete the chat and all its messages for the specified ID.

        Args:
            chat_id: Chat ID

        Returns:
            Whether the deletion was successful
        """
        return self._chat_repo.delete_chat(chat_id)

    def clear_all_chats(self) -> bool:
        """
        Clear all chat records.

        Returns:
            Whether the operation was successful
        """
        return self._chat_repo.clear_all_chats()

    # --- Message Management ---

    def add_message(
        self, chat_id: int, sender: str, content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Add a message to the specified chat.

        Args:
            chat_id: Chat ID
            sender: Sender, such as "You" or "Assistant"
            content: Message content

        Returns:
            The information of the newly added message, or None if adding fails
        """
        message_id = self._message_repo.add_message(chat_id, sender, content)
        if message_id is None:
            return None

        # Update the chat's timestamp
        self._chat_repo.update_chat_timestamp(chat_id)

        return self._message_repo.get_message(message_id)

    def get_messages(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all messages for the specified chat.

        Args:
            chat_id: Chat ID

        Returns:
            List of messages
        """
        return self._message_repo.get_messages(chat_id)

    def delete_message(self, message_id: int) -> bool:
        """
        Delete the message for the specified ID.

        Args:
            message_id: Message ID

        Returns:
            Whether the deletion was successful
        """
        return self._message_repo.delete_message(message_id)

    # --- Chat Listing and Grouping ---

    def get_all_chats(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all chat sessions, sorted by update time.

        Args:
            limit: Limit on the number of returned results
            offset: Pagination offset

        Returns:
            List of chats
        """
        chats = self._chat_repo.get_all_chats(limit, offset)

        return chats

    def get_grouped_chats(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get grouped chat sessions, grouped by Today, Yesterday, Others.

        Returns:
            A dictionary of chats grouped by date
        """
        # Get all chats
        all_chats = self.get_all_chats(limit=100)  # Limit the number appropriately

        # Calculate date boundaries
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Initialize groups
        grouped_chats = {"Today": [], "Yesterday": [], "Others": []}

        # Group chats
        for chat in all_chats:
            try:
                # Try to parse the chat creation time
                chat_date_str = chat.get("created_at") or chat.get("updated_at")
                if not chat_date_str:
                    # If there is no time information, put it in the Others group
                    grouped_chats["Others"].append(chat)
                    continue

                chat_date = datetime.fromisoformat(chat_date_str).date()

                # Group by date
                if chat_date == today:
                    grouped_chats["Today"].append(chat)
                elif chat_date == yesterday:
                    grouped_chats["Yesterday"].append(chat)
                else:
                    grouped_chats["Others"].append(chat)
            except (ValueError, TypeError):
                # Date parsing error, put it in the Others group
                grouped_chats["Others"].append(chat)

        return grouped_chats

    # --- Question Answering ---

    async def answer_question(
        self, question: str, chat_id: Optional[int] = None, stream_callback=None
    ) -> Dict[str, Any]:
        """
        Answer the question and store the Q&A pair in the chat record.

        Args:
            question: User question
            chat_id: Optional chat ID, if provided, add to the existing chat, otherwise create a new chat
            stream_callback: Optional callback function for handling streamed response text chunks

        Returns:
            A dictionary containing the answer and chat information
        """
        if not question or not question.strip():
            return {
                "answer": "Please enter a valid question.",
                "error": "Empty question",
            }

        try:
            logger.info(f"Answering question via LLM: '{question}'")

            # Check if LLM client pool is configured
            if not self._llm_pool:
                logger.error("LLM client pool is not configured")
                return {
                    "answer": "LLM service is not properly configured. Please try again later.",
                    "error": "LLM service unavailable",
                }

            # Prepare the prompt
            prompt = self._build_direct_qa_prompt(question)

            # Prepare for storing chat records
            result = {}

            # If no chat ID is provided, create a new chat
            if chat_id is None:
                # Use the first 30 characters of the question as the chat title
                title = question[:30] + ("..." if len(question) > 30 else "")
                new_chat = self.create_chat(title)
                if new_chat:
                    chat_id = new_chat["id"]
                    result["chat_id"] = chat_id
                    result["is_new_chat"] = True
                else:
                    logger.error("Failed to create new chat")
                    return {
                        "answer": "Unable to create new chat record.",
                        "error": "Unable to create new chat",
                    }
            else:
                # Use existing chat
                result["chat_id"] = chat_id
                result["is_new_chat"] = False

            # Save user question
            user_message = self.add_message(chat_id, "You", question)
            if not user_message:
                logger.error(f"Failed to add user question to chat {chat_id}")

            # Initialize system answer (to be filled in during streaming)
            assistant_message_id = self._message_repo.add_message(
                chat_id, "Assistant", ""
            )
            if not assistant_message_id:
                logger.error(
                    f"Failed to create assistant message placeholder, chat ID: {chat_id}"
                )
                return {
                    "answer": "Unable to create reply record.",
                    "error": "Database error",
                }

            # Record message ID for updates
            result["message_id"] = assistant_message_id
            full_answer = ""

            try:
                # Use shared LLM client pool
                async with self._llm_pool.context() as llm_client:
                    # Use streaming API to get response
                    stream_generator = await llm_client.stream_completion_content(
                        model=DEFAULT_QA_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a helpful assistant that answers questions clearly and concisely.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=1024,
                        temperature=0.7,
                    )

                    if stream_generator:
                        # Process streaming response
                        async for text_chunk in stream_generator:
                            # Accumulate full answer
                            full_answer += text_chunk

                            # Regularly update the answer in the database
                            if (
                                len(full_answer) % 50 == 0
                            ):  # Update approximately every 50 characters
                                self._message_repo.update_message_content(
                                    assistant_message_id, full_answer
                                )

                            # If a callback function is provided, call it
                            if stream_callback:
                                callback_data = {
                                    "text_chunk": text_chunk,
                                    "full_text": full_answer,
                                    "message_id": assistant_message_id,
                                    "chat_id": chat_id,
                                    "is_final": False,
                                }
                                stream_callback(callback_data)

                if not stream_generator:
                    # Streaming request failed
                    error_msg = "Unable to establish LLM streaming connection"
                    logger.error(f"LLM streaming query failed: {error_msg}")
                    # Update message with error prompt
                    self._message_repo.update_message_content(
                        assistant_message_id,
                        f"Sorry, an error occurred while answering the question: {error_msg}",
                    )
                    return {
                        "answer": f"Sorry, an error occurred while answering the question: {error_msg}",
                        "error": error_msg,
                        "message_id": assistant_message_id,
                        "chat_id": chat_id,
                    }

            except Exception as e:
                logger.error(f"Error during LLM call: {e}", exc_info=True)
                error_msg = f"LLM call failed: {str(e)}"
                self._message_repo.update_message_content(
                    assistant_message_id,
                    f"Sorry, an error occurred while answering the question: {error_msg}",
                )
                return {
                    "answer": f"Sorry, an error occurred while calling the LLM service: {error_msg}",
                    "error": error_msg,
                    "message_id": assistant_message_id,
                    "chat_id": chat_id,
                }

            # After streaming is complete, ensure final update of database content
            if full_answer:
                self._message_repo.update_message_content(
                    assistant_message_id, full_answer
                )

                # Final callback indicating stream is complete
                if stream_callback:
                    callback_data = {
                        "text_chunk": "",
                        "full_text": full_answer,
                        "message_id": assistant_message_id,
                        "chat_id": chat_id,
                        "is_final": True,
                    }
                    stream_callback(callback_data)

                # If an old QA repository is provided, also save a copy (for backward compatibility)
                if hasattr(self, "_qa_repo") and self._qa_repo:
                    try:
                        self._qa_repo.add_qa(question, full_answer, "[]")
                    except Exception as db_err:
                        logger.error(
                            f"Failed to save Q&A to old history: {db_err}",
                            exc_info=True,
                        )

                result["answer"] = full_answer
                return result
            else:
                error_msg = "LLM returned an empty response"
                logger.error(f"LLM query failed: {error_msg}")
                # Update message with error prompt
                self._message_repo.update_message_content(
                    assistant_message_id,
                    f"Sorry, an error occurred while answering the question: {error_msg}",
                )
                return {
                    "answer": f"Sorry, an error occurred while answering the question: {error_msg}",
                    "error": error_msg,
                    "message_id": assistant_message_id,
                    "chat_id": chat_id,
                }

        except Exception as e:
            logger.error(f"Error during Q&A process: {e}", exc_info=True)
            return {
                "answer": f"An unexpected error occurred while processing your question.",
                "error": str(e),
                "chat_id": chat_id if "chat_id" in locals() else None,
                "message_id": (
                    assistant_message_id if "assistant_message_id" in locals() else None
                ),
            }

    def _build_direct_qa_prompt(self, question: str) -> str:
        """Build a prompt to directly ask the LLM."""
        return f"Please directly answer the following question:\n\nQuestion: {question}\n\nAnswer: "
