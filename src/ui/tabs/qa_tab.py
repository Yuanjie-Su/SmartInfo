#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Intelligent Q&A Tab (Refactored)
Implements knowledge-based intelligent question answering (using Service Layer)
"""

import logging
import asyncio
from typing import List, Dict, Optional, Any  # Added

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QFrame,
    QMessageBox,
    QApplication,  # Added QApplication
)
from PySide6.QtCore import Qt, Slot, QThreadPool  # Added Slot, QThreadPool
from PySide6.QtGui import QFont, QColor

# Import Services needed
from src.services.qa_service import QAService

# Assuming AsyncTaskRunner is now in ui.async_runner
from src.ui.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


class QATab(QWidget):
    """Intelligent Q&A Tab (Refactored)"""

    def __init__(self, qa_service: QAService):  # Inject service
        super().__init__()
        self._qa_service = qa_service
        self._current_answer_sources: List[Dict] = (
            []
        )  # Store sources for current answer
        self._setup_ui()
        self.load_history()  # Load history on init

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
        history_layout.addWidget(QLabel("Q&A history (last 20):"))

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

        # Chat Display Area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        # Increase font size for readability
        font = self.chat_display.font()
        font.setPointSize(font.pointSize() + 1)
        self.chat_display.setFont(font)
        chat_layout.addWidget(self.chat_display, 1)  # Give more space

        # Input Area
        input_layout = QHBoxLayout()
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText(
            "Enter your question here, based on the collected and analyzed information..."
        )
        self.question_input.returnPressed.connect(
            self._send_question
        )  # Trigger on Enter
        input_layout.addWidget(self.question_input, 1)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._send_question)
        input_layout.addWidget(self.send_button)

        chat_layout.addLayout(input_layout)
        main_splitter.addWidget(chat_widget)

        # Adjust splitter sizes
        main_splitter.setSizes([250, 750])

        self._show_welcome_message()

    def load_history(self):
        """Loads Q&A history from the service."""
        logger.info("Loading QA history...")
        try:
            self.history_list.clear()
            history_items = self._qa_service.get_qa_history(limit=20)  # Get recent 20
            if history_items:
                for item in reversed(history_items):  # Show oldest first in list
                    q_item = QListWidgetItem(item["question"])
                    # Store full item data in the list item? Or just ID?
                    q_item.setData(Qt.ItemDataRole.UserRole, item["id"])
                    # Set tooltip to show answer preview?
                    q_item.setToolTip(f"Answer: {item['answer'][:100]}...")
                    self.history_list.addItem(q_item)
            logger.info(f"Loaded {len(history_items)} QA history items.")
        except Exception as e:
            logger.error(f"Failed to load QA history: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load QA history: {e}")

    def _show_welcome_message(self):
        """Display welcome message"""
        welcome_message = (
            "<p>Welcome to <b>SmartInfo Intelligent Q&A</b>!</p>"
            "<p>You can ask questions based on the collected and analyzed information. "
            "The system will use the knowledge base and large language model to provide answers.</p>"
            "<p><b>For example:</b></p>"
            "<ul>"
            "<li>What are the major advancements in AI recently?</li>"
            "<li>Summarize the current state of quantum computing.</li>"
            "<li>What is the latest breakthrough in chip technology?</li>"
            "</ul>"
            "<p>Please enter your question to start exploring!</p>"
        )
        self.chat_display.setHtml(welcome_message)

    def _send_question(self):
        """Sends the user's question to the QA service asynchronously."""
        question = self.question_input.text().strip()
        if not question:
            return

        self.question_input.clear()
        self._add_message_to_chat("👤 User", question)  # Add user message immediately
        self._current_answer_sources = []  # Clear sources from previous answer

        # --- Update UI State ---
        self.send_button.setEnabled(False)
        self.question_input.setEnabled(False)
        # Append thinking message without newline before it if chat is not empty
        separator = "\n" if self.chat_display.toPlainText() else ""
        self.chat_display.append(
            f"{separator}<i style='color: gray;'>🤖 System is thinking...</i>"
        )
        self.chat_display.ensureCursorVisible()  # Scroll down
        QApplication.processEvents()

        # --- Run async task ---
        answer_coro = self._qa_service.answer_question
        args = (question,)

        self.runner = AsyncTaskRunner(answer_coro, *args)
        self.runner.setAutoDelete(True)
        self.runner.signals.finished.connect(self._on_answer_received)
        self.runner.signals.error.connect(self._on_qa_error)
        QThreadPool.globalInstance().start(self.runner)

    @Slot(object)
    def _on_answer_received(self, result: Dict[str, Any]):
        """Handles the result from the QA service."""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()  # Set focus back to input

        # Remove "Thinking..." message
        html = self.chat_display.toHtml()
        # Be careful with replacing HTML, might remove previous formatting
        html = html.replace(
            '<p style="-qt-paragraph-type:empty"><br /></p>', ""
        )  # Remove empty paragraphs sometimes added
        thinking_msg = "<i style='color: gray;'>🤖 System is thinking...</i>"
        # Find the last occurrence and remove it cleanly
        last_occurrence = html.rfind(thinking_msg)
        if last_occurrence != -1:
            # Check if it's at the very end or followed by closing tags
            end_part = html[last_occurrence + len(thinking_msg) :].strip()
            if end_part.lower() in ["</p>", "</body></html>", ""]:
                html = html[:last_occurrence]
            else:  # Fallback: simple replace (might leave empty tags)
                html = html.replace(thinking_msg, "")

        self.chat_display.setHtml(html)  # Update HTML without the thinking message

        if result and result.get("error"):
            logger.error(f"QA service returned an error: {result['error']}")
            self._add_message_to_chat(
                "⚠️ System Error",
                f"Sorry, an error occurred while answering: {result['error']}",
            )
        elif result and result.get("answer"):
            answer = result["answer"]
            self._current_answer_sources = result.get("sources", [])
            # Add the actual answer
            self._add_message_to_chat("🤖 System", answer)
            # Add sources if any
            if self._current_answer_sources:
                sources_html = "<br /><small><b>Reference Sources (Similarity):</b><ul>"
                for src in self._current_answer_sources:
                    title = src.get("title", "Unknown Title")
                    sim = src.get("similarity", 0)
                    # Make title clickable if we store/retrieve the link? Need service change.
                    # For now, just display title and similarity.
                    sources_html += f"<li>{title} ({sim}%)</li>"
                sources_html += "</ul></small>"
                self.chat_display.append(sources_html)

            # Update history list if the question was new
            self.load_history()  # Reload history to show the new entry

        else:
            # Should not happen if error is None, but handle defensively
            logger.error("QA service returned an unexpected empty result.")
            self._add_message_to_chat(
                "⚠️ System Error", "Sorry, the system couldn't generate an answer."
            )

        self.chat_display.ensureCursorVisible()

    @Slot(Exception)
    def _on_qa_error(self, error: Exception):
        """Handle errors during question answering"""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()

        # Remove "Thinking..." message (same logic as in _on_answer_received)
        html = self.chat_display.toHtml()
        html = html.replace('<p style="-qt-paragraph-type:empty"><br /></p>', "")
        thinking_msg = "<i style='color: gray;'>🤖 System is thinking...</i>"
        last_occurrence = html.rfind(thinking_msg)
        if last_occurrence != -1:
            end_part = html[last_occurrence + len(thinking_msg) :].strip()
            if end_part.lower() in ["</p>", "</body></html>", ""]:
                html = html[:last_occurrence]
            else:
                html = html.replace(thinking_msg, "")
        self.chat_display.setHtml(html)

        logger.error(f"QA task execution failed: {error}", exc_info=error)
        self._add_message_to_chat(
            "⚠️ System Error",
            f"An internal error occurred while processing the question: {str(error)}",
        )
        self.chat_display.ensureCursorVisible()

    def _add_message_to_chat(self, sender: str, message: str):
        """Add a message to the chat display"""
        # Basic HTML escaping for the message content
        message = (
            message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        # Convert newlines to <br> for HTML display
        message = message.replace("\n", "<br />")

        sender_style = ""
        if "User" in sender:
            sender_style = "color: #005eff; font-weight: bold;"  # Blue for user
            message_html = f"<p style='margin-bottom: 5px;'><span style='{sender_style}'>{sender}:</span><br />{message}</p>"
        elif "System Error" in sender:
            sender_style = "color: #D50000; font-weight: bold;"  # Red for error
            message_html = f"<p style='margin-bottom: 5px;'><span style='{sender_style}'>{sender}:</span><br />{message}</p>"
        else:  # System answer
            sender_style = "color: #008000; font-weight: bold;"  # Green for system
            # Add message without extra <p> tag if it's part of answer
            message_html = (
                f"<span style='{sender_style}'>{sender}:</span><br />{message}"
            )

        # Append message and ensure visibility
        # Check if the last block is an empty paragraph, common issue
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        if self.chat_display.toPlainText():  # Add separator if not the first message
            self.chat_display.append("")  # Adds a paragraph break

        self.chat_display.insertHtml(message_html)
        self.chat_display.ensureCursorVisible()

    def _on_history_item_clicked(self, item: QListWidgetItem):
        """Load and display a question-answer pair from history"""
        question = item.text()
        # Re-submit the question
        self.question_input.setText(question)
        self._send_question()

    def _clear_history(self):
        """Clear the Q&A history"""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all Q&A history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._qa_service.clear_qa_history():
                    self.history_list.clear()
                    self.chat_history = (
                        []
                    )  # Assuming chat_history is still used somewhere? If not, remove.
                    self._show_welcome_message()  # Show welcome message again
                    QMessageBox.information(
                        self, "Success", "Q&A history has been cleared."
                    )
                else:
                    QMessageBox.warning(self, "Failure", "Failed to clear Q&A history.")
            except Exception as e:
                logger.error(f"Error clearing QA history: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Error clearing history: {e}")
