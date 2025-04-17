#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
Refactored for threaded fetching and detailed progress reporting.
"""

import logging
import asyncio
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
)
from PySide6.QtCore import (
    Qt,
    QSortFilterProxyModel,
    Signal,
    Slot,
    QThreadPool,
    QMetaObject,
    Q_ARG,
    QThread,
)
from PySide6.QtSql import QSqlTableModel
from src.db.connection import get_db
from src.db.schema_constants import NEWS_TABLE

from src.services.news_service import NewsService

from src.ui.dialogs.fetch_progress_dialog import FetchProgressDialog
from src.ui.dialogs.llm_stream_dialog import LlmStreamDialog

from src.ui.workers.news_fetch_workers import (
    WorkerSignals,
    InitialCrawlerWorker,
    ProcessingWorker,
)

logger = logging.getLogger(__name__)


class NewsTab(QWidget):
    """News Management Tab"""

    news_data_changed = Signal()

    def __init__(self, news_service: NewsService):
        super().__init__()
        self._news_service = news_service
        self.categories_cache: List[Tuple[int, str]] = []
        self.sources_cache: List[Dict[str, Any]] = []
        self._is_fetching = False
        self._is_closing = False
        self.fetch_progress_dialog: Optional[FetchProgressDialog] = None
        self.llm_stream_dialogs: Dict[str, LlmStreamDialog] = {}
        self.analysis_results_cache: Dict[str, str] = {}

        # --- Threading Setup ---
        self.thread_pool = QThreadPool()
        self.signals = WorkerSignals()
        self.processing_worker = ProcessingWorker(self._news_service, self.signals)
        self.processing_worker.start()
        try:
            self.processing_worker.wait_until_ready(timeout=5)
            logger.info(
                f"Processing worker thread started and event loop is ready. ID: {self.processing_worker.currentThread()}"
            )
        except TimeoutError as e:
            logger.error(f"Processing worker failed to start: {e}")
            QMessageBox.critical(
                self,
                "Error",
                "Processing worker thread failed to start. Functionality may be limited.",
            )

        # --- Task Tracking ---
        self._total_sources_to_process = 0
        self._initial_crawl_finished_flag = False
        self._processing_tasks_finished_count = 0
        self._active_initial_crawler: Optional[InitialCrawlerWorker] = (
            None  # Track the crawler worker
        )

        # Connect signals
        self.signals.initial_crawl_status.connect(self._handle_initial_crawl_status)
        self.signals.html_ready.connect(self._handle_html_ready)
        self.signals.initial_crawl_finished.connect(
            self._handle_initial_crawl_phase_finished
        )
        self.signals.processing_status.connect(self._handle_processing_status)
        self.signals.processing_finished.connect(self._handle_processing_finished)

        self._setup_ui()
        self._load_filters()
        self._load_news()

    # --- UI Setup, Load News, Load Filters, Filter Handling ---
    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()
        main_layout.addLayout(toolbar_layout)

        self.fetch_button = QPushButton("Fetch News")
        self.fetch_button.setToolTip("Start fetching news and show progress window.")
        self.fetch_button.clicked.connect(self._fetch_news_handler)
        toolbar_layout.addWidget(self.fetch_button)

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
        self._setup_table_model()
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

        # --- Connect Signals ---
        self.category_filter.currentIndexChanged.connect(
            self._on_category_filter_changed
        )
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        # 添加右键菜单
        self.news_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.news_table.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_table_model(self):
        db = get_db()
        if not db.isOpen():
            QMessageBox.critical(
                self,
                "Database Error",
                f"Unable to get database connection: {db.lastError().text()}",
            )
            # May need to disable related UI or exit
            return

        self.news_model = QSqlTableModel(parent=self, db=db)
        self.news_model.setTable(NEWS_TABLE)

        # Set edit strategy (optional, choose as needed)
        # OnFieldChange: Try to write to the database immediately when the field changes
        # OnRowChange: Try to write to the database after the row changes
        # OnManualSubmit: Need to manually call submitAll() or revertAll()
        self.news_model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)

        # Note: fieldIndex may vary due to database schema, use constants or ensure names are correct
        col_map = {
            "title": "Title",
            "source_name": "Source",
            "category_name": "Category",
            "date": "Publish Date",
        }
        # Record column indices for later use and set headers
        self._column_indices = {}
        for i in range(self.news_model.columnCount()):
            field_name = self.news_model.record().fieldName(i)
            self._column_indices[field_name] = i
            if field_name in col_map:
                self.news_model.setHeaderData(
                    i, Qt.Orientation.Horizontal, col_map[field_name]
                )

        # --- Key: Load data into the model ---
        if not self.news_model.select():
            error = self.news_model.lastError()
            logger.error(f"Failed to select data for news table: {error.text()}")
            QMessageBox.warning(
                self, "Data Load Failed", f"Unable to load news list: {error.text()}"
            )

        # Set proxy model
        self.proxy_model = QSortFilterProxyModel(self)
        # --- Key: Set source model to QSqlTableModel ---
        self.proxy_model.setSourceModel(self.news_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(
            -1
        )  # Default to filtering on all columns (when searching)

        self.news_table.setModel(self.proxy_model)

        # Hide columns that do not need to be displayed directly in the table, such as id, summary, analysis, etc.
        if "id" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["id"], True)
        if "link" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["link"], True)
        if "summary" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["summary"], True)
        if "analysis" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["analysis"], True)
        if "source_id" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["source_id"], True)
        if "category_id" in self._column_indices:
            self.news_table.setColumnHidden(self._column_indices["category_id"], True)

        # Ensure sorting is enabled (proxy model will handle)
        self.news_table.setSortingEnabled(True)
        # Initial sorting (e.g., by date descending, assuming date column index is known or can be obtained)
        date_col_index = self._column_indices.get("date", -1)
        if date_col_index != -1:
            # Note: Initial sorting is set on the proxy model
            self.proxy_model.sort(date_col_index, Qt.SortOrder.DescendingOrder)

    def _refresh_all(self):
        if self._is_fetching:
            QMessageBox.warning(
                self, "Busy", "A fetch task is currently running. Please wait."
            )
            return
        logger.info("Refreshing filters and news list...")
        self._load_filters()
        self._load_news()

    def _load_news(self):
        logger.info("Reloading news data using QSqlTableModel...")
        try:
            # --- Core: Let the model re-query data from the database ---
            if not self.news_model.select():
                error = self.news_model.lastError()
                logger.error(f"Failed to re-select news data: {error.text()}")
                QMessageBox.warning(
                    self,
                    "Refresh Failed",
                    f"Unable to refresh news list: {error.text()}",
                )
                return

            logger.info(f"News model reloaded. Row count: {self.news_model.rowCount()}")

            self.news_table.resizeColumnsToContents()
            self.news_table.horizontalHeader().setStretchLastSection(True)
            self.news_data_changed.emit()
        except AttributeError as e:
            logger.error(f"Error accessing news model (likely during init): {e}")
        except Exception as e:
            logger.error(f"Failed to reload news: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"Error occurred while refreshing news list: {str(e)}"
            )

    def _load_filters(self):
        logger.info("Loading filters...")
        try:
            # --- Category Filter ---
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
            # Update source filter based on loaded category
            self._update_source_filter(self.category_filter.currentData())
        except Exception as e:
            logger.error(f"Failed to load filters: {e}", exc_info=True)
            QMessageBox.warning(
                self, "Warning", f"Failed to load filter options: {str(e)}"
            )
        finally:
            self.category_filter.blockSignals(False)
            self.source_filter.blockSignals(
                False
            )  # Ensure source filter signals are unblocked

    def _on_category_filter_changed(self, index):
        if self._is_fetching:
            return
        category_id = self.category_filter.itemData(index)
        logger.debug(f"Category filter changed to index {index}, ID: {category_id}")
        self._update_source_filter(category_id)
        self._apply_filters()

    def _update_source_filter(self, category_id: int):
        logger.debug(f"Updating source filter for category ID: {category_id}")
        try:
            current_source_name = (
                self.source_filter.currentText()
            )  # Save current selection if possible
            self.source_filter.blockSignals(True)
            self.source_filter.clear()
            self.source_filter.addItem("All", -1)  # Add "All" option first

            if category_id == -1:  # "All" categories selected
                # Load all sources if cache is empty or needs full refresh
                if not self.sources_cache:
                    self.sources_cache = self._news_service.get_all_sources()
                # Use all unique names from the cache
                sources_to_add = sorted(
                    list(set(s["name"] for s in self.sources_cache if s.get("name")))
                )
            else:  # Specific category selected
                # Fetch only sources for this category
                self.sources_cache = self._news_service.get_sources_by_category_id(
                    category_id
                )
                sources_to_add = sorted(
                    s["name"] for s in self.sources_cache if s.get("name")
                )

            for name in sources_to_add:
                self.source_filter.addItem(name, name)

            # Try to restore previous selection
            restored_src_index = self.source_filter.findText(current_source_name)
            self.source_filter.setCurrentIndex(
                restored_src_index if restored_src_index != -1 else 0
            )  # Default to "All" if not found

            logger.debug(
                f"Source filter updated with {self.source_filter.count() - 1} sources."
            )
        except Exception as e:
            logger.error(f"Failed to update source filter: {e}", exc_info=True)
            QMessageBox.warning(
                self, "Warning", f"Failed to update source filter: {str(e)}"
            )
        finally:
            self.source_filter.blockSignals(False)

    # --- Fetching Logic (Modified) ---
    def _fetch_news_handler(self):
        """Handles clicks on the Fetch News button."""
        if self._is_fetching:
            if self.fetch_progress_dialog:
                self.fetch_progress_dialog.show()
                self.fetch_progress_dialog.raise_()
            return

        try:
            selected_sources = self._get_selected_source_info_for_fetch()
            if not selected_sources:
                QMessageBox.information(
                    self, "Notice", "No sources selected/found for fetch."
                )
                return

            # --- Reset state and counters ---
            self._is_fetching = True
            self.analysis_results_cache.clear()
            self.fetch_button.setText("Fetching...")
            self.fetch_button.setEnabled(False)  # Disable fetch button
            self._total_sources_to_process = len(selected_sources)
            self._initial_crawl_finished_flag = False
            self._processing_tasks_finished_count = 0
            self._active_initial_crawler = None  # Clear previous instance reference
            logger.info(
                f"Expecting results for {self._total_sources_to_process} sources."
            )

            # Ensure processing worker is ready
            if (
                not self.processing_worker.isRunning()
                or not self.processing_worker.loop
                or not self.processing_worker.loop.is_running()
            ):
                logger.error("Processing worker is not ready. Cannot start fetch.")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Processing worker is not running. Please restart the application.",
                )
                self._reset_fetch_state("Processing worker error")
                return

            # Create/Show Progress Dialog
            if self.fetch_progress_dialog is None:
                self.fetch_progress_dialog = FetchProgressDialog(selected_sources, self)
                self.fetch_progress_dialog.view_llm_output_requested.connect(
                    self._show_llm_stream_dialog
                )
            else:
                self.fetch_progress_dialog.populate_table(selected_sources)
            self.fetch_progress_dialog.setWindowTitle("News Fetch Progress")
            self.fetch_progress_dialog.show()
            self.fetch_progress_dialog.raise_()

            # --- Start ONE Initial Crawler Worker ---
            logger.info(
                f"Starting ONE InitialCrawlerWorker for {self._total_sources_to_process} sources."
            )
            self._active_initial_crawler = InitialCrawlerWorker(
                selected_sources, self.signals
            )
            self.thread_pool.start(self._active_initial_crawler)

        except Exception as e:
            logger.error(f"Failed to initiate news fetch: {e}", exc_info=True)
            self._reset_fetch_state(f"Error initiating fetch: {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to initiate news fetch: {str(e)}"
            )

    def _reset_fetch_state(self, final_message: Optional[str] = None):
        """Resets the UI state after fetching finishes, fails, or is cancelled."""
        # Check if called from worker thread and queue if necessary
        if QThread.currentThread() != self.thread():
            safe_final_message = final_message if final_message is not None else ""
            if not self._is_closing:
                QMetaObject.invokeMethod(
                    self,
                    "_reset_fetch_state",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, safe_final_message),
                )
            else:
                logger.debug(
                    "Skipping queued _reset_fetch_state call as widget is closing."
                )
            return

        # --- Main thread execution ---
        if self._is_closing:
            logger.info(
                "Fetch state reset executing, but widget is closing. Minimal reset."
            )
            self._is_fetching = False
            self._total_sources_to_process = 0
            self._initial_crawl_finished_flag = False
            self._processing_tasks_finished_count = 0
            self._active_initial_crawler = None
            return

        # Original reset logic
        self._is_fetching = False
        self.fetch_button.setText("Fetch News")
        self.fetch_button.setEnabled(True)

        if self.fetch_progress_dialog and final_message:
            try:
                self.fetch_progress_dialog.setWindowTitle(
                    f"News Fetch - {final_message}"
                )
            except RuntimeError:
                logger.warning(
                    "Fetch progress dialog was already deleted during reset."
                )

        # Reset counters and active worker
        self._total_sources_to_process = 0
        self._initial_crawl_finished_flag = False
        self._processing_tasks_finished_count = 0
        self._active_initial_crawler = None
        logger.info(f"Fetch state reset on main thread. Final message: {final_message}")

    # --- Slots for Handling Worker Signals (Modified Finish Handling) ---
    @Slot(str, str)
    def _handle_initial_crawl_status(self, url: str, status: str):
        """Update progress dialog with initial crawl status."""
        if self.fetch_progress_dialog:
            QMetaObject.invokeMethod(
                self.fetch_progress_dialog,
                "update_status",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, url),
                Q_ARG(str, status),
                Q_ARG(bool, False),
            )

    @Slot(str, str, dict)
    def _handle_html_ready(self, url: str, html_content: str, source_info: dict):
        """Schedule processing task on the ProcessingWorker's event loop."""
        # Check if fetching is still active *and* not cancelled
        if not self._is_fetching or (
            self._active_initial_crawler and self._active_initial_crawler.is_cancelled()
        ):
            logger.warning(
                f"Received html_ready for {url} but fetch not active or cancelled. Ignoring."
            )
            return

        logger.info(f"HTML received for {url}. Submitting to processing worker loop.")
        future = self.processing_worker.submit_task(url, html_content, source_info)
        if future is None:
            logger.error(f"Failed to submit processing task for {url}.")
            if self.fetch_progress_dialog:
                QMetaObject.invokeMethod(
                    self.fetch_progress_dialog,
                    "update_status",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, url),
                    Q_ARG(str, "Error: Submit Failed"),
                    Q_ARG(bool, True),  # Mark as final for this URL
                )
            # Decrement count as this task won't finish successfully
            self._processing_tasks_finished_count += 1
            self._check_if_all_fetching_done(
                "Task submit failed"
            )  # Check completion state
        else:
            if self.fetch_progress_dialog:
                QMetaObject.invokeMethod(
                    self.fetch_progress_dialog,
                    "update_status",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, url),
                    Q_ARG(str, "Processing Scheduled"),
                    Q_ARG(bool, False),
                )

    @Slot()
    def _handle_initial_crawl_phase_finished(self):
        """Handles signal that the single InitialCrawlerWorker finished (or was cancelled)."""
        logger.info("Initial crawl phase finished (worker run method completed).")
        self._initial_crawl_finished_flag = True
        # Check if it finished due to cancellation
        was_cancelled = (
            self._active_initial_crawler is not None
            and self._active_initial_crawler.is_cancelled()
        )
        self._check_if_all_fetching_done(
            "Initial Crawl Finished" + (" (Cancelled)" if was_cancelled else "")
        )

    @Slot(str, str)
    def _handle_processing_status(self, url: str, status: str):
        """Update progress dialog with intermediate processing status."""
        if self.fetch_progress_dialog:
            QMetaObject.invokeMethod(
                self.fetch_progress_dialog,
                "update_status",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, url),
                Q_ARG(str, status),
                Q_ARG(bool, False),
            )

    @Slot(str, str, str, str)
    def _handle_processing_finished(
        self, url: str, final_status: str, details: str, analysis_result: str
    ):
        """Handle completion of processing for a single URL."""
        logger.info(
            f"Processing finished signal received for {url}. Status: {final_status}, Details: {details[:50]}..., Result length: {len(analysis_result)}"
        )

        # Store the full analysis result
        self.analysis_results_cache[url] = (
            analysis_result
            if analysis_result
            else (
                f"Error during processing: {details}"
                if final_status == "Error"
                else "Analysis result not available."
            )
        )

        # --- This count must only happen ONCE per source URL ---
        # Check if we already counted this URL's final status (e.g. if submit failed earlier)
        # A simple way is to just increment here, assuming submit_task failure already incremented.
        # A more robust way might involve tracking URLs explicitly.
        self._processing_tasks_finished_count += 1  # Increment finished count

        # --- Update Progress Dialog Status ---
        if self.fetch_progress_dialog:
            status_to_display = final_status
            if final_status == "Complete" and details:
                status_to_display = f"Complete ({details})"
            elif final_status == "Error" and details:
                status_to_display = f"Error: {details[:30]}"
            elif final_status == "Complete*" and details:
                status_to_display = f"Complete* ({details})"
            elif final_status == "Cancelled":
                status_to_display = "Cancelled"

            QMetaObject.invokeMethod(
                self.fetch_progress_dialog,
                "update_status",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, url),
                Q_ARG(str, status_to_display),
                Q_ARG(bool, True),  # Mark as final status for this URL
            )

        self._check_if_all_fetching_done(f"Processed: {url}")

    def _check_if_all_fetching_done(self, trigger_reason: str):
        """Checks if initial crawl is done AND all expected processing tasks finished or cancelled."""
        if not self._is_fetching:
            return  # Already reset or not started

        logger.debug(
            f"Check completion ({trigger_reason}): "
            f"Initial Done? {self._initial_crawl_finished_flag}, "
            f"Processing Finished ({self._processing_tasks_finished_count}/{self._total_sources_to_process})"
        )

        # Check if the initial crawl worker's run() method has finished AND
        # if the number of finished/cancelled processing tasks matches the total number expected.
        is_complete = (
            self._initial_crawl_finished_flag
            and self._processing_tasks_finished_count >= self._total_sources_to_process
        )

        # OR, check if cancellation was requested and the initial worker finished
        is_cancelled = (
            self._active_initial_crawler is not None
            and self._active_initial_crawler.is_cancelled()
            and self._initial_crawl_finished_flag
        )

        if is_complete or is_cancelled:
            final_message = "Finished"
            if is_cancelled:
                final_message = "Cancelled"
            elif self._processing_tasks_finished_count < self._total_sources_to_process:
                final_message = "Finished (Some tasks may have failed)"

            if self._is_closing:
                logger.info(
                    f"All fetch tasks {final_message.lower()}, but NewsTab is closing. Skipping final _load_news."
                )
                self._reset_fetch_state(f"{final_message} (Closing)")
                return

            logger.info(
                f"All fetch and processing tasks are complete/cancelled. Status: {final_message}. Queueing _load_news."
            )
            self._reset_fetch_state(final_message)
            # Refresh the news list using invokeMethod safely on the main thread
            QMetaObject.invokeMethod(
                self.news_model, "select", Qt.ConnectionType.QueuedConnection
            )

    @Slot(str)
    def _show_llm_stream_dialog(self, url: str):
        """Creates or shows the LLM result dialog for the given URL."""
        dialog_title = "LLM Analysis Output"
        source_name = "Unknown Source"

        if self.fetch_progress_dialog and url in self.fetch_progress_dialog.sources_map:
            row = self.fetch_progress_dialog.sources_map[url]
            name_item = self.fetch_progress_dialog.table.item(
                row, FetchProgressDialog.COL_NAME
            )
            if name_item:
                source_name = name_item.text()
                dialog_title = f"LLM Analysis - {source_name}"

        if url in self.llm_stream_dialogs:
            dialog = self.llm_stream_dialogs[url]
            dialog.set_window_title(dialog_title)
        else:
            dialog = LlmStreamDialog(title=dialog_title, parent=self)
            dialog.finished.connect(lambda *args, u=url: self._llm_dialog_closed(u))
            self.llm_stream_dialogs[url] = dialog

        full_result = self.analysis_results_cache.get(url)
        placeholder_message = f"<p style='color: #555;'>LLM analysis result is not available for this source ({source_name})...</p>"  # Simplified

        content_to_display = placeholder_message
        if full_result and isinstance(full_result, str) and full_result.strip():
            if (
                "Error during processing:" not in full_result
                and "Analysis result not available" not in full_result
            ):
                content_to_display = full_result

        dialog.clear_display()
        dialog.set_content(content_to_display)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _llm_dialog_closed(self, url: str):
        """Slot called when an LLM stream dialog is closed."""
        if url in self.llm_stream_dialogs:
            logger.debug(f"LLM result dialog for {url} closed.")
            del self.llm_stream_dialogs[url]

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        # 刷新列表
        act_refresh = menu.addAction("Refresh List")
        act_refresh.triggered.connect(self._refresh_all)
        # 获取选中行
        indexes = self.news_table.selectionModel().selectedRows()
        # 分析功能
        act_analyze = menu.addAction("Analyze Selected")
        act_analyze.setEnabled(bool(indexes))
        act_analyze.triggered.connect(self._analyze_selected)
        # 编辑
        act_edit = menu.addAction("Edit")
        act_edit.setEnabled(len(indexes) == 1)
        act_edit.triggered.connect(self._edit_news)
        # 删除
        act_delete = menu.addAction("Delete Selected")
        act_delete.setEnabled(bool(indexes))
        act_delete.triggered.connect(self._delete_news)
        menu.exec(self.news_table.viewport().mapToGlobal(pos))

    def _analyze_selected(self):
        indexes = self.news_table.selectionModel().selectedRows()
        if not indexes:
            return
        for idx in indexes:
            src = self.proxy_model.mapToSource(idx)
            col_id = self.news_model.fieldIndex("id")
            nid = self.news_model.data(self.news_model.index(src.row(), col_id))
            news = self._news_service.get_news_by_id(nid)
            if news and news.get("link"):
                self._show_llm_stream_dialog(news.get("link"))

    # --- Helper Methods (_get_selected_source_info_for_fetch remains the same) ---
    def _get_selected_source_info_for_fetch(self) -> List[Dict[str, Any]]:
        selected_sources: List[Dict[str, Any]] = []
        selected_category_id = self.category_filter.currentData()
        selected_source_name = self.source_filter.currentText()

        if not self.sources_cache:
            try:
                logger.debug(
                    "Sources cache empty, loading all sources for fetch selection."
                )
                self.sources_cache = self._news_service.get_all_sources()
            except Exception as e:
                logger.error(f"Failed to load sources cache for fetch: {e}")
                QMessageBox.critical(
                    self, "Error", f"Failed to load news sources: {str(e)}"
                )
                return []

        all_sources_in_cache = self.sources_cache
        source_list_details = []

        if selected_category_id != -1:
            filtered_by_cat = [
                s
                for s in all_sources_in_cache
                if s.get("category_id") == selected_category_id
            ]
            if selected_source_name != "All":
                source_list_details = [
                    s for s in filtered_by_cat if s.get("name") == selected_source_name
                ]
            else:
                source_list_details = filtered_by_cat
        elif selected_source_name != "All":
            source_list_details = [
                s for s in all_sources_in_cache if s.get("name") == selected_source_name
            ]
        else:
            source_list_details = all_sources_in_cache

        # Validate and structure the final list
        for s in source_list_details:
            required_keys = ["id", "url", "name", "category_id", "category_name"]
            if all(key in s for key in required_keys):
                selected_sources.append(
                    {
                        "id": s["id"],
                        "url": s["url"],
                        "name": s["name"],
                        "category_id": s["category_id"],
                        "category_name": s["category_name"],
                    }
                )
            else:
                logger.warning(
                    f"Source missing required keys, skipped: {s.get('name', 'N/A')} - Keys: {list(s.keys())}"
                )

        logger.info(
            f"Selected {len(selected_sources)} sources for fetch based on filters."
        )
        return selected_sources

    # --- Other Methods ---
    def _delete_news(self):
        """Delete selected news items from the model."""
        selected_proxy_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Notice", "Please select news items to delete.")
            return

        news_to_delete: List[Tuple[int, str]] = []
        news_to_delete_titles: List[str] = []  # For display in confirmation dialog
        id_col_index = self.news_model.fieldIndex("id")
        title_col_index = self.news_model.fieldIndex(
            "title"
        )  # Get title for confirmation

        if id_col_index == -1:
            QMessageBox.critical(self, "Error", "Unable to find ID column.")
            return

        news_to_delete_ids: List[int] = []
        for proxy_index in selected_proxy_indexes:
            source_index = self.proxy_model.mapToSource(proxy_index)
            news_id_variant = self.news_model.data(
                self.news_model.index(source_index.row(), id_col_index)
            )
            news_id = news_id_variant if isinstance(news_id_variant, int) else None

            if news_id is not None:
                news_to_delete_ids.append(news_id)
                if title_col_index != -1:
                    title_variant = self.news_model.data(
                        self.news_model.index(source_index.row(), title_col_index)
                    )
                    news_to_delete_titles.append(str(title_variant))
                else:
                    news_to_delete_titles.append(f"ID {news_id}")

        if not news_to_delete_ids:
            QMessageBox.warning(
                self, "Notice", "Failed to retrieve valid IDs for selected items."
            )
            return

        confirm_msg = f"Are you sure you want to delete {len(news_to_delete_ids)} selected news item(s)?"
        if len(news_to_delete_ids) == 1:
            confirm_msg = (
                f"Are you sure you want to delete '{news_to_delete_titles[0]}'?"
            )

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            errors = []
            for news_id, news_title in zip(news_to_delete_ids, news_to_delete_titles):
                try:
                    if self._news_service.delete_news(news_id):
                        logger.info(f"Deleted news ID: {news_id} ('{news_title}')")
                        deleted_count += 1
                    else:
                        logger.error(f"Service failed deleting news ID: {news_id}")
                        errors.append(f"Failed deleting '{news_title}' (Service Error)")
                except Exception as e:
                    logger.error(
                        f"Error calling delete_news for ID {news_id}: {e}",
                        exc_info=True,
                    )
                    errors.append(f"Error deleting '{news_title}': {e}")

            if errors:
                QMessageBox.warning(
                    self,
                    "Partial Success",
                    f"Deleted {deleted_count} items.\nErrors occurred:\n- "
                    + "\n- ".join(errors),
                )
            elif deleted_count > 0:
                logger.info("Refreshing news model after deletion.")
                if not self.news_model.select():
                    error = self.news_model.lastError()
                    logger.error(
                        f"Failed to refresh news model after deletion: {error.text()}"
                    )
                    QMessageBox.warning(
                        self,
                        "Refresh Failed",
                        f"Failed to refresh list after deletion: {error.text()}",
                    )
            else:
                QMessageBox.warning(self, "No Action", "No news items were deleted.")

    def _edit_news(self):
        if self._is_fetching:
            return
        QMessageBox.information(
            self, "Notice", "Edit functionality is not implemented."
        )

    def _on_selection_changed(self, selected, deselected):
        indexes = self.news_table.selectionModel().selectedRows()

        if not indexes:
            self.preview_text.clear()
            return

        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)

        id_col_index = self.news_model.fieldIndex("id")
        if id_col_index == -1:
            logger.error("Could not find 'id' column in news model.")
            self.preview_text.setText("Error: Unable to find ID column.")
            return

        news_id_variant = self.news_model.data(
            self.news_model.index(source_index.row(), id_col_index)
        )
        news_id = news_id_variant if isinstance(news_id_variant, int) else None

        if news_id is not None:
            # --- Get complete data from Service ---
            try:
                news = self._news_service.get_news_by_id(news_id)
                if news:
                    preview_html = f"<h3>{news.get('title', 'N/A')}</h3>"
                    preview_html += (
                        f"<p>{news.get('source_name', '')} {news.get('date', '')}<br>"
                    )
                    link = news.get("link", "#")
                    preview_html += f"<a href='{link}'>{link}</a></p>"
                    preview_html += f"<p>{news.get('summary', '')}</p>"
                    self.preview_text.setHtml(preview_html)
                else:
                    self.preview_text.setText(
                        f"Unable to load preview data (ID: {news_id}, not found)"
                    )
            except Exception as e:
                logger.error(
                    f"Error fetching news details for preview (ID: {news_id}): {e}",
                    exc_info=True,
                )
                self.preview_text.setText(f"Error loading preview (ID: {news_id})")
        else:
            self.preview_text.setText(
                f"Unable to retrieve valid ID for selected row (Row: {source_index.row()})"
            )

    def _apply_filters(self):
        """
        Apply filters to the news model.
        """
        search_text = self.search_input.text().strip()

        # 1. Use QSqlTableModel's setFilter to handle Category and Source
        filter_parts = []
        category_id = self.category_filter.currentData()
        source_text = self.source_filter.currentText()
        if category_id != -1:
            filter_parts.append(f"category_id = {category_id}")
        if source_text != "All":
            filter_parts.append(f"source_name = '{source_text.replace('\"', '\"\"')}'")

        sql_filter = " AND ".join(filter_parts)
        self.news_model.setFilter(sql_filter)

        # 2. Use QSortFilterProxyModel to handle text search
        # -1 indicates searching across all columns
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterRegularExpression(search_text)

        # Reload data from the database with the applied SQL filter
        if not self.news_model.select():
            error = self.news_model.lastError()
            logger.error(
                f"Failed to select data after applying filters: {error.text()}"
            )

    # --- Cleanup ---
    def perform_cleanup(self) -> bool:
        """Ensure threads and signals are cleaned up gracefully."""
        logger.info("NewsTab close event triggered. Preparing to stop workers...")
        self._is_closing = True  # Set flag immediately

        # 1. Request cancellation of the Initial Crawler Worker (if active)
        cancelled_initial = False
        if self._active_initial_crawler:
            logger.info("Requesting cancellation for active InitialCrawlerWorker...")
            try:
                self._active_initial_crawler.cancel()
                cancelled_initial = True  # Assume request sent
            except Exception as e:
                logger.error(f"Error requesting InitialCrawlerWorker cancellation: {e}")
            # We don't wait here, just request it. waitForDone will handle waiting.
        else:
            cancelled_initial = True  # No worker was active

        # 2. Disconnect signals FIRST
        logger.debug("Attempting to disconnect worker signals...")
        signal_pairs = [
            (self.signals.initial_crawl_status, self._handle_initial_crawl_status),
            (self.signals.html_ready, self._handle_html_ready),
            (
                self.signals.initial_crawl_finished,
                self._handle_initial_crawl_phase_finished,
            ),
            (self.signals.processing_status, self._handle_processing_status),
            (self.signals.processing_finished, self._handle_processing_finished),
        ]
        for signal, slot in signal_pairs:
            try:
                signal.disconnect(slot)
                logger.debug(f"Successfully disconnected slot {slot.__name__}.")
            except RuntimeError:
                logger.debug(
                    f"Signal likely already disconnected for slot {slot.__name__}."
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error disconnecting signal for {slot.__name__}: {e}",
                    exc_info=True,
                )
        logger.info("Worker signals disconnected.")

        # 3. Close Progress Dialog
        if self.fetch_progress_dialog and self.fetch_progress_dialog.isVisible():
            logger.debug("Closing fetch progress dialog.")
            try:
                self.fetch_progress_dialog.close()
            except RuntimeError as e:
                logger.warning(
                    f"Error closing fetch progress dialog (already deleted?): {e}"
                )

        # 4. Stop the persistent ProcessingWorker QThread
        logger.info("Stopping ProcessingWorker thread...")
        worker_stopped = False
        if self.processing_worker and self.processing_worker.isRunning():
            self.processing_worker.stop()  # Request internal loop stop/cancel
            self.processing_worker.quit()  # Tell QThread to quit
            logger.info("Waiting for ProcessingWorker QThread to finish...")
            if not self.processing_worker.wait(7000):  # Wait up to 7 seconds
                logger.warning(
                    "ProcessingWorker QThread did not terminate gracefully within timeout."
                )
            else:
                worker_stopped = True
                logger.info("ProcessingWorker QThread finished.")
        else:
            logger.info("ProcessingWorker QThread was not running or already stopped.")
            worker_stopped = True

        # 5. Wait for QThreadPool Runnables (including InitialCrawlerWorker)
        # This wait should now be more effective as cancellation was requested first.
        logger.info("Waiting for global QThreadPool to finish...")
        QThreadPool.globalInstance().waitForDone(
            10000
        )  # Wait up to 10 seconds for runnables
        logger.info("Global QThreadPool finished.")

        logger.info("NewsTab cleanup finished.")
        # Return True if both cancellation was requested/not needed and worker stopped
        return cancelled_initial and worker_stopped
