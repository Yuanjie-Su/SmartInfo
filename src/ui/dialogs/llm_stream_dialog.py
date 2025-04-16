# src/ui/dialogs/llm_stream_dialog.py (Modified)
# -*- coding: utf-8 -*-

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTextEdit,
    QDialogButtonBox,
    QApplication,
    QLabel,
    QHBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG  # Added QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor, QIcon, QFont  # Keep QTextCursor

logger = logging.getLogger(__name__)


# Class name kept as LlmStreamDialog, but behavior changed
class LlmStreamDialog(QDialog):
    """Dialog to display the complete LLM analysis output for a specific task/URL."""

    def __init__(self, title: str = "LLM分析结果", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(750, 550)
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 添加标题标签
        header_layout = QHBoxLayout()
        icon_label = QLabel("🤖")
        icon_label.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(icon_label)

        title_label = QLabel("大语言模型分析结果")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #07c160;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 描述标签
        description = QLabel("以下是大语言模型对所选内容的分析结果。")
        description.setStyleSheet("color: #6c757d;")
        layout.addWidget(description)

        # 内容容器
        content_container = QWidget()
        content_container.setObjectName("LlmResultContainer")
        content_container.setStyleSheet(
            """
            #LlmResultContainer {
                background-color: #ffffff;
                border: 1px solid #e0e4e7;
                border-radius: 8px;
            }
        """
        )
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(15, 15, 15, 15)

        # 结果显示区域
        self.result_display = QTextEdit()
        self.result_display.setObjectName("LlmResultDisplay")
        self.result_display.setReadOnly(True)
        # 设置更好的字体和大小
        font = QFont("Microsoft YaHei", 11)
        self.result_display.setFont(font)
        # 设置样式
        self.result_display.setStyleSheet(
            """
            #LlmResultDisplay {
                border: none;
                background-color: #ffffff;
                color: #2a3142;
            }
        """
        )
        content_layout.addWidget(self.result_display, 1)

        layout.addWidget(content_container, 1)

        # 底部按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = self.button_box.button(QDialogButtonBox.StandardButton.Close)
        close_button.setText("关闭")
        close_button.setMinimumHeight(35)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box, 0, Qt.AlignmentFlag.AlignRight)

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
        # Use setMarkdown for better rendering
        self.result_display.setMarkdown(content)
        self.result_display.moveCursor(QTextCursor.MoveOperation.Start)
        self.result_display.ensureCursorVisible()

    def set_window_title(self, title: str):
        """Updates the dialog's window title."""
        self.setWindowTitle(title)
