#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
News Management Tab
Implements news retrieval, viewing, deletion and editing functionality (using Service Layer)
Refactored for threaded fetching and detailed progress reporting.
"""

import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any, Callable
import threading  # Import threading for Event

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
    QTableWidget,
    QTableWidgetItem,  # Added QTableWidget elements
)
from PySide6.QtCore import (
    Qt,
    QSortFilterProxyModel,
    Signal,
    Slot,
    QThreadPool,
    QRunnable,
    QObject,
    QMetaObject,
    Q_ARG,
    QThread,
    QTimer,
)
from PySide6.QtGui import QStandardItemModel, QStandardItem

from src.services.news_service import NewsService

from src.core.crawler import PlaywrightCrawler  # Make sure crawler is imported
from src.ui.dialogs.fetch_progress_dialog import FetchProgressDialog
from src.ui.dialogs.llm_stream_dialog import LlmStreamDialog

# Assume FetchProgressDialog and LlmStreamDialog classes are defined elsewhere


logger = logging.getLogger(__name__)


# --- Keep WorkerSignals class definition here ---
class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""

    # Initial Crawl Signals (emitted by InitialCrawlerWorker)
    html_ready = Signal(str, str, dict)
    initial_crawl_status = Signal(str, str)
    initial_crawl_finished = Signal()  # Signal when the *initial crawl phase* is done

    # Processing Signals (emitted by SingleProcessingWorker)
    processing_status = Signal(str, str)  # url, status_details
    processing_finished = Signal(
        str, str, str, str
    )  # url, final_status, details, analysis_result

    # Signal to indicate ALL processing tasks are completed
    all_processing_complete = Signal()


# --- Runnable for Initial Crawling (Modified for Cancellation) ---
class InitialCrawlerWorker(QRunnable):
    """
    Worker thread using QRunnable for performing the initial crawl for ALL selected URLs.
    Emits html_ready for each successfully crawled URL as it becomes available.
    Now supports external cancellation.
    """

    def __init__(
        self,
        urls_with_info: List[Dict[str, Any]],  # Takes the full list
        parent_signals: WorkerSignals,
    ):
        super().__init__()
        self.urls_with_info = urls_with_info
        self.signals = parent_signals
        self._cancel_event = threading.Event()  # Cancellation flag
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._crawler_instance: Optional[PlaywrightCrawler] = None
        self._main_task: Optional[asyncio.Task] = None

    def is_cancelled(self):
        """Check if cancellation has been requested."""
        return self._cancel_event.is_set()

    async def _shutdown_crawler(self):
        """Gracefully shuts down the crawler instance."""
        if self._crawler_instance:
            logger.info(
                f"InitialCrawlerWorker ({threading.get_ident()}) shutting down Playwright crawler..."
            )
            await self._crawler_instance.shutdown()
            self._crawler_instance = None
            logger.info(
                f"InitialCrawlerWorker ({threading.get_ident()}) Playwright crawler shut down."
            )

    @Slot()
    def run(self):
        worker_id = threading.get_ident()  # Get thread ID for logging
        logger.info(
            f"InitialCrawlerWorker ({worker_id}) started for {len(self.urls_with_info)} URLs."
        )

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Create crawler instance here
            self._crawler_instance = PlaywrightCrawler()

            # --- Create and run the main async task ---
            self._main_task = self._loop.create_task(self._crawl_tasks_async())
            self._loop.run_until_complete(self._main_task)

        except asyncio.CancelledError:
            logger.info(f"InitialCrawlerWorker ({worker_id}) main task was cancelled.")
            # Ensure crawler is shut down if cancellation happened during run_until_complete
            if self._loop and self._loop.is_running():
                self._loop.run_until_complete(self._shutdown_crawler())
            elif self._crawler_instance:
                logger.warning(
                    f"InitialCrawlerWorker ({worker_id}) loop not running, cannot guarantee async crawler shutdown."
                )

        except Exception as e:
            logger.error(
                f"({worker_id}) Exception running InitialCrawlerWorker event loop: {e}",
                exc_info=True,
            )
            # Try to shutdown crawler on general exceptions too
            if self._loop and self._loop.is_running():
                self._loop.run_until_complete(self._shutdown_crawler())

        finally:
            # --- Loop Cleanup ---
            if self._loop:
                try:
                    # Ensure all pending tasks are handled or cancelled before closing
                    pending = asyncio.all_tasks(self._loop)
                    tasks_to_cancel = [
                        task
                        for task in pending
                        if task is not self._main_task and not task.done()
                    ]
                    if tasks_to_cancel:
                        logger.info(
                            f"({worker_id}) Cancelling {len(tasks_to_cancel)} leftover tasks in initial crawl loop..."
                        )
                        for task in tasks_to_cancel:
                            task.cancel()
                        # Allow cancellations to process
                        self._loop.run_until_complete(
                            asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                        )

                    # Shutdown async generators if needed by the loop policy
                    if hasattr(self._loop, "shutdown_asyncgens"):
                        logger.debug(
                            f"({worker_id}) Shutting down async generators in initial crawl loop..."
                        )
                        self._loop.run_until_complete(self._loop.shutdown_asyncgens())

                    logger.debug(f"({worker_id}) Closing initial crawl event loop...")
                    self._loop.close()
                    logger.info(f"({worker_id}) Initial crawl event loop closed.")
                except Exception as loop_close_err:
                    logger.error(
                        f"({worker_id}) Error closing initial crawl event loop: {loop_close_err}"
                    )
            asyncio.set_event_loop(None)  # Clean up policy

            # Emit finished signal AFTER the loop completes/closes
            # Check cancellation flag one last time before emitting finished signal
            if not self.is_cancelled():
                self.signals.initial_crawl_finished.emit()
            else:
                logger.info(
                    f"({worker_id}) Initial crawl was cancelled, finished signal suppressed."
                )
            logger.info(f"InitialCrawlerWorker ({worker_id}) run method finished.")

    async def _crawl_tasks_async(self):
        """The main async method that performs crawling."""
        worker_id = threading.get_ident()
        if not self._crawler_instance:
            logger.error(
                f"({worker_id}) Crawler instance not available in _crawl_tasks_async."
            )
            return

        urls_to_crawl = [info["url"] for info in self.urls_with_info]
        source_map = {info["url"]: info for info in self.urls_with_info}
        tasks_processed_count = 0

        try:
            # Process all URLs using the async generator
            async for result in self._crawler_instance.process_urls(
                urls_to_crawl, scroll_pages=True
            ):
                # --- Check for cancellation inside the loop ---
                if self.is_cancelled():
                    logger.info(
                        f"Initial crawl ({worker_id}) cancelled during URL processing loop."
                    )
                    # Raise CancelledError to break out and trigger cleanup
                    raise asyncio.CancelledError()

                tasks_processed_count += 1
                url = result.get("original_url")
                html = result.get("content")
                error = result.get("error")
                source_info = source_map.get(url)

                if not source_info:
                    logger.warning(
                        f"({worker_id}) Crawler returned result for unknown URL: {url}"
                    )
                    continue

                # --- Emit signals (check cancellation before emitting) ---
                if self.is_cancelled():
                    break  # Check again before emitting

                if error:
                    logger.warning(f"({worker_id}) Crawl failed for {url}: {error}")
                    self.signals.initial_crawl_status.emit(
                        url, f"Crawled - Failed: {error}"
                    )
                elif html:
                    logger.debug(
                        f"({worker_id}) Crawl success for {url}. Emitting html_ready."
                    )
                    self.signals.initial_crawl_status.emit(url, "Crawled - Success")
                    self.signals.html_ready.emit(url, html, source_info)
                else:
                    logger.warning(f"({worker_id}) Crawl failed for {url}: No content")
                    self.signals.initial_crawl_status.emit(
                        url, "Crawled - Failed: No content"
                    )

        except asyncio.CancelledError:
            # This is expected if cancel() was called
            logger.info(f"({worker_id}) _crawl_tasks_async caught CancelledError.")
            # No need to re-raise, finally block will handle cleanup
        except Exception as e:
            logger.error(
                f"({worker_id}) Error in InitialCrawlerWorker _crawl_tasks_async: {e}",
                exc_info=True,
            )
        finally:
            # Ensure crawler is shut down when this task finishes or is cancelled
            await self._shutdown_crawler()
            logger.info(
                f"({worker_id}) Initial crawl task generator finished or was cancelled after processing {tasks_processed_count} results."
            )

    def cancel(self):
        """Requests cancellation of the worker."""
        worker_id = threading.get_ident()  # May not be the worker thread's ID here
        logger.info(
            f"InitialCrawlerWorker cancellation requested (requested by thread {worker_id})."
        )
        self._cancel_event.set()  # Set the event first

        # If the loop and task are running, attempt to cancel the main async task
        if (
            self._loop
            and self._loop.is_running()
            and self._main_task
            and not self._main_task.done()
        ):
            logger.info(
                f"Requesting cancellation of main asyncio task in InitialCrawlerWorker via call_soon_threadsafe."
            )
            # Schedule the cancellation on the worker's loop thread-safely
            self._loop.call_soon_threadsafe(self._main_task.cancel)
        elif self._loop:
            # If loop exists but isn't running or task is done, still try to stop the loop
            logger.info(
                f"Requesting loop stop in InitialCrawlerWorker via call_soon_threadsafe (task might be done/loop stopping)."
            )
            self._loop.call_soon_threadsafe(self._loop.stop)


# --- ProcessingWorker QThread (Remains the same) ---
class ProcessingWorker(QThread):
    """
    Dedicated QThread that runs an asyncio event loop to process analysis tasks concurrently.
    """

    def __init__(self, news_service: NewsService, signals: WorkerSignals, parent=None):
        super().__init__(parent)
        self.news_service = news_service
        self.signals = signals
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_ready = threading.Event()  # To signal when the loop is running
        self._futures = set()  # Keep track of submitted tasks if cancellation needed
        logger.info("ProcessingWorker (QThread) initialized.")

    def run(self):
        """Starts the asyncio event loop."""
        thread_id = threading.get_ident()
        logger.info(f"ProcessingWorker ({thread_id}) thread starting...")
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._is_ready.set()  # Signal that the loop is set up
            logger.info(f"ProcessingWorker ({thread_id}) event loop running...")
            self.loop.run_forever()  # Keep the loop running
        except Exception as e:
            logger.error(
                f"ProcessingWorker ({thread_id}) event loop error: {e}", exc_info=True
            )
        finally:
            logger.info(f"ProcessingWorker ({thread_id}) event loop stopping...")
            if self.loop:
                # Cleanup before closing loop (cancel pending tasks)
                try:
                    # Gather all tasks remaining in the loop
                    pending_tasks = asyncio.all_tasks(self.loop)
                    tasks_to_cancel = [
                        task for task in pending_tasks if not task.done()
                    ]

                    if tasks_to_cancel:
                        logger.info(
                            f"Cancelling {len(tasks_to_cancel)} remaining tasks in loop ({thread_id})..."
                        )
                        for task in tasks_to_cancel:
                            task.cancel()

                        # Give cancelled tasks a moment to process cancellation
                        # Use run_until_complete carefully if loop is stopping
                        async def gather_cancel():
                            await asyncio.gather(
                                *tasks_to_cancel, return_exceptions=True
                            )

                        if self.loop.is_running():
                            self.loop.run_until_complete(gather_cancel())

                    # Ensure async generators are properly closed
                    if hasattr(self.loop, "shutdown_asyncgens"):
                        logger.debug(f"Shutting down async generators ({thread_id})...")
                        # Use run_until_complete carefully if loop is stopping
                        if self.loop.is_running():
                            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                        logger.debug(f"Async generators shut down ({thread_id}).")

                    # Close the loop
                    if not self.loop.is_closed():
                        logger.debug(f"Closing event loop ({thread_id})...")
                        self.loop.close()
                        logger.info(
                            f"ProcessingWorker ({thread_id}) event loop closed."
                        )
                    else:
                        logger.debug(
                            f"ProcessingWorker ({thread_id}) loop already closed."
                        )
                except Exception as close_err:
                    logger.error(
                        f"ProcessingWorker ({thread_id}) error during loop cleanup: {close_err}",
                        exc_info=True,
                    )
            asyncio.set_event_loop(None)
            logger.info(f"ProcessingWorker ({thread_id}) thread finished.")

    def wait_until_ready(self, timeout=5):
        """Blocks until the event loop is running."""
        if not self._is_ready.wait(timeout):
            raise TimeoutError(
                f"ProcessingWorker event loop did not start within {timeout}s"
            )

    async def _do_process_task(
        self, url: str, html_content: str, source_info: Dict[str, Any]
    ):
        """The actual async task coroutine that performs the processing."""
        task_id = (
            asyncio.current_task().get_name()
            if hasattr(asyncio.current_task(), "get_name")
            else url[:20]
        )
        logger.debug(f"Processing task starting for {url} on worker loop ({task_id}).")
        analysis_result_md = ""
        final_status = "Error"
        details = "Processing task failed unexpectedly"

        try:
            # --- Check for cancellation at the beginning ---
            if asyncio.current_task().cancelled():
                logger.info(f"Processing task for {url} cancelled before start.")
                raise asyncio.CancelledError()

            # Define status callback lambda to emit signal
            def status_callback(u, s, d):
                # Check cancellation before emitting signal from potentially stopped loop
                if (
                    self.loop
                    and self.loop.is_running()
                    and not asyncio.current_task().cancelled()
                ):
                    self.signals.processing_status.emit(u, f"{s}: {d}")

            # Call the async service method
            saved_count, analysis_result_md, error_obj = (
                await self.news_service._process_html_and_analyze(
                    url,
                    html_content,
                    source_info,
                    status_callback,
                )
            )

            # --- Check for cancellation after main processing ---
            if asyncio.current_task().cancelled():
                logger.info(f"Processing task for {url} cancelled after service call.")
                raise asyncio.CancelledError()

            if error_obj:
                final_status = "Error"
                details = f"Processing Failed: {error_obj}"
                logger.error(
                    f"Error processing {url} in service: {error_obj}",
                    exc_info=(isinstance(error_obj, Exception)),
                )
            else:
                final_status = "Complete"
                details = f"Saved {saved_count} items."

        except asyncio.CancelledError:
            final_status = "Cancelled"
            details = "Task was cancelled during execution."
            logger.info(f"Processing task for {url} ({task_id}) was cancelled.")
            # analysis_result_md remains empty or as it was before cancellation
            # Note: Don't re-raise CancelledError here, let finally handle it.

        except Exception as e:
            final_status = "Error"
            details = f"Unexpected processing task error: {e}"
            analysis_result_md = f"Error during processing: {e}"  # Store error details
            logger.error(
                f"Unexpected error processing task for {url} ({task_id}): {e}",
                exc_info=True,
            )
        finally:
            # Emit the finished signal for this task, even if cancelled
            logger.debug(
                f"Processing task finished/cancelled for {url} ({task_id}). Status: {final_status}"
            )
            # Ensure signal emission happens only if loop is still running
            if self.loop and self.loop.is_running():
                self.signals.processing_finished.emit(
                    url,
                    final_status,
                    details,
                    analysis_result_md if analysis_result_md else "",
                )
            else:
                logger.warning(f"Skipping final signal for {url} as loop is stopped.")

    def submit_task(self, url: str, html_content: str, source_info: Dict[str, Any]):
        """
        Submits a processing task (coroutine) to the running event loop.
        This method MUST be called from a thread-safe context (e.g., main GUI thread via signals).
        """
        if self.loop and self.loop.is_running():
            logger.debug(f"Submitting processing task for {url} to worker event loop.")
            # Create the coroutine object
            coro = self._do_process_task(url, html_content, source_info)
            # Schedule it using run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            self._futures.add(future)
            # Optional: Remove future from set when done
            future.add_done_callback(lambda f: self._futures.discard(f))
            return future  # Return future if caller needs to track it
        else:
            logger.error(
                f"Cannot submit task for {url}: ProcessingWorker loop is not running."
            )
            # Emit an error signal?
            self.signals.processing_finished.emit(
                url, "Error", "Processing thread not ready", ""
            )
            return None

    def stop(self):
        """Stops the event loop and the thread, cancelling pending tasks."""
        thread_id = threading.get_ident()
        logger.info(f"Stop requested for ProcessingWorker ({thread_id}).")
        if self.loop and self.loop.is_running():
            logger.debug(
                f"Requesting cancellation of {len(self._futures)} tracked futures ({thread_id})."
            )
            # 1. Cancel tracked futures submitted via run_coroutine_threadsafe
            # Note: This requests cancellation; the coroutine needs to handle it.
            cancelled_count = 0
            for future in list(self._futures):  # Iterate over a copy
                if not future.done():
                    future.cancel()
                    cancelled_count += 1
            if cancelled_count > 0:
                logger.info(f"Requested cancellation for {cancelled_count} futures.")

            # 2. Request the loop to stop *after* submitting cancellation requests
            logger.debug(
                f"Requesting event loop stop via call_soon_threadsafe ({thread_id})."
            )
            # Stop the loop from the outside thread
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            logger.warning(
                f"ProcessingWorker ({thread_id}) loop not running or already stopped."
            )


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

    # --- UI Setup, Load News, Load Filters, Filter Handling (Mostly Unchanged) ---
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

        # Add a Cancel button (initially hidden/disabled)
        self.cancel_button = QPushButton("Cancel Fetch")
        self.cancel_button.setToolTip("Attempt to cancel the ongoing fetch operation.")
        self.cancel_button.clicked.connect(self._cancel_fetch_handler)
        self.cancel_button.setVisible(False)  # Start hidden
        toolbar_layout.addWidget(self.cancel_button)

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

        self.analyze_button = QPushButton("Analyze Selected")
        self.analyze_button.setToolTip(
            "Analysis now happens automatically during Fetch News."
        )
        self.analyze_button.setEnabled(False)
        bottom_toolbar.addWidget(self.analyze_button)

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
        self.category_filter.currentIndexChanged.connect(
            self._on_category_filter_changed
        )
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)
        self.news_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    def _setup_table_model(self):
        self.model = QStandardItemModel(0, 4, self)
        self.model.setHorizontalHeaderLabels(
            ["Title", "Source", "Category", "Published Date"]
        )
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Filter on all columns
        self.news_table.setModel(self.proxy_model)

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
        logger.info("Loading news data...")
        try:
            self.model.removeRows(0, self.model.rowCount())
            self.news_data.clear()
            self.preview_text.clear()
            news_list = self._news_service.get_all_news(limit=1000)
            logger.info(f"Retrieved {len(news_list)} news items from service.")
            for news in news_list:
                news_id = news.get("id")
                if news_id is None:
                    continue
                self.news_data[news_id] = news

                title_item = QStandardItem(news.get("title", "N/A"))
                source_item = QStandardItem(news.get("source_name", "N/A"))
                category_item = QStandardItem(news.get("category_name", "N/A"))
                date_item = QStandardItem(news.get("date", ""))
                title_item.setData(news_id, Qt.ItemDataRole.UserRole)  # Store ID

                for item in [title_item, source_item, category_item, date_item]:
                    item.setEditable(False)
                self.model.appendRow(
                    [title_item, source_item, category_item, date_item]
                )

            self._apply_filters()
            self.news_table.resizeColumnsToContents()
            self.news_table.horizontalHeader().setStretchLastSection(True)
            logger.info(
                f"Populated table with {self.proxy_model.rowCount()} visible news items."
            )
            self.news_data_changed.emit()
        except Exception as e:
            logger.error(f"Failed to load news: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load news list: {str(e)}")

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
                f"Source filter updated with {self.source_filter.count() -1} sources."
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
            self.cancel_button.setVisible(True)  # Show cancel button
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

    def _cancel_fetch_handler(self):
        """Handles clicks on the Cancel Fetch button."""
        if not self._is_fetching:
            logger.warning("Cancel fetch requested, but no fetch is active.")
            return

        logger.info("User requested fetch cancellation.")
        self.cancel_button.setEnabled(False)  # Prevent double clicks
        self.cancel_button.setText("Cancelling...")

        # --- Signal Cancellation to Workers ---
        # 1. Cancel Initial Crawler Worker (if active)
        if self._active_initial_crawler:
            logger.info("Requesting cancellation for InitialCrawlerWorker...")
            self._active_initial_crawler.cancel()
            # Note: We don't immediately know if it succeeded, rely on flags/counts

        # 2. Cancel Processing Worker Tasks (indirectly via its stop/cancel mechanism)
        # The ProcessingWorker's stop method already handles cancelling its internal futures.
        # We don't call stop() here, as that's for full cleanup.
        # If we wanted finer control, ProcessingWorker could have a specific `cancel_pending_tasks` method.
        # For now, rely on the fact that html_ready won't be emitted for cancelled crawls.

        # Update progress dialog?
        if self.fetch_progress_dialog:
            self.fetch_progress_dialog.setWindowTitle("News Fetch - Cancelling...")

        # The state reset will happen when workers acknowledge cancellation or finish.
        # We might want to force a reset after a timeout if workers don't respond.

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
        self.cancel_button.setVisible(False)  # Hide cancel button
        self.cancel_button.setText("Cancel Fetch")  # Reset text
        self.cancel_button.setEnabled(True)  # Re-enable for next time

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
                self, "_load_news", Qt.ConnectionType.QueuedConnection
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
            # self.llm_stream_dialogs[url].deleteLater() # Optional: explicitly delete
            del self.llm_stream_dialogs[url]

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

    # --- Other Methods (Delete, Edit, Selection, Filters - Unchanged) ---
    def _delete_news(self):
        if self._is_fetching:
            QMessageBox.warning(
                self, "Busy", "A task is currently running. Please wait."
            )
            return

        selected_proxy_indexes = self.news_table.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Notice", "Please select news items to delete.")
            return

        news_to_delete: List[Tuple[int, str]] = []
        for proxy_index in selected_proxy_indexes:
            source_index = self.proxy_model.mapToSource(proxy_index)
            news_id = self.model.item(source_index.row(), 0).data(
                Qt.ItemDataRole.UserRole
            )
            news_title = self.model.item(source_index.row(), 0).text()
            if news_id is not None:
                news_to_delete.append((news_id, news_title))

        if not news_to_delete:
            QMessageBox.critical(
                self, "Error", "Could not retrieve IDs for selected news."
            )
            return

        confirm_msg = f"Are you sure you want to delete {len(news_to_delete)} selected news item(s)?"
        if len(news_to_delete) == 1:
            confirm_msg = f"Are you sure you want to delete '{news_to_delete[0][1]}'?"

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
            for news_id, news_title in news_to_delete:
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
                QMessageBox.information(
                    self, "Success", f"{deleted_count} news item(s) deleted."
                )
            else:
                QMessageBox.warning(self, "No Action", "No news items were deleted.")

            if deleted_count > 0:
                self._load_news()  # Refresh the list

    def _edit_news(self):
        if self._is_fetching:
            return
        QMessageBox.information(
            self, "Notice", "Edit functionality is not implemented."
        )

    def _on_selection_changed(self, selected, deselected):
        indexes = self.news_table.selectionModel().selectedRows()
        enable_buttons = bool(indexes)
        self.delete_button.setEnabled(enable_buttons)
        # self.edit_button remains disabled

        if not indexes:
            self.preview_text.clear()
            return

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
            preview_html += (
                f"<b>Summary:</b><p>{news.get('summary', 'No summary available.')}</p>"
            )
            analysis = news.get("analysis")
            if analysis:
                # Basic markdown-like formatting to HTML (can be improved)
                analysis_html = analysis.replace("\n", "<br>")
                preview_html += f"<hr><b>Analysis:</b><p>{analysis_html}</p>"
            self.preview_text.setHtml(preview_html)
        else:
            self.preview_text.setText(f"Cannot load preview data (ID: {news_id})")
            self.delete_button.setEnabled(
                False
            )  # Disable delete if data is inconsistent

    def _apply_filters(self):
        search_text = self.search_input.text().strip()
        selected_category_text = self.category_filter.currentText()
        selected_source_text = self.source_filter.currentText()

        source_model = self.proxy_model.sourceModel()
        if not source_model:
            return

        visible_count = 0
        for row in range(source_model.rowCount()):
            category_matches = True
            if selected_category_text != "All":
                cat_item = source_model.item(row, 2)  # Category column index
                category_matches = (
                    cat_item and cat_item.text() == selected_category_text
                )

            source_matches = True
            if selected_source_text != "All":
                src_item = source_model.item(row, 1)  # Source column index
                source_matches = src_item and src_item.text() == selected_source_text

            text_matches = True
            if search_text:
                text_matches = False
                # Search Title, Source, Category Name (use original model indices)
                # Also search Summary and Analysis (from news_data dict)
                news_id = source_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
                news_item_data = self.news_data.get(news_id)

                # Check table columns first
                for col_idx in [0, 1, 2]:  # Title, Source, Category
                    item = source_model.item(row, col_idx)
                    if item and search_text.lower() in item.text().lower():
                        text_matches = True
                        break
                # If not found in visible columns, check hidden data
                if not text_matches and news_item_data:
                    summary = news_item_data.get("summary", "")
                    analysis = news_item_data.get("analysis", "")
                    if (summary and search_text.lower() in summary.lower()) or (
                        analysis and search_text.lower() in analysis.lower()
                    ):
                        text_matches = True

            # Determine visibility based on all filters
            is_visible = category_matches and source_matches and text_matches

            # Hide/show the row in the view (TableView manages mapping from source model)
            self.news_table.setRowHidden(row, not is_visible)
            if is_visible:
                visible_count += 1

        logger.debug(
            f"Applied filters: Cat='{selected_category_text}', Src='{selected_source_text}', Search='{search_text}'. Visible rows: {visible_count}"
        )

    # --- Cleanup (Modified) ---
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
