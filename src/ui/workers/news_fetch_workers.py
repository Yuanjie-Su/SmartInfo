# src/ui/workers/news_fetch_workers.py
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading
from typing import List, Dict, Optional, Any, Set, Callable, Union, Tuple

from PySide6.QtCore import QObject, Signal, QThread

from src.services.news_service import NewsService
from src.core.crawler import PlaywrightCrawler

logger = logging.getLogger(__name__)


# --- WorkerSignals Class ---
class WorkerSignals(QObject):
    """Defines signals available from all workers."""

    # Initial Crawl Signals (emitted by CrawlerWorker)
    html_ready = Signal(str, str, dict)  # url, html_content, source_info
    initial_crawl_status = Signal(str, str)  # url, status_message
    initial_crawl_finished = Signal()  # Signal when the *initial crawl phase* is done

    # Processing Signals (emitted by ProcessorWorker's tasks)
    processing_status = Signal(str, str)  # url, status_details
    processing_finished = Signal(
        str, str, str, str
    )  # url, final_status, details, analysis_result


class SourceManager:
    """Manages source information including URL mappings and metadata."""

    def __init__(self, initial_sources: List[Dict[str, Any]]):
        self._source_map_lock = threading.Lock()
        self._source_map: Dict[str, Dict[str, Any]] = {
            source.get("url", ""): source
            for source in initial_sources
            if source.get("url")
        }

    def add_sources(self, sources: List[Dict[str, Any]]) -> None:
        """Add new sources to the source map."""
        with self._source_map_lock:
            for source in sources:
                url = source.get("url")
                if url:
                    self._source_map[url] = source

    def get_source_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get source information for a URL."""
        with self._source_map_lock:
            return self._source_map.get(url)

    def has_source(self, url: str) -> bool:
        """Check if a URL exists in the source map."""
        with self._source_map_lock:
            return url in self._source_map

    def get_all_urls(self) -> List[str]:
        """Get all URLs in the source map."""
        with self._source_map_lock:
            return list(self._source_map.keys())


class AsyncWorkerBase(QThread):
    """
    Base class for workers that manage asyncio tasks within a QThread.
    Unifies the task tracking, cancellation, and event loop management.
    """

    def __init__(self, worker_signals: WorkerSignals, parent=None):
        """Initialize the base worker with common attributes."""
        super().__init__(parent)
        self.signals = worker_signals
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        self._is_ready = threading.Event()
        self._cancel_event = threading.Event()  # General cancel flag

        # Task tracking
        self._tasks_lock = threading.Lock()
        self._active_tasks: Dict[str, Union[asyncio.Task, asyncio.Future]] = {}

        # Specific cancellation tracking
        self._specific_cancel_lock = threading.Lock()
        self._urls_to_cancel: Set[str] = set()

        # For main worker task
        self._main_task: Optional[asyncio.Task] = None

    def run(self):
        """Main thread execution method that all QThreads must implement."""
        thread_id = threading.get_ident()
        worker_name = self.__class__.__name__
        logger.info(f"{worker_name} ({thread_id}) thread starting...")

        try:
            # Create and set up event loop
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Initialize worker-specific resources
            self._initialize_resources()

            # Notify that the worker is ready for tasks
            self.loop.call_soon(self._is_ready.set)

            # Start the main worker coroutine
            self._main_task = self.loop.create_task(
                self._main_worker_coroutine(), name=f"{worker_name}_main"
            )

            # Run the event loop
            logger.info(f"{worker_name} ({thread_id}) event loop running...")
            self.loop.run_forever()

        except Exception as e:
            logger.error(
                f"{worker_name} ({thread_id}) event loop error: {e}", exc_info=True
            )
        finally:
            # Clean up resources
            self._cleanup_event_loop(thread_id)
            logger.info(f"{worker_name} ({thread_id}) thread finished.")

    def _initialize_resources(self):
        """
        Initialize worker-specific resources.
        Override in subclasses to set up any required resources.
        """
        pass

    async def _main_worker_coroutine(self):
        """
        Main coroutine that drives the worker's operation.
        Override in subclasses to implement worker-specific logic.
        """
        raise NotImplementedError("Subclasses must implement _main_worker_coroutine")

    def _cleanup_event_loop(self, thread_id: int):
        """Clean up the event loop and pending tasks."""
        worker_name = self.__class__.__name__

        if self.loop:
            try:
                # Cancel pending tasks
                pending = asyncio.all_tasks(self.loop)
                tasks_to_cancel = [
                    task
                    for task in pending
                    if not task.done() and task is not self._main_task
                ]

                if tasks_to_cancel:
                    logger.info(
                        f"{worker_name} ({thread_id}): Cancelling {len(tasks_to_cancel)} "
                        "leftover tasks..."
                    )

                    for task in tasks_to_cancel:
                        task.cancel()

                    self.loop.run_until_complete(
                        asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                    )

                # Shutdown async generators
                if hasattr(self.loop, "shutdown_asyncgens"):
                    logger.debug(
                        f"{worker_name} ({thread_id}): Shutting down async generators..."
                    )
                    self.loop.run_until_complete(self.loop.shutdown_asyncgens())

                # Close the loop
                logger.debug(f"{worker_name} ({thread_id}): Closing event loop...")
                self.loop.close()
                logger.info(f"{worker_name} ({thread_id}): Event loop closed.")

            except Exception as e:
                logger.error(
                    f"{worker_name} ({thread_id}): Error during event loop cleanup: {e}",
                    exc_info=True,
                )

        # Clear task tracking
        with self._tasks_lock:
            self._active_tasks.clear()

        with self._specific_cancel_lock:
            self._urls_to_cancel.clear()

        asyncio.set_event_loop(None)

    def wait_until_ready(self, timeout: float = 5.0):
        """
        Blocks until the event loop is running and ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If the worker doesn't become ready within the timeout
        """
        if not self._is_ready.wait(timeout):
            raise TimeoutError(
                f"{self.__class__.__name__} event loop did not start within {timeout}s"
            )

    def is_cancelled(self) -> bool:
        """Check if general cancellation has been requested."""
        return self._cancel_event.is_set()

    def add_task(self, url: str, task: Union[asyncio.Task, asyncio.Future]) -> None:
        """Add a task to tracking."""
        with self._tasks_lock:
            self._active_tasks[url] = task

    def remove_task(self, url: str) -> None:
        """Remove a task from tracking."""
        with self._tasks_lock:
            self._active_tasks.pop(url, None)

    def get_active_tasks(self) -> Dict[str, Union[asyncio.Task, asyncio.Future]]:
        """Get a copy of the active tasks dictionary."""
        with self._tasks_lock:
            return self._active_tasks.copy()

    def get_active_task_count(self) -> int:
        """Get the number of active tasks."""
        with self._tasks_lock:
            return len(self._active_tasks)

    def has_active_tasks(self) -> bool:
        """Check if there are any active tasks."""
        with self._tasks_lock:
            return bool(self._active_tasks)

    def mark_for_cancellation(self, urls: List[str]) -> None:
        """Mark specific URLs for cancellation."""
        with self._specific_cancel_lock:
            self._urls_to_cancel.update(urls)

    def is_marked_for_cancellation(self, url: str) -> bool:
        """Check if a URL is marked for cancellation."""
        with self._specific_cancel_lock:
            return url in self._urls_to_cancel

    def cancel_specific_tasks(self, urls: List[str]) -> None:
        """
        Cancel specific tasks by URL and remove them from tracking.

        Args:
            urls: List of URLs to cancel
        """
        if not self.loop or not self.loop.is_running():
            logger.warning(
                f"{self.__class__.__name__}: Loop not running, cannot cancel/remove specific tasks."
            )
            return

        worker_name = self.__class__.__name__
        logger.info(
            f"{worker_name}: Cancellation and removal requested for {len(urls)} specific tasks."
        )
        self.mark_for_cancellation(urls)

        tasks_to_cancel_and_remove: List[
            Tuple[str, Union[asyncio.Task, asyncio.Future]]
        ] = []
        with self._tasks_lock:
            for url in urls:
                task = self._active_tasks.get(url)
                # Check if task exists and is not done
                if task and not task.done():
                    tasks_to_cancel_and_remove.append((url, task))
                elif url in self._active_tasks and task and task.done():
                    logger.debug(
                        f"{worker_name}: Task for {url} already done, marking for removal from tracking."
                    )
                    # If task is already done but still being tracked, also remove it
                    tasks_to_cancel_and_remove.append((url, task))

        if tasks_to_cancel_and_remove:
            logger.info(
                f"{worker_name}: Scheduling cancellation and removal for {len(tasks_to_cancel_and_remove)} specific tasks"
            )
            # Schedule actual cancellation and removal on the event loop thread
            self.loop.call_soon_threadsafe(
                self._cancel_and_remove_tasks_from_loop, tasks_to_cancel_and_remove
            )
        else:
            logger.info(
                f"{worker_name}: No active, non-done tasks found matching the URLs to cancel/remove."
            )

    def _cancel_and_remove_tasks_from_loop(
        self, tasks_to_process: List[Tuple[str, Union[asyncio.Task, asyncio.Future]]]
    ):
        """Internal helper. Cancels and removes tasks. Must be called from the worker's event loop thread."""
        worker_name = self.__class__.__name__
        if not self.loop or not self.loop.is_running():
            logger.warning(
                f"{worker_name}: Loop not running during _cancel_and_remove_tasks_from_loop."
            )
            return

        logger.debug(
            f"{worker_name}: Executing cancel/remove for {len(tasks_to_process)} tasks on loop thread."
        )
        removed_count = 0
        processed_urls = set()  # Keep track of URLs processed in this call

        for url, task in tasks_to_process:
            processed_urls.add(
                url
            )  # Mark URL as processed for this cancellation request

            # 1. If task is not done, cancel it
            if not task.done():
                task.cancel()

            # 2. Remove from active task tracking
            with self._tasks_lock:
                # Double-check the task is still the one we want to remove
                if url in self._active_tasks and self._active_tasks[url] is task:
                    del self._active_tasks[url]
                    removed_count += 1
                else:
                    # Task might have completed and been removed by other logic, or URL might not match (theoretically shouldn't happen)
                    logger.debug(
                        f"{worker_name}: Task for URL {url} was not found in active tracking for removal (might have finished/been removed already)."
                    )

        # --- Clear cancellation flags for processed URLs ---
        if processed_urls:
            with self._specific_cancel_lock:
                initial_cancel_count = len(self._urls_to_cancel)
                self._urls_to_cancel.difference_update(
                    processed_urls
                )  # Remove processed URLs
                cleared_cancel_count = initial_cancel_count - len(self._urls_to_cancel)
                if cleared_cancel_count > 0:
                    logger.debug(
                        f"{worker_name}: Cleared {cleared_cancel_count} specific cancellation flags."
                    )

        if removed_count > 0:
            logger.info(
                f"{worker_name}: Finished cancellation/removal on loop thread. Removed {removed_count} tasks from tracking."
            )
        else:
            logger.debug(
                f"{worker_name}: Finished cancellation/removal on loop thread. No tasks removed from tracking (likely already finished/removed)."
            )

    def stop(self) -> None:
        """Stop the worker and cancel all tasks."""
        thread_id = threading.get_ident()
        worker_name = self.__class__.__name__
        logger.info(f"Stop requested for {worker_name} (by thread {thread_id}).")

        # Set general cancel flag
        self._cancel_event.set()

        if self.loop and self.loop.is_running():
            # Cancel main task if it exists and is not done
            if self._main_task and not self._main_task.done():
                logger.debug(f"Cancelling main task for {worker_name}")
                self.loop.call_soon_threadsafe(self._main_task.cancel)

            # Cancel all active tasks (don't remove here, let cleanup handle final removal)
            tasks_to_cancel = []
            with self._tasks_lock:
                tasks_to_cancel = list(self._active_tasks.values())

            if tasks_to_cancel:
                logger.info(
                    f"Cancelling {len(tasks_to_cancel)} tasks during stop for {worker_name}."
                )
                for task in tasks_to_cancel:
                    if not task.done():
                        self.loop.call_soon_threadsafe(task.cancel)

            # Stop the event loop
            logger.debug(f"Requesting event loop stop for {worker_name}")
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            logger.warning(
                f"{worker_name}: Loop not running or already stopped during stop request."
            )


