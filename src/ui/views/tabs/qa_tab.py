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
    QScrollArea,
)
from PySide6.QtCore import (
    Qt,
    Slot,
    QThreadPool,
    QSize,
)  # Added Slot, QThreadPool, QSize
from PySide6.QtGui import QFont, QColor, QIcon

# Import Services needed
from src.services.qa_service import QAService  # 保留兼容，后续可移除
from src.ui.controllers.qa_controller import QAController
from src.ui.workers.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


class QATab(QWidget):
    """Intelligent Q&A Tab (Refactored)"""

    def __init__(self, controller: QAController):  # Inject controller
        super().__init__()
        self.controller = controller
        # 连接 Controller 信号
        self.controller.history_loaded.connect(self._on_history_loaded)
        self.controller.answer_received.connect(self._on_answer_received)
        self.controller.error_occurred.connect(self._on_qa_error)

        self._setup_ui()
        self.controller.load_history()  # Load history on init

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter, 1)

        # --- Left Panel (History) ---
        history_widget = QWidget()
        history_widget.setObjectName("HistoryPanel")
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(15, 15, 15, 15)

        # 历史标题
        history_title = QLabel("历史对话记录")
        history_title.setObjectName("HistoryTitle")
        history_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; margin-bottom: 10px;"
        )
        history_layout.addWidget(history_title)

        # 会话列表
        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        history_layout.addWidget(self.history_list, 1)

        # 清除历史按钮
        clear_button = QPushButton("清除历史记录")
        clear_button.setProperty("secondary", "true")  # 使用次要按钮样式
        clear_button.clicked.connect(self._clear_history)
        history_layout.addWidget(clear_button)

        main_splitter.addWidget(history_widget)

        # --- Right Panel (Chat) ---
        chat_widget = QWidget()
        chat_widget.setObjectName("ChatPanel")
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(15, 15, 15, 15)
        chat_layout.setSpacing(15)

        # 聊天标题
        chat_title = QLabel("智能问答")
        chat_title.setObjectName("ChatTitle")
        chat_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        chat_layout.addWidget(chat_title)

        # Chat Display Area with ScrollArea for better control
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setFrameShape(QFrame.Shape.NoFrame)

        chat_container = QWidget()
        chat_container_layout = QVBoxLayout(chat_container)
        chat_container_layout.setContentsMargins(5, 5, 5, 5)

        self.chat_display = QTextEdit()
        self.chat_display.setObjectName("qa_chat_display")
        self.chat_display.setReadOnly(True)
        # 增加字体大小
        font = self.chat_display.font()
        font.setPointSize(font.pointSize() + 1)
        self.chat_display.setFont(font)
        chat_container_layout.addWidget(self.chat_display, 1)

        chat_scroll.setWidget(chat_container)
        chat_layout.addWidget(chat_scroll, 1)  # 给更多空间

        # Input Area - Modernized
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
        self.question_input.setPlaceholderText("输入问题...")
        self.question_input.setMinimumHeight(40)
        self.question_input.returnPressed.connect(
            self._send_question
        )  # Trigger on Enter
        input_layout.addWidget(self.question_input, 1)

        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("SendButton")
        self.send_button.setMinimumSize(QSize(80, 40))
        self.send_button.clicked.connect(self._send_question)
        input_layout.addWidget(self.send_button)

        chat_layout.addWidget(input_container)
        main_splitter.addWidget(chat_widget)

        # Adjust splitter sizes - 更宽的聊天区域
        main_splitter.setSizes([280, 720])

        self._show_welcome_message()

    def load_history(self):
        """Trigger history load via controller."""
        self.controller.load_history()

    @Slot(list)
    def _on_history_loaded(self, history_items: List[Dict[str, Any]]):
        """Populate Q&A history list."""
        self.history_list.clear()
        for item in reversed(history_items):
            q_item = QListWidgetItem(item["question"])
            q_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            q_item.setToolTip(f"回答: {item['answer'][:100]}...")
            self.history_list.addItem(q_item)
        logger.info(f"Loaded {len(history_items)} QA history items.")

    def _show_welcome_message(self):
        """Display welcome message"""
        welcome_message = (
            "<div style='margin: 20px; line-height: 1.5;'>"
            "<h2 style='color: #07c160;'>欢迎使用 SmartInfo 智能问答</h2>"
            "<p>您可以基于已收集和分析的信息提问。系统将使用知识库和大型语言模型提供答案。</p>"
            "<p><b>示例问题:</b></p>"
            "<ul>"
            "<li>最近AI领域有哪些重大进展？</li>"
            "<li>总结当前量子计算的发展状态。</li>"
            "<li>芯片技术的最新突破是什么？</li>"
            "</ul>"
            "<p>请输入您的问题开始探索！</p>"
            "</div>"
        )
        self.chat_display.setHtml(welcome_message)

    def _send_question(self):
        """Sends the user's question to the QA service asynchronously."""
        question = self.question_input.text().strip()
        if not question:
            return

        self.question_input.clear()
        self._add_message_to_chat("👤 用户", question)  # Add user message immediately
        self.controller.clear_answer_sources()  # Clear sources from previous answer

        # --- Update UI State ---
        self.send_button.setEnabled(False)
        self.question_input.setEnabled(False)
        # Append thinking message without newline before it if chat is not empty
        separator = "\n" if self.chat_display.toPlainText() else ""
        self.chat_display.append(
            f"{separator}<i style='color: #07c160;'>🤖 系统思考中...</i>"
        )
        self.chat_display.ensureCursorVisible()  # Scroll down
        QApplication.processEvents()

        # --- Run async task ---
        self.controller.answer_question(question)

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
        thinking_msg = "<i style='color: #07c160;'>🤖 系统思考中...</i>"
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
                "⚠️ 系统错误",
                f"抱歉，回答问题时发生错误: {result['error']}",
            )
        elif result and result.get("answer"):
            answer = result["answer"]
            self.controller.add_answer_sources(result.get("sources", []))
            # Add the actual answer
            self._add_message_to_chat("🤖 系统", answer)
            # Add sources if any
            if self.controller.answer_sources:
                sources_html = "<div style='margin: 10px 0 0 70px; font-size: 13px; color: #6c757d;'><b>参考来源 (相似度):</b><ul style='margin-top: 5px;'>"
                for src in self.controller.answer_sources:
                    title = src.get("title", "未知标题")
                    sim = src.get("similarity", 0)
                    # Make title clickable if we store/retrieve the link? Need service change.
                    # For now, just display title and similarity.
                    sources_html += f"<li>{title} ({sim}%)</li>"
                sources_html += "</ul></div>"
                self.chat_display.append(sources_html)

            # Update history list if the question was new
            self.load_history()  # Reload history to show the new entry

        else:
            # Should not happen if error is None, but handle defensively
            logger.error("QA service returned an unexpected empty result.")
            self._add_message_to_chat("⚠️ 系统错误", "抱歉，系统无法生成答案。")

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
        thinking_msg = "<i style='color: #07c160;'>🤖 系统思考中...</i>"
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
            "⚠️ 系统错误",
            f"处理问题时发生内部错误: {str(error)}",
        )
        self.chat_display.ensureCursorVisible()

    def _add_message_to_chat(self, sender: str, message: str):
        """Add a message to the chat display (modern bubble style)"""
        # Basic HTML escaping for the message content
        message = (
            message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        # Convert newlines to <br> for HTML display
        message = message.replace("\n", "<br />")

        # 现代聊天气泡样式
        if "用户" in sender:
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
        elif "系统错误" in sender:
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
            # 添加系统头像
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

        # Append message and ensure visibility
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
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
            "确认清除",
            "确定要清除所有问答历史记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.controller.clear_qa_history():
                    self.history_list.clear()
                    self._show_welcome_message()  # Show welcome message again
                    QMessageBox.information(self, "成功", "问答历史记录已清除。")
                else:
                    QMessageBox.warning(self, "失败", "清除问答历史记录失败。")
            except Exception as e:
                logger.error(f"Error clearing QA history: {e}", exc_info=True)
                QMessageBox.critical(self, "错误", f"清除历史记录时出错: {e}")
