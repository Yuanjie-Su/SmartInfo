# src/ui/tabs/news_tab.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
"""

import datetime
import logging
import asyncio # <--- Import asyncio
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
# QThreadPool is no longer needed here
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, Slot, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QStandardItemModel, QStandardItem

from src.services.news_service import NewsService
from src.ui.task_log_viewer import TaskLogViewer

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
        self.fetch_task: Optional[asyncio.Task] = None
        self.task_status_popup: Optional[TaskLogViewer] = None
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
        # Update tooltip for cancellation behavior
        self.fetch_button.setToolTip("Start fetching news. Click again while fetching to attempt cancellation.")
        self.fetch_button.clicked.connect(self._fetch_news_handler)
        toolbar_layout.addWidget(self.fetch_button)

        self.show_status_button = QPushButton("Show Task Status")
        self.show_status_button.clicked.connect(self._show_task_progress_window)
        self.show_status_button.setEnabled(False)
        self.show_status_button.setToolTip("Shows the status window from the last/current task (fetch).")
        toolbar_layout.addWidget(self.show_status_button)

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
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel("Preview/Content:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        splitter.addWidget(preview_widget)

        splitter.setSizes([600, 200])

        # --- Bottom Toolbar ---
        bottom_toolbar = QHBoxLayout()
        main_layout.addLayout(bottom_toolbar)

        self.refresh_button = QPushButton("Refresh List")
        self.refresh_button.clicked.connect(self._refresh_all)
        bottom_toolbar.addWidget(self.refresh_button)

        bottom_toolbar.addStretch(1)

        # Analyze button removed or permanently disabled
        # self.analyze_button = QPushButton("Analyze Selected")
        # self.analyze_button.setEnabled(False)
        # bottom_toolbar.addWidget(self.analyze_button)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setToolTip("Edit the selected news item (Not Implemented).")
        self.edit_button.setEnabled(False)
        bottom_toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setToolTip("Delete the selected news item(s).")
        self.delete_button.clicked.connect(self._delete_news)
        self.delete_button.setEnabled(False)
        bottom_toolbar.addWidget(self.delete_button)

        # --- Connect Signals ---
        self.category_filter.currentIndexChanged.connect(self._on_category_filter_changed)
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(self._on_selection_changed)


    # --- Methods ---

    def _setup_table_model(self):
        """Sets up the QStandardItemModel and QSortFilterProxyModel."""
        self.model = QStandardItemModel(0, 4, self) # Columns: Title, Source, Category, Date
        self.model.setHorizontalHeaderLabels(
            ["Title", "Source", "Category", "Published Date"]
        )
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1) # Search all columns
        self.news_table.setModel(self.proxy_model)

    def _refresh_all(self):
        """Refreshes both filters and news list."""
        if self._is_fetching:
            QMessageBox.warning(self, "Busy", "A fetch task is currently running. Please wait or cancel.")
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
            news_list = self._news_service.get_all_news(limit=1000) # Consider pagination later
            logger.info(f"Retrieved {len(news_list)} news items from service.")
            for news in news_list:
                news_id = news.get("id")
                if news_id is None: continue
                self.news_data[news_id] = news # Cache for preview

                title_item = QStandardItem(news.get("title", "N/A"))
                source_item = QStandardItem(news.get("source_name", "N/A"))
                category_item = QStandardItem(news.get("category_name", "N/A"))
                date_str = news.get("date", "")
                display_date = date_str[:16] if date_str else "N/A" # Basic display formatting
                date_item = QStandardItem(display_date)

                title_item.setData(news_id, Qt.ItemDataRole.UserRole)

                for item in [title_item, source_item, category_item, date_item]:
                    item.setEditable(False)

                self.model.appendRow([title_item, source_item, category_item, date_item])

            self._apply_filters()
            self.news_table.resizeColumnsToContents()
            self.news_table.horizontalHeader().setStretchLastSection(True)
            logger.info(f"Populated table with {self.proxy_model.rowCount()} visible news items.")
            self.news_data_changed.emit()
        except Exception as e:
            logger.error(f"Failed to load news: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load news list: {str(e)}")

    def _load_filters(self):
        """Load filter options"""
        logger.info("Loading filters...")
        try:
            # Category Filter
            current_category_id = self.category_filter.currentData()
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem("All", -1)
            self.categories_cache = self._news_service.get_all_categories()
            restored_cat_index = 0
            for i, (cat_id, cat_name) in enumerate(self.categories_cache):
                self.category_filter.addItem(cat_name, cat_id)
                if cat_id == current_category_id:
                     restored_cat_index = i + 1
            self.category_filter.setCurrentIndex(restored_cat_index)
            self.category_filter.blockSignals(False)
            logger.info(f"Loaded {len(self.categories_cache)} categories.")

            # Source Filter
            self._update_source_filter(self.category_filter.currentData())

        except Exception as e:
            logger.error(f"Failed to load filters: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to load filter options: {str(e)}")
        finally:
            self.category_filter.blockSignals(False)
            self.source_filter.blockSignals(False)

    def _on_category_filter_changed(self, index):
        """Handle category filter change"""
        if self._is_fetching: return
        category_id = self.category_filter.itemData(index)
        logger.debug(f"Category filter changed to index {index}, ID: {category_id}")
        self._update_source_filter(category_id)
        self._apply_filters()

    def _update_source_filter(self, category_id: int):
        """Update source filter options based on category ID"""
        logger.debug(f"Updating source filter for category ID: {category_id}")
        try:
            current_source_name = self.source_filter.currentText()
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All", -1)

            if category_id == -1:
                 self.sources_cache = self._news_service.get_all_sources()
                 sources_to_add = sorted(list(set(s["name"] for s in self.sources_cache if s.get("name"))))
            else:
                 self.sources_cache = self._news_service.get_sources_by_category_id(category_id)
                 sources_to_add = sorted(s["name"] for s in self.sources_cache if s.get("name"))

            for name in sources_to_add:
                 self.source_filter.addItem(name, name)

            restored_src_index = self.source_filter.findText(current_source_name)
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
            # Show status window (current behavior)
            self._show_task_progress_window()
        else:
            logger.debug("Fetch button clicked: starting fetch process.")
            self._start_fetch_news()

    def _start_fetch_news(self):
        """Starts the news fetching process using asyncio in the main event loop."""
        # --- Ensure no task is already running ---
        if self._is_fetching or (self.fetch_task and not self.fetch_task.done()):
             logger.warning("Fetch task requested while another is still running.")
             QMessageBox.warning(self, "Busy", "A fetch task is already in progress.")
             return

        try:
            source_ids_to_fetch = self._get_selected_source_ids_for_fetch()
            urls_to_fetch_count = len(self._get_selected_urls_for_fetch(source_ids_to_fetch))

            if urls_to_fetch_count == 0:
                 QMessageBox.information(
                    self, "Notice", "No active news sources found based on current filters."
                 )
                 return

            logger.info(
                f"Starting fetch task for Source IDs: {source_ids_to_fetch} ({urls_to_fetch_count} URLs)"
            )

            # --- Update UI State ---
            self._is_fetching = True
            self.fetch_button.setEnabled(False) # Disable button temporarily
            self.fetch_button.setText("Fetching...")

            # --- Setup TaskLogViewer ---
            if self.task_status_popup is None:
                logger.info("Creating new TaskLogViewer instance.")
                self.task_status_popup = TaskLogViewer(self) # Use new class name
                self.task_status_popup.show()
            else:
                logger.info("Reusing existing TaskLogViewer instance.")
            self.task_status_popup.clear_display()
            self.task_status_popup.append_log_message(f"Starting fetch for {urls_to_fetch_count} URLs...\n")
            self.show_status_button.setEnabled(True)

            # --- Prepare the coroutine ---
            # The callbacks will be called directly from the service now
            fetch_coro = self._news_service.fetch_news_from_sources(
                source_ids=source_ids_to_fetch,
                on_url_status_update=self._handle_url_status_update,
                on_stream_chunk_update=self._handle_stream_chunk_update,
            )

            # --- Create and run the asyncio task ---
            loop = asyncio.get_event_loop()
            self.fetch_task = loop.create_task(fetch_coro)

            # --- Add a callback for when the task is done ---
            self.fetch_task.add_done_callback(self._on_fetch_task_done)

            logger.info("Fetch task created and scheduled in asyncio event loop.")
            # self._show_task_progress_window() # Optional: Show popup automatically

        except Exception as e:
            logger.error(f"Failed to initiate news fetch: {e}", exc_info=True)
            self._reset_fetch_state() # Reset UI state
            if self.task_status_popup:
                 self.task_status_popup.set_final_status(f"Error initiating fetch: {e}", is_error=True)
                 self.task_status_popup.append_log_message(f"\n[CRITICAL] Failed to start: {e}")
            QMessageBox.critical(self, "Error", f"Failed to initiate news fetch: {str(e)}")

    def _reset_fetch_state(self):
        """Resets the UI elements related to fetching."""
        self._is_fetching = False
        self.fetch_task = None
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch News")
        # Keep show_status_button enabled so user can review last log

    def _on_fetch_task_done(self, task: asyncio.Task):
        """Callback executed when the asyncio fetch task finishes."""
        final_message = ""
        try:
            # Check if the task was cancelled
            if task.cancelled():
                final_message = "Fetch task was cancelled."
                logger.warning(final_message)
                if self.task_status_popup:
                    # Append cancellation message, don't change title drastically
                    self.task_status_popup.append_log_message(f"\n=== {final_message} ===")

            # Check if an exception occurred
            elif task.exception():
                error = task.exception()
                final_message = f"Task failed: {error}"
                logger.error(final_message, exc_info=error)
                if self.task_status_popup:
                    self.task_status_popup.set_final_status(f"Error: {error}", is_error=True)
                    self.task_status_popup.append_log_message(f"\n=== [ERROR] {final_message} ===")
                QMessageBox.critical(self, "Task Error", f"Error occurred during task:\n{str(error)}")

            # Task completed successfully
            else:
                result = task.result() # result is the total count of saved items
                final_message = f"Fetch task completed. Total new items saved: {result}."
                logger.info(final_message)
                if self.task_status_popup:
                    self.task_status_popup.set_final_status(f"Complete ({result} items saved)")
                    self.task_status_popup.append_log_message(f"\n=== {final_message} ===")
                QMessageBox.information(self, "Task Complete", final_message)
                self._load_news() # Refresh the news list only on success

        except Exception as e:
            # Catch errors within the callback itself
            logger.error(f"Error in _on_fetch_task_done callback: {e}", exc_info=True)
            if self.task_status_popup:
                 self.task_status_popup.set_final_status(f"Callback Error: {e}", is_error=True)
            QMessageBox.critical(self, "Callback Error", f"Error processing task result:\n{str(e)}")
        finally:
            # --- Reset UI state regardless of outcome ---
            self._reset_fetch_state()

    def _get_selected_source_ids_for_fetch(self) -> Optional[List[int]]:
        """Helper to determine which source IDs to fetch based on filters."""
        source_ids: Optional[List[int]] = None
        selected_category_id = self.category_filter.currentData()
        selected_source_name = self.source_filter.currentText()

        if not self.sources_cache:
             try:
                 self.sources_cache = self._news_service.get_all_sources()
                 logger.debug("Loaded sources cache for fetch selection.")
             except Exception as e:
                 logger.error(f"Failed to load sources cache for fetch: {e}")
                 return []

        all_sources = self.sources_cache
        if selected_category_id != -1:
            filtered_by_cat = [s for s in all_sources if s.get("category_id") == selected_category_id]
            if selected_source_name != "All":
                source_ids = [s["id"] for s in filtered_by_cat if s.get("name") == selected_source_name and s.get("id") is not None]
            else:
                source_ids = [s["id"] for s in filtered_by_cat if s.get("id") is not None]
        elif selected_source_name != "All":
            source_ids = [s["id"] for s in all_sources if s.get("name") == selected_source_name and s.get("id") is not None]
        else:
             source_ids = None # Let the service handle fetching all

        return source_ids


    def _get_selected_urls_for_fetch(self, source_ids: Optional[List[int]]) -> List[str]:
        """Helper to get the actual URLs based on selected source IDs."""
        if not self.sources_cache:
             try:
                 self.sources_cache = self._news_service.get_all_sources()
             except Exception as e:
                 logger.error(f"Failed to load sources cache for URL fetch: {e}")
                 return []

        all_sources = self.sources_cache
        if source_ids is None: # Fetch all
             return [s['url'] for s in all_sources if s.get('url')]
        else: # Fetch specific IDs
            urls = []
            source_map = {s['id']: s['url'] for s in all_sources if s.get('id') is not None and s.get('url')}
            for sid in source_ids:
                 if sid in source_map:
                      urls.append(source_map[sid])
            return urls


    @Slot()
    def _show_task_progress_window(self):
        """Shows the task status popup window."""
        if self.task_status_popup and isinstance(self.task_status_popup, TaskLogViewer): # Use new class name
            logger.debug("Showing task log viewer.")
            self.task_status_popup.show()
            self.task_status_popup.raise_()
            self.task_status_popup.activateWindow()
        else:
            logger.info("Task log viewer has not been created yet.")
            QMessageBox.information(self, "Info", "The task log viewer hasn't been created yet. Start a task first.")

    # Slot needed for signal connection, but now called directly by service
    # The @Slot decorator doesn't hurt, but isn't strictly necessary for direct calls
    @Slot(str, str, str)
    def _handle_url_status_update(self, url: str, status: str, details: str):
        """Handles URL status updates (called directly from async task)."""
        # Updates the TaskStatusPopup which handles thread safety internally if needed
        if self.task_status_popup:
            # Log high-level status changes to the text area
            # Escape potential HTML in details before appending
            safe_details = details.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self.task_status_popup.append_log_message(f"[{status}] {url} - {safe_details}\n")
        else:
             logger.warning("Received URL status update but task status popup does not exist.")

    # Slot needed for signal connection, but now called directly by service
    @Slot(str)
    def _handle_stream_chunk_update(self, chunk: str):
        """Handles LLM stream chunks (called directly from async task)."""
        # Updates the TaskStatusPopup which handles thread safety internally
        if self.task_status_popup:
            self.task_status_popup.append_log_message(chunk)
        else:
             logger.warning("Received stream chunk update but task status popup does not exist.")


    # _on_fetch_runner_finished and _on_fetch_error are now replaced by _on_fetch_task_done


    def _delete_news(self):
        """Delete selected news items."""
        if self._is_fetching:
            QMessageBox.warning(self, "Busy", "A fetch task is currently running. Please wait or cancel.")
            return

        selected_proxy_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Notice", "Please select news items to delete.")
            return

        news_to_delete: List[Tuple[int, str]] = []
        for proxy_index in selected_proxy_indexes:
             source_index = self.proxy_model.mapToSource(proxy_index)
             news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
             news_title = self.model.item(source_index.row(), 0).text()
             if news_id is not None:
                 news_to_delete.append((news_id, news_title))

        if not news_to_delete:
             QMessageBox.critical(self, "Error", "Could not retrieve IDs for selected news.")
             return

        confirm_msg = f"Are you sure you want to delete {len(news_to_delete)} selected news item(s)?"
        if len(news_to_delete) == 1:
            confirm_msg = f"Are you sure you want to delete '{news_to_delete[0][1]}'?"

        reply = QMessageBox.question(self, "Confirm Delete", confirm_msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0; errors = []
            for news_id, news_title in news_to_delete:
                try:
                    if self._news_service.delete_news(news_id):
                        logger.info(f"Deleted news ID: {news_id} ('{news_title}')")
                        deleted_count += 1
                    else:
                        errors.append(f"Failed deleting '{news_title}' (Service Error)")
                except Exception as e:
                    errors.append(f"Error deleting '{news_title}': {e}")

            if errors:
                 QMessageBox.warning(self, "Partial Success", f"Deleted {deleted_count} items.\nErrors occurred:\n- " + "\n- ".join(errors))
            elif deleted_count > 0:
                 QMessageBox.information(self, "Success", f"{deleted_count} news item(s) deleted.")
            else:
                 QMessageBox.warning(self, "No Action", "No news items were deleted.")

            if deleted_count > 0:
                 self._load_news() # Refresh list

    def _edit_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Edit functionality is not implemented.")

    def _export_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Export functionality is not implemented.")

    def _on_selection_changed(self, selected, deselected):
        """Update preview and button states based on selection."""
        indexes = self.news_table.selectionModel().selectedRows()
        enable_buttons = bool(indexes)
        self.delete_button.setEnabled(enable_buttons)
        self.edit_button.setEnabled(False) # Keep edit disabled

        if not indexes:
            self.preview_text.clear(); return

        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)

        if news_id is not None and news_id in self.news_data:
            news = self.news_data[news_id]
            preview_html = f"<h3>{news.get('title', 'N/A')}</h3>"
            preview_html += f"<p><b>Source:</b> {news.get('source_name', 'N/A')}<br>"
            preview_html += f"<b>Category:</b> {news.get('category_name', 'N/A')}<br>"
            date_str = news.get("date", "")
            preview_html += f"<b>Date:</b> {date_str[:19] if date_str else 'N/A'}<br>"
            link = news.get("link", "#")
            preview_html += f"<b>Link:</b> <a href='{link}'>{link}</a></p><hr>"
            preview_html += f"<b>Summary:</b><p>{news.get('summary', 'No summary available.')}</p>"
            analysis = news.get("analysis")
            if analysis:
                analysis_html = analysis.replace('\n', '<br>')
                preview_html += f"<hr><b>Analysis:</b><p>{analysis_html}</p>"
            self.preview_text.setHtml(preview_html)
        else:
            self.preview_text.setText(f"Cannot load preview data (ID: {news_id})")
            self.delete_button.setEnabled(False)

    def _apply_filters(self):
        """Applies filters based on UI selections (manual row hiding)."""
        search_text = self.search_input.text().strip().lower()
        selected_category_text = self.category_filter.currentText()
        selected_source_text = self.source_filter.currentText()

        source_model = self.proxy_model.sourceModel()
        if not source_model: return

        visible_count = 0
        for row in range(source_model.rowCount()):
            category_matches = True
            if selected_category_text != "All":
                cat_item = source_model.item(row, 2) # Category Name column
                category_matches = (cat_item and cat_item.text() == selected_category_text)

            source_matches = True
            if selected_source_text != "All":
                src_item = source_model.item(row, 1) # Source Name column
                source_matches = (src_item and src_item.text() == selected_source_text)

            text_matches = True
            if search_text:
                text_matches = False
                for col in [0, 1, 2]: # Title, Source, Category Name
                     item = source_model.item(row, col)
                     if item and search_text in item.text().lower():
                         text_matches = True; break
                # Add search in summary/analysis if needed (requires accessing self.news_data)
                if not text_matches:
                    news_id = source_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    if news_id in self.news_data:
                         news_item_data = self.news_data[news_id]
                         if (news_item_data.get('summary') and search_text in news_item_data['summary'].lower()) or \
                            (news_item_data.get('analysis') and search_text in news_item_data['analysis'].lower()):
                             text_matches = True

            is_visible = category_matches and source_matches and text_matches
            # Use mapFromSource to get the proxy index for hiding
            proxy_index = self.proxy_model.mapFromSource(source_model.index(row, 0))
            if proxy_index.isValid(): # Check if the row is currently visible in the proxy
                 self.news_table.setRowHidden(proxy_index.row(), not is_visible)
                 if is_visible: visible_count += 1
            elif is_visible:
                 # This case is less common but might happen if proxy model itself filtered it out before
                 # We might need to invalidate the proxy filter if combining methods,
                 # but for manual hiding, focus on rows the proxy currently shows.
                 pass


        logger.debug(
            f"Applied filters: Cat='{selected_category_text}', Src='{selected_source_text}', "
            f"Search='{search_text}'. Visible rows after manual hide: {visible_count}" # Note: this count might not be perfect if proxy model also filters
        )

    # Ensure task is cancelled if the tab/window is closed while fetching
    def closeEvent(self, event):
        if self.fetch_task and not self.fetch_task.done():
            logger.info("News tab closing, cancelling active fetch task.")
            self.fetch_task.cancel()
        super().closeEvent(event) # Call parent implementation if necessary (usually not needed for QWidget)