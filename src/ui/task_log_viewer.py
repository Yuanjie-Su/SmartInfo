# src/ui/task_log_viewer.py  <-- Renamed file
# -*- coding: utf-8 -*-

import logging
from typing import Optional
import markdown
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox, QApplication # Changed QTextEdit
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor # Keep for scrolling if needed

logger = logging.getLogger(__name__)

# Renamed class
class TaskLogViewer(QDialog):
    """
    A dialog to display the status and streaming output (e.g., from LLM)
    of a background task, with basic Markdown/HTML rendering.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Log") # Updated title
        self.setMinimumSize(800, 500)

        # Standard window flags
        current_flags = self.windowFlags()
        new_flags = current_flags | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowSystemMenuHint
        self.setWindowFlags(new_flags)

        self._layout = QVBoxLayout(self)

        # --- Use QTextBrowser for better rich text/markdown rendering ---
        self.log_display = QTextBrowser() # Changed from QTextEdit
        self.log_display.setReadOnly(True)
        self.log_display.setOpenExternalLinks(True) # Open links in browser
        self.log_display.setAcceptRichText(True) # QTextBrowser does this by default
        self._layout.addWidget(self.log_display, 1)

        # --- Close Button ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)
        self._layout.addWidget(self.button_box)

    @Slot(str)
    def append_log_message(self, message: str):
        """Appends a message (e.g., a stream chunk) to the log display."""
        if QApplication.instance().thread() != self.thread():
            QMetaObject.invokeMethod(self, "append_log_message", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, message))
            return

        # Use append for QTextBrowser - it handles basic HTML/Markdown automatically
        # For more complex markdown, convert to HTML first using a library
        # message = markdown.markdown(message) # Example using 'markdown' library
        self.log_display.moveCursor(QTextCursor.End)
        self.log_display.insertPlainText(message)

    def clear_display(self):
        """Clears the log display and resets the state."""
        if QApplication.instance().thread() != self.thread():
             QMetaObject.invokeMethod(self, "clear_display", Qt.ConnectionType.QueuedConnection)
             return
        self.log_display.clear()
        self.setWindowTitle("Task Log") # Reset title

    def set_final_status(self, status: str, is_error: bool = False):
        """Sets the overall final status, reflected in the window title."""
        if QApplication.instance().thread() != self.thread():
            QMetaObject.invokeMethod(self, "set_final_status", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, status), Q_ARG(bool, is_error))
            return

        log_level = logging.ERROR if is_error else logging.INFO
        logger.log(log_level, f"Task Status Popup Final Status: {status}")
        base_title = "Task Log"
        if is_error:
            self.setWindowTitle(f"{base_title} Error - {status}")
        else:
            self.setWindowTitle(f"{base_title} Complete - {status}")

    # --- Methods for Hiding ---
    def reject(self):
        logger.debug("Task log viewer reject triggered, hiding instead.")
        self.hide()

    def closeEvent(self, event):
        logger.debug("Task log viewer closeEvent triggered, hiding instead.")
        self.hide()
        event.ignore()