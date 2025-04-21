# src/ui/workers/news_fetch_workers.py
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading
from typing import List, Dict, Optional, Any

from PySide6.QtCore import QObject, Signal, QRunnable, QThread

from src.services.news_service import NewsService
from src.core.crawler import PlaywrightCrawler

logger = logging.getLogger(__name__)


# --- WorkerSignals Class ---
class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""

    # Initial Crawl Signals (emitted by InitialCrawlerWorker)
    html_ready = Signal(str, str, dict)  # url, html_content, source_info
    initial_crawl_status = Signal(str, str)  # url, status_message
    initial_crawl_finished = Signal()  # Signal when the *initial crawl phase* is done

    # Processing Signals (emitted by ProcessingWorker's tasks)
    processing_status = Signal(str, str)  # url, status_details
    processing_finished = Signal(
        str, str, str, str
    )  # url, final_status, details, analysis_result


# --- Runnable for Initial Crawling ---
class InitialCrawlerWorker(QRunnable):
    """
    Worker thread using QRunnable for performing the initial crawl for ALL selected URLs.
    Emits html_ready for each successfully crawled URL as it becomes available.
    Supports external cancellation.
    """

    def __init__(
        self,
        urls_with_info: List[Dict[str, Any]],
        parent_signals: WorkerSignals,
    ):
        super().__init__()
        self.urls_with_info = urls_with_info
        self.signals = parent_signals
        self._cancel_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._main_task: Optional[asyncio.Task] = None

    def is_cancelled(self):
        """Check if cancellation has been requested."""
        return self._cancel_event.is_set()

    def run(self):
        worker_id = threading.get_ident()
        logger.info(
            f"InitialCrawlerWorker ({worker_id}) started for {len(self.urls_with_info)} URLs."
        )

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._main_task = self._loop.create_task(self._crawl_tasks_async())
            self._loop.run_until_complete(self._main_task)

        except asyncio.CancelledError:
            logger.info(f"InitialCrawlerWorker ({worker_id}) main task was cancelled.")
        except Exception as e:
            logger.error(
                f"({worker_id}) Exception running InitialCrawlerWorker event loop: {e}",
                exc_info=True,
            )
        finally:
            # --- Loop Cleanup ---
            if self._loop:
                try:
                    pending = asyncio.all_tasks(self._loop)
                    tasks_to_cancel = [
                        task
                        for task in pending
                        if task is not self._main_task and not task.done()
                    ]
                    if tasks_to_cancel:
                        logger.info(
                            f"({worker_id}) Cancelling {len(tasks_to_cancel)} leftover tasks..."
                        )
                        for task in tasks_to_cancel:
                            task.cancel()
                        self._loop.run_until_complete(
                            asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                        )

                    if hasattr(self._loop, "shutdown_asyncgens"):
                        logger.debug(f"({worker_id}) Shutting down async generators...")
                        self._loop.run_until_complete(self._loop.shutdown_asyncgens())

                    logger.debug(f"({worker_id}) Closing initial crawl event loop...")
                    self._loop.close()
                    logger.info(f"({worker_id}) Initial crawl event loop closed.")
                except Exception as loop_close_err:
                    logger.error(
                        f"({worker_id}) Error closing initial crawl event loop: {loop_close_err}"
                    )
            asyncio.set_event_loop(None)

            if not self.is_cancelled():
                self.signals.initial_crawl_finished.emit()
            else:
                logger.info(
                    f"({worker_id}) Initial crawl was cancelled, finished signal suppressed."
                )
            logger.info(f"InitialCrawlerWorker ({worker_id}) run method finished.")

    async def _crawl_tasks_async(self):
        """The main async method that performs crawling by creating individual tasks for each URL."""
        worker_id = threading.get_ident()

        urls_to_crawl = [info["url"] for info in self.urls_with_info]
        source_map = {info["url"]: info for info in self.urls_with_info}
        tasks_processed_count = 0

        try:
            # Use context management to automatically start and shut down PlaywrightCrawler
            async with PlaywrightCrawler() as crawler:
                # Create individual tasks for each URL instead of using process_urls
                tasks = []
                for url in urls_to_crawl:
                    if self.is_cancelled():
                        logger.info(f"Initial crawl ({worker_id}) cancelled before creating tasks.")
                        raise asyncio.CancelledError()
                    
                    # Create task for each URL using _fetch_single directly
                    task = asyncio.create_task(
                        crawler._fetch_single(url, scroll_page=True),
                        name=f"fetch_{url[:50]}"
                    )
                    tasks.append(task)
                
                # Process completed tasks
                for future in asyncio.as_completed(tasks):
                    if self.is_cancelled():
                        logger.info(f"Initial crawl ({worker_id}) cancelled during task processing.")
                        raise asyncio.CancelledError()
                    
                    try:
                        result = await future
                        tasks_processed_count += 1
                        url = result.get("original_url")
                        html = result.get("content")
                        error = result.get("error")
                        source_info = source_map.get(url)

                        if not source_info:
                            logger.warning(f"({worker_id}) Crawler returned result for unknown URL: {url}")
                            continue

                        if error:
                            self.signals.initial_crawl_status.emit(url, f"Crawled - Failed: {error}")
                        elif html:
                            self.signals.initial_crawl_status.emit(url, "Crawled - Success")
                            self.signals.html_ready.emit(url, html, source_info)
                        else:
                            self.signals.initial_crawl_status.emit(url, "Crawled - Failed: No content")
                    
                    except Exception as e:
                        task_name = future.get_name() if hasattr(future, "get_name") else "unknown_task"
                        logger.error(f"Task {task_name} raised an unexpected exception: {e}", exc_info=True)
                        
                        # Try to extract URL from task name to report failure
                        original_url = (
                            task_name.replace("fetch_", "") if task_name.startswith("fetch_") else "unknown_url"
                        )
                        
                        source_info = source_map.get(original_url)
                        if source_info:
                            self.signals.initial_crawl_status.emit(
                                original_url, f"Crawled - Failed: Task execution error: {e}"
                            )

        except asyncio.CancelledError:
            logger.info(f"({worker_id}) _crawl_tasks_async caught CancelledError.")
        except Exception as e:
            logger.error(f"({worker_id}) Error in _crawl_tasks_async: {e}", exc_info=True)
        finally:
            logger.info(f"({worker_id}) Initial crawl loop finished after {tasks_processed_count} results.")

    def cancel(self):
        """Requests cancellation of the worker."""
        requesting_thread_id = threading.get_ident()
        logger.info(
            f"InitialCrawlerWorker cancellation requested (by thread {requesting_thread_id})."
        )
        self._cancel_event.set()

        if (
            self._loop
            and self._loop.is_running()
            and self._main_task
            and not self._main_task.done()
        ):
            logger.info(
                "Requesting cancellation of main asyncio task via call_soon_threadsafe."
            )
            self._loop.call_soon_threadsafe(self._main_task.cancel)
        elif self._loop:
            logger.info("Requesting loop stop via call_soon_threadsafe.")
            self._loop.call_soon_threadsafe(self._loop.stop)


