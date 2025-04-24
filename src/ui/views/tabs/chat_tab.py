#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Chat Interface Module
Implements intelligent question-answering chat functionality based on new database structure
"""

import logging
import asyncio
import time
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
    Signal,
    QRectF,
    QEvent,
    QTimer,
    QItemSelectionModel,
)
from PySide6.QtGui import (
    QFont,
    QColor,
    QIcon,
    QPainter,
    QTextDocument,
    QTextOption,
)

# Import necessary services and controllers
from src.ui.controllers.chat_controller import ChatController
from src.ui.workers.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


from PySide6.QtWidgets import QListView, QStyledItemDelegate, QStyle
from PySide6.QtCore import QAbstractListModel, QModelIndex


class ChatMessage:
    """Data class for a chat message"""

    def __init__(
        self, sender, content, is_user=False, message_id=None, is_streaming=False
    ):
        self.sender = sender
        self.content = content
        self.is_user = is_user
        self.message_id = message_id
        self.is_streaming = is_streaming
        self.show_copy_button = False  # Flag to track hover state


class ChatListModel(QAbstractListModel):
    """Model to hold chat messages data"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.messages)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.messages):
            return None

        message = self.messages[index.row()]

        if role == Qt.DisplayRole:
            return message

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or index.row() >= len(self.messages):
            return False

        if role == Qt.UserRole:  # Use this role for setting hover state
            self.messages[index.row()].show_copy_button = value
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    def addMessage(self, message):
        self.beginInsertRows(QModelIndex(), len(self.messages), len(self.messages))
        self.messages.append(message)
        self.endInsertRows()
        return len(self.messages) - 1  # Return index of added message

    def updateMessage(self, message_id, content):
        for i, msg in enumerate(self.messages):
            if msg.message_id == message_id:
                msg.content = content
                self.dataChanged.emit(self.index(i, 0), self.index(i, 0))
                break