class CrawlerWorker(AsyncWorkerBase):
    """
    Worker for asynchronous crawling of URLs.
    Replaces the previous InitialCrawlerWorker (QRunnable).
    """

    def __init__(
        self,
        urls_with_info: List[Dict[str, Any]],
        worker_signals: WorkerSignals,
        parent=None,
    ):
        """
        Initialize the crawler worker.

        Args:
            urls_with_info: List of source dictionaries with URL and metadata
            worker_signals: Signals object for communication
            parent: Optional parent QObject
        """
        super().__init__(worker_signals, parent)
        self.source_manager = SourceManager(urls_with_info)

        # Crawler instance management
        self._crawler_lock = threading.Lock()
        self._crawler = PlaywrightCrawler()

    async def _main_worker_coroutine(self):
        """Main coroutine that performs crawling operations."""
        worker_id = threading.get_ident()
        logger.info(f"CrawlerWorker main coroutine starting (thread {worker_id})")

        try:
            # Get all initial source URLs
            initial_urls = self.source_manager.get_all_urls()
            sources_to_process = [{"url": url} for url in initial_urls]

            # Process the initial batch of sources
            await self._process_source_batch(sources_to_process)

        except asyncio.CancelledError:
            logger.info(f"CrawlerWorker main coroutine was cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error in CrawlerWorker main coroutine: {e}", exc_info=True)
        finally:
            # Signal that initial crawl phase is finished if not already cancelled
            if not self.is_cancelled():
                self.signals.initial_crawl_finished.emit()

            logger.info(f"CrawlerWorker main coroutine finished (thread {worker_id})")

    async def _process_source_batch(self, sources: List[Dict[str, Any]]) -> None:
        """
        Process a batch of sources by creating tasks for each URL.

        Args:
            sources: List of source dictionaries with URLs to process
        """
        # Create a task for each URL
        for source in sources:
            if self.is_cancelled():
                logger.info("CrawlerWorker cancelled before creating all tasks.")
                break

            url = source.get("url")
            if not url:
                continue

            # Skip URLs marked for cancellation
            if self.is_marked_for_cancellation(url):
                logger.info(f"Skipping already cancelled URL: {url}")
                self.signals.initial_crawl_status.emit(url, "Cancelled")
                continue

            # Emit initial status
            self.signals.initial_crawl_status.emit(url, "Crawling - Started")

            # Create and track the task
            task = asyncio.create_task(
                self._crawl_single_url(url), name=f"crawl_{url[:50]}"
            )
            self.add_task(url, task)

        # Wait for all tasks to complete or be cancelled
        remaining_tasks = list(self.get_active_tasks().values())
        if remaining_tasks:
            logger.info(f"Waiting for {len(remaining_tasks)} crawl tasks to complete")
            await asyncio.gather(*remaining_tasks, return_exceptions=True)

    async def _crawl_single_url(self, url: str) -> None:
        """
        Crawl a single URL and process the result.

        Args:
            url: The URL to crawl
        """
        try:
            # Check for cancellation
            if self.is_cancelled() or self.is_marked_for_cancellation(url):
                logger.info(f"Task for {url} cancelled before starting.")
                self.signals.initial_crawl_status.emit(url, "Cancelled")
                return

            # Perform the crawl
            result = await self._crawler._fetch_single(url)
            url_from_result = result.get("original_url", url)

            # Check for cancellation after crawl
            if self.is_cancelled() or self.is_marked_for_cancellation(url_from_result):
                logger.info(f"Task for {url_from_result} cancelled after completion.")
                self.signals.initial_crawl_status.emit(url_from_result, "Cancelled")
                return

            # Get source info
            source_info = self.source_manager.get_source_info(url_from_result)
            if not source_info:
                logger.warning(f"Source info missing for {url_from_result}")
                self.signals.initial_crawl_status.emit(
                    url_from_result, "Error: Missing source info"
                )
                return

            # Extract content and error information
            html = result.get("content")
            error = result.get("error")

            # Emit appropriate signals
            if error:
                self.signals.initial_crawl_status.emit(
                    url_from_result, f"Crawled - Failed: {error}"
                )
            elif html:
                self.signals.initial_crawl_status.emit(
                    url_from_result, "Crawled - Success"
                )
                self.signals.html_ready.emit(url_from_result, html, source_info)
            else:
                self.signals.initial_crawl_status.emit(
                    url_from_result, "Crawled - Failed: No content"
                )

        except asyncio.CancelledError:
            logger.info(f"Task for {url} was cancelled during execution.")
            if not self.is_cancelled():
                self.signals.initial_crawl_status.emit(url, "Cancelled")
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}", exc_info=True)
            if not self.is_cancelled():
                self.signals.initial_crawl_status.emit(url, f"Error: {str(e)[:50]}")
        finally:
            # Remove task from tracking
            self.remove_task(url)

    def add_urls_to_crawl(self, new_sources: List[Dict[str, Any]]) -> None:
        """
        Add new URLs to crawl while the worker is running.

        Args:
            new_sources: List of new source dictionaries to add

        Raises:
            RuntimeError: If the worker is not running or has been cancelled
        """
        if self.is_cancelled():
            raise RuntimeError("Cannot add URLs to cancelled crawler")

        if not self.loop or not self.loop.is_running():
            raise RuntimeError("Cannot add URLs: crawler event loop is not running")

        # Add new sources to the source manager
        self.source_manager.add_sources(new_sources)

        # Schedule the creation of new tasks on the event loop
        self.loop.call_soon_threadsafe(self._add_new_tasks, new_sources)

    def _add_new_tasks(self, new_sources: List[Dict[str, Any]]) -> None:
        """
        Create new tasks for the given sources on the event loop.
        Must only be called from within the event loop thread.

        Args:
            new_sources: List of source dictionaries to process
        """
        try:
            # Create a task for each new URL
            for source in new_sources:
                url = source.get("url")

                # Skip invalid URLs or already processing/cancelled URLs
                if not url or self.is_marked_for_cancellation(url):
                    continue

                # Skip URLs that already have active tasks
                active_tasks = self.get_active_tasks()
                if url in active_tasks:
                    continue

                # Emit initial status
                self.signals.initial_crawl_status.emit(url, "Crawling - Started")

                # Create and track the task
                task = asyncio.create_task(
                    self._crawl_single_url(url), name=f"crawl_{url[:50]}"
                )
                self.add_task(url, task)

            logger.info(f"Added {len(new_sources)} new tasks to the crawler")
        except Exception as e:
            logger.error(f"Error adding new tasks: {e}", exc_info=True)

    def _cleanup_event_loop(self, thread_id: int):
        """Clean up the event loop, pending tasks, and crawler resources."""
        worker_name = self.__class__.__name__

        # Shutdown the crawler
        try:
            logger.info(f"{worker_name} ({thread_id}): Shutting down crawler...")
            self._crawler.shutdown()
            logger.info(f"{worker_name} ({thread_id}): Crawler shut down.")
        except Exception as e:
            logger.error(
                f"{worker_name} ({thread_id}): Error shutting down crawler: {e}",
                exc_info=True,
            )

        # Call the parent class method to clean up the event loop
        super()._cleanup_event_loop(thread_id)


