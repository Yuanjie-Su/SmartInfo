#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Interface Module
Implements intelligent question-answering chat functionality based on new database structure
"""

import logging
import asyncio
from typing import List, Dict, Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QLabel,
    QFrame,
    QMessageBox,
    QApplication,
    QScrollArea,
)
from PySide6.QtCore import (
    Qt,
    Slot,
    QThreadPool,
    QSize,
)
from PySide6.QtGui import QFont, QColor, QIcon

# Import necessary services and controllers
from src.ui.controllers.chat_controller import ChatController
from src.ui.workers.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


class ChatTab(QWidget):
    """Intelligent Chat Interface"""

    def __init__(self, controller: ChatController):  # Inject controller
        super().__init__()
        self.controller = controller
        # Connect controller signals
        self.controller.answer_received.connect(self._on_answer_received)
        self.controller.error_occurred.connect(self._on_chat_error)

        # Track the current active chat ID
        self.current_chat_id = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Chat Panel ---
        chat_widget = QWidget()
        chat_widget.setObjectName("ChatPanel")
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(15, 15, 15, 15)
        chat_layout.setSpacing(15)

        # Chat title
        chat_title = QLabel("Intelligent Chat")
        chat_title.setObjectName("ChatTitle")
        chat_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        chat_layout.addWidget(chat_title)

        # Chat display area
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setFrameShape(QFrame.Shape.NoFrame)

        chat_container = QWidget()
        chat_container_layout = QVBoxLayout(chat_container)
        chat_container_layout.setContentsMargins(5, 5, 5, 5)

        self.chat_display = QTextEdit()
        self.chat_display.setObjectName("chat_display")
        self.chat_display.setReadOnly(True)
        # Increase font size
        font = self.chat_display.font()
        font.setPointSize(font.pointSize() + 1)
        self.chat_display.setFont(font)
        chat_container_layout.addWidget(self.chat_display, 1)

        chat_scroll.setWidget(chat_container)
        chat_layout.addWidget(chat_scroll, 1)  # Give more space

        # Input area - modern style
        input_container = QWidget()
        input_container.setObjectName("ChatInputContainer")
        input_container.setStyleSheet(
            """
            #ChatInputContainer {
                background-color: #ffffff;
                border: 1px solid #e0e4e7;
                border-radius: 8px;
                padding: 5px;
            }
        """
        )
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(10)

        self.question_input = QLineEdit()
        self.question_input.setObjectName("ChatInput")
        self.question_input.setPlaceholderText("Enter your question...")
        self.question_input.setMinimumHeight(40)
        self.question_input.returnPressed.connect(
            self._send_question
        )  # Trigger on Enter key
        input_layout.addWidget(self.question_input, 1)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setMinimumSize(QSize(80, 40))
        self.send_button.clicked.connect(self._send_question)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(input_container)
        main_layout.addWidget(chat_widget)

        self._show_welcome_message()

    def load_history(self):
        """Compatibility method, kept but does not perform loading operation"""
        pass

    def _show_welcome_message(self):
        """Display welcome message"""
        welcome_message = (
            "<div style='margin: 20px; line-height: 1.5;'>"
            "<h2 style='color: #07c160;'>Welcome to SmartInfo Intelligent Chat</h2>"
            "<p>You can ask any question, and the system will provide answers using a large language model.</p>"
            "<p><b>Example questions:</b></p>"
            "<ul>"
            "<li>What are the major recent advancements in the field of artificial intelligence?</li>"
            "<li>Summarize the current status of quantum computing.</li>"
            "<li>What are the latest breakthroughs in chip technology?</li>"
            "</ul>"
            "<p>Please enter your question to start exploring!</p>"
            "</div>"
        )
        self.chat_display.setHtml(welcome_message)

    def start_new_chat(self):
        """Create and start a new chat session"""
        logger.info("Starting a new chat session")

        # Clear chat display
        self._show_welcome_message()

        # Clear input box
        self.question_input.clear()

        # Reset current chat ID
        self.current_chat_id = None

    def load_chat(self, chat_id: int):
        """Load chat session with specified ID"""
        logger.info(f"Loading chat session: {chat_id}")

        try:
            # Save current chat ID
            self.current_chat_id = chat_id

            # Get chat history from controller
            chat = self.controller.get_chat(chat_id)

            # Clear current chat display
            self.chat_display.clear()

            # Display historical conversation content
            if chat and "error" not in chat:
                # Display title (optional)
                title = chat.get("title", "Chat Session")

                # Display all messages
                messages = chat.get("messages", [])
                for message in messages:
                    sender = message["sender"]
                    content = message["content"]
                    self._add_message_to_chat(sender, content)
            else:
                # If no history found or format is incorrect, display error message
                error_message = chat.get(
                    "error", f"Unable to load chat history (ID: {chat_id})"
                )
                self.chat_display.setHtml(f"<p style='color: red;'>{error_message}</p>")
                logger.error(f"Failed to load chat history: {error_message}")

        except Exception as e:
            error_message = f"Error loading chat history: {str(e)}"
            self.chat_display.setHtml(f"<p style='color: red;'>{error_message}</p>")
            logger.error(f"Exception loading chat history: {e}", exc_info=True)

    def _send_question(self):
        """Send question and get answer"""
        question = self.question_input.text().strip()
        if not question:
            return

        # Disable input and button during processing
        self.question_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.send_button.setText("Processing...")

        # Display user question in chat
        self._add_message_to_chat("You", question)

        # Clear input box
        self.question_input.clear()

        try:
            # Use AsyncTaskRunner to avoid UI freezing
            self.controller.ask_question(question, self.current_chat_id)

        except Exception as e:
            logger.error(f"Error sending question: {e}", exc_info=True)
            self._add_message_to_chat(
                "System", f"Error processing request: {str(e)}", error=True
            )
            # Re-enable input
            self.question_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.send_button.setText("Send")

    @Slot(object)
    def _on_answer_received(self, result: Dict[str, Any]):
        """Handle results received from chat service."""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()  # Set focus back to input box

        # Update current chat ID (if it's a newly created chat)
        if result.get("is_new_chat", False) and "chat_id" in result:
            self.current_chat_id = result["chat_id"]

        # Remove "Thinking..." message
        html = self.chat_display.toHtml()
        html = html.replace(
            '<p style="-qt-paragraph-type:empty"><br /></p>', ""
        )  # Remove sometimes added empty paragraph
        thinking_msg = "<i style='color: #07c160;'>🤖 System is thinking...</i>"
        # Find last occurrence and cleanly remove it
        last_occurrence = html.rfind(thinking_msg)
        if last_occurrence != -1:
            # Check if it is at the end or followed by a closing tag
            end_part = html[last_occurrence + len(thinking_msg) :].strip()
            if end_part.lower() in ["</p>", "</body></html>", ""]:
                html = html[:last_occurrence]
            else:  # Alternative: simple replace (may leave empty tags)
                html = html.replace(thinking_msg, "")

        self.chat_display.setHtml(html)  # Update HTML, remove thinking message

        if result and result.get("error"):
            logger.error(f"Chat service returned error: {result['error']}")
            self._add_message_to_chat(
                "⚠️ System Error",
                f"Sorry, an error occurred while answering the question: {result['error']}",
            )
        elif result and result.get("answer"):
            answer = result["answer"]
            self.controller.add_answer_sources(result.get("sources", []))
            # Add actual answer
            self._add_message_to_chat("🤖 System", answer)
            # Add reference sources (if any)
            if self.controller.answer_sources:
                sources_html = "<div style='margin: 10px 0 0 70px; font-size: 13px; color: #6c757d;'><b>Reference Sources (Similarity):</b><ul style='margin-top: 5px;'>"
                for src in self.controller.answer_sources:
                    title = src.get("title", "Unknown Title")
                    sim = src.get("similarity", 0)
                    sources_html += f"<li>{title} ({sim}%)</li>"
                sources_html += "</ul></div>"
                self.chat_display.append(sources_html)

        else:
            # If error is None but no answer, this should not happen
            logger.error("Chat service returned unexpected empty result.")
            self._add_message_to_chat(
                "⚠️ System Error", "Sorry, the system could not generate an answer."
            )

        self.chat_display.ensureCursorVisible()

    @Slot(Exception)
    def _on_chat_error(self, error: Exception):
        """Handle errors during the Q&A process"""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()

        # Remove "Thinking..." message (same logic as in _on_answer_received)
        html = self.chat_display.toHtml()
        html = html.replace('<p style="-qt-paragraph-type:empty"><br /></p>', "")
        thinking_msg = "<i style='color: #07c160;'>🤖 System is thinking...</i>"
        last_occurrence = html.rfind(thinking_msg)
        if last_occurrence != -1:
            end_part = html[last_occurrence + len(thinking_msg) :].strip()
            if end_part.lower() in ["</p>", "</body></html>", ""]:
                html = html[:last_occurrence]
            else:
                html = html.replace(thinking_msg, "")
        self.chat_display.setHtml(html)

        logger.error(f"Chat task execution failed: {error}", exc_info=error)
        self._add_message_to_chat(
            "⚠️ System Error",
            f"An internal error occurred while processing the question: {str(error)}",
        )
        self.chat_display.ensureCursorVisible()

    def _add_message_to_chat(self, sender: str, message: str, error: bool = False):
        """Add message to chat display area (modern bubble style)"""
        # Basic HTML escape
        message = (
            message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        # Convert newlines to <br> for HTML display
        message = message.replace("\n", "<br />")

        # Modern chat bubble style
        if "You" in sender:
            bubble_style = (
                "background: #07c160; color: #fff; border-radius: 18px 18px 4px 18px; padding: 12px 18px; "
                "max-width: 70%; margin: 8px 0 15px auto; float: right; text-align: left; "
                "box-shadow: 0 1px 2px rgba(0,0,0,0.1); line-height: 1.4;"
            )
            sender_style = (
                "font-weight: bold; color: #fff; margin-bottom: 5px; font-size: 14px;"
            )
            message_html = f"""
            <div style='clear:both;'></div>
            <div style='{bubble_style}'>
                <div style='{sender_style}'>{sender}</div>{message}
            </div>
            <div style='clear:both;'></div>
            """
        elif error or "System Error" in sender:
            bubble_style = (
                "background: #ffebee; color: #d32f2f; border-radius: 18px 18px 18px 4px; padding: 12px 18px; "
                "max-width: 70%; margin: 8px auto 15px 0; float: left; text-align: left; "
                "box-shadow: 0 1px 2px rgba(0,0,0,0.1); line-height: 1.4;"
            )
            sender_style = "font-weight: bold; color: #d32f2f; margin-bottom: 5px; font-size: 14px;"
            message_html = f"""
            <div style='clear:both;'></div>
            <div style='{bubble_style}'>
                <div style='{sender_style}'>{sender}</div>{message}
            </div>
            <div style='clear:both;'></div>
            """
        else:  # System/AI
            bubble_style = (
                "background: #f5f7fa; color: #2a3142; border-radius: 18px 18px 18px 4px; padding: 12px 18px; "
                "max-width: 70%; margin: 8px auto 15px 70px; float: left; text-align: left; "
                "box-shadow: 0 1px 2px rgba(0,0,0,0.1); line-height: 1.4;"
            )
            sender_style = "font-weight: bold; color: #07c160; margin-bottom: 5px; font-size: 14px;"
            # Add system avatar
            avatar_html = (
                "<div style='position: absolute; left: 15px; width: 40px; height: 40px; "
                + "background-color: #e7f7ed; border-radius: 50%; text-align: center; "
                + "line-height: 40px; color: #07c160; font-size: 20px;'>🤖</div>"
            )

            message_html = f"""
            <div style='clear:both;'></div>
            <div style='position: relative; padding-left: 55px;'>
                {avatar_html}
                <div style='{bubble_style}'>
                    <div style='{sender_style}'>{sender}</div>{message}
                </div>
            </div>
            <div style='clear:both;'></div>
            """

        # Add message and ensure visibility
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertHtml(message_html)
        self.chat_display.ensureCursorVisible()
