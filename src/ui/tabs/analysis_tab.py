#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Intelligent Analysis Tab (Refactored)
Implements intelligent analysis and summarization of news (using Service Layer)
"""

import logging
import asyncio
from typing import List, Dict, Optional, Any  # Added

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QLabel,
    QTextEdit,
    QSplitter,
    QComboBox,
    QSpinBox,
    QHeaderView,
    QMessageBox,
    QApplication,  # Added QApplication
)
from PySide6.QtCore import (
    Qt,
    QSortFilterProxyModel,
    QThreadPool,
    Slot,
)  # Added QThreadPool, Slot
from PySide6.QtGui import QStandardItemModel, QStandardItem

# Import Services needed
from src.services.analysis_service import AnalysisService
from src.services.news_service import NewsService  # To get full news content

# Assuming AsyncTaskRunner is now in ui.async_runner
from src.ui.async_runner import AsyncTaskRunner

logger = logging.getLogger(__name__)


class AnalysisTab(QWidget):
    """Intelligent Analysis Tab (Refactored)"""

    def __init__(
        self, analysis_service: AnalysisService, news_service: NewsService
    ):  # Inject services
        super().__init__()
        self._analysis_service = analysis_service
        self._news_service = news_service
        self._current_news_id: Optional[int] = None  # Store ID of item being analyzed
        self._setup_ui()
        self.load_pending_news()  # Load initially

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)

        # --- Top Control Panel ---
        control_layout = QHBoxLayout()
        main_layout.addLayout(control_layout)

        control_layout.addWidget(QLabel("Analysis type:"))
        self.analysis_type_combo = QComboBox()
        # TODO: Consider making these types configurable or dynamic
        self.analysis_type_combo.addItems(
            ["一般摘要", "技术分析", "趋势洞察", "竞争分析", "学术研究"]
        )
        control_layout.addWidget(self.analysis_type_combo)

        control_layout.addWidget(QLabel("Maximum length (approx):"))
        self.summary_length_spin = QSpinBox()
        self.summary_length_spin.setRange(100, 2000)  # Increased range
        self.summary_length_spin.setValue(300)
        self.summary_length_spin.setSingleStep(50)
        control_layout.addWidget(self.summary_length_spin)

        self.analyze_button = QPushButton("Start analysis")
        self.analyze_button.clicked.connect(self._start_analysis)
        control_layout.addWidget(self.analyze_button)

        # Save button might be less relevant if analysis is saved automatically
        # self.save_button = QPushButton("Save analysis result")
        # self.save_button.clicked.connect(self._save_analysis)
        # control_layout.addWidget(self.save_button)

        self.refresh_button = QPushButton("Refresh list")
        self.refresh_button.clicked.connect(self.load_pending_news)
        control_layout.addWidget(self.refresh_button)

        control_layout.addStretch()

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter, 1)

        # --- Left Panel (Pending News List) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Pending news items (last 10):"))  # Indicate limit

        self.pending_table = QTableView()
        self.pending_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.pending_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.pending_table.verticalHeader().setVisible(False)
        self.pending_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.pending_table.setSortingEnabled(True)
        left_layout.addWidget(self.pending_table)

        self._setup_table_model()  # Setup model and proxy
        main_splitter.addWidget(left_widget)

        # --- Right Panel (Content & Analysis) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_layout.addWidget(right_splitter)

        # Original Content Area
        original_widget = QWidget()
        original_layout = QVBoxLayout(original_widget)
        original_layout.setContentsMargins(0, 0, 0, 0)
        original_layout.addWidget(QLabel("Original content preview:"))
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        original_layout.addWidget(self.original_text)
        right_splitter.addWidget(original_widget)

        # Analysis Result Area
        analysis_widget = QWidget()
        analysis_layout = QVBoxLayout(analysis_widget)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.addWidget(QLabel("Analysis result:"))
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        analysis_layout.addWidget(self.analysis_text)
        right_splitter.addWidget(analysis_widget)

        right_splitter.setSizes([300, 400])  # Adjust proportions
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([400, 600])  # Adjust proportions

        # Connect selection change
        self.pending_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    def _setup_table_model(self):
        """Sets up the table model and proxy."""
        self.model = QStandardItemModel(0, 3, self)  # Title, Source, Date
        self.model.setHorizontalHeaderLabels(["Title", "Source", "Date"])
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.pending_table.setModel(self.proxy_model)

    def load_pending_news(self):
        """Loads unanalyzed news items into the table."""
        logger.info("Loading unanalyzed news for analysis tab...")
        try:
            self.model.removeRows(0, self.model.rowCount())  # Clear existing
            # Get limited list from analysis service
            # Returns List[Dict] with basic info + summary/content if needed by service
            news_list = self._analysis_service.get_unanalyzed_news(limit=10)

            if not news_list:
                logger.info("No unanalyzed news items found.")
                # Optionally display a message in the table area
                return

            for news in news_list:
                news_id = news.get("id")
                title_item = QStandardItem(news.get("title", "N/A"))
                source_item = QStandardItem(news.get("source_name", "N/A"))
                date_str = (
                    news.get("published_date")
                    or news.get("date")
                    or news.get("fetched_date", "")
                )
                date_item = QStandardItem(date_str[:10] if date_str else "N/A")

                title_item.setData(news_id, Qt.ItemDataRole.UserRole)  # Store ID
                for item in [title_item, source_item, date_item]:
                    item.setEditable(False)

                self.model.appendRow([title_item, source_item, date_item])

            logger.info(
                f"Loaded {len(news_list)} unanalyzed items into analysis table."
            )

        except Exception as e:
            logger.error(f"Failed to load unanalyzed news: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"Failed to load unanalyzed news: {str(e)}"
            )

    def load_news_for_analysis(self, news_id: int):
        """Load a specific news item for analysis"""
        logger.info(f"Loading specific news ID {news_id} for analysis.")
        # TODO: Implement logic to find/select this item in the pending_table
        # Or, directly load its content into the preview areas.
        # Simplest for now: just load its content, don't change table selection.
        self._load_content_for_id(news_id)
        self._current_news_id = news_id  # Set the ID to analyze

    def _load_content_for_id(self, news_id: int):
        """Load the content of a specific news item by ID"""
        self.original_text.clear()
        self.analysis_text.clear()
        try:
            news_details = self._news_service.get_news_by_id(news_id)
            if news_details:
                # Display original content (prefer full content, fallback summary)
                content = (
                    news_details.get("content")
                    or news_details.get("summary")
                    or "无内容"
                )
                title = news_details.get("title", "N/A")
                source = news_details.get("source_name", "N/A")
                date = (
                    news_details.get("published_date")
                    or news_details.get("date")
                    or news_details.get("fetched_date", "")
                )

                self.original_text.setText(
                    f"ID: {news_id}\n"
                    f"Title: {title}\n"
                    f"Source: {source}\n"
                    f"Date: {date[:19]}\n\n"
                    f"--- Content ---\n{content}"
                )
                # Display existing analysis if available
                llm_analysis = news_details.get("llm_analysis")
                if llm_analysis:
                    self.analysis_text.setText(llm_analysis)
                else:
                    self.analysis_text.setPlaceholderText("尚未进行分析。")
                self._current_news_id = news_id  # Store the currently viewed ID
            else:
                self.original_text.setText(f"错误：无法加载 ID 为 {news_id} 的资讯。")
                self._current_news_id = None
        except Exception as e:
            logger.error(
                f"Error loading content for news ID {news_id}: {e}", exc_info=True
            )
            self.original_text.setText(f"加载资讯内容时出错 (ID: {news_id}):\n{e}")
            self._current_news_id = None

    def _on_selection_changed(self, selected, deselected):
        """Handle selection change event"""
        indexes = selected.indexes()
        if indexes:
            source_index = self.proxy_model.mapToSource(indexes[0])
            news_id = self.model.item(source_index.row(), 0).data(
                Qt.ItemDataRole.UserRole
            )
            if news_id is not None:
                self._load_content_for_id(news_id)

    def _start_analysis(self):
        """Start the analysis process for the selected news item"""
        if self._current_news_id is None:
            # Check if a row is selected in the table as a fallback
            selected_indexes = self.pending_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(
                    self, "警告", "请先在左侧列表中选择一个资讯进行分析。"
                )
                return
            source_index = self.proxy_model.mapToSource(selected_indexes[0])
            self._current_news_id = self.model.item(source_index.row(), 0).data(
                Qt.ItemDataRole.UserRole
            )
            if self._current_news_id is None:
                QMessageBox.critical(self, "错误", "无法获取所选资讯的ID。")
                return

        # Get parameters from UI
        analysis_type = self.analysis_type_combo.currentText()
        max_length = self.summary_length_spin.value()
        news_id_to_analyze = self._current_news_id

        logger.info(
            f"Starting analysis for news ID {news_id_to_analyze} (Type: {analysis_type}, Length: {max_length})"
        )

        # Update UI state
        self.analysis_text.setText("<i>正在生成分析报告，请稍候...</i>")
        self.analyze_button.setEnabled(False)
        QApplication.processEvents()  # Ensure UI updates

        # --- Run async task ---
        analyze_coro = self._analysis_service.analyze_single_news
        args = (news_id_to_analyze, analysis_type, max_length)

        self.runner = AsyncTaskRunner(analyze_coro, *args)
        self.runner.setAutoDelete(True)
        self.runner.signals.finished.connect(self._on_analysis_finished)
        self.runner.signals.error.connect(self._on_analysis_error)
        QThreadPool.globalInstance().start(self.runner)

    @Slot(object)
    def _on_analysis_finished(self, result: Optional[str]):
        """Handle successful completion of analysis"""
        self.analyze_button.setEnabled(True)  # Re-enable button
        if result:
            logger.info(f"Analysis successful for news ID {self._current_news_id}.")
            self.analysis_text.setText(result)
            QMessageBox.information(
                self,
                "Analysis completed",
                f"News (ID: {self._current_news_id}) analysis completed.",
            )
            # Refresh the pending list as this item is now analyzed
            self.load_pending_news()
            # Maybe clear selection or update the analyzed status in the main news tab?
        else:
            # Service layer should have logged the error, result is None or specific error message
            logger.warning(
                f"Analysis task finished but returned no result/error message for ID {self._current_news_id}."
            )
            # Display the error message that might have been saved by the service
            news_details = self._news_service.get_news_by_id(self._current_news_id)
            fail_msg = "分析失败，LLM 未返回结果。"
            if news_details and news_details.get("llm_analysis", "").startswith(
                "分析失败"
            ):
                fail_msg = news_details["llm_analysis"]
            self.analysis_text.setText(f"<font color='red'>{fail_msg}</font>")
            QMessageBox.warning(
                self,
                "Analysis failed",
                f"Unable to generate analysis report for news ID {self._current_news_id}.",
            )

    @Slot(Exception)
    def _on_analysis_error(self, error: Exception):
        """Handle errors during analysis"""
        self.analyze_button.setEnabled(True)  # Re-enable button
        logger.error(
            f"Analysis task failed for news ID {self._current_news_id}: {error}",
            exc_info=error,
        )
        self.analysis_text.setText(
            f"<font color='red'>Analysis error:\n{str(error)}</font>"
        )
        QMessageBox.critical(
            self,
            "Analysis error",
            f"Error analyzing news ID {self._current_news_id}:\n{str(error)}",
        )

    # def _save_analysis(self):
    #     """Saves the analysis result (Placeholder - likely not needed if auto-saved)."""
    #     # Analysis is saved automatically by analyze_single_news
    #     QMessageBox.information(self, "提示", "分析结果已自动保存到数据库。")
