from PySide6.QtCore import QObject, Signal, QThreadPool
from src.services.chat_service import ChatService
from src.ui.workers.async_runner import AsyncTaskRunner
from typing import List, Dict, Any, Optional
from datetime import datetime


class ChatController(QObject):
    """
    Controller class for handling chat functionality, decoupled from the UI layer.
    """

    history_loaded = Signal(list)
    answer_received = Signal(dict)
    error_occurred = Signal(Exception)
    grouped_chats_loaded = Signal(dict)  # Signal for sending the grouped chat list

    def __init__(self, chat_service: ChatService, parent=None):
        super().__init__(parent)
        self._service = chat_service
        self.answer_sources = []  # Store reference sources, if any

    def load_history(self, limit: int = 20):
        """
        Load chat history and emit history_loaded signal.
        """
        try:
            history = self._service.get_all_chats(limit=limit)
            self.history_loaded.emit(history)
        except Exception as e:
            self.error_occurred.emit(e)

    def load_grouped_chats(self):
        """
        Load chat records grouped by date.
        """
        try:
            grouped_chats = self._service.get_grouped_chats()
            self.grouped_chats_loaded.emit(grouped_chats)
        except Exception as e:
            self.error_occurred.emit(e)

    def get_history_items(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get a list of historical chat records without emitting a signal.
        """
        try:
            return self._service.get_all_chats(limit=limit)
        except Exception as e:
            self.error_occurred.emit(e)
            return []

    def get_chat(self, chat_id: int) -> Dict[str, Any]:
        """
        Get chat records for a specific ID

        Args:
            chat_id: Chat record ID

        Returns:
            A dictionary containing chat information and messages
        """
        try:
            chat = self._service.get_chat(chat_id)
            if chat:
                return chat
            else:
                return {"error": f"Chat record with ID {chat_id} not found"}
        except Exception as e:
            self.error_occurred.emit(e)
            return {"error": str(e)}

    def ask_question(self, question: str, chat_id: Optional[int] = None):
        """
        Send a question and get an answer, supporting association with a specific chat ID

        Args:
            question: Question text
            chat_id: Optional chat ID for updating an existing chat
        """
        try:
            # Save the current chat ID for use in the callback
            self._current_chat_id = chat_id

            # Use AsyncTaskRunner to asynchronously call the service method
            runner = AsyncTaskRunner(self._service.answer_question, question, chat_id)
            runner.setAutoDelete(True)
            runner.signals.finished.connect(self._on_answer_received)
            runner.signals.error.connect(self.error_occurred)
            QThreadPool.globalInstance().start(runner)

        except Exception as e:
            self.error_occurred.emit(e)

    def _on_answer_received(self, result):
        """Process the received answer and emit a signal"""
        # If needed, add the chat ID here
        if hasattr(self, "_current_chat_id") and self._current_chat_id:
            result["chat_id"] = self._current_chat_id

        # Emit the signal for receiving the answer
        self.answer_received.emit(result)

    def create_new_chat(self, title: str = "New Chat") -> Optional[Dict[str, Any]]:
        """
        Create a new chat session

        Args:
            title: Chat title

        Returns:
            Information about the newly created chat
        """
        try:
            return self._service.create_chat(title)
        except Exception as e:
            self.error_occurred.emit(e)
            return None

    def update_chat_title(self, chat_id: int, title: str) -> bool:
        """
        Update the chat title

        Args:
            chat_id: Chat ID
            title: New title

        Returns:
            Whether the update was successful
        """
        try:
            return self._service.update_chat_title(chat_id, title)
        except Exception as e:
            self.error_occurred.emit(e)
            return False

    def delete_chat(self, chat_id: int) -> bool:
        """
        Delete the chat with the specified ID

        Args:
            chat_id: Chat ID

        Returns:
            Whether the deletion was successful
        """
        try:
            return self._service.delete_chat(chat_id)
        except Exception as e:
            self.error_occurred.emit(e)
            return False

    def clear_answer_sources(self):
        """Clear the reference sources from the last query."""
        self.answer_sources = []

    def add_answer_sources(self, sources):
        """Add reference sources to the list."""
        if sources:
            self.answer_sources = sources

    def clear_chat_history(self):
        """Clear all chat history records."""
        try:
            return self._service.clear_all_chats()
        except Exception as e:
            self.error_occurred.emit(e)
            return False
