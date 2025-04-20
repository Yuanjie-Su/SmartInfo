#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion functionality via its Controller.
"""

import logging
from typing import List, Dict, Optional, Tuple, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QComboBox,
    QLabel,
    QLineEdit,
    QMenu,
    QSplitter,
    QTextEdit,
    QHeaderView,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QMetaObject, Q_ARG
from PySide6.QtGui import QAction

from src.ui.controllers.news_controller import NewsController
from src.ui.views.dialogs.fetch_progress_dialog import FetchProgressDialog
from src.ui.views.dialogs.llm_stream_dialog import LlmStreamDialog
from src.ui.views.dialogs.analysis_detail_dialog import AnalysisDetailDialog

logger = logging.getLogger(__name__)


class NewsTab(QWidget):
    """News Management Tab (View Component)"""

    def __init__(self, controller: NewsController):
        super().__init__()
        self.controller = controller
        self._is_closing = False
        self.fetch_progress_dialog: Optional[FetchProgressDialog] = None
        self.llm_stream_dialogs: Dict[str, LlmStreamDialog] = {}
        self._cached_analysis_results: Dict[str, str] = {}

        self._setup_ui()
        self._connect_signals()

        # Initial data load triggered via controller
        self.controller.load_initial_data()
        logger.info("NewsTab initialized and requested initial data load.")

    # --- UI Setup ---
    def _setup_ui(self):
        """Set up user interface widgets."""
        main_layout = QVBoxLayout(self)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()
        main_layout.addLayout(toolbar_layout)

        self.fetch_button = QPushButton("Fetch News")
        self.fetch_button.setToolTip("Start fetching news and show progress window.")
        toolbar_layout.addWidget(self.fetch_button)

        self.cancel_fetch_button = QPushButton("Cancel Fetch")  # Added Cancel Button
        self.cancel_fetch_button.setToolTip("Cancel the ongoing fetch operation.")
        self.cancel_fetch_button.setEnabled(False)  # Initially disabled
        toolbar_layout.addWidget(self.cancel_fetch_button)

        # --- Filters ---
        toolbar_layout.addWidget(QLabel("Category:"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All", -1)
        toolbar_layout.addWidget(self.category_filter)

        toolbar_layout.addWidget(QLabel("Source:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("All", -1)
        toolbar_layout.addWidget(self.source_filter)

        toolbar_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title, source, summary...")
        toolbar_layout.addWidget(self.search_input)

        # --- Splitter, Table, Preview ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, 1)

        # Setup Table
        self.news_table = QTableView()
        self.news_table.setSortingEnabled(True)
        self.news_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.news_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.news_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.news_table.horizontalHeader().setStretchLastSection(True)
        self.news_table.verticalHeader().setVisible(False)

        # Set model from controller
        if self.controller.proxy_model:
            self.news_table.setModel(self.controller.proxy_model)
            # Hide columns after setting the model
            self._hide_table_columns()
        else:
            logger.error("NewsController did not provide a valid proxy model!")
            # Consider disabling table or showing an error message in the UI

        splitter.addWidget(self.news_table)

        # Setup Preview Area
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel("Preview:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        splitter.addWidget(preview_widget)

        splitter.setSizes([600, 200])

        # Context Menu
        self.news_table.setContextMenuPolicy(Qt.CustomContextMenu)

    def _hide_table_columns(self):
        """Hides specific columns in the news table."""
        if not self.controller.proxy_model:
            return
        model = (
            self.controller.proxy_model.sourceModel()
        )  # Get the underlying QSqlTableModel
        if not model:
            return

        columns_to_hide = [
            "id",
            "link",
            "summary",
            "analysis",
            "source_id",
            "category_id",
            "content",
        ]
        for col_name in columns_to_hide:
            col_index = model.fieldIndex(col_name)
            if col_index != -1:
                self.news_table.setColumnHidden(col_index, True)

    # --- Signal Connections ---
    def _connect_signals(self):
        """Connect UI signals to internal slots or controller slots."""
        # UI Actions -> Internal Trigger Methods -> Controller Actions
        self.fetch_button.clicked.connect(self._trigger_fetch_news)
        self.cancel_fetch_button.clicked.connect(self._trigger_cancel_fetch)
        self.category_filter.currentIndexChanged.connect(self._handle_category_change)
        self.source_filter.currentIndexChanged.connect(self._trigger_filter_apply)
        self.search_input.textChanged.connect(self._trigger_filter_apply)
        self.news_table.selectionModel().selectionChanged.connect(
            self._trigger_selection_changed
        )
        self.news_table.customContextMenuRequested.connect(self._show_context_menu)

        # Controller Signals -> View Update Slots
        self.controller.news_data_updated.connect(self._update_table_view)
        self.controller.filters_loaded.connect(self._populate_filters)
        self.controller.fetch_status_update.connect(self._update_fetch_progress)
        self.controller.fetch_analysis_result.connect(self._cache_analysis_result)
        self.controller.fetch_process_finished.connect(self._handle_fetch_finished)
        self.controller.error_occurred.connect(self._show_error_message)

    # --- Internal Trigger Methods (Called by UI Signals) ---
    def _trigger_fetch_news(self):
        """Gathers selected sources from UI and initiates fetch via controller."""
        # Determine selected sources based on filters
        selected_sources = (
            self._get_selected_source_info_for_fetch()
        )  # Keep this helper in View
        if not selected_sources:
            QMessageBox.information(
                self, "Notice", "No sources selected/found for fetch."
            )
            return

        if self.fetch_progress_dialog is None:
            self.fetch_progress_dialog = FetchProgressDialog(selected_sources, self)
            # Connect the dialog's request signal to the handler
            self.fetch_progress_dialog.view_llm_output_requested.connect(
                self._show_llm_stream_dialog
            )
        else:
            # Update the table in the existing dialog
            self.fetch_progress_dialog.populate_table(selected_sources)

        self.fetch_progress_dialog.setWindowTitle("News Fetch Progress")
        self.fetch_progress_dialog.show()
        self.fetch_progress_dialog.raise_()

        # Update UI state
        self.fetch_button.setEnabled(False)
        self.cancel_fetch_button.setEnabled(True)

        # Call controller to start fetch
        self.controller.start_fetch(selected_sources)

    def _trigger_cancel_fetch(self):
        """Triggers the cancellation of the ongoing fetch operation."""
        self.cancel_fetch_button.setEnabled(False)
        self.controller.cancel_fetch()

    def _trigger_filter_apply(self):
        """Gathers filter values and tells controller to apply them."""
        category_id = (
            self.category_filter.currentData()
            if self.category_filter.currentIndex() >= 0
            else -1
        )
        source_name = (
            self.source_filter.currentData()
            if self.source_filter.currentIndex() >= 0
            else "All"
        )
        # Ensure source_name is used correctly if data is name itself
        if isinstance(source_name, int) and source_name == -1:
            source_name = "All"  # Correct if itemData was -1

        search_text = self.search_input.text().strip()
        self.controller.apply_filters(category_id, source_name, search_text)

    def _handle_category_change(self):
        """处理分类选择改变，更新对应的数据源过滤列表"""
        category_id = self.category_filter.currentData()
        
        # 获取当前选中的分类对应的所有新闻源
        source_names = self.controller.get_source_names_by_category(category_id)
        
        # 更新新闻源下拉框
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("All", "All")
        for name in source_names:
            self.source_filter.addItem(name, name)
        self.source_filter.setCurrentIndex(0)  # 默认选中"All"
        self.source_filter.blockSignals(False)
        
        # 应用过滤器更新表格
        self._trigger_filter_apply()

    def _trigger_selection_changed(self):
        """Handles selection change in the table to update the preview."""
        indexes = self.news_table.selectionModel().selectedRows()
        if not indexes:
            self.preview_text.clear()
            return

        proxy_index = indexes[
            0
        ]  # Get the first selected row's index in the proxy model
        if not proxy_index.isValid():
            self.preview_text.clear()
            return

        # Ask controller for details based on proxy index
        news_details = self.controller.get_news_details(proxy_index)

        if news_details:
            preview_html = f"<h3>{news_details.get('title', 'N/A')}</h3>"
            preview_html += f"<p>{news_details.get('source_name', '')} {news_details.get('date', '')}<br>"
            link = news_details.get("link", "#")
            preview_html += f"<a href='{link}'>{link}</a></p><hr>"  # Added HR
            # Display summary first, then analysis if available
            summary = news_details.get("summary", "")
            analysis = news_details.get(
                "analysis", ""
            )  # Assuming controller gets this too

            if summary:
                preview_html += f"<h4>Summary:</h4><p>{summary.replace(chr(10), '<br>')}</p>"  # Use chr(10) for newline
            if analysis:
                preview_html += (
                    f"<h4>Analysis:</h4><p>{analysis.replace(chr(10), '<br>')}</p>"
                )

            self.preview_text.setHtml(preview_html)
        else:
            # Controller might emit an error signal, or return None
            self.preview_text.setText("Unable to load preview data for selected item.")

    def _trigger_delete_news(self):
        """Handles the delete action from the context menu."""
        selected_proxy_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Notice", "Please select news items to delete.")
            return

        count = len(selected_proxy_indexes)
        confirm_msg = f"Are you sure you want to delete {count} selected news item(s)?"
        # Get title for single item confirmation (optional, needs controller method)
        # if count == 1:
        #    details = self.controller.get_news_details(selected_proxy_indexes[0])
        #    if details: confirm_msg = f"Are you sure you want to delete '{details.get('title', 'this item')}'?"

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.controller.delete_selected_news(selected_proxy_indexes)

    # --- View Update Slots (Called by Controller Signals) ---
    @Slot()
    def _update_table_view(self):
        """Refreshes the table view appearance after model updates."""
        logger.debug("NewsTab: Received news_data_updated signal. Resizing columns.")
        # Model data is already updated by the controller calling model.select()
        # We just need to resize columns etc.
        self.news_table.resizeColumnsToContents()
        self.news_table.horizontalHeader().setStretchLastSection(True)
        # self.news_data_changed.emit() # May not be needed

    @Slot(list, list)
    def _populate_filters(
        self, categories: List[Tuple[int, str]], source_names: List[str]
    ):
        """Populates the category and source filter dropdowns."""
        logger.debug(
            f"Populating filters. Categories: {len(categories)}, Sources: {len(source_names)}"
        )

        # --- Category Filter ---
        current_category_id = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All", -1)
        restored_cat_index = 0
        for i, (cat_id, cat_name) in enumerate(categories):
            self.category_filter.addItem(cat_name, cat_id)
            if cat_id == current_category_id:
                restored_cat_index = i + 1
        self.category_filter.setCurrentIndex(restored_cat_index)
        self.category_filter.blockSignals(False)

        # --- Source Filter ---
        # 初始加载时，使用所有来源填充source_filter
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("All", "All")
        for name in source_names:
            self.source_filter.addItem(name, name)
        self.source_filter.setCurrentIndex(0)  # 默认选择"All"
        self.source_filter.blockSignals(False)

        # 初始过滤器应用
        self._trigger_filter_apply()

    @Slot(str, str, bool)
    def _update_fetch_progress(self, url: str, status: str, is_final: bool):
        """Updates the FetchProgressDialog."""
        if self.fetch_progress_dialog and self.fetch_progress_dialog.isVisible():
            # Use invokeMethod to ensure thread safety when calling dialog method
            QMetaObject.invokeMethod(
                self.fetch_progress_dialog,
                "update_status",
                Qt.ConnectionType.QueuedConnection,  # Ensure it runs on the dialog's thread
                Q_ARG(str, url),
                Q_ARG(str, status),
                Q_ARG(bool, is_final),
            )
        else:
            logger.debug(
                f"Progress dialog not visible, ignoring status update for {url}: {status}"
            )

    @Slot(str, str)
    def _cache_analysis_result(self, url: str, analysis_result: str):
        """Stores the received analysis result locally."""
        self._cached_analysis_results[url] = analysis_result
        # Update dialog if it's currently showing this URL
        if url in self.llm_stream_dialogs and self.llm_stream_dialogs[url].isVisible():
            self.llm_stream_dialogs[url].set_content(analysis_result)

    @Slot(str)
    def _handle_fetch_finished(self, final_message: str):
        """Handles the end of the fetch process."""
        logger.info(f"NewsTab received fetch finished signal: {final_message}")
        self.fetch_button.setEnabled(True)
        self.cancel_fetch_button.setEnabled(False)

        if self.fetch_progress_dialog:
            # Update dialog title, keep it open for review
            self.fetch_progress_dialog.setWindowTitle(f"News Fetch - {final_message}")

        # Trigger a refresh of news list implicitly by controller
        self.controller.refresh_news() # Controller should do this

    @Slot(str, str)
    def _show_error_message(self, title: str, message: str):
        """Displays an error message box."""
        logger.warning(f"Displaying error: Title='{title}', Message='{message}'")
        # Map common errors to message box types
        if "Busy" in title or "Busy" in message:
            QMessageBox.warning(self, title, message)
        elif "Error" in title:
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    # --- Context Menu ---
    def _show_context_menu(self, pos):
        """Shows the right-click context menu for the news table."""
        menu = QMenu(self)
        selected_indexes = self.news_table.selectionModel().selectedRows()
        has_selection = bool(selected_indexes)
        is_single_selection = len(selected_indexes) == 1

        # Refresh Action
        act_refresh = menu.addAction("Refresh List")
        act_refresh.triggered.connect(
            self.controller.refresh_news
        )  # Directly call controller

        # View Analysis Action
        act_analyze = menu.addAction("View Analysis")
        act_analyze.setEnabled(is_single_selection)  # Enable only for single selection
        if is_single_selection:
            act_analyze.triggered.connect(
                lambda: self._show_analysis_for_selected(selected_indexes[0])
            )

        menu.addSeparator()

        # Delete Action
        act_delete = menu.addAction("Delete Selected")
        act_delete.setEnabled(has_selection)
        act_delete.triggered.connect(
            self._trigger_delete_news
        )  # Calls internal trigger

        # Edit Action (Placeholder)
        act_edit = menu.addAction("Edit Selected")
        act_edit.setEnabled(is_single_selection)  # Only single edit makes sense
        act_edit.triggered.connect(
            lambda: self._show_error_message(
                "Not Implemented", "Edit functionality is not yet available."
            )
        )

        menu.exec(self.news_table.viewport().mapToGlobal(pos))

    def _show_analysis_for_selected(self, proxy_index: QModelIndex):
        """
        处理右键菜单 "View Analysis" 的点击事件。
        打开一个新的对话框显示详情，并在需要时触发 LLM 分析。
        """
        if not self.controller.proxy_model or not self.controller.news_model or not proxy_index.isValid():
            logger.warning("无法显示分析：模型或索引无效。")
            self._show_error_message("错误", "无法获取所选项目的数据。")
            return

        # --- 从模型获取所需要的数据 ---
        source_index = self.controller.proxy_model.mapToSource(proxy_index)
        news_details = self.controller.get_news_details(proxy_index)
        
        if not news_details:
            self._show_error_message("错误", "无法获取新闻详情。")
            return
            
        news_id = news_details.get("id")
        title = news_details.get("title", "")
        link = news_details.get("link", "")
        date = news_details.get("date", "")
        summary = news_details.get("summary", "")
        source_name = news_details.get("source_name", "")
        existing_analysis = news_details.get("analysis", "")
        content = news_details.get("content", "")

        # --- 创建并显示 AnalysisDetailDialog ---
        try:
            # 检查是否已有此对话框实例 (希望每个分析只打开一个窗口)
            dialog_key = f"analysis_{news_id}" # 使用 news_id 作为唯一标识符
            if dialog_key in self.llm_stream_dialogs and self.llm_stream_dialogs[dialog_key].isVisible():
                 existing_dialog = self.llm_stream_dialogs[dialog_key]
                 existing_dialog.raise_()
                 existing_dialog.activateWindow()
                 logger.debug(f"Analysis dialog for ID {news_id} already open.")
                 return # 不重复打开


            logger.info(f"为新闻 ID {news_id} 打开分析详情对话框。")
            analysis_dialog = AnalysisDetailDialog(
                news_id=news_id,
                controller=self.controller, # 将控制器传递给对话框，用于连接信号
                parent=self # 设置父窗口
            )
            self.llm_stream_dialogs[dialog_key] = analysis_dialog # 跟踪打开的对话框
            analysis_dialog.finished.connect(lambda result, key=dialog_key: self._analysis_dialog_closed(key))


            analysis_dialog.set_details(title, link, date, summary, source_name)

            if existing_analysis and existing_analysis.strip():
                logger.debug(f"新闻 ID {news_id} 已有分析结果，直接显示。")
                analysis_dialog.set_analysis_content(existing_analysis) # 假设对话框有此方法
            else:
                logger.debug(f"新闻 ID {news_id} 无分析结果，将触发 LLM 分析。")
                analysis_dialog.set_analysis_content("⏳ 正在生成分析，请稍候...") # 初始提示
                if not content or not content.strip():
                     logger.warning(f"无法为新闻 ID {news_id} 生成分析，因为原文内容为空。")
                     analysis_dialog.set_analysis_content("❌ 无法生成分析：原文内容缺失。")
                else:
                    # --- 调用 Controller 触发 LLM 分析 ---
                    # 这个调用应该是异步的，Controller 内部会处理线程/异步任务
                    # 对话框 AnalysisDetailDialog 内部需要连接 Controller 发出的流式信号
                    self.controller.trigger_single_item_analysis(news_id, content)

            analysis_dialog.show()

        except Exception as e:
            logger.error(f"创建或显示分析对话框时出错: {e}", exc_info=True)
            self._show_error_message("界面错误", f"无法打开分析窗口: {e}")

    # --- 新增: 对话框关闭处理 ---
    @Slot(str) # 参数是之前设置的 dialog_key
    def _analysis_dialog_closed(self, dialog_key: str):
        """当分析详情对话框关闭时，从跟踪字典中移除它。"""
        if dialog_key in self.llm_stream_dialogs:
            logger.debug(f"Analysis detail dialog for key '{dialog_key}' closed.")
            del self.llm_stream_dialogs[dialog_key]
        else:
            logger.warning(f"Attempted to remove non-tracked dialog key: {dialog_key}")

    # --- Dialog Management ---
    def _show_llm_stream_dialog(self, url: str):
        """Creates or shows the LLM result dialog for the given URL."""
        dialog_title = "LLM Analysis Output"
        source_name = "Unknown Source"  # Try to get from model if needed

        # Try to get source name from the model (might be slow if model is large)
        # This requires finding the row corresponding to the URL, which is inefficient here.
        # It's better if the controller provides name along with analysis if possible,
        # or we rely on the progress dialog's info if called from there.
        # For now, keep it simple or use placeholder.

        if url in self.llm_stream_dialogs:
            dialog = self.llm_stream_dialogs[url]
        else:
            dialog = LlmStreamDialog(title=dialog_title, parent=self)
            # Connect finished signal to cleanup slot
            dialog.finished.connect(lambda *args, u=url: self._llm_dialog_closed(u))
            self.llm_stream_dialogs[url] = dialog

        # Get cached result from internal cache (populated by controller signal)
        full_result = self._cached_analysis_results.get(url)
        placeholder_message = f"<p style='color: #555;'>LLM analysis result is loading or not available for this source...</p>"

        content_to_display = full_result if full_result else placeholder_message
        # Maybe enhance placeholder if status indicates error vs loading
        dialog.set_content(content_to_display)
        dialog.set_window_title(f"LLM Analysis - {url[:50]}...")  # Use URL in title

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _llm_dialog_closed(self, url: str):
        """Slot called when an LLM stream dialog is closed."""
        if url in self.llm_stream_dialogs:
            logger.debug(f"LLM result dialog for {url} closed. Removing from tracking.")
            del self.llm_stream_dialogs[url]

    # --- Helpers ---
    def _get_selected_source_info_for_fetch(self) -> List[Dict[str, Any]]:
        """
        Determines which news sources to fetch based on UI filter selections.
        """
        selected_cat_id = self.category_filter.currentData()
        selected_src_name = self.source_filter.currentData()
        return self.controller.get_sources_matching_filters(
            selected_cat_id, selected_src_name
        )

    # --- Cleanup ---
    def perform_cleanup(self):
        """Ensure controller cleanup is called."""
        logger.info("NewsTab performing cleanup...")
        self._is_closing = True  # Set flag to prevent race conditions
        # Close any open dialogs managed by this tab
        if self.fetch_progress_dialog:
            try:
                self.fetch_progress_dialog.close()
            except Exception as e:
                logger.warning(f"Error closing progress dialog: {e}")
        for url, dialog in list(self.llm_stream_dialogs.items()):
            try:
                dialog.close()
            except Exception as e:
                logger.warning(f"Error closing LLM dialog for {url}: {e}")
        self.llm_stream_dialogs.clear()

        # Call controller's cleanup
        if self.controller:
            self.controller.cleanup()
        logger.info("NewsTab cleanup finished.")
        return True  # Indicate cleanup attempt was made
