# src/ui/controllers/news_controller.py (Updated Version)

"""
NewsController orchestrates the business logic and UI updates for the News Tab.

Core responsibilities:
- Interact with NewsService to load, refresh, and update news records.
- Initialize and configure QSqlTableModel and QSortFilterProxyModel for table display and filtering.
- Preload filter criteria (categories and sources) and emit filters_loaded signal to notify the UI.
- Manage asynchronous crawling and processing workflows using InitialCrawlerWorker and ProcessingWorker:
    * Monitor fetch progress and processing status, emitting fetch_status_update for real-time updates.
    * Deliver processed analysis output via fetch_analysis_result.
    * Handle cancellation, errors, and notify final completion through fetch_process_finished.
- Cache analysis results for quick retrieval via get_analysis_result(url).
- Emit error_occurred signal with a title and message to report exceptions.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QModelIndex, Qt
from PySide6.QtSql import QSqlTableModel  # Or use QAbstractTableModel if preferred
from PySide6.QtCore import QSortFilterProxyModel

from src.services.news_service import NewsService
from src.services.setting_service import SettingService
from src.db.connection import get_db  # Needed for QSqlTableModel
from src.db.schema_constants import NEWS_TABLE
from src.ui.workers.news_fetch_workers import (
    WorkerSignals,
    InitialCrawlerWorker,
    ProcessingWorker,
)

# --- New Imports ---
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.utils.prompt import SYSTEM_PROMPT_ANALYZE_CONTENT
# --- End New Imports ---

logger = logging.getLogger(__name__)


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
    
    # --- New Signals ---
    analysis_chunk_received = Signal(int, str)  # news_id, chunk_text
    # --- End New Signals ---

    def __init__(self, news_service: NewsService, setting_service: SettingService, parent=None):
        super().__init__(parent)
        self._news_service = news_service
        self._setting_service = setting_service
        self._is_fetching = False
        self._active_initial_crawler: Optional[InitialCrawlerWorker] = None
        self._processing_worker: Optional[ProcessingWorker] = None
        self._worker_signals = (
            WorkerSignals()
        )  # Signals local to controller <-> worker comms
        self._analysis_results_cache: Dict[str, str] = {}
        
        # --- New Member Variables ---
        self._thread_pool = QThreadPool.globalInstance()
        self._single_item_analysis_tasks = {}  # Track ongoing single item analysis tasks
        # --- End New Member Variables ---

        # --- Model Setup ---
        self._setup_table_model()  # Initialize the model here

        # Connect worker signals to internal handler slots
        self._worker_signals.initial_crawl_status.connect(
            self._handle_initial_crawl_status
        )
        self._worker_signals.html_ready.connect(self._handle_html_ready)
        self._worker_signals.initial_crawl_finished.connect(
            self._handle_initial_crawl_phase_finished
        )
        self._worker_signals.processing_status.connect(self._handle_processing_status)
        self._worker_signals.processing_finished.connect(
            self._handle_processing_finished
        )

        # --- Task Tracking ---
        self._total_sources_to_process = 0
        self._initial_crawl_finished_flag = False
        self._processing_tasks_finished_count = 0

        self._cancellation_in_progress = False

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
            sources = (
                self._news_service.get_all_sources()
            )  # List[Dict] - maybe just names needed?
            source_names = sorted(
                list(set(s["name"] for s in sources if s.get("name")))
            )
            self.filters_loaded.emit(categories, source_names)
        except Exception as e:
            logger.error(f"Failed to load filter options: {e}", exc_info=True)
            self.error_occurred.emit(
                "Filter Load Error", f"Could not load filters: {e}"
            )

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
            logger.error(
                f"Failed to select data after applying filters: {self._news_model.lastError().text()}"
            )
            self.error_occurred.emit(
                "Filter Error",
                f"Failed to apply filters: {self._news_model.lastError().text()}",
            )
        else:
            self.news_data_updated.emit()  # Notify view that data/filtering changed

    def refresh_news(self):
        """Reloads data from the database."""
        # if self._is_fetching:
        #     self.error_occurred.emit("Busy", "Cannot refresh while fetching.")
        #     return
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
                logger.error(
                    f"Error fetching news details for ID {news_id}: {e}", exc_info=True
                )
                self.error_occurred.emit(
                    "Preview Error", f"Could not load details: {e}"
                )
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
        This has been updated to use the modified InitialCrawlerWorker that creates individual tasks for each URL.
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
        self._total_sources_to_process = len(sources_to_fetch)
        self._initial_crawl_finished_flag = False
        self._processing_tasks_finished_count = 0
        self._active_initial_crawler = None

        # Get LLM configuration information
        volcengine_api_key = self._setting_service.get_api_key("volcengine")
        if not volcengine_api_key:
            logger.warning("Volcano Engine API key not configured. LLM-dependent features may fail.")
            self.error_occurred.emit(
                "API Key Error", "Volcano Engine API key not configured. Please check your settings."
            )
            self._reset_fetch_state("API Key not configured")
            return
            
        llm_base_url = "https://ark.cn-beijing.volces.com/api/v3"

        # Start the ProcessingWorker thread if not running
        if self._processing_worker is None:
            self._processing_worker = ProcessingWorker(
                self._news_service, self._worker_signals, llm_base_url, volcengine_api_key
            )
            self._processing_worker.start()
            try:
                self._processing_worker.wait_until_ready(timeout=5)
                logger.info("Processing worker started by NewsController.")
            except TimeoutError:
                logger.error("Processing worker failed to start.")
                self.error_occurred.emit(
                    "Fetch Error", "Processing worker failed to start."
                )
                self._reset_fetch_state("Worker start failed")
                return

        # Start the InitialCrawlerWorker runnable with our modified implementation
        # that creates individual tasks for each URL instead of using process_urls
        self._active_initial_crawler = InitialCrawlerWorker(
            sources_to_fetch, self._worker_signals
        )
        QThreadPool.globalInstance().start(self._active_initial_crawler)
        logger.info("InitialCrawlerWorker submitted to thread pool.")

    def cancel_fetch(self):
        if not self._is_fetching or self._cancellation_in_progress:
            return
        self._cancellation_in_progress = True
        logger.info("Controller requesting fetch cancellation.")
        
        # 1. InitialCrawlerWorker
        try:
            if self._active_initial_crawler:
                self._active_initial_crawler.cancel()  # This should trigger the cascade
            self._active_initial_crawler = None
        except Exception as e:
            logger.error(f"Error cancelling fetch: {e}", exc_info=True)

        # 2. ProcessingWorker (QThread)
        if self._processing_worker and self._processing_worker.isRunning():
            logger.info("Stopping NewsController's ProcessingWorker...")
            self._processing_worker.stop()
            self._processing_worker.quit()
            if not self._processing_worker.wait(5000):
                logger.warning("ProcessingWorker did not stop gracefully.")
            self._processing_worker = None

        # 3. Reset internal state and notify the interface
        self._reset_fetch_state("Cancelled")
        self.fetch_process_finished.emit("Cancelled")
        self.refresh_news()

        self._cancellation_in_progress = False

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
        self.cancel_fetch()  # Request cancellation first
        if self._processing_worker and self._processing_worker.isRunning():
            logger.info("Stopping NewsController's ProcessingWorker...")
            self._processing_worker.stop()
            self._processing_worker.quit()
            if not self._processing_worker.wait(5000):
                logger.warning("ProcessingWorker did not stop gracefully.")
        self._processing_worker = None  # Release reference
        logger.info("NewsController cleanup finished.")

    # --- Internal Slots for Worker Signals ---
    @Slot(str, str)
    def _handle_initial_crawl_status(self, url: str, status: str):
        self.fetch_status_update.emit(url, status, False)  # is_final=False

    @Slot(str, str, dict)
    def _handle_html_ready(self, url: str, html_content: str, source_info: dict):
        if not self._is_fetching or (
            self._active_initial_crawler and self._active_initial_crawler.is_cancelled()
        ):
            return  # Ignore if fetch cancelled or stopped
        if self._processing_worker:
            future = self._processing_worker.submit_task(url, html_content, source_info)
            if future is None:
                logger.error(f"Failed to submit processing task for {url}.")
                self.fetch_status_update.emit(
                    url, "Error: Submit Failed", True
                )  # Mark as final
                self._processing_tasks_finished_count += 1
                self._check_if_all_fetching_done("Task submit failed")
            else:
                self.fetch_status_update.emit(url, "Processing Scheduled", False)
        else:
            logger.error("Processing worker not available to handle HTML.")
            self.fetch_status_update.emit(
                url, "Error: Worker Missing", True
            )  # Mark as final
            self._processing_tasks_finished_count += 1
            self._check_if_all_fetching_done("Worker missing")

    @Slot()
    def _handle_initial_crawl_phase_finished(self):
        logger.info("Controller noted: Initial crawl phase finished.")
        self._initial_crawl_finished_flag = True
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
        logger.info(
            f"Controller noted: Processing finished for {url}. Status: {final_status}"
        )
        self._analysis_results_cache[url] = (
            analysis_result or f"Status: {final_status} - Details: {details}"
        )
        self.fetch_analysis_result.emit(url, analysis_result)  # Emit the raw result

        self._processing_tasks_finished_count += 1

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
        self.fetch_status_update.emit(url, status_to_display, True)  # is_final=True

        self._check_if_all_fetching_done(f"Processed: {url}")

    def _check_if_all_fetching_done(self, trigger_reason: str):
        if not self._is_fetching:
            return

        logger.debug(
            f"Check completion ({trigger_reason}): InitialDone={self._initial_crawl_finished_flag}, Processed={self._processing_tasks_finished_count}/{self._total_sources_to_process}"
        )

        is_complete = (
            self._initial_crawl_finished_flag
            and self._processing_tasks_finished_count >= self._total_sources_to_process
        )
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
                final_message = "Finished (Some errors)"

            logger.info(
                f"All fetch/processing tasks complete/cancelled. Status: {final_message}"
            )
            self._reset_fetch_state(final_message)
            self.fetch_process_finished.emit(final_message)  # Notify view
            self.refresh_news()  # Refresh the news list

    def _reset_fetch_state(self, final_message: Optional[str] = None):
        logger.info(f"Resetting fetch state. Final status: {final_message}")
        self._is_fetching = False
        self._total_sources_to_process = 0
        self._initial_crawl_finished_flag = False
        self._processing_tasks_finished_count = 0
        self._active_initial_crawler = None
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
            self.error_occurred.emit("Analysis Error", "Content is empty, cannot perform analysis")
            return
            
        # Check if API key is configured
        volcengine_api_key = self._setting_service.get_api_key("volcengine")
        if not volcengine_api_key:
            logger.warning("Volcano Engine API key not configured, LLM functionality cannot be used")
            self.error_occurred.emit(
                "API Key Error", "Volcano Engine API key not configured, please check settings"
            )
            return
            
        # Set LLM parameters
        llm_base_url = "https://ark.cn-beijing.volces.com/api/v3"
        
        # Create and start analysis task
        try:
            # Avoid duplicate analysis
            if news_id in self._single_item_analysis_tasks:
                logger.warning(f"News ID {news_id} already has an ongoing analysis task")
                return
                
            # Start asynchronous task
            def run_analysis_task():
                # Create a separate event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Notify UI to start analysis
                    logger.info(f"Starting analysis for news ID {news_id}")
                    
                    # Use asynchronous function for analysis
                    result = loop.run_until_complete(
                        self._analyze_single_content(news_id, content, volcengine_api_key, llm_base_url)
                    )
                    
                    # Save analysis result to database
                    if result and result.strip():
                        success = self._news_service.update_news_analysis(news_id, result)
                        if not success:
                            logger.error(f"Failed to save analysis result for news ID {news_id}")
                    
                    logger.info(f"Analysis task for news ID {news_id} completed")
                except Exception as e:
                    logger.error(f"Error analyzing news ID {news_id}: {e}", exc_info=True)
                    self.error_occurred.emit("Analysis Error", f"Error processing news: {str(e)}")
                finally:
                    # Close event loop
                    loop.close()
                    # Remove task from tracking dictionary
                    if news_id in self._single_item_analysis_tasks:
                        del self._single_item_analysis_tasks[news_id]
            
            # Submit task to thread pool
            self._single_item_analysis_tasks[news_id] = True  # Mark task as started
            self._thread_pool.start(run_analysis_task)
            logger.debug(f"Analysis task for news ID {news_id} submitted")
            
        except Exception as e:
            logger.error(f"Error submitting analysis task: {e}", exc_info=True)
            self.error_occurred.emit("System Error", f"Unable to start analysis task: {str(e)}")
            
    async def _analyze_single_content(self, news_id: int, content: str, api_key: str, base_url: str):
        """
        Analyze a single news content using LLM and return the result in a streaming manner.
        
        Args:
            news_id: The news ID for associating the result
            content: The news content to analyze
            api_key: LLM API key
            base_url: LLM API base URL
            
        Returns:
            Complete analysis result text
        """
        try:
            user_prompt = f"""
            Please analyze the following news content:\n\"\"\"\n{content}\n\"\"\"
            **Write in the same language as the original content** (e.g., if the original content is in Chinese, the analysis should also be in Chinese). 
            """
            
            # Get streaming analysis result from NewsService
            full_result = ""
            
            async for chunk in self._news_service.analyze_single_content(
                system_prompt=SYSTEM_PROMPT_ANALYZE_CONTENT,
                user_prompt=user_prompt,
                api_key=api_key,
                base_url=base_url
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