# --- ProcessingWorker QThread ---
class ProcessingWorker(QThread):
    """
    Dedicated QThread that runs an asyncio event loop to process analysis tasks concurrently.
    """

    def __init__(self, news_service: NewsService, signals: WorkerSignals, llm_base_url: str, llm_api_key: str, parent=None):
        super().__init__(parent)
        self.news_service = news_service
        self.signals = signals
        self.llm_base_url = llm_base_url
        self.llm_api_key = llm_api_key
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_ready = threading.Event()
        self._cancel_event = threading.Event()
        self._futures = set()
        self.llm_semaphore = None  # Will be initialized in the run method
        logger.info("ProcessingWorker (QThread) initialized.")

    def run(self):
        thread_id = threading.get_ident()
        logger.info(f"ProcessingWorker ({thread_id}) thread starting...")
        try:
            # 1) Create and register event loop
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # 2) Initialize LLM concurrency control semaphore
            self.llm_semaphore = asyncio.Semaphore(3)

            # 3) Notify main thread: loop is ready
            self.loop.call_soon(self._is_ready.set)

            logger.info(f"ProcessingWorker ({thread_id}) event loop running...")
            self.loop.run_forever()

        except Exception as e:
            logger.error(
                f"ProcessingWorker ({thread_id}) event loop error: {e}", exc_info=True
            )
        finally:
            logger.info(f"ProcessingWorker ({thread_id}) event loop stopping...")
            if self.loop:
                try:
                    # Cleanup before closing loop (cancel pending tasks)
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

                        async def gather_cancel():
                            await asyncio.gather(
                                *tasks_to_cancel, return_exceptions=True
                            )

                        if self.loop.is_running():
                            self.loop.run_until_complete(gather_cancel())

                    if hasattr(self.loop, "shutdown_asyncgens"):
                        logger.debug(f"Shutting down async generators ({thread_id})...")
                        if self.loop.is_running():
                            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                        logger.debug(f"Async generators shut down ({thread_id}).")

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
            if asyncio.current_task().cancelled():
                logger.info(f"Processing task for {url} cancelled before start.")
                raise asyncio.CancelledError()

            def status_callback(u, s, d):
                if (
                    self.loop
                    and self.loop.is_running()
                    and not asyncio.current_task().cancelled()
                ):
                    self.signals.processing_status.emit(u, f"{s}: {d}")

            # Use semaphore to control the number of concurrent LLM clients
            async with self.llm_semaphore:
                # Dynamically create LLM client
                from src.services.llm_client import LLMClient
                llm_client = LLMClient(
                    base_url=self.llm_base_url,
                    api_key=self.llm_api_key,
                    async_mode=True,
                )
                logger.debug(f"Created LLM client for task {task_id}")
                
                # Use the dynamically created LLM client to execute the task
                saved_count, analysis_result_md, error_obj = (
                    await self.news_service._process_html_and_analyze(
                        url, html_content, source_info, status_callback, llm_client
                    )
                )

            if asyncio.current_task().cancelled():
                logger.info(f"Processing task for {url} cancelled after service call.")
                raise asyncio.CancelledError()

            if error_obj:
                final_status = "Error"
                details = f"Processing Failed: {error_obj}"
            else:
                final_status = "Complete"
                details = f"Saved {saved_count} items."

        except asyncio.CancelledError:
            final_status = "Cancelled"
            details = "Task was cancelled during execution."
            logger.info(f"Processing task for {url} ({task_id}) was cancelled.")

        except Exception as e:
            final_status = "Error"
            details = f"Unexpected processing task error: {e}"
            analysis_result_md = f"Error during processing: {e}"
            logger.error(
                f"Unexpected error processing task for {url} ({task_id}): {e}",
                exc_info=True,
            )
        finally:
            logger.debug(
                f"Processing task finished/cancelled for {url} ({task_id}). Status: {final_status}"
            )
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
        """Submits a processing task (coroutine) to the running event loop."""
        if self.loop and self.loop.is_running():
            logger.debug(f"Submitting processing task for {url} to worker event loop.")
            coro = self._do_process_task(url, html_content, source_info)
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            self._futures.add(future)
            future.add_done_callback(lambda f: self._futures.discard(f))
            return future
        else:
            logger.error(
                f"Cannot submit task for {url}: ProcessingWorker loop is not running."
            )
            self.signals.processing_finished.emit(
                url, "Error", "Processing thread not ready", ""
            )
            return None

    def stop(self):
        """Stops the event loop and the thread, cancelling pending tasks."""
        thread_id = threading.get_ident()
        logger.info(f"Stop requested for ProcessingWorker ({thread_id}).")
        if self.loop and self.loop.is_running():
            # 1) Set exit flag
            self._cancel_event.set()

            # 2) Cancel pending futures to avoid "loop closed" exceptions
            for future in list(self._futures):
                if not future.done():
                    future.cancel()

            # 3) Stop event loop
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            logger.warning(
                f"ProcessingWorker ({thread_id}) loop not running or already stopped."
            )