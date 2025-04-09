#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
"""

import logging
import asyncio
# Add Callable for the callback type hint
from typing import List, Dict, Optional, Tuple, Any, Callable

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QComboBox,
    QLabel,
    QLineEdit,
    QSplitter,
    QTextEdit,
    QHeaderView,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, Slot, QThreadPool, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QStandardItemModel, QStandardItem

from src.services.news_service import NewsService
from src.ui.async_runner import AsyncTaskRunner
# Import the NEW popup class
from src.ui.fetch_status_popup import FetchStatusPopup

logger = logging.getLogger(__name__)


class NewsTab(QWidget):
    """News Management Tab"""

    news_data_changed = Signal()

    def __init__(self, news_service: NewsService):
        super().__init__()
        self._news_service = news_service
        self.news_data: Dict[int, Dict[str, Any]] = {}
        self.categories_cache: List[Tuple[int, str]] = []
        self.sources_cache: List[Dict[str, Any]] = []
        self._is_fetching = False
        # Use the new popup class
        self.fetch_status_popup: Optional[FetchStatusPopup] = None
        self._setup_ui()
        self._load_filters()
        self._load_news()

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()
        main_layout.addLayout(toolbar_layout)

        self.fetch_button = QPushButton("Fetch News")
        self.fetch_button.setToolTip("Start fetching news from selected sources.\nClick again while fetching to view progress.")
        self.fetch_button.clicked.connect(self._fetch_news_handler)
        toolbar_layout.addWidget(self.fetch_button)

        # This button now shows the new status popup
        self.show_status_button = QPushButton("Show Fetch Status")
        self.show_status_button.clicked.connect(self._show_fetch_progress_window)
        self.show_status_button.setEnabled(False) # Disable initially
        self.show_status_button.setToolTip("Shows the status window from the last/current fetch operation.")
        toolbar_layout.addWidget(self.show_status_button)

        # Rest of the toolbar remains the same...
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
        self._setup_table_model()
        splitter.addWidget(self.news_table)

        # Setup Preview Area
        preview_widget = QWidget() # Container for preview elements
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel("Preview/Content:"))
        self.preview_text = QTextEdit() # Initialize self.preview_text here
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        splitter.addWidget(preview_widget)

        # Set initial sizes for splitter panes
        splitter.setSizes([600, 200])

        # --- Bottom Toolbar ---
        bottom_toolbar = QHBoxLayout()
        main_layout.addLayout(bottom_toolbar)

        self.refresh_button = QPushButton("Refresh List")
        self.refresh_button.clicked.connect(self._refresh_all)
        bottom_toolbar.addWidget(self.refresh_button)

        bottom_toolbar.addStretch(1)

        self.analyze_button = QPushButton("Analyze Selected")
        self.analyze_button.setToolTip("Run LLM analysis on the selected news item(s).")
        # self.analyze_button.clicked.connect(self._analyze_selected_news) # Connect later
        self.analyze_button.setEnabled(False)
        bottom_toolbar.addWidget(self.analyze_button)

        self.edit_button = QPushButton("Edit") # Keep Edit button, maybe disable
        self.edit_button.setToolTip("Edit the selected news item (Not Implemented).")
        # self.edit_button.clicked.connect(self._edit_news) # Connect later if needed
        self.edit_button.setEnabled(False) # Disable edit for now
        bottom_toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setToolTip("Delete the selected news item(s).")
        # self.delete_button.clicked.connect(self._delete_selected_news) # Connect later
        self.delete_button.setEnabled(False)
        bottom_toolbar.addWidget(self.delete_button)

        # --- Connect Signals --- 
        self.category_filter.currentIndexChanged.connect(self._on_category_filter_changed)
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(self._on_selection_changed)


    # --- Methods ---

    # _setup_table_model, _refresh_all, _load_news, _load_filters,
    # _on_category_filter_changed, _update_source_filter remain the same
    # ... (paste existing implementations here) ...
    def _setup_table_model(self):
        """Sets up the QStandardItemModel and QSortFilterProxyModel."""
        self.model = QStandardItemModel(0, 5, self)  # 5 columns
        self.model.setHorizontalHeaderLabels(
            ["Title", "Source", "Category", "Published Date", "Analyzed"]
        )
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.news_table.setModel(self.proxy_model)

    def _refresh_all(self):
        """Refreshes both filters and news list."""
        if self._is_fetching:
            QMessageBox.warning(self, "正在获取", "正在获取资讯，请稍后再刷新。")
            return
        logger.info("Refreshing filters and news list...")
        self._load_filters()
        self._load_news()

    def _load_news(self):
        """Loads news from the service into the table model."""
        logger.info("Loading news data...")
        try:
            self.model.removeRows(0, self.model.rowCount())
            self.news_data.clear()
            self.preview_text.clear()
            news_list = self._news_service.get_all_news(limit=1000)
            logger.info(f"Retrieved {len(news_list)} news items from service.")
            for news in news_list:
                news_id = news.get("id")
                if news_id is None: continue
                self.news_data[news_id] = news
                title_item = QStandardItem(news.get("title", "N/A"))
                source_item = QStandardItem(news.get("source_name", "N/A"))
                category_item = QStandardItem(news.get("category_name", "N/A"))
                date_item = QStandardItem(news.get("published_date", "N/A"))
                analyzed_item = QStandardItem("Yes" if news.get("analyzed") else "No")
                title_item.setData(news_id, Qt.ItemDataRole.UserRole)
                for item in [title_item, source_item, category_item, date_item, analyzed_item]:
                    item.setEditable(False)
                self.model.appendRow([title_item, source_item, category_item, date_item, analyzed_item])
            self._apply_filters()
            logger.info(f"Populated table with {self.model.rowCount()} news items.")
            self.news_data_changed.emit()
        except Exception as e:
            logger.error(f"Failed to load news: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load news list: {str(e)}")

    def _load_filters(self):
        """Load filter options"""
        logger.info("Loading filters...")
        try:
            current_category_id = self.category_filter.currentData()
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem("All", -1)
            self.categories_cache = self._news_service.get_all_categories()
            restored_cat_index = 0
            for i, (cat_id, cat_name) in enumerate(self.categories_cache):
                self.category_filter.addItem(cat_name, cat_id)
                if cat_id == current_category_id: restored_cat_index = i + 1
            self.category_filter.setCurrentIndex(restored_cat_index)
            self.category_filter.blockSignals(False)
            logger.info(f"Loaded {len(self.categories_cache)} categories.")
            self._on_category_filter_changed(restored_cat_index)
        except Exception as e:
            logger.error(f"Failed to load filters: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to load filter options: {str(e)}")
        finally:
            self.category_filter.blockSignals(False)

    def _on_category_filter_changed(self, index):
        """Handle category filter change"""
        if self._is_fetching: return
        category_id = self.category_filter.itemData(index)
        self._update_source_filter(category_id)
        self._apply_filters()

    def _update_source_filter(self, category_id: int):
        """Update source filter options"""
        logger.debug(f"Updating source filter for category ID: {category_id}")
        try:
            current_source_text = self.source_filter.currentText()
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All", -1)
            if category_id == -1:
                self.sources_cache = self._news_service.get_all_sources()
                sources_to_add = sorted(list(set(s["name"] for s in self.sources_cache)))
            else:
                self.sources_cache = self._news_service.get_sources_by_category_id(category_id)
                sources_to_add = sorted(s["name"] for s in self.sources_cache)
            self.source_filter.addItems(sources_to_add)
            restored_src_index = self.source_filter.findText(current_source_text)
            self.source_filter.setCurrentIndex(restored_src_index if restored_src_index != -1 else 0)
            self.source_filter.blockSignals(False)
            logger.debug(f"Source filter updated with {self.source_filter.count() - 1} sources.")
        except Exception as e:
            logger.error(f"Failed to update source filter: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to update source filter: {str(e)}")
        finally:
            self.source_filter.blockSignals(False)


    def _fetch_news_handler(self):
        """Handles clicks on the Fetch News button."""
        if self._is_fetching:
            logger.debug("Fetch button clicked while fetching: showing status window.")
            self._show_fetch_progress_window()
        else:
            logger.debug("Fetch button clicked: starting fetch process.")
            self._start_fetch_news()

    def _start_fetch_news(self):
        """Starts the actual news fetching process."""
        try:
            source_ids_to_fetch = self._get_selected_source_ids_for_fetch()
            urls_to_fetch = self._get_selected_urls_for_fetch(source_ids_to_fetch) # Get URLs for popup

            if not urls_to_fetch:
                 QMessageBox.information(
                    self, "Notice", "No active news sources found based on current filters."
                 )
                 return

            logger.info(
                f"Starting fetch for {len(urls_to_fetch)} URLs (Source IDs: {source_ids_to_fetch if source_ids_to_fetch else 'All Active'})"
            )

            self._is_fetching = True
            self.fetch_button.setEnabled(False)
            self.fetch_button.setText("Fetching...")

            # --- Use the new FetchStatusPopup ---
            if self.fetch_status_popup is None:
                logger.info("Creating new FetchStatusPopup instance.")
                self.fetch_status_popup = FetchStatusPopup(self)
            else:
                logger.info("Reusing existing FetchStatusPopup instance.")

            # Initialize the popup with URLs (but don't show yet)
            self.fetch_status_popup.initialize_urls(urls_to_fetch)
            self.show_status_button.setEnabled(True)
            # --- End Popup Handling ---

            fetch_coro = self._news_service.fetch_news_from_sources
            fetch_args = ()
            fetch_kwargs = {
                "source_ids": source_ids_to_fetch,
                # Pass the new status update callback
                "on_url_status_update": self._handle_url_status_update,
            }

            self.fetch_runner = AsyncTaskRunner(fetch_coro, *fetch_args, **fetch_kwargs)
            self.fetch_runner.setAutoDelete(True)
            self.fetch_runner.signals.finished.connect(self._on_fetch_runner_finished)
            self.fetch_runner.signals.error.connect(self._on_fetch_error)

            QThreadPool.globalInstance().start(self.fetch_runner)
            logger.info("Fetch task started in background. Status popup is hidden.")

        except Exception as e:
            logger.error(f"Failed to initiate news fetch: {e}", exc_info=True)
            self._is_fetching = False
            self.fetch_button.setEnabled(True)
            self.fetch_button.setText("Fetch News")
            if self.fetch_status_popup:
                 self.fetch_status_popup.set_final_status(f"Error initiating fetch: {e}", is_error=True)
            QMessageBox.critical(self, "Error", f"Failed to initiate news fetch: {str(e)}")

    def _get_selected_source_ids_for_fetch(self) -> Optional[List[int]]:
        """Helper to determine which source IDs to fetch based on filters."""
        # (Implementation remains the same as before)
        source_ids_to_fetch: Optional[List[int]] = None
        selected_category_id = self.category_filter.currentData()
        selected_source_name = self.source_filter.currentText()
        if not self.sources_cache: self._load_sources_and_categories()
        all_sources = self.sources_cache
        if selected_category_id != -1:
             filtered_by_cat = [s for s in all_sources if s["category_id"] == selected_category_id]
             if selected_source_name != "All":
                 source_ids_to_fetch = [s["id"] for s in filtered_by_cat if s["name"] == selected_source_name]
             else:
                 source_ids_to_fetch = [s["id"] for s in filtered_by_cat]
        elif selected_source_name != "All":
             source_ids_to_fetch = [s["id"] for s in all_sources if s["name"] == selected_source_name]
        return source_ids_to_fetch

    def _get_selected_urls_for_fetch(self, source_ids: Optional[List[int]]) -> List[str]:
        """Helper to get the actual URLs based on selected source IDs."""
        if not self.sources_cache: self._load_sources_and_categories()
        all_sources = self.sources_cache

        if source_ids is None: # Fetch all
             return [s['url'] for s in all_sources if s.get('url')]
        else: # Fetch specific IDs
            urls = []
            source_map = {s['id']: s['url'] for s in all_sources if s.get('url')}
            for sid in source_ids:
                 if sid in source_map:
                      urls.append(source_map[sid])
            return urls


    @Slot()
    def _show_fetch_progress_window(self):
        """Shows the fetch status popup window."""
        if self.fetch_status_popup and isinstance(self.fetch_status_popup, FetchStatusPopup):
            logger.debug("Showing fetch status popup.")
            self.fetch_status_popup.show()
            self.fetch_status_popup.raise_()
            self.fetch_status_popup.activateWindow()
        else:
            logger.info("Fetch status popup has not been created yet.")
            QMessageBox.information(self, "Info", "The fetch status window hasn't been created yet. Please start a news fetch first.")

    @Slot(str, str, str)
    def _handle_url_status_update(self, url: str, status: str, details: str):
        """Slot to receive URL status updates and update the popup."""
        # logger.debug(f"Status Update Received: URL={url}, Status={status}, Details={details}")
        if self.fetch_status_popup:
            # Let the popup handle thread safety via its invokeMethod call
            self.fetch_status_popup.update_url_status(url, status, details)
        else:
             logger.warning("Received URL status update but fetch status popup does not exist.")

    @Slot(object)
    def _on_fetch_runner_finished(self, result):
        """Callback for async fetch completion."""
        logger.info(f"Fetch runner finished with result: {result}")
        QMessageBox.information(self, "Fetch Complete", f"Fetch process completed. Total items saved: {result}.")

        self._is_fetching = False
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch News")
        if self.fetch_status_popup:
             self.fetch_status_popup.set_final_status(f"Fetch Complete ({result} total items saved)")

        # Keep show_status_button enabled

        self._load_news()

    @Slot(Exception)
    def _on_fetch_error(self, error):
        """Callback for async fetch error."""
        logger.error(f"News fetch task failed: {error}", exc_info=error)
        QMessageBox.critical(self, "Fetch Error", f"Error occurred during news fetch:\n{str(error)}")

        self._is_fetching = False
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch News")
        if self.fetch_status_popup:
             self.fetch_status_popup.set_final_status(f"Fetch Error: {error}", is_error=True)

        # Keep show_status_button enabled

    # _delete_news, _edit_news, _send_to_analysis, _export_news,
    # _on_selection_changed, _apply_filters remain the same
    # ... (paste existing implementations here) ...
    def _delete_news(self):
        """Delete news"""
        if self._is_fetching:
            QMessageBox.warning(self, "正在获取", "正在获取资讯，请稍后再操作。")
            return
        selected_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "Notice", "Please select news to delete first.")
            return
        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        news_title = self.model.item(source_index.row(), 0).text()
        if news_id is None:
            QMessageBox.critical(self, "Error", "Cannot get ID of selected news.")
            return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete '{news_title}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._news_service.delete_news(news_id):
                    logger.info(f"Deleted news ID: {news_id}")
                    QMessageBox.information(self, "Success", "News deleted.")
                    self._load_news()
                    self._load_filters()
                else:
                    logger.error(f"Service failed deleting news ID: {news_id}")
                    QMessageBox.warning(self, "Failed", "Failed to delete news.")
            except Exception as e:
                logger.error(f"Error calling delete_news: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Error deleting news: {str(e)}")

    def _edit_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Edit not implemented.")

    def _send_to_analysis(self):
        if self._is_fetching: return
        selected_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "Notice", "Select news to analyze first.")
            return
        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        news_title = self.model.item(source_index.row(), 0).text()
        if news_id is not None:
            try:
                main_window = self.window()
                if hasattr(main_window, "analysis_tab") and main_window.analysis_tab:
                    main_window.analysis_tab.load_news_for_analysis(news_id)
                    if hasattr(main_window, "tabs"):
                        main_window.tabs.setCurrentWidget(main_window.analysis_tab)
                    QMessageBox.information(self, "Notice", f"'{news_title}' sent to Analysis.")
                else:
                    QMessageBox.warning(self, "Error", "Cannot access Analysis tab.")
            except Exception as e:
                logger.error(f"Error sending to analysis: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to send: {e}")
        else:
            QMessageBox.warning(self, "Error", "Cannot get ID.")

    def _export_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Export not implemented.")

    def _on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        enable_buttons = bool(indexes)
        self.delete_button.setEnabled(enable_buttons)
        self.analyze_button.setEnabled(enable_buttons)
        # self.edit_button.setEnabled(enable_buttons) # Keep disabled

        if not indexes:
            self.preview_text.clear()
            return

        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if news_id is not None and news_id in self.news_data:
            news = self.news_data[news_id]
            preview_html = f"<h3>{news.get('title', 'N/A')}</h3>"
            # ... (rest of the HTML formatting) ...
            preview_html += f"<p><b>Source:</b> {news.get('source_name', 'N/A')}<br>"
            preview_html += f"<b>Category:</b> {news.get('category_name', 'N/A')}<br>"
            date_str = news.get("published_date") or news.get("date") or news.get("fetched_date", "")
            preview_html += f"<b>Date:</b> {date_str[:19] if date_str else 'N/A'}<br>"
            link = news.get("link", "#")
            preview_html += f"<b>Link:</b> <a href='{link}'>{link}</a><br>"
            preview_html += f"<b>Analyzed:</b> {'Yes' if news.get('analyzed') else 'No'}</p><hr>"
            preview_html += f"<b>Summary:</b><p>{news.get('summary', 'No summary')}</p>"
            llm_analysis = news.get("llm_analysis")
            if llm_analysis:
                preview_html += f"<hr><p><b>AI Analysis:</b></p><p>{llm_analysis}</p>"
            self.preview_text.setHtml(preview_html)
        else:
            self.preview_text.setText(f"Cannot load preview (ID: {news_id})")
            self.delete_button.setEnabled(False)
            self.analyze_button.setEnabled(False)

    def _apply_filters(self):
        """Apply filters"""
        search_text = self.search_input.text().strip()
        selected_category_text = self.category_filter.currentText()
        selected_source_text = self.source_filter.currentText()
        self.proxy_model.setFilterRegularExpression("")
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterFixedString(search_text)
        source_model = self.proxy_model.sourceModel()
        if not source_model: return
        for row in range(source_model.rowCount()):
            category_matches = True
            source_matches = True
            text_match = True
            cat_item = source_model.item(row, 2)
            if cat_item and selected_category_text != "All":
                category_matches = cat_item.text() == selected_category_text
            src_item = source_model.item(row, 1)
            if src_item and selected_source_text != "All":
                source_matches = src_item.text() == selected_source_text
            source_index = source_model.index(row, 0)
            proxy_index = self.proxy_model.mapFromSource(source_index)
            text_match = proxy_index.isValid()
            self.news_table.setRowHidden(row, not (text_match and category_matches and source_matches))
        logger.debug(f"Applied filters: Cat='{selected_category_text}', Src='{selected_source_text}', Search='{search_text}'")