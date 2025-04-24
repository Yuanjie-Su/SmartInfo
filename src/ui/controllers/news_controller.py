# src/ui/controllers/news_controller.py

"""
NewsController orchestrates the business logic and UI updates for the News Tab.

Core responsibilities:
- Interact with NewsService to load, refresh, and update news records.
- Initialize and configure QSqlTableModel and QSortFilterProxyModel for table display and filtering.
- Preload filter criteria (categories and sources) and emit filters_loaded signal to notify the UI.
- Manage asynchronous crawling and processing workflows using CrawlerWorker and ProcessorWorker:
    * Monitor fetch progress and processing status, emitting fetch_status_update for real-time updates.
    * Deliver processed analysis output via fetch_analysis_result.
    * Handle cancellation, errors, and notify final completion through fetch_process_finished.
- Cache analysis results for quick retrieval via get_analysis_result(url).
- Emit error_occurred signal with a title and message to report exceptions.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QModelIndex, Qt
from PySide6.QtSql import QSqlTableModel
from PySide6.QtCore import QSortFilterProxyModel

from src.services.news_service import NewsService
from src.db.connection import get_db  # Needed for QSqlTableModel
from src.db.schema_constants import NEWS_TABLE
from src.ui.workers.news_fetch_workers import (
    WorkerSignals,
    CrawlerWorker,  # Changed from InitialCrawlerWorker
    ProcessorWorker,  # Changed from ProcessingWorker
)

import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.utils.prompt import SYSTEM_PROMPT_ANALYZE_CONTENT

logger = logging.getLogger(__name__)


class TaskTracker:
    """Helper class to track task status and completion."""

    def __init__(self):
        self.active_urls = set()
        self.cancelled_urls = set()
        self.final_status_map = {}
        self.processed_count = 0
        self.total_count = 0
        self.initial_phase_complete = False

    def add_urls(self, urls: List[str]):
        """Add URLs to tracking."""
        added_count = 0
        for url in urls:
            if (
                url not in self.final_status_map
            ):  # Prevent duplicate additions affecting count
                self.active_urls.add(url)
                self.final_status_map[url] = False
                added_count += 1
        self.total_count = len(self.final_status_map)  # Base total count on map size
        logger.debug(
            f"TaskTracker: Added {added_count} URLs. New total count: {self.total_count}"
        )

    def remove_urls(self, urls: List[str]):
        """Remove URLs completely from tracking."""
        removed_count = 0
        for url in urls:
            self.active_urls.discard(url)  # Remove from active set
            if url in self.final_status_map:
                del self.final_status_map[url]  # Remove from status mapping
                removed_count += 1

        if removed_count > 0:
            # Update total count and processed count
            self.total_count = len(self.final_status_map)
            # Recalculate processed_count based on final_status_map
            self.processed_count = sum(
                1 for is_final in self.final_status_map.values() if is_final
            )

            logger.debug(
                f"TaskTracker: Removed {removed_count} URLs. New total count: {self.total_count}, New processed count: {self.processed_count}"
            )

    def mark_cancelled(self, urls: List[str]):
        """Mark URLs as cancelled."""
        self.cancelled_urls.update(urls)

    def mark_final_status(self, url: str, is_final: bool = True):
        """Mark a URL as having received its final status."""
        if url in self.final_status_map:
            # Only increment processed_count when status changes from non-final to final
            if not self.final_status_map[url] and is_final:
                self.processed_count += 1
            self.final_status_map[url] = is_final
        else:
            # If URL was previously removed, ignore
            logger.debug(
                f"TaskTracker: Ignoring final status for removed/unknown URL: {url}"
            )

    def is_complete(self) -> bool:
        """Check if all tasks are complete."""
        # Check if initial phase is complete and all URLs in final_status_map have final status
        all_final = (
            all(self.final_status_map.values()) if self.final_status_map else True
        )
        # Ensure total_count is based on current final_status_map size
        self.total_count = len(self.final_status_map)

        complete = (
            self.initial_phase_complete
            and all_final
            and self.total_count == self.processed_count
        )

        return complete

    def reset(self):
        """Reset all tracking data."""
        self.active_urls.clear()
        self.cancelled_urls.clear()
        self.final_status_map.clear()
        self.processed_count = 0
        self.total_count = 0
        self.initial_phase_complete = False


class NewsController(QObject):
    """Controller for the News Tab"""

    # Signals to update the View
    news_data_updated = Signal()
    filters_loaded = Signal(list, list)  # categories, sources for initial load
    fetch_status_update = Signal(str, str, bool)  # url, status_message, is_final
    fetch_analysis_result = Signal(str, str)  # url, analysis_markdown
    fetch_process_finished = Signal(
        str
    )  # Final status message (e.g., "Finished", "Cancelled")
    error_occurred = Signal(str, str)  # title, message
    analysis_chunk_received = Signal(int, str)  # news_id, chunk_text

    def __init__(self, news_service: NewsService, parent=None):
        super().__init__(parent)
        self._news_service = news_service
        self._is_fetching = False
        self._active_initial_crawler: Optional[CrawlerWorker] = None
        self._processing_worker: Optional[ProcessorWorker] = None
        self._worker_signals = (
            WorkerSignals()
        )  # Signals local to controller <-> worker comms
        self._analysis_results_cache: Dict[str, str] = {}

        # --- Thread pool for analyzing individual news content ---
        self._thread_pool = QThreadPool.globalInstance()
        self._single_item_analysis_tasks = (
            {}
        )  # Track ongoing single item analysis tasks

        # --- Task Tracking with the new TaskTracker class ---
        self._task_tracker = TaskTracker()

        # --- Model Setup ---
        self._setup_table_model()  # Initialize the model here

        # --- Connect worker signals ---
        self._connect_worker_signals()

    def _connect_worker_signals(self):
        """Connect worker signals to handler methods."""
        # Crawl phase signals
        self._worker_signals.initial_crawl_status.connect(
            self._handle_initial_crawl_status
        )
        self._worker_signals.html_ready.connect(self._handle_html_ready)
        self._worker_signals.initial_crawl_finished.connect(
            self._handle_initial_crawl_phase_finished
        )

        # Processing phase signals
        self._worker_signals.processing_status.connect(self._handle_processing_status)
        self._worker_signals.processing_finished.connect(
            self._handle_processing_finished
        )

    def _handle_error(
        self, operation: str, error: Exception, details: str = None
    ) -> bool:
        """
        Centralized error handler.

        Args:
            operation: Description of the operation that failed
            error: Exception that occurred
            details: Optional additional details

        Returns:
            False, to be used as a return value for operations
        """
        error_msg = str(error)
        if details:
            error_msg = f"{error_msg}: {details}"

        logger.error(f"Error during {operation}: {error_msg}", exc_info=True)
        self.error_occurred.emit(f"{operation.title()} Error", error_msg)
        return False

    def _setup_table_model(self):
        """Initializes the QSqlTableModel and proxy model."""
        db = get_db()
        if not db.isOpen():
            # Emit error signal instead of direct QMessageBox
            self.error_occurred.emit(
                "Database Error", "Failed to get database connection."
            )
            self._news_model = None
            self._proxy_model = None
            return

        self._news_model = QSqlTableModel(parent=self, db=db)
        self._news_model.setTable(NEWS_TABLE)
        self._news_model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)

        # Determine column indices and headers (can be reused from NewsTab)
        self._column_indices = {}
        col_map = {
            "title": "Title",
            "source_name": "Source",
            "category_name": "Category",
            "date": "Publish Date",
        }
        for i in range(self._news_model.columnCount()):
            field_name = self._news_model.record().fieldName(i)
            self._column_indices[field_name] = i
            if field_name in col_map:
                self._news_model.setHeaderData(
                    i, Qt.Orientation.Horizontal, col_map[field_name]
                )

        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._news_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy_model.setFilterKeyColumn(-1)

        # Initial load and sort
        if not self._news_model.select():
            self.error_occurred.emit(
                "Data Load Error",
                f"Failed to load news: {self._news_model.lastError().text()}",
            )
        else:
            date_col_index = self._column_indices.get("date", -1)
            if date_col_index != -1:
                self._proxy_model.sort(date_col_index, Qt.SortOrder.DescendingOrder)

    @property
    def news_model(self) -> Optional[QSqlTableModel]:
        """Provides access to the underlying data model."""
        return self._news_model

    @property
    def proxy_model(self) -> Optional[QSortFilterProxyModel]:
        """Provides access to the proxy model for the view."""
        return self._proxy_model

    def load_initial_data(self):
        """Loads filters and initial news data."""
        self.load_filter_options()
        # Model is loaded during init, just emit signal
        if self._news_model:
            self.news_data_updated.emit()

    def load_filter_options(self):
        """Loads category and source data for filters."""
        try:
            categories = (
                self._news_service.get_all_categories()
            )  # List[Tuple[int, str]]
            sources = self._news_service.get_all_sources()  # List[Dict]
            source_names = sorted(
                list(set(s["name"] for s in sources if s.get("name")))
            )
            self.filters_loaded.emit(categories, source_names)
        except Exception as e:
            self._handle_error("filter load", e)

    def apply_filters(self, category_id: int, source_name: str, search_text: str):
        """Applies filters to the news model."""
        if not self._news_model or not self._proxy_model:
            logger.warning("Attempted to apply filters, but model is not ready.")
            return

        # 1. SQL Filter (Category, Source Name)
        filter_parts = []
        if category_id != -1:
            filter_parts.append(f"category_id = {category_id}")
        if source_name != "All":
            # Ensure proper quoting for SQL
            safe_source_name = source_name.replace("'", "''")
            filter_parts.append(f"source_name = '{safe_source_name}'")

        sql_filter = " AND ".join(filter_parts)
        self._news_model.setFilter(sql_filter)

        # 2. Proxy Filter (Search Text)
        self._proxy_model.setFilterKeyColumn(-1)  # Search all columns
        self._proxy_model.setFilterRegularExpression(search_text)

        # 3. Refresh model data
        if not self._news_model.select():
            self.error_occurred.emit(
                "Filter Error",
                f"Failed to apply filters: {self._news_model.lastError().text()}",
            )
        else:
            self.news_data_updated.emit()  # Notify view that data/filtering changed

    def refresh_news(self):
        """Reloads data from the database."""
        if self._news_model:
            if self._news_model.select():
                self.news_data_updated.emit()
            else:
                self.error_occurred.emit(
                    "Refresh Error",
                    f"Failed to refresh news list: {self._news_model.lastError().text()}",
                )

    def get_news_details(self, proxy_index: QModelIndex) -> Optional[Dict[str, Any]]:
        """Gets full details for a selected news item using the service."""
        if not self._proxy_model or not self._news_model or not proxy_index.isValid():
            return None
        source_index = self._proxy_model.mapToSource(proxy_index)
        id_col = self._column_indices.get("id", -1)
        if id_col == -1:
            return None

        news_id_variant = self._news_model.data(
            self._news_model.index(source_index.row(), id_col)
        )
        news_id = news_id_variant if isinstance(news_id_variant, int) else None

        if news_id is not None:
            try:
                return self._news_service.get_news_by_id(news_id)
            except Exception as e:
                self._handle_error("news detail retrieval", e, f"ID: {news_id}")
        return None

    def delete_selected_news(self, proxy_indexes: List[QModelIndex]):
        """Deletes selected news items."""
        if not proxy_indexes:
            self.error_occurred.emit("Delete Error", "No items selected.")
            return

        id_col = self._column_indices.get("id", -1)
        title_col = self._column_indices.get("title", -1)
        if id_col == -1:
            self.error_occurred.emit("Delete Error", "Cannot find ID column.")
            return

        ids_to_delete = []
        titles_to_delete = []
        for proxy_index in proxy_indexes:
            source_index = self._proxy_model.mapToSource(proxy_index)
            news_id_variant = self._news_model.data(
                self._news_model.index(source_index.row(), id_col)
            )
            news_id = news_id_variant if isinstance(news_id_variant, int) else None
            if news_id is not None:
                ids_to_delete.append(news_id)
                if title_col != -1:
                    titles_to_delete.append(
                        str(
                            self._news_model.data(
                                self._news_model.index(source_index.row(), title_col)
                            )
                        )
                    )
                else:
                    titles_to_delete.append(f"ID {news_id}")

        if not ids_to_delete:
            self.error_occurred.emit("Delete Error", "No valid IDs found for deletion.")
            return

        # Confirmation should ideally happen in the View before calling this
        deleted_count = 0
        errors = []
        for news_id, title in zip(ids_to_delete, titles_to_delete):
            try:
                if self._news_service.delete_news(news_id):
                    deleted_count += 1
                else:
                    errors.append(f"Failed to delete '{title}' (Service Error)")
            except Exception as e:
                errors.append(f"Error deleting '{title}': {e}")

        if errors:
            self.error_occurred.emit(
                "Delete Error",
                f"Deleted {deleted_count} items.\nErrors:\n- " + "\n- ".join(errors),
            )
        elif deleted_count > 0:
            logger.info(f"Deleted {deleted_count} news items.")
            self.refresh_news()  # Refresh list after successful deletion

    # --- Fetching Logic ---
    def start_fetch(self, sources_to_fetch: List[Dict[str, Any]]):
        """
        Starts the fetch process for selected news sources.
        """
        if self._is_fetching:
            self.error_occurred.emit(
                "Busy", "A fetch operation is already in progress."
            )
            return
        if not sources_to_fetch:
            self.error_occurred.emit("Fetch Error", "No sources selected to fetch.")
            return

        logger.info(f"Controller starting fetch for {len(sources_to_fetch)} sources.")
        self._is_fetching = True
        self._analysis_results_cache.clear()

        # Reset and initialize task tracker
        self._task_tracker.reset()
        source_urls = [
            source.get("url") for source in sources_to_fetch if source.get("url")
        ]
        self._task_tracker.add_urls(source_urls)

        # Start the ProcessorWorker thread if not running
        if self._processing_worker is None:
            try:
                self._processing_worker = ProcessorWorker(
                    self._news_service,
                    self._worker_signals,
                )
                self._processing_worker.start()
                self._processing_worker.wait_until_ready(timeout=5)
                logger.info("ProcessorWorker started by NewsController.")
            except TimeoutError:
                logger.error("ProcessorWorker failed to start.")
                self.error_occurred.emit(
                    "Fetch Error", "ProcessorWorker failed to start."
                )
                self._reset_fetch_state("Worker start failed")
                return
            except Exception as e:
                self._handle_error("processor worker start", e)
                self._reset_fetch_state("Worker start failed")
                return

        # Start the CrawlerWorker
        try:
            self._active_initial_crawler = CrawlerWorker(
                sources_to_fetch, self._worker_signals
            )
            self._active_initial_crawler.start()  # Using QThread's start method
            logger.info("CrawlerWorker started.")
        except Exception as e:
            self._handle_error("crawler worker start", e)
            self._reset_fetch_state("Worker start failed")
            return

    def filter_new_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters the provided sources list to only include sources that are not already being fetched.

        Args:
            sources: List of source dictionaries with 'url' keys

        Returns:
            List of source dictionaries that are not already being processed
        """
        if not self._is_fetching:
            return sources

        new_sources = []
        for source in sources:
            url = source.get("url")
            if url and url not in self._task_tracker.active_urls:
                new_sources.append(source)

        return new_sources

    def add_sources_to_fetch(self, new_sources: List[Dict[str, Any]]):
        """
        Adds new sources to an already running fetch operation.

        Args:
            new_sources: List of new source dictionaries to add
        """
        if not self._is_fetching or not self._active_initial_crawler:
            logger.warning("Cannot add sources: No active fetch operation")
            self.error_occurred.emit(
                "Operation Error", "No active fetch operation to add sources to"
            )
            return

        if not new_sources:
            logger.debug("No new sources to add to fetch")
            return

        logger.info(f"Adding {len(new_sources)} new sources to active fetch operation")

        # Update task tracker
        source_urls = [source.get("url") for source in new_sources if source.get("url")]
        self._task_tracker.add_urls(source_urls)

        # Add new URLs to the crawler
        try:
            # Forward the new sources to the active crawler
            self._active_initial_crawler.add_urls_to_crawl(new_sources)
            logger.debug(
                f"Successfully added {len(new_sources)} sources to active crawler"
            )
        except Exception as e:
            logger.error(f"Error adding sources to crawler: {e}", exc_info=True)
            # Mark the added URLs as failed so they don't block completion
            for url in source_urls:
                self.fetch_status_update.emit(
                    url, f"Error: Failed to add task - {str(e)[:30]}", True
                )
                self._task_tracker.mark_final_status(url, True)

    @Slot(list)
    def handle_stop_tasks_request(self, urls_to_stop: List[str]):
        """Handles the request from the dialog to stop specific tasks."""
        if not self._is_fetching:
            logger.warning("Received stop request, but no fetch is active.")
            return

        if not urls_to_stop:
            logger.info("Received stop request with empty URL list.")
            return

        logger.info(
            f"Controller received request to stop and remove tasks for URLs: {urls_to_stop}"
        )

        # --- 1. Remove from Task Tracker ---
        self._task_tracker.remove_urls(urls_to_stop)
        logger.info(f"Removed {len(urls_to_stop)} URLs from TaskTracker.")

        # --- 2. Forward cancellation and removal request to Workers ---
        workers_notified = 0
        if self._active_initial_crawler and self._active_initial_crawler.isRunning():
            try:
                # This now handles cancelling the task and removing from worker's internal tracking
                self._active_initial_crawler.cancel_specific_tasks(urls_to_stop)
                workers_notified += 1
                logger.debug(
                    f"Cancellation/removal request forwarded to CrawlerWorker."
                )
            except Exception as e:
                logger.error(
                    f"Error calling cancel_specific_tasks on CrawlerWorker: {e}",
                    exc_info=True,
                )

        if self._processing_worker and self._processing_worker.isRunning():
            try:
                # This now handles cancelling the task and removing from worker's internal tracking
                self._processing_worker.cancel_specific_tasks(urls_to_stop)
                workers_notified += 1
                logger.debug(
                    f"Cancellation/removal request forwarded to ProcessorWorker."
                )
            except Exception as e:
                logger.error(
                    f"Error calling cancel_specific_tasks on ProcessorWorker: {e}",
                    exc_info=True,
                )

        if workers_notified == 0:
            logger.warning(
                "Stop request handled, but no active workers were notified (they might have finished)."
            )

        # --- 3. Check if the overall process is now finished after removal ---
        # This helps update the state immediately if removing the last tasks finishes the process.
        self._check_if_all_fetching_done(f"User stopped {len(urls_to_stop)} tasks")

    def get_sources_matching_filters(
        self, category_id: int, source_name: str
    ) -> List[Dict[str, Any]]:
        """Retrieves sources matching the given category and source name."""
        if category_id == -1:
            sources = self._news_service.get_all_sources()
        else:
            sources = self._news_service.get_sources_by_category_id(category_id)
        if source_name == "All":
            return sources
        return [s for s in sources if s["name"] == source_name]

    def get_source_names_by_category(self, category_id: int) -> List[str]:
        """Retrieves all news source names for the specified category."""
        if category_id == -1:
            sources = self._news_service.get_all_sources()
        else:
            sources = self._news_service.get_sources_by_category_id(category_id)
        return sorted(list(set(s["name"] for s in sources if s.get("name"))))

    def get_analysis_result(self, url: str) -> Optional[str]:
        """Retrieves cached analysis result for a URL."""
        return self._analysis_results_cache.get(url)

    def cleanup(self):
        """Stop workers and clean up resources."""
        logger.info("NewsController cleanup initiated.")

        # Helper to stop a worker safely
        def stop_worker(worker, worker_name):
            if worker and worker.isRunning():
                logger.info(f"Stopping {worker_name}...")
                worker.stop()  # Signal the worker to stop
                worker.quit()  # Exit the event loop
                if not worker.wait(5000):  # Wait up to 5 seconds
                    logger.warning(
                        f"{worker_name} did not stop gracefully, terminating"
                    )
                    worker.terminate()  # Force termination if necessary
                logger.info(f"{worker_name} stopped")

        # Stop both workers
        stop_worker(self._active_initial_crawler, "CrawlerWorker")
        stop_worker(self._processing_worker, "ProcessorWorker")

        # Clear references
        self._active_initial_crawler = None
        self._processing_worker = None

        logger.info("NewsController cleanup finished.")

    # --- Internal Slots for Worker Signals ---
    @Slot(str, str)
    def _handle_initial_crawl_status(self, url: str, status: str):
        # Update task tracker if status is "Cancelled"
        if "Cancelled" in status:
            self._task_tracker.mark_cancelled([url])
            self._task_tracker.mark_final_status(url, True)

        self.fetch_status_update.emit(url, status, False)  # is_final=False

    @Slot(str, str, dict)
    def _handle_html_ready(self, url: str, html_content: str, source_info: dict):
        if url in self._task_tracker.cancelled_urls:
            logger.info(f"Ignoring html_ready for cancelled URL: {url}")
            # Ensure final status is emitted for this cancelled URL
            self.fetch_status_update.emit(url, "Cancelled", True)
            self._check_if_all_fetching_done(f"Skipped cancelled: {url}")
            return

        if not self._is_fetching or (
            self._active_initial_crawler and self._active_initial_crawler.is_cancelled()
        ):
            return  # Ignore if fetch cancelled or stopped

        if self._processing_worker and self._processing_worker.isRunning():
            future = self._processing_worker.submit_task(url, html_content, source_info)
            if future is None:
                logger.error(f"Failed to submit processing task for {url}.")
                self.fetch_status_update.emit(
                    url, "Error: Submit Failed", True
                )  # Mark as final
                self._task_tracker.mark_final_status(url, True)
                self._check_if_all_fetching_done("Task submit failed")
            else:
                self.fetch_status_update.emit(url, "Processing Scheduled", False)
        else:
            logger.error("Processing worker not available to handle HTML.")
            self.fetch_status_update.emit(
                url, "Error: Worker Missing", True
            )  # Mark as final
            self._task_tracker.mark_final_status(url, True)
            self._check_if_all_fetching_done("Worker missing on ready")

    @Slot()
    def _handle_initial_crawl_phase_finished(self):
        logger.info("Controller noted: Initial crawl phase finished.")
        self._task_tracker.initial_phase_complete = True
        was_cancelled = (
            self._active_initial_crawler is not None
            and self._active_initial_crawler.is_cancelled()
        )
        self._check_if_all_fetching_done(
            "Initial Crawl Finished" + (" (Cancelled)" if was_cancelled else "")
        )

    @Slot(str, str)
    def _handle_processing_status(self, url: str, status: str):
        # Might want to filter/simplify status before emitting to view
        self.fetch_status_update.emit(url, status, False)

    @Slot(str, str, str, str)
    def _handle_processing_finished(
        self, url: str, final_status: str, details: str, analysis_result: str
    ):
        if url in self._task_tracker.cancelled_urls and final_status != "Cancelled":
            logger.info(
                f"Overriding final status for {url} to Cancelled due to prior request."
            )
            final_status = "Cancelled"
            details = "Task was cancelled by user request."
            analysis_result = ""  # Clear analysis if cancelled

        logger.info(
            f"Controller noted: Processing finished for {url}. Status: {final_status}"
        )
        self._analysis_results_cache[url] = (
            analysis_result or f"Status: {final_status} - Details: {details}"
        )
        self.fetch_analysis_result.emit(url, analysis_result)  # Emit the raw result

        # Format final status for view
        status_to_display = final_status
        if final_status == "Complete" and details:
            status_to_display = f"Complete ({details})"
        elif final_status == "Error" and details:
            status_to_display = f"Error: {details[:40]}"
        elif final_status == "Complete*" and details:
            status_to_display = f"Complete* ({details})"
        elif final_status == "Cancelled":
            status_to_display = "Cancelled"

        # Update the task tracker
        self._task_tracker.mark_final_status(url, True)

        self.fetch_status_update.emit(url, status_to_display, True)  # is_final=True
        self._check_if_all_fetching_done(f"Processed: {url}")

    def _check_if_all_fetching_done(self, trigger_reason: str):
        if not self._is_fetching:
            return

        logger.debug(
            f"Check completion ({trigger_reason}): InitialDone={self._task_tracker.initial_phase_complete}, "
            f"Processed={self._task_tracker.processed_count}/{self._task_tracker.total_count}, "
            f"FinalStatusCount={sum(1 for status in self._task_tracker.final_status_map.values() if status)}"
        )

        # Check if all tasks are complete using the task tracker
        if self._task_tracker.is_complete():
            # Determine final message
            final_message = "Finished"

            logger.info(
                f"All fetch/processing tasks complete or removed. Status: {final_message}"
            )
            self.fetch_process_finished.emit(final_message)  # Notify view
            self._reset_fetch_state(final_message)
            self.refresh_news()  # Refresh the news list

    def _reset_fetch_state(self, final_message: Optional[str] = None):
        logger.info(f"Resetting fetch state. Final status: {final_message}")
        self._is_fetching = False
        self._task_tracker.reset()
        self._active_initial_crawler = None  # Release reference to crawler
        # Don't stop the processing worker here, keep it running

    # --- New Method: Single News Analysis ---
    def trigger_single_item_analysis(self, news_id: int, content: str):
        """
        Trigger LLM analysis on a single news content.
        The analysis result will be returned in a streaming manner via the analysis_chunk_received signal.
        After completion, the analysis result will be saved to the database.

        Args:
            news_id: The ID of the news item
            content: The original content text of the news
        """
        if not content or not content.strip():
            self.error_occurred.emit(
                "Analysis Error", "Content is empty, cannot perform analysis"
            )
            return

        # Create and start analysis task
        try:
            # Avoid duplicate analysis
            if news_id in self._single_item_analysis_tasks:
                logger.warning(
                    f"News ID {news_id} already has an ongoing analysis task"
                )
                return

            # --- run_analysis_task ---
            def run_analysis_task():
                # Create a separate event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                analysis_task = None  # Keep track of the task

                try:
                    # Notify UI to start analysis
                    logger.info(f"Starting analysis for news ID {news_id}")

                    # Create the task using loop.create_task
                    analysis_task = loop.create_task(
                        self._analyze_single_content(news_id, content)
                    )

                    # Run the event loop until the analysis_task is complete
                    loop.run_until_complete(analysis_task)

                    # Get the result (or exception) after the task is done
                    result = (
                        analysis_task.result()
                    )  # This will raise exception if task failed

                    # Save analysis result to database (if successful and result is valid)
                    if result and isinstance(result, str) and result.strip():
                        # Schedule database update on the main thread or handle thread-safety
                        # Assuming _news_service.update_news_analysis is thread-safe or handles it
                        success = self._news_service.update_news_analysis(
                            news_id, result
                        )
                        if not success:
                            logger.error(
                                f"Failed to save analysis result for news ID {news_id}"
                            )
                        else:
                            logger.info(
                                f"Successfully saved analysis for news ID {news_id}"
                            )

                    logger.info(
                        f"Analysis task for news ID {news_id} completed successfully."
                    )

                except asyncio.CancelledError:
                    logger.info(f"Analysis task for news ID {news_id} was cancelled.")
                    # Optionally handle cancellation cleanup if needed
                except Exception as e:
                    logger.error(
                        f"Error analyzing news ID {news_id}: {e}", exc_info=True
                    )
                    # Error emission might need to be marshalled back to the GUI thread if needed
                    # self.error_occurred.emit("Analysis Error", f"Error processing news: {str(e)}")
                finally:
                    # Gracefully shutdown the event loop and related resources
                    try:
                        # Cancel the task if it's somehow still pending (e.g., run_until_complete was interrupted)
                        if analysis_task and not analysis_task.done():
                            analysis_task.cancel()
                            # Give cancellation a chance to run
                            loop.run_until_complete(asyncio.sleep(0))

                        # Standard asyncio cleanup procedures
                        tasks = asyncio.all_tasks(loop=loop)
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        # Wait for tasks to cancel
                        if tasks:
                            loop.run_until_complete(
                                asyncio.gather(*tasks, return_exceptions=True)
                            )

                        # Shutdown async generators
                        loop.run_until_complete(loop.shutdown_asyncgens())

                        # Close the loop
                        loop.close()
                        logger.debug(f"Event loop for analysis task {news_id} closed.")

                    except Exception as loop_close_err:
                        logger.error(
                            f"Error during event loop cleanup for analysis task {news_id}: {loop_close_err}",
                            exc_info=True,
                        )

                    # Remove the loop from the current thread context
                    asyncio.set_event_loop(None)

                    # Remove task from tracking dictionary
                    if news_id in self._single_item_analysis_tasks:
                        try:  # Add try-except for thread safety if dict access is concurrent
                            del self._single_item_analysis_tasks[news_id]
                            logger.debug(
                                f"Removed analysis task {news_id} from tracking."
                            )
                        except KeyError:
                            logger.warning(
                                f"Task {news_id} already removed from tracking."
                            )

            # --- End of run_analysis_task ---

            # Submit task to thread pool
            self._single_item_analysis_tasks[news_id] = True  # Mark task as started
            self._thread_pool.start(run_analysis_task)
            logger.debug(f"Analysis task for news ID {news_id} submitted")

        except Exception as e:
            self._handle_error("analysis task submission", e)

    async def _analyze_single_content(self, news_id: int, content: str) -> str:
        """
        Analyze a single news content using LLM and return the result in a streaming manner.

        Args:
            news_id: The news ID for associating the result
            content: The news content to analyze

        Returns:
            Complete analysis result text
        """
        try:
            user_prompt = f"""
            Please analyze the following news content:\n\"\"\"\n{content}\n\"\"\"
            **Write in the same language as the original content** (e.g., if the original content is in Chinese, the analysis should also be in Chinese). 
            """

            # Get streaming analysis result from NewsService using LLMClientPool
            full_result = ""

            async for chunk in self._news_service.analyze_single_content(
                system_prompt=SYSTEM_PROMPT_ANALYZE_CONTENT,
                user_prompt=user_prompt,
            ):
                if chunk and chunk.strip():
                    # Send chunk to UI
                    self.analysis_chunk_received.emit(news_id, chunk)
                    full_result += chunk

            return full_result

        except Exception as e:
            logger.error(f"Error executing LLM analysis: {e}", exc_info=True)
            # Send error message as the last chunk
            error_message = f"\n\n**Error during analysis**: {str(e)}"
            self.analysis_chunk_received.emit(news_id, error_message)
            return error_message