class SelectableTextDocument(QTextDocument):
    """QTextDocument that supports text selection"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # TextInteractionFlags don't directly apply to QTextDocument when used in a delegate
        # Actual text selection is handled by the view's selection mechanism


class ChatItemDelegate(QStyledItemDelegate):
    """Custom delegate for rendering chat messages with copy button"""

    copyButtonClicked = Signal(int)  # Signal emitted when copy button is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_index = QModelIndex()
        # Use a Unicode character instead of an icon file
        self.copy_text = "📋"  # Unicode clipboard icon
        self.active_copy_button = None  # Tracks which message has an active copy button

    def paint(self, painter, option, index):
        message = index.data(Qt.DisplayRole)
        if not message:
            return

        painter.save()

        # Prepare document for rendering
        doc = SelectableTextDocument()
        doc.setDocumentMargin(10)

        # Set up text options
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)

        # Different styling for user vs system messages
        if message.is_user:
            html = f"""
            <div style="color: #000; background-color: #f0f0f0; 
                        border-radius: 10px; padding: 8px 12px; 
                        margin-left: 50px; margin-right: 10px;">
                {message.content}
            </div>
            """
        else:
            sender_style = ""
            if message.is_streaming:
                animation = "<span style='color: #07c160;'>●</span>"
                html = f"""
                <div style="color: #000; background-color: #ffffff; 
                            border-radius: 10px; padding: 8px 12px; 
                            margin-left: 10px; margin-right: 50px;">
                    {sender_style}
                    {message.content} {animation}
                </div>
                """
            else:
                html = f"""
                <div style="color: #000; background-color: #ffffff; 
                            border-radius: 10px; padding: 8px 12px; 
                            margin-left: 10px; margin-right: 50px;">
                    {sender_style}
                    {message.content}
                </div>
                """

        doc.setHtml(html)

        # Set document width to the width of the view
        doc.setTextWidth(option.rect.width())

        # Draw the document
        ctx = option.widget.style().styleHint(QStyle.SH_ItemView_ShowDecorationSelected)
        if option.state & QStyle.State_Selected and ctx:
            painter.fillRect(option.rect, option.palette.highlight())

        painter.translate(option.rect.topLeft())
        doc.drawContents(painter)

        # Draw copy button if it's not a user message and hovering
        if not message.is_user and message.show_copy_button:
            # Position the copy button at the top right of the message
            button_size = 24
            button_x = option.rect.width() - button_size - 10
            button_y = 10  # Position at top for better visibility

            button_rect = QRectF(button_x, button_y, button_size, button_size)

            # Draw a subtle background for the button
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(240, 240, 240, 200))  # Light gray with transparency
            painter.drawRoundedRect(button_rect, 4, 4)

            # Draw the copy icon
            painter.setPen(QColor(80, 80, 80))  # Dark gray text
            painter.drawText(button_rect.toRect(), Qt.AlignCenter, self.copy_text)

        painter.restore()

    def sizeHint(self, option, index):
        message = index.data(Qt.DisplayRole)
        if not message:
            return QSize(0, 0)

        doc = QTextDocument()
        doc.setDocumentMargin(10)

        # Apply the same styling as in paint()
        if message.is_user:
            html = f"""
            <div style="color: #000; background-color: #f0f0f0; 
                        border-radius: 10px; padding: 8px 12px; 
                        margin-left: 50px; margin-right: 10px;">
                {message.content}
            </div>
            """
        else:
            html = f"""
            <div style="color: #000; background-color: #ffffff; 
                        border-radius: 10px; padding: 8px 12px; 
                        margin-left: 10px; margin-right: 50px;">
                {message.content}
            </div>
            """

        doc.setHtml(html)
        doc.setTextWidth(option.rect.width())

        # Add extra space for copy button and margins
        extra_height = 20
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + extra_height)

    def editorEvent(self, event, model, option, index):
        """Handle mouse events within the delegate"""
        if not index.isValid():
            return False

        message = index.data(Qt.DisplayRole)
        if not message or message.is_user:
            return False

        if event.type() == QEvent.MouseMove:
            # Set hover state for copy button
            model.setData(index, True, Qt.UserRole)
            return True

        elif event.type() == QEvent.MouseButtonPress:
            # Check if click was on copy button
            if message.show_copy_button:
                button_size = 24
                button_x = option.rect.width() - button_size - 10
                button_y = 10  # Match the position from paint

                button_rect = QRectF(
                    button_x, button_y, button_size, button_size
                ).toRect()
                transformed_rect = button_rect.translated(option.rect.topLeft())

                if transformed_rect.contains(event.pos()):
                    # Copy the message content to clipboard without HTML tags
                    content = message.content.replace("<br />", "\n")
                    # Remove any HTML entities
                    content = (
                        content.replace("&lt;", "<")
                        .replace("&gt;", ">")
                        .replace("&amp;", "&")
                    )
                    QApplication.clipboard().setText(content)
                    self.copyButtonClicked.emit(index.row())
                    self.active_copy_button = index
                    return True

        return False


class ChatListView(QListView):
    """Enhanced QListView with hover detection for copy buttons and text selection"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)  # Enable mouse tracking for hover
        self.last_hover_index = QModelIndex()
        self.setTextElideMode(Qt.ElideNone)  # Don't elide text
        self.setWordWrap(True)  # Enable word wrap
        self.setSelectionMode(
            QListView.SelectionMode.ExtendedSelection
        )  # Allow text selection

    def mouseMoveEvent(self, event):
        """Track mouse movement to show/hide copy buttons"""
        index = self.indexAt(event.pos())

        if self.last_hover_index.isValid() and index != self.last_hover_index:
            # Mouse moved away from previous item
            self.model().setData(self.last_hover_index, False, Qt.UserRole)

        if index.isValid():
            # Mouse moved over an item
            self.model().setData(index, True, Qt.UserRole)
            self.last_hover_index = index

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the widget"""
        if self.last_hover_index.isValid():
            self.model().setData(self.last_hover_index, False, Qt.UserRole)
            self.last_hover_index = QModelIndex()

        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click to select text in message"""
        index = self.indexAt(event.pos())
        if index.isValid():
            message = index.data(Qt.DisplayRole)
            if message:
                # Select the entire message text when double-clicked
                self.setSelection(
                    self.visualRect(index), QItemSelectionModel.SelectionFlag.Select
                )
                # Emit a selection changed signal to update the UI
                self.selectionModel().select(
                    index, QItemSelectionModel.SelectionFlag.Select
                )
        super().mouseDoubleClickEvent(event)


