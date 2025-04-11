#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
"""

import datetime
import logging
import asyncio
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
# Import the RENAMED popup class
from src.ui.task_status_popup import TaskStatusPopup # <-- Import renamed class

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
        self.task_status_popup: Optional[TaskStatusPopup] = None
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

        self.show_status_button = QPushButton("Show Task Status")
        self.show_status_button.clicked.connect(self._show_task_progress_window)
        self.show_status_button.setEnabled(False)
        self.show_status_button.setToolTip("Shows the status window from the last/current task (fetch/analysis).")
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
        # ... (splitter, news_table, preview_text setup remains the same) ...
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
        # ... (bottom toolbar setup remains the same) ...
        bottom_toolbar = QHBoxLayout()
        main_layout.addLayout(bottom_toolbar)

        self.refresh_button = QPushButton("Refresh List")
        self.refresh_button.clicked.connect(self._refresh_all)
        bottom_toolbar.addWidget(self.refresh_button)

        bottom_toolbar.addStretch(1)

        self.analyze_button = QPushButton("Analyze Selected")
        self.analyze_button.setToolTip("Analysis now happens automatically during Fetch News.") # Update tooltip
        self.analyze_button.setEnabled(False)  # Disable permanently
        # self.analyze_button.clicked.connect(self._analyze_removed_notification) # Can remove connection
        bottom_toolbar.addWidget(self.analyze_button)

        self.edit_button = QPushButton("Edit") # Keep Edit button, maybe disable
        self.edit_button.setToolTip("Edit the selected news item (Not Implemented).")
        # self.edit_button.clicked.connect(self._edit_news) # Connect later if needed
        self.edit_button.setEnabled(False) # Disable edit for now
        bottom_toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setToolTip("Delete the selected news item(s).")
        self.delete_button.clicked.connect(self._delete_news) # Connect delete action
        self.delete_button.setEnabled(False)
        bottom_toolbar.addWidget(self.delete_button)


        # --- Connect Signals ---
        # ... (signal connections remain the same) ...
        self.category_filter.currentIndexChanged.connect(self._on_category_filter_changed)
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(self._on_selection_changed)


    # --- Methods ---

    # _setup_table_model, _refresh_all, _load_news, _load_filters,
    # _on_category_filter_changed, _update_source_filter remain the same
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
            QMessageBox.warning(self, "Busy", "A task is currently running. Please wait.")
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
                # Attempt to format date for sorting if possible, otherwise keep as string
                try:
                     dt = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else None
                     display_date = dt.strftime('%Y-%m-%d %H:%M') if dt else "N/A"
                except ValueError:
                     display_date = date_str[:16] if date_str else "N/A" # Fallback display
                date_item = QStandardItem(display_date)

                # Store ID in the first column's item data for retrieval
                title_item.setData(news_id, Qt.ItemDataRole.UserRole)

                # Store sortable data if possible (e.g., timestamp for date)
                # date_item.setData(dt.timestamp() if dt else 0, Qt.ItemDataRole.UserRole + 1) # Example for sorting

                for item in [title_item, source_item, category_item, date_item]:
                    item.setEditable(False)

                self.model.appendRow([title_item, source_item, category_item, date_item])

            self._apply_filters() # Apply filters after loading
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
            # --- Category Filter ---
            current_category_id = self.category_filter.currentData()
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem("All", -1) # UserRole data = -1
            self.categories_cache = self._news_service.get_all_categories() # List[Tuple[int, str]]
            restored_cat_index = 0
            for i, (cat_id, cat_name) in enumerate(self.categories_cache):
                self.category_filter.addItem(cat_name, cat_id) # UserRole data = cat_id
                if cat_id == current_category_id:
                     restored_cat_index = i + 1 # +1 because of "All"
            self.category_filter.setCurrentIndex(restored_cat_index)
            self.category_filter.blockSignals(False)
            logger.info(f"Loaded {len(self.categories_cache)} categories.")

            # --- Source Filter (Trigger update based on selected category) ---
            self._update_source_filter(self.category_filter.currentData())

        except Exception as e:
            logger.error(f"Failed to load filters: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to load filter options: {str(e)}")
        finally:
            self.category_filter.blockSignals(False)
            self.source_filter.blockSignals(False) # Ensure source filter signals are unblocked

    def _on_category_filter_changed(self, index):
        """Handle category filter change"""
        if self._is_fetching: return # Ignore during fetch
        category_id = self.category_filter.itemData(index) # Get data (ID or -1)
        logger.debug(f"Category filter changed to index {index}, ID: {category_id}")
        self._update_source_filter(category_id)
        self._apply_filters()

    def _update_source_filter(self, category_id: int):
        """Update source filter options based on category ID"""
        logger.debug(f"Updating source filter for category ID: {category_id}")
        try:
            current_source_name = self.source_filter.currentText() # Remember current selection by name
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All", -1) # UserRole data = -1

            # Get sources based on category_id
            if category_id == -1: # "All" categories selected
                 self.sources_cache = self._news_service.get_all_sources() # List[Dict]
                 # Get unique source names across all categories
                 sources_to_add = sorted(list(set(s["name"] for s in self.sources_cache if s.get("name"))))
            else:
                 # Get sources only for the specific category
                 self.sources_cache = self._news_service.get_sources_by_category_id(category_id) # List[Dict]
                 sources_to_add = sorted(s["name"] for s in self.sources_cache if s.get("name"))

            # Add source names to the combo box
            for name in sources_to_add:
                 self.source_filter.addItem(name, name) # Store name as data for simplicity here

            # Try to restore previous selection by name
            restored_src_index = self.source_filter.findText(current_source_name)
            self.source_filter.setCurrentIndex(restored_src_index if restored_src_index != -1 else 0) # Default to "All" if not found

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
            self._show_task_progress_window()
        else:
            logger.debug("Fetch button clicked: starting fetch process.")
            self._start_fetch_news()

    def _start_fetch_news(self):
        """Starts the actual news fetching process."""
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

            self._is_fetching = True
            self.fetch_button.setEnabled(False)
            self.fetch_button.setText("Fetching...")

            # --- Use the TaskStatusPopup ---
            if self.task_status_popup is None:
                logger.info("Creating new TaskStatusPopup instance.")
                self.task_status_popup = TaskStatusPopup(self)
            else:
                logger.info("Reusing existing TaskStatusPopup instance.")

            # Clear the popup display before starting
            self.task_status_popup.clear_display()
            # Append an initial message
            self.task_status_popup.append_log_message(f"Starting fetch for {urls_to_fetch_count} URLs...\n")

            self.show_status_button.setEnabled(True) # Enable show status button
            # --- End Popup Handling ---

            fetch_coro = self._news_service.fetch_news_from_sources
            fetch_args = ()
            fetch_kwargs = {
                "source_ids": source_ids_to_fetch,
                # Pass the URL status update callback (still useful for title updates)
                "on_url_status_update": self._handle_url_status_update,
                # Pass the NEW stream chunk update callback
                "on_stream_chunk_update": self._handle_stream_chunk_update, # Connect to the new slot
            }

            self.fetch_runner = AsyncTaskRunner(fetch_coro, *fetch_args, **fetch_kwargs)
            self.fetch_runner.setAutoDelete(True)
            self.fetch_runner.signals.finished.connect(self._on_fetch_runner_finished)
            self.fetch_runner.signals.error.connect(self._on_fetch_error)

            QThreadPool.globalInstance().start(self.fetch_runner)
            logger.info("Fetch task started in background. Status popup is available.")
            # Optionally show the popup automatically
            # self._show_task_progress_window()

        except Exception as e:
            logger.error(f"Failed to initiate news fetch: {e}", exc_info=True)
            self._is_fetching = False
            self.fetch_button.setEnabled(True)
            self.fetch_button.setText("Fetch News")
            if self.task_status_popup:
                 # Use the popup's method to set final error status
                 self.task_status_popup.set_final_status(f"Error initiating fetch: {e}", is_error=True)
                 self.task_status_popup.append_log_message(f"\n[CRITICAL] Failed to start: {e}")
            QMessageBox.critical(self, "Error", f"Failed to initiate news fetch: {str(e)}")

    def _get_selected_source_ids_for_fetch(self) -> Optional[List[int]]:
        """Helper to determine which source IDs to fetch based on filters."""
        # (Implementation remains the same)
        source_ids: Optional[List[int]] = None
        selected_category_id = self.category_filter.currentData()
        selected_source_name = self.source_filter.currentText() # Get the name

        # Ensure cache is loaded if empty (e.g., if fetch is clicked before filters load)
        if not self.sources_cache:
             try:
                 # We only need all sources here, not necessarily tied to category filter state
                 self.sources_cache = self._news_service.get_all_sources()
                 logger.debug("Loaded sources cache for fetch selection.")
             except Exception as e:
                 logger.error(f"Failed to load sources cache for fetch: {e}")
                 return [] # Return empty list on error

        all_sources = self.sources_cache

        if selected_category_id != -1:
            # Filter by category first
            filtered_by_cat = [s for s in all_sources if s.get("category_id") == selected_category_id]
            if selected_source_name != "All":
                # Then filter by specific source name within that category
                source_ids = [s["id"] for s in filtered_by_cat if s.get("name") == selected_source_name and s.get("id") is not None]
            else:
                # Get all source IDs within that category
                source_ids = [s["id"] for s in filtered_by_cat if s.get("id") is not None]
        elif selected_source_name != "All":
            # Filter only by source name across all categories
            source_ids = [s["id"] for s in all_sources if s.get("name") == selected_source_name and s.get("id") is not None]
        else:
            # No filters selected, fetch all active sources (return None to indicate all)
             source_ids = None # Let the service handle fetching all

        # logger.debug(f"Selected source IDs for fetch: {source_ids}")
        return source_ids


    def _get_selected_urls_for_fetch(self, source_ids: Optional[List[int]]) -> List[str]:
        """Helper to get the actual URLs based on selected source IDs (used for count/logging)."""
        # (Implementation remains the same)
        if not self.sources_cache:
             try:
                 self.sources_cache = self._news_service.get_all_sources()
             except Exception as e:
                 logger.error(f"Failed to load sources cache for URL fetch: {e}")
                 return []

        all_sources = self.sources_cache

        if source_ids is None: # Fetch all
             # Get URLs from all sources in the cache
             return [s['url'] for s in all_sources if s.get('url')]
        else: # Fetch specific IDs
            urls = []
            # Create a map for efficient lookup
            source_map = {s['id']: s['url'] for s in all_sources if s.get('id') is not None and s.get('url')}
            for sid in source_ids:
                 if sid in source_map:
                      urls.append(source_map[sid])
            return urls


    # Rename method
    @Slot()
    def _show_task_progress_window(self):
        """Shows the task status popup window."""
        # Check for the renamed popup instance
        if self.task_status_popup and isinstance(self.task_status_popup, TaskStatusPopup):
            logger.debug("Showing task status popup.")
            self.task_status_popup.show()
            self.task_status_popup.raise_() # Bring to front
            self.task_status_popup.activateWindow() # Make active
        else:
            logger.info("Task status popup has not been created yet.")
            QMessageBox.information(self, "Info", "The task status window hasn't been created yet. Please start a fetch task first.")

    # Slot to handle URL-specific status updates (e.g., Crawled, Processing, Complete)
    # This might now primarily update the window title or add high-level logs.
    @Slot(str, str, str)
    def _handle_url_status_update(self, url: str, status: str, details: str):
        """Slot to receive URL status updates (mainly for window title)."""
        if self.task_status_popup:
            # Maybe just log high-level status changes to the text area?
            # self.task_status_popup.append_log_message(f"[{status}] {url} {details}\n")
            # Or primarily use it to update the overall window title status (less granular now)
            # The TaskStatusPopup itself doesn't have per-URL display anymore.
            pass # Decide if you want URL status in the main log or just title updates
        else:
             logger.warning("Received URL status update but task status popup does not exist.")

    # NEW Slot to handle incoming stream chunks
    @Slot(str)
    def _handle_stream_chunk_update(self, chunk: str):
        """Slot to receive LLM stream chunks and update the popup's text area."""
        # logger.debug(f"Stream Chunk Received: {chunk[:50]}...") # Can be very verbose
        if self.task_status_popup:
            # Pass the chunk directly to the popup's append method
            self.task_status_popup.append_log_message(chunk)
        else:
             logger.warning("Received stream chunk update but task status popup does not exist.")


    @Slot(object)
    def _on_fetch_runner_finished(self, result):
        """Callback for async fetch completion."""
        # result is the total count of saved items from fetch_news_from_sources
        final_message = f"Fetch task completed. Total new items saved: {result}."
        logger.info(final_message)
        QMessageBox.information(self, "Task Complete", final_message)

        self._is_fetching = False
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch News")
        if self.task_status_popup:
             # Set final status title and append final message to log
             self.task_status_popup.set_final_status(f"Complete ({result} items saved)")
             self.task_status_popup.append_log_message(f"\n=== {final_message} ===")

        # Keep show_status_button enabled

        self._load_news() # Refresh the news list

    @Slot(Exception)
    def _on_fetch_error(self, error):
        """Callback for async fetch error."""
        final_message = f"Task failed: {error}"
        logger.error(final_message, exc_info=error)
        QMessageBox.critical(self, "Task Error", f"Error occurred during task:\n{str(error)}")

        self._is_fetching = False
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Fetch News")
        if self.task_status_popup:
             # Set final error status title and append final message to log
             self.task_status_popup.set_final_status(f"Error: {error}", is_error=True)
             self.task_status_popup.append_log_message(f"\n=== [ERROR] {final_message} ===")

        # Keep show_status_button enabled

    # _delete_news, _edit_news, _send_to_analysis (removed), _export_news,
    # _on_selection_changed, _apply_filters remain mostly the same
    def _delete_news(self):
        """Delete selected news items."""
        if self._is_fetching:
            QMessageBox.warning(self, "Busy", "A task is currently running. Please wait.")
            return

        selected_proxy_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Notice", "Please select news items to delete.")
            return

        news_to_delete: List[Tuple[int, str]] = [] # Store (id, title)
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
            deleted_count = 0
            errors = []
            for news_id, news_title in news_to_delete:
                try:
                    if self._news_service.delete_news(news_id):
                        logger.info(f"Deleted news ID: {news_id} ('{news_title}')")
                        deleted_count += 1
                    else:
                        logger.error(f"Service failed deleting news ID: {news_id}")
                        errors.append(f"Failed deleting '{news_title}' (Service Error)")
                except Exception as e:
                    logger.error(f"Error calling delete_news for ID {news_id}: {e}", exc_info=True)
                    errors.append(f"Error deleting '{news_title}': {e}")

            if errors:
                 QMessageBox.warning(self, "Partial Success", f"Deleted {deleted_count} items.\nErrors occurred:\n- " + "\n- ".join(errors))
            elif deleted_count > 0:
                 QMessageBox.information(self, "Success", f"{deleted_count} news item(s) deleted.")
            else: # Should not happen if selection was valid, but handle defensively
                 QMessageBox.warning(self, "No Action", "No news items were deleted.")

            if deleted_count > 0:
                 self._load_news() # Refresh list if something was deleted
                 # self._load_filters() # Filters might not need reloading unless counts change drastically

    def _edit_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Edit functionality is not implemented.")

    # Removed analyze functionality - this method is no longer needed or connected
    # def _analyze_removed_notification(self):
    #     QMessageBox.information(self, "Notice", "Analysis functionality now happens during 'Fetch News'.")

    def _export_news(self):
        if self._is_fetching: return
        QMessageBox.information(self, "Notice", "Export functionality is not implemented.")

    def _on_selection_changed(self, selected, deselected):
        """Update preview and button states based on selection."""
        indexes = self.news_table.selectionModel().selectedRows() # Use selectedRows for consistency
        enable_buttons = bool(indexes)

        # Update button states
        self.delete_button.setEnabled(enable_buttons)
        # self.analyze_button remains disabled
        # self.edit_button remains disabled

        # Update preview
        if not indexes:
            self.preview_text.clear()
            return

        # Get data for the first selected row
        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)

        if news_id is not None and news_id in self.news_data:
            news = self.news_data[news_id]
            # Build HTML for preview (make sure keys match your news_data structure)
            preview_html = f"<h3>{news.get('title', 'N/A')}</h3>"
            preview_html += f"<p><b>Source:</b> {news.get('source_name', 'N/A')}<br>"
            preview_html += f"<b>Category:</b> {news.get('category_name', 'N/A')}<br>"
            date_str = news.get("date", "")
            preview_html += f"<b>Date:</b> {date_str[:19] if date_str else 'N/A'}<br>" # Show date/time
            link = news.get("link", "#")
            preview_html += f"<b>Link:</b> <a href='{link}'>{link}</a></p><hr>" # Removed analyzed flag
            preview_html += f"<b>Summary:</b><p>{news.get('summary', 'No summary available.')}</p>"
            analysis = news.get("analysis")
            if analysis:
                # Basic formatting for analysis preview
                analysis_html = analysis.replace('\n', '<br>')
                preview_html += f"<hr><b>Analysis:</b><p>{analysis_html}</p>"

            self.preview_text.setHtml(preview_html)
        else:
            self.preview_text.setText(f"Cannot load preview data (ID: {news_id})")
            # Ensure buttons are disabled if data is bad
            self.delete_button.setEnabled(False)

    def _apply_filters(self):
        """Applies filters based on UI selections."""
        search_text = self.search_input.text().strip()
        selected_category_text = self.category_filter.currentText()
        selected_source_text = self.source_filter.currentText() # Filter by source name

        # Option 1: Use QSortFilterProxyModel's filtering (simpler for basic text search)
        # self.proxy_model.setFilterKeyColumn(-1) # Search all columns
        # self.proxy_model.setFilterRegularExpression(search_text) # Or setFilterFixedString

        # Option 2: Manual row hiding (more flexible for combined filters)
        # This seems to be the original approach, let's refine it
        source_model = self.proxy_model.sourceModel()
        if not source_model: return

        visible_count = 0
        for row in range(source_model.rowCount()):
            # Check Category Filter
            category_matches = True
            if selected_category_text != "All":
                cat_item = source_model.item(row, 2) # Column index for Category Name
                category_matches = (cat_item and cat_item.text() == selected_category_text)

            # Check Source Filter
            source_matches = True
            if selected_source_text != "All":
                src_item = source_model.item(row, 1) # Column index for Source Name
                source_matches = (src_item and src_item.text() == selected_source_text)

            # Check Search Text Filter (across relevant columns)
            text_matches = True
            if search_text:
                text_matches = False
                # Check Title, Source, Category, Summary/Analysis (if loaded in model)
                for col in [0, 1, 2]: # Title, Source, Category Name columns
                     item = source_model.item(row, col)
                     if item and search_text.lower() in item.text().lower():
                         text_matches = True
                         break
                # If you want to search summary/analysis, you'd need that data accessible
                # or perform the search on the self.news_data cache, which is more complex here.

            # Determine visibility
            is_visible = category_matches and source_matches and text_matches
            self.news_table.setRowHidden(row, not is_visible)
            if is_visible:
                visible_count += 1

        logger.debug(
            f"Applied filters: Cat='{selected_category_text}', Src='{selected_source_text}', "
            f"Search='{search_text}'. Visible rows: {visible_count}"
        )