class ProcessorWorker(AsyncWorkerBase):
    """
    Worker for processing HTML content and running analysis.
    Replaces the previous ProcessingWorker (QThread).
    """

    def __init__(
        self,
        news_service: NewsService,
        worker_signals: WorkerSignals,
        parent=None,
    ):
        """
        Initialize the processor worker.

        Args:
            news_service: NewsService instance for database operations
            worker_signals: Signals object for communication
            parent: Optional parent QObject
        """
        super().__init__(worker_signals, parent)
        self.news_service = news_service
        self.llm_semaphore = None

    def _initialize_resources(self):
        """Initialize LLM semaphore to control concurrent LLM requests."""
        self.llm_semaphore = asyncio.Semaphore(3)

    async def _main_worker_coroutine(self):
        """
        Main coroutine that keeps the worker alive.
        For the processor, this just maintains the event loop until cancellation.
        """
        try:
            # Keep the worker alive until stopped
            while not self.is_cancelled():
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("ProcessorWorker main coroutine cancelled.")

    def submit_task(self, url: str, html_content: str, source_info: Dict[str, Any]):
        """
        Submit a processing task to be executed asynchronously.

        Args:
            url: URL of the content
            html_content: HTML content to process
            source_info: Source metadata dictionary

        Returns:
            Future object representing the task or None if submission failed
        """
        if not self.loop or not self.loop.is_running() or self.is_cancelled():
            logger.error(
                f"Cannot submit task for {url}: ProcessorWorker not ready or stopping."
            )
            self.signals.processing_finished.emit(
                url, "Error", "Processing thread not ready", ""
            )
            return None

        logger.debug(f"Submitting processing task for {url} to ProcessorWorker.")

        # Create the coroutine
        coro = self._process_task(url, html_content, source_info)

        # Schedule it on the event loop
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        # Track the future
        self.add_task(url, future)
        return future

    async def _process_task(
        self, url: str, html_content: str, source_info: Dict[str, Any]
    ):
        """
        Process a single URL's content.

        Args:
            url: URL of the content
            html_content: HTML content to process
            source_info: Source metadata dictionary
        """
        task = asyncio.current_task()
        task_id = task.get_name() if hasattr(task, "get_name") else url[:20]
        logger.debug(f"Processing task starting for {url} ({task_id}).")

        analysis_result_md = ""
        final_status = "Error"
        details = "Processing task failed unexpectedly"

        try:
            # Check for cancellation at the start
            if self.is_cancelled() or self.is_marked_for_cancellation(url):
                logger.info(f"Processing task for {url} cancelled before start.")
                raise asyncio.CancelledError()

            # Create status callback for progress updates
            def status_callback(u: str, s: str, d: str):
                if not self.is_cancelled() and not self.is_marked_for_cancellation(u):
                    self.signals.processing_status.emit(u, f"{s}: {d}")

            # Use semaphore to control concurrent LLM requests
            async with self.llm_semaphore:
                # Check cancellation before LLM
                if self.is_cancelled() or self.is_marked_for_cancellation(url):
                    logger.info(f"Processing task for {url} cancelled before LLM call.")
                    raise asyncio.CancelledError()

                # Process the HTML content and analyze - NewsService will use LLMClientPool internally
                saved_count, analysis_result_md, error_obj = (
                    await self.news_service._process_html_and_analyze(
                        url, html_content, source_info, status_callback
                    )
                )

            # Check cancellation after service call
            if self.is_cancelled() or self.is_marked_for_cancellation(url):
                logger.info(f"Processing task for {url} cancelled after service call.")
                raise asyncio.CancelledError()

            # Set final status based on results
            if error_obj:
                final_status = "Error"
                details = f"Processing Failed: {error_obj}"
            else:
                final_status = "Complete"
                details = f"Saved {saved_count} items."

        except asyncio.CancelledError:
            # Handle explicit cancellation
            final_status = "Cancelled"
            details = "Task was cancelled during execution."
            analysis_result_md = ""  # No analysis result if cancelled
            logger.info(f"Processing task for {url} ({task_id}) was cancelled.")

        except Exception as e:
            # Handle unexpected errors
            final_status = "Error"
            details = f"Unexpected processing error: {e}"
            analysis_result_md = f"Error during processing: {e}"
            logger.error(
                f"Unexpected error  {url} ({task_id}): {e}",
                exc_info=True,
            )
        finally:
            # Emit final status if not cancelled
            if not self.is_cancelled():
                self.signals.processing_finished.emit(
                    url, final_status, details, analysis_result_md
                )

            # Remove the task from tracking
            self.remove_task(url)

            logger.debug(
                f"Processing task finished for {url} ({task_id}). Status: {final_status}"
            )