class ChatTab(QWidget):
    """Intelligent Chat Interface"""

    def __init__(self, controller: ChatController):  # Inject controller
        super().__init__()
        self.controller = controller
        # Connect controller signals
        self.controller.answer_received.connect(self._on_answer_received)
        self.controller.streaming_chunk_received.connect(self._on_streaming_chunk)
        self.controller.error_occurred.connect(self._on_chat_error)

        # Track the current active chat ID
        self.current_chat_id = None

        # Track for streaming messages
        self.current_message_id = None
        self.current_streaming_content = ""

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

        # Use our custom ChatListView instead of QListView
        self.chat_display = ChatListView()
        self.chat_display.setObjectName("chat_display")
        self.chat_display.setFrameShape(QFrame.NoFrame)
        self.chat_display.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.chat_display.setSelectionMode(QListView.NoSelection)

        # Set up the model and delegate
        self.chat_model = ChatListModel()
        self.chat_delegate = ChatItemDelegate()
        self.chat_display.setModel(self.chat_model)
        self.chat_display.setItemDelegate(self.chat_delegate)

        # Connect copy button clicked signal
        self.chat_delegate.copyButtonClicked.connect(self._on_copy_button_clicked)

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
        """Display welcome message using the chat model"""
        welcome_message = (
            "<h2 style='color: #07c160;'>Welcome to SmartInfo Intelligent Chat</h2>"
            "<p>You can ask any question, and the system will provide answers using a large language model.</p>"
            "<p><b>Example questions:</b></p>"
            "<ul>"
            "<li>What are the major recent advancements in the field of artificial intelligence?</li>"
            "<li>Summarize the current status of quantum computing.</li>"
            "<li>What are the latest breakthroughs in chip technology?</li>"
            "</ul>"
            "<p>Please enter your question to start exploring!</p>"
        )

        # Create a system message and add it to the model
        system_msg = ChatMessage(
            sender="System",
            content=welcome_message,
            is_user=False,
            message_id="welcome-msg",
        )

        # Add to model
        self.chat_model.addMessage(system_msg)

        # Scroll to show the message
        self.chat_display.scrollToBottom()

    def start_new_chat(self):
        """Create and start a new chat session"""
        logger.info("Starting a new chat session")

        # Clear chat display
        self.chat_model.messages.clear()
        self.chat_model.layoutChanged.emit()

        # Show welcome message
        self._show_welcome_message()

        # Clear input box
        self.question_input.clear()

        # Reset current chat ID
        self.current_chat_id = None
        self.current_message_id = None
        self.current_streaming_content = ""

    def load_chat(self, chat_id: int):
        """Load chat session with specified ID"""
        logger.info(f"Loading chat session: {chat_id}")

        try:
            # Save current chat ID
            self.current_chat_id = chat_id
            self.current_message_id = None
            self.current_streaming_content = ""

            # Get chat history from controller
            chat = self.controller.get_chat(chat_id)

            # Clear current chat display
            self.chat_model.messages.clear()
            self.chat_model.layoutChanged.emit()

            # Display historical conversation content
            if chat and "error" not in chat:
                # Display all messages
                messages = chat.get("messages", [])
                for message in messages:
                    sender = message["sender"]
                    content = message["content"]
                    # Escape HTML special characters
                    content = (
                        content.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    content = content.replace("\n", "<br />")

                    is_user = sender == "You"
                    chat_msg = ChatMessage(
                        sender=sender,
                        content=content,
                        is_user=is_user,
                        message_id=f"hist-{message.get('id', '')}",
                    )
                    self.chat_model.addMessage(chat_msg)
            else:
                # If no history found or format is incorrect, display error message
                error_message = chat.get(
                    "error", f"Unable to load chat history (ID: {chat_id})"
                )
                error_msg = ChatMessage(
                    sender="System Error",
                    content=error_message,
                    is_user=False,
                    message_id="error-msg",
                )
                self.chat_model.addMessage(error_msg)
                logger.error(f"Failed to load chat history: {error_message}")

            # Scroll to show latest message
            if self.chat_model.rowCount() > 0:
                self.chat_display.scrollToBottom()

        except Exception as e:
            error_message = f"Error loading chat history: {str(e)}"
            error_msg = ChatMessage(
                sender="System Error",
                content=error_message,
                is_user=False,
                message_id="error-msg",
            )
            self.chat_model.addMessage(error_msg)
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
            # Create a message ID for the assistant's response
            assistant_msg_id = f"assistant-msg-{int(time.time() * 1000)}"

            # Add a placeholder for the system response with typing indicator
            typing_msg = ChatMessage(
                sender="System",
                content="",  # Will be updated with streaming content
                is_user=False,
                message_id=assistant_msg_id,
                is_streaming=True,
            )
            self.chat_model.addMessage(typing_msg)

            # Scroll to show typing indicator
            self.chat_display.scrollToBottom()

            # Store message ID for streaming updates
            self.current_streaming_message_id = assistant_msg_id
            self.current_streaming_content = ""

            # Use controller to ask question
            self.controller.ask_question(question, self.current_chat_id)

        except Exception as e:
            logger.error(f"Error sending question: {e}", exc_info=True)
            self._add_message_to_chat(
                "System Error", f"Error processing request: {str(e)}", error=True
            )
            # Re-enable input
            self.question_input.setEnabled(True)
            self.send_button.setEnabled(True)
            self.send_button.setText("Send")

    @Slot(dict)
    def _on_streaming_chunk(self, chunk_data: Dict[str, Any]):
        """Handle streaming chunks with the new model"""
        try:
            # Get data from chunk
            message_id = chunk_data.get("message_id")
            chat_id = chunk_data.get("chat_id")
            text_chunk = chunk_data.get("text_chunk", "")
            full_text = chunk_data.get("full_text", "")
            is_final = chunk_data.get("is_final", False)

            # Skip if not for current chat
            if self.current_chat_id is not None and chat_id != self.current_chat_id:
                return

            # Skip if the streaming ID has been cleared (meaning _on_answer_received has already run)
            if is_final and not hasattr(self, "current_streaming_message_id"):
                return

            if is_final and self.current_streaming_message_id is None:
                return

            # Update streaming content
            self.current_streaming_content = full_text

            # Escape HTML content
            escaped_content = (
                full_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br />")
            )

            # Update message in model
            if self.current_streaming_message_id:
                self.chat_model.updateMessage(
                    self.current_streaming_message_id, escaped_content
                )

                # Scroll to bottom to show latest content
                self.chat_display.scrollToBottom()

                # Clear streaming state if final
                if is_final:
                    # Update the message to no longer show streaming animation
                    for i, msg in enumerate(self.chat_model.messages):
                        if msg.message_id == self.current_streaming_message_id:
                            msg.is_streaming = False
                            self.chat_model.dataChanged.emit(
                                self.chat_model.index(i, 0), self.chat_model.index(i, 0)
                            )
                            break

                    self.current_streaming_message_id = None
                    self.current_streaming_content = ""

        except Exception as e:
            logger.error(f"Error handling streaming chunk: {e}", exc_info=True)

    @Slot(object)
    def _on_answer_received(self, result: Dict[str, Any]):
        """Handle results received from chat service."""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()  # Set focus back to input box
        self.send_button.setText("Send")

        # Update current chat ID (if it's a newly created chat)
        if result.get("is_new_chat", False) and "chat_id" in result:
            self.current_chat_id = result["chat_id"]

        # Clean up streaming state if needed
        if hasattr(self, "current_streaming_message_id"):
            self.current_streaming_message_id = None
            self.current_streaming_content = ""

        # Add reference sources (if any)
        if self.controller.answer_sources:
            sources_msg = "Reference Sources (Similarity):\n"
            for src in self.controller.answer_sources:
                title = src.get("title", "Unknown Title")
                sim = src.get("similarity", 0)
                sources_msg += f"- {title} ({sim}%)\n"

            # Add sources as a separate message
            source_message = ChatMessage(
                sender="System",
                content=sources_msg,
                is_user=False,
                message_id=f"sources-{int(time.time() * 1000)}",
            )
            self.chat_model.addMessage(source_message)
            self.chat_display.scrollToBottom()

    @Slot(Exception)
    def _on_chat_error(self, error: Exception):
        """Handle errors during the Q&A process"""
        self.send_button.setEnabled(True)
        self.question_input.setEnabled(True)
        self.question_input.setFocus()
        self.send_button.setText("Send")

        # Clear any streaming state
        if self.current_streaming_message_id:
            # Find and update the streaming message to show error
            for i, msg in enumerate(self.chat_model.messages):
                if msg.message_id == self.current_streaming_message_id:
                    msg.content = "Error: processing failed"
                    msg.is_streaming = False
                    self.chat_model.dataChanged.emit(
                        self.chat_model.index(i, 0), self.chat_model.index(i, 0)
                    )
                    break

            self.current_streaming_message_id = None
            self.current_streaming_content = ""

        logger.error(f"Chat task execution failed: {error}", exc_info=error)

        # Add error message
        self._add_message_to_chat(
            "System Error",
            f"An internal error occurred while processing the question: {str(error)}",
        )

        # Scroll to show the error message
        self.chat_display.scrollToBottom()

    def _add_message_to_chat(self, sender: str, message: str, error: bool = False):
        """Add message to chat display using the new model"""
        is_user = sender == "You"
        msg_id = f"msg-{int(time.time() * 1000)}" if not is_user else None

        # Escape HTML special characters
        message = (
            message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        message = message.replace("\n", "<br />")

        chat_msg = ChatMessage(
            sender=sender, content=message, is_user=is_user, message_id=msg_id
        )

        # Add to model
        idx = self.chat_model.addMessage(chat_msg)

        # Scroll to show the new message
        self.chat_display.scrollTo(self.chat_model.index(idx, 0))

        return msg_id

    def _on_copy_button_clicked(self, row):
        """Handle copy button clicks"""
        if 0 <= row < self.chat_model.rowCount():
            message = self.chat_model.messages[row]
            # The content is already copied to clipboard in the delegate

            # Show a quick status message if the status bar is available
            status_bar = self.window().statusBar()
            if status_bar:
                status_bar.showMessage("Message copied to clipboard", 2000)

            # If no status bar is available, show a small tooltip-like popup
            else:
                # Find top-level window position
                top_window = self.window()
                global_pos = top_window.mapToGlobal(top_window.rect().center())

                # Create a message box with no buttons
                popup = QMessageBox(top_window)
                popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
                popup.setText("Copied to clipboard")
                popup.setStandardButtons(QMessageBox.NoButton)

                # Position in center of window
                popup.move(
                    global_pos.x() - popup.width() // 2,
                    global_pos.y() - popup.height() // 2,
                )

                # Show for a short time
                popup.show()

                # Use a timer to automatically close the popup
                QTimer.singleShot(1500, popup.close)
