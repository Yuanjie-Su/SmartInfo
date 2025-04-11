# src/ui/task_status_popup.py  <-- Renamed file
# -*- coding: utf-8 -*-

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QApplication,
    QSizePolicy # Keep QSizePolicy if used elsewhere, otherwise can remove
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor # For scrolling

logger = logging.getLogger(__name__)

# Renamed class
class TaskStatusPopup(QDialog):
    """
    A dialog to display the status and streaming output (e.g., from LLM) of a background task.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Update window title to be more general
        self.setWindowTitle("Task Status")
        self.setMinimumSize(800, 500) # Adjusted size for text area

        # Standard window flags
        current_flags = self.windowFlags()
        new_flags = current_flags | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowSystemMenuHint
        self.setWindowFlags(new_flags)

        self._layout = QVBoxLayout(self)

        # --- Text Edit for Streaming Output ---
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        # Optional: Use a monospaced font for better log readability
        # font = QFont("Courier New", 10)
        # self.log_display.setFont(font)
        self.log_display.setAcceptRichText(True) # To handle potential markdown/HTML formatting
        self._layout.addWidget(self.log_display, 1) # Text area takes most space

        # --- Close Button ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject) # Connect Close button to hide
        self._layout.addWidget(self.button_box)

    @Slot(str)
    def append_log_message(self, message: str):
        """Appends a message (e.g., a stream chunk) to the log display."""
        # Ensure this runs on the GUI thread
        if QApplication.instance().thread() != self.thread():
            # Use QueuedConnection for cross-thread signals/slots
            QMetaObject.invokeMethod(self, "append_log_message", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, message))
            return

        # Append the message - using insertPlainText might be safer if markdown rendering is basic
        # Or append() if you expect simple text lines. Using insertHtml for flexibility.
        # Note: Full markdown rendering in QTextEdit is limited.
        # Consider converting markdown chunk to basic HTML if needed, or just display as text.
        # For now, just appending the raw chunk.
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(message) # Appends the text chunk
        self.log_display.setTextCursor(cursor)
        # self.log_display.ensureCursorVisible() # Auto-scroll to the bottom

    def clear_display(self):
        """Clears the log display and resets the state."""
        # Ensure this runs on the GUI thread if called from elsewhere
        if QApplication.instance().thread() != self.thread():
             QMetaObject.invokeMethod(self, "clear_display", Qt.ConnectionType.QueuedConnection)
             return
        self.log_display.clear()
        self.setWindowTitle("Task Status") # Reset title

    def set_final_status(self, status: str, is_error: bool = False):
        """Sets the overall final status, reflected in the window title."""
        # Ensure this runs on the GUI thread
        if QApplication.instance().thread() != self.thread():
            QMetaObject.invokeMethod(self, "set_final_status", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, status), Q_ARG(bool, is_error))
            return

        log_level = logging.ERROR if is_error else logging.INFO
        logger.log(log_level, f"Task Status Popup Final Status: {status}")
        base_title = "Task"
        if is_error:
            self.setWindowTitle(f"{base_title} Error - {status}")
        else:
            self.setWindowTitle(f"{base_title} Complete - {status}")

    # --- Methods for Hiding ---
    def reject(self):
        logger.debug("Task status popup reject triggered, hiding instead.")
        self.hide()

    def closeEvent(self, event):
        logger.debug("Task status popup closeEvent triggered, hiding instead.")
        self.hide()
        event.ignore()