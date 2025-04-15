# src/ui/dialogs/llm_stream_dialog.py (Modified)
# -*- coding: utf-8 -*-

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTextEdit,
    QDialogButtonBox,
    QApplication,
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG  # Added QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor  # Keep QTextCursor

logger = logging.getLogger(__name__)


# Class name kept as LlmStreamDialog, but behavior changed
class LlmStreamDialog(QDialog):
    """Dialog to display the complete LLM analysis output for a specific task/URL."""

    def __init__(self, title: str = "LLM Analysis Output", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(700, 500)
        self.setModal(False)

        current_flags = self.windowFlags()
        new_flags = (
            current_flags
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowFlags(new_flags)

        layout = QVBoxLayout(self)

        # Rename display variable for clarity
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        # Use setMarkdown to potentially render the output better
        # self.result_display.setAcceptRichText(False) # Set to false if using setMarkdown
        layout.addWidget(self.result_display, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    # REMOVED: append_chunk method

    def clear_display(self):
        """Clears the display area."""
        self.result_display.clear()

    # ADDED: set_content method
    def set_content(self, content: str):  # Changed parameter name
        """Sets the entire content of the display area."""
        if QApplication.instance().thread() != self.thread():
            QMetaObject.invokeMethod(
                self,
                "_set_content_on_gui",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, content),
            )
        else:
            self._set_content_on_gui(content)

    @Slot(str)
    def _set_content_on_gui(self, content: str):
        """Slot to safely update the display content from the GUI thread."""
        # Use setMarkdown for both real results and the HTML placeholder
        self.result_display.setMarkdown(content)
        self.result_display.moveCursor(QTextCursor.MoveOperation.Start)
        self.result_display.ensureCursorVisible()

    def set_window_title(self, title: str):
        """Updates the dialog's window title."""
        self.setWindowTitle(title)
