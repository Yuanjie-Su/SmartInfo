#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Intelligent Q&A Tab (Refactored)
Implements knowledge-based intelligent question answering (using Service Layer)
"""

import logging
import asyncio
from typing import List, Dict, Optional, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, # Changed to QTextBrowser
    QLineEdit, QLabel, QListWidget, QListWidgetItem, QSplitter,
    QFrame, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, Slot # Removed QThreadPool
from PySide6.QtGui import QFont, QColor

# Import Services needed
from src.services.qa_service import QAService

# AsyncTaskRunner is no longer needed
# from src.ui.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)

class QATab(QWidget):
    """Intelligent Q&A Tab (Refactored)"""

    def __init__(self, qa_service: QAService): # Inject service
        super().__init__()
        self._qa_service = qa_service
        self._current_answer_sources: List[Dict] = []
        self._qa_task: Optional[asyncio.Task] = None # To hold the running task
        self._setup_ui()
        self.load_history() # Load history on init

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter, 1)

        # --- Left Panel (History) ---
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.addWidget(QLabel("Q&A history (last 50):")) # Increased limit

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        history_layout.addWidget(self.history_list)

        clear_button = QPushButton("Clear history")
        clear_button.clicked.connect(self._clear_history)
        history_layout.addWidget(clear_button)

        main_splitter.addWidget(history_widget)

        # --- Right Panel (Chat) ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        # Use QTextBrowser for better rich text display
        self.chat_display = QTextBrowser()
        self.chat_display.setReadOnly(True)
        self.chat_display.setOpenExternalLinks(True)
        font = self.chat_display.font()
        font.setPointSize(font.pointSize() + 1) # Keep increased font size
        self.chat_display.setFont(font)
        chat_layout.addWidget(self.chat_display, 1)

        # Input Area
        input_layout = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Enter your question...")
        self.question_input.returnPressed.connect(self._send_question)
        input_layout.addWidget(self.question_input, 1)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send_question)
        input_layout.addWidget(self.send_button)

        chat_layout.addLayout(input_layout)
        main_splitter.addWidget(chat_widget)

        # Adjust splitter sizes
        main_splitter.setSizes([300, 700]) # Adjusted history panel size slightly

        self._show_welcome_message()

    def load_history(self):
        """Loads Q&A history from the service."""
        logger.info("Loading QA history...")
        try:
            self.history_list.clear()
            history_items = self._qa_service.get_qa_history(limit=50) # Load more history
            if history_items:
                for item in reversed(history_items):
                    q_item = QListWidgetItem(item["question"])
                    q_item.setData(Qt.ItemDataRole.UserRole, item) # Store full item data
                    q_item.setToolTip(f"A: {item['answer'][:100]}...")
                    self.history_list.addItem(q_item)
            logger.info(f"Loaded {len(history_items)} QA history items.")
        except Exception as e:
            logger.error(f"Failed to load QA history: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load QA history: {e}")

    def _show_welcome_message(self):
        """Display welcome message"""
        # Slightly updated welcome message
        welcome_message = (
            "<p>Welcome to <b>SmartInfo Intelligent Q&A</b>!</p>"
            "<p>Ask questions based on the information analyzed by the system. "
            "Use the history panel on the left to revisit previous conversations.</p>"
            "<p>Enter your question below and press Enter or click Send.</p>"
        )
        self.chat_display.setHtml(welcome_message)

    def _send_question(self):
        """Sends the user's question to the QA service using asyncio."""
        question = self.question_input.text().strip()
        if not question or (self._qa_task and not self._qa_task.done()):
             if not question:
                  return
             else:
                  QMessageBox.information(self, "Busy", "Please wait for the current answer.")
                  return

        self.question_input.clear()
        self._add_message_to_chat("👤 User", question)
        self._current_answer_sources = []

        # --- Update UI State ---
        self.send_button.setEnabled(False)
        self.question_input.setEnabled(False)
        self._add_thinking_message()
        QApplication.processEvents()

        # --- Run async task using asyncio ---
        try:
            loop = asyncio.get_running_loop()
            coro = self._qa_service.answer_question(question)
            self._qa_task = loop.create_task(coro)
            self._qa_task.add_done_callback(self._on_qa_task_done)
            logger.info(f"QA task created for question: {question[:50]}...")
        except Exception as e:
             logger.error(f"Failed to create QA task: {e}", exc_info=True)
             self._remove_thinking_message()
             self._add_message_to_chat("⚠️ System Error", f"Failed to start task: {e}")
             self.send_button.setEnabled(True)
             self.question_input.setEnabled(True)

    def _on_qa_task_done(self, task: asyncio.Task):
        """Handles the completion of the asyncio QA task."""
        self._qa_task = None # Clear the task holder
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()
        self._remove_thinking_message()

        try:
            if task.cancelled():
                logger.warning("QA task was cancelled.")
                self._add_message_to_chat("⚠️ System Info", "Question answering was cancelled.")
            elif task.exception():
                error = task.exception()
                logger.error(f"QA task failed: {error}", exc_info=error)
                self._add_message_to_chat(
                    "⚠️ System Error",
                    f"Sorry, an error occurred while answering: {error}",
                )
            else:
                result = task.result()
                if result and result.get("answer"):
                    answer = result["answer"]
                    self._current_answer_sources = result.get("context_ids", None) # Get context IDs if provided
                    self._add_message_to_chat("🤖 System", answer)

                    # Display source info if available (adjust based on what context_ids contains)
                    if self._current_answer_sources:
                        sources_text = f"Context IDs: {self._current_answer_sources}"
                        sources_html = f"<br /><small><i>{sources_text}</i></small>"
                        self.chat_display.append(sources_html)

                    self.load_history() # Refresh history
                else:
                     # Handle case where result might be valid but empty or has an error flag
                     error_msg = result.get("error", "System couldn't generate an answer.") if result else "System couldn't generate an answer."
                     logger.error(f"QA service returned: {error_msg}")
                     self._add_message_to_chat("⚠️ System Error", f"Sorry, {error_msg}")

        except Exception as e:
             # Catch errors within the callback itself
             logger.error(f"Error in _on_qa_task_done callback: {e}", exc_info=True)
             self._add_message_to_chat("⚠️ System Error", f"Error processing result: {e}")

        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_display.ensureCursorVisible()


    def _add_thinking_message(self):
        """Adds a 'thinking' message to the chat display."""
        thinking_html = "<p style='color: gray; font-style: italic;'>🤖 System is thinking...</p>"
        self.chat_display.append(thinking_html)
        self.chat_display.ensureCursorVisible()

    def _remove_thinking_message(self):
        """Removes the 'thinking' message from the chat display."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Move up to select the last block (the thinking message)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
        # A more robust check might be needed if other messages could interfere
        if "System is thinking..." in cursor.selectedText():
             cursor.removeSelectedText()
             # Also remove the potentially empty paragraph left behind
             cursor.deletePreviousChar()
             self.chat_display.setTextCursor(cursor)


    def _add_message_to_chat(self, sender: str, message: str):
        """Add a formatted message to the chat display (QTextBrowser)."""
        # Prepare sender style
        sender_style = ""
        sender_color = "#212121" # Default color
        if "User" in sender:
            sender_color = "#005eff" # Blue
        elif "System Error" in sender:
            sender_color = "#D50000" # Red
        elif "System" in sender:
            sender_color = "#008000" # Green

        sender_html = f"<strong style='color: {sender_color};'>{sender}:</strong><br>"

        # Basic HTML escaping for the message
        message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Convert newlines to <br> for HTML display
        message_html = message.replace("\n", "<br />")

        # Combine and append (append adds a paragraph block)
        full_html = sender_html + message_html
        self.chat_display.append(full_html)
        self.chat_display.ensureCursorVisible()


    def _on_history_item_clicked(self, item: QListWidgetItem):
        """Load and display a question-answer pair from history"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            self.chat_display.clear() # Clear current chat
            self._add_message_to_chat("👤 User", data.get("question", "N/A"))
            self._add_message_to_chat("🤖 System", data.get("answer", "N/A"))
            # Optionally display context IDs if stored
            context_ids = data.get("context_ids")
            if context_ids:
                 sources_text = f"Context IDs: {context_ids}"
                 sources_html = f"<br /><small><i>{sources_text}</i></small>"
                 self.chat_display.append(sources_html)
            self.chat_display.moveCursor(QTextCursor.MoveOperation.Start) # Scroll to top
        else:
             # Fallback: Re-submit the question if full data wasn't stored
             question = item.text()
             self.question_input.setText(question)
             self._send_question()

    def _clear_history(self):
        """Clear the Q&A history"""
        reply = QMessageBox.question(
            self, "Confirm Clear", "Are you sure you want to clear all Q&A history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._qa_service.clear_qa_history():
                    self.history_list.clear()
                    self._show_welcome_message()
                    QMessageBox.information(self, "Success", "Q&A history has been cleared.")
                else:
                    QMessageBox.warning(self, "Failure", "Failed to clear Q&A history.")
            except Exception as e:
                logger.error(f"Error clearing QA history: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Error clearing history: {e}")

    # Ensure task is cancelled if tab/window is closed
    def closeEvent(self, event): # This might be better placed in MainWindow closing the whole app
        if self._qa_task and not self._qa_task.done():
            logger.info("QA tab closing, cancelling active task.")
            self._qa_task.cancel()
        # super().closeEvent(event) # Usually not needed for QWidget unless overridden