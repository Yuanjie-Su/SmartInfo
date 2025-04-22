# src/ui/workers/news_fetch_workers.py
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading
from typing import List, Dict, Optional, Any, Set

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
    Supports external cancellation (general and specific).
    """

    def __init__(
        self,
        urls_with_info: List[Dict[str, Any]],
        parent_signals: WorkerSignals,
    ):
        super().__init__()
        self.urls_with_info = urls_with_info
        self.signals = parent_signals
        self._cancel_event = threading.Event()  # General cancel flag
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._main_task: Optional[asyncio.Task] = None

        # --- Task tracking and specific cancellation ---
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._tasks_lock = threading.Lock()  # Lock for accessing _active_tasks
        self._urls_to_cancel: Set[str] = set()
        self._specific_cancel_lock = threading.Lock()

    def is_cancelled(self):
        """Check if general cancellation has been requested."""
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
            # Ensure final signal is emitted even on cancellation
            if not self._cancel_event.is_set():
                self.signals.initial_crawl_finished.emit()
        except Exception as e:
            logger.error(
                f"({worker_id}) Exception running InitialCrawlerWorker event loop: {e}",
                exc_info=True,
            )
            # Ensure final signal is emitted on other errors too
            if not self.is_cancelled():
                self.signals.initial_crawl_finished.emit()
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

            # Cleanup active task references
            with self._tasks_lock:
                self._active_tasks.clear()

            logger.info(f"InitialCrawlerWorker ({worker_id}) run method finished.")

    async def _crawl_tasks_async(self):
        """The main async method that performs crawling."""
        worker_id = threading.get_ident()
        source_map = {info["url"]: info for info in self.urls_with_info}
        tasks_processed_count = 0

        try:
            # Use context management for the crawler
            async with PlaywrightCrawler() as crawler:
                tasks_to_await = []
                for url, source_info in source_map.items():
                    if self.is_cancelled():
                        logger.info(
                            f"Initial crawl ({worker_id}) cancelled before creating task for {url}."
                        )
                        break

                    # --- Create and track task ---
                    task = asyncio.create_task(
                        crawler._fetch_single(url, scroll_page=True),
                        name=f"fetch_{url[:50]}",
                    )
                    with self._tasks_lock:
                        self._active_tasks[url] = task
                    tasks_to_await.append(task)

                # Process completed tasks
                async for future in asyncio.as_completed(tasks_to_await):
                    original_url = "unknown_url"
                    task_name = (
                        future.get_name() if hasattr(future, "get_name") else "unknown_task"
                    )
                    if task_name.startswith("fetch_"):
                        original_url = task_name.replace("fetch_", "")

                    # --- Check for specific cancellation before awaiting ---
                    with self._specific_cancel_lock:
                        should_skip = original_url in self._urls_to_cancel

                    if should_skip:
                        logger.info(
                            f"Skipping result for specifically cancelled URL: {original_url}"
                        )
                        if not self.is_cancelled():
                            self.signals.initial_crawl_status.emit(original_url, "Cancelled")
                        tasks_processed_count += 1
                        continue

                    if self.is_cancelled():
                        logger.info(
                            f"Initial crawl ({worker_id}) cancelled during task processing for {original_url}."
                        )
                        break

                    try:
                        result = await future
                        tasks_processed_count += 1
                        url_from_result = result.get("original_url")

                        # --- Re-check specific cancellation *after* await ---
                        with self._specific_cancel_lock:
                            if url_from_result in self._urls_to_cancel:
                                logger.info(
                                    f"Result for {url_from_result} arrived after specific cancel request. Ignoring."
                                )
                                if not self.is_cancelled():
                                    self.signals.initial_crawl_status.emit(
                                        url_from_result, "Cancelled"
                                    )
                                continue

                        html = result.get("content")
                        error = result.get("error")
                        source_info = source_map.get(url_from_result)

                        if not source_info:
                            logger.warning(
                                f"({worker_id}) Crawler returned result for unknown URL: {url_from_result}"
                            )
                            continue

                        if not self.is_cancelled():
                            if error:
                                self.signals.initial_crawl_status.emit(
                                    url_from_result, f"Crawled - Failed: {error}"
                                )
                            elif html:
                                self.signals.initial_crawl_status.emit(
                                    url_from_result, "Crawled - Success"
                                )
                                self.signals.html_ready.emit(
                                    url_from_result, html, source_info
                                )
                            else:
                                self.signals.initial_crawl_status.emit(
                                    url_from_result, "Crawled - Failed: No content"
                                )

                    except asyncio.CancelledError:
                        logger.info(f"Task for {original_url} was cancelled.")
                        if not self.is_cancelled():
                            self.signals.initial_crawl_status.emit(original_url, "Cancelled")
                    except Exception as e:
                        logger.error(
                            f"Task {task_name} raised an unexpected exception: {e}",
                            exc_info=True,
                        )
                        if not self.is_cancelled():
                            self.signals.initial_crawl_status.emit(
                                original_url, "Crawled - Failed: Task Error"
                            )
                    finally:
                        # --- Remove task from active dict ---
                        with self._tasks_lock:
                            self._active_tasks.pop(original_url, None)

        except asyncio.CancelledError:
            logger.info(f"({worker_id}) _crawl_tasks_async caught CancelledError.")
            raise
        except Exception as e:
            logger.error(f"({worker_id}) Error in _crawl_tasks_async: {e}", exc_info=True)
        finally:
            logger.info(
                f"({worker_id}) Initial crawl loop finished after processing {tasks_processed_count} results."
            )

    def cancel(self):
        """Requests general cancellation of the worker."""
        if self.is_cancelled():
            return
        requesting_thread_id = threading.get_ident()
        logger.info(
            f"InitialCrawlerWorker general cancellation requested (by thread {requesting_thread_id})."
        )
        self._cancel_event.set()

        # Also trigger specific cancellation for all remaining active tasks
        with self._tasks_lock:
            urls_to_cancel_now = list(self._active_tasks.keys())
        if urls_to_cancel_now:
            self.cancel_specific_tasks(urls_to_cancel_now)

        # Cancel the main task coordinating the fetches
        if (
            self._loop
            and self._loop.is_running()
            and self._main_task
            and not self._main_task.done()
        ):
            logger.info("Requesting cancellation of main asyncio task via call_soon_threadsafe.")
            self._loop.call_soon_threadsafe(self._main_task.cancel)
        elif self._loop and not self._loop.is_running():
            logger.warning("Loop not running, cannot schedule main task cancellation or stop.")
        elif self._loop:
            logger.info("Requesting loop stop via call_soon_threadsafe.")
            self._loop.call_soon_threadsafe(self._loop.stop)

    def cancel_specific_tasks(self, urls: List[str]):
        """Requests cancellation of specific tasks by URL."""
        if self.is_cancelled():
            return

        requesting_thread_id = threading.get_ident()
        logger.info(
            f"InitialCrawlerWorker specific cancellation requested for {len(urls)} URLs (by thread {requesting_thread_id})."
        )

        with self._specific_cancel_lock:
            self._urls_to_cancel.update(urls)

        if self._loop and self._loop.is_running():
            tasks_to_schedule_cancel = []
            with self._tasks_lock:
                for url in urls:
                    task = self._active_tasks.get(url)
                    if task and not task.done():
                        tasks_to_schedule_cancel.append(task)

            if tasks_to_schedule_cancel:
                logger.info(
                    f"Scheduling cancellation for {len(tasks_to_schedule_cancel)} specific asyncio tasks."
                )
                for task in tasks_to_schedule_cancel:
                    self._loop.call_soon_threadsafe(task.cancel)
        elif self._loop:
            logger.warning("Loop not running, cannot schedule specific task cancellation.")
        else:
            logger.warning("Loop not available, cannot schedule specific task cancellation.")


# --- ProcessingWorker QThread ---
class ProcessingWorker(QThread):
    """
    Dedicated QThread that runs an asyncio event loop to process analysis tasks concurrently.
    Supports specific task cancellation.
    """

    def __init__(self, news_service: NewsService, signals: WorkerSignals, llm_base_url: str, llm_api_key: str, parent=None):
        super().__init__(parent)
        self.news_service = news_service
        self.signals = signals
        self.llm_base_url = llm_base_url
        self.llm_api_key = llm_api_key
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_ready = threading.Event()
        self._cancel_event = threading.Event()  # General stop flag
        # --- Future tracking and specific cancellation ---
        self._active_futures: Dict[str, asyncio.Future] = {}
        self._futures_lock = threading.Lock()  # Lock for accessing _active_futures
        self.llm_semaphore = None
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
            logger.error(f"ProcessingWorker ({thread_id}) event loop error: {e}", exc_info=True)
        finally:
            logger.info(f"ProcessingWorker ({thread_id}) event loop stopping...")
            if self.loop:
                try:
                    # Cancel remaining registered futures first
                    with self._futures_lock:
                        futures_to_cancel = list(self._active_futures.values())
                    if futures_to_cancel:
                        logger.info(f"Cancelling {len(futures_to_cancel)} remaining processing futures...")
                        for future in futures_to_cancel:
                            if not future.done():
                                self.loop.call_soon_threadsafe(future.cancel)

                    # Cleanup before closing loop (cancel pending tasks)
                    pending_tasks = asyncio.all_tasks(self.loop)
                    tasks_to_cancel = [task for task in pending_tasks if not task.done()]
                    if tasks_to_cancel:
                        logger.info(f"Cancelling {len(tasks_to_cancel)} remaining tasks in loop ({thread_id})...")
                        for task in tasks_to_cancel:
                            task.cancel()

                        async def gather_cancel():
                            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

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
                        logger.info(f"ProcessingWorker ({thread_id}) event loop closed.")
                    else:
                        logger.debug(f"ProcessingWorker ({thread_id}) loop already closed.")

                except Exception as close_err:
                    logger.error(f"ProcessingWorker ({thread_id}) error during loop cleanup: {close_err}", exc_info=True)

            # Clear tracked futures
            with self._futures_lock:
                self._active_futures.clear()

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
        task = asyncio.current_task()
        task_id = task.get_name() if hasattr(task, "get_name") else url[:20]
        logger.debug(f"Processing task starting for {url} on worker loop ({task_id}).")
        analysis_result_md = ""
        final_status = "Error"
        details = "Processing task failed unexpectedly"

        try:
            # ---Check for cancellation at the start ---
            if task.cancelled():
                logger.info(f"Processing task for {url} cancelled before start.")
                raise asyncio.CancelledError()

            def status_callback(u, s, d):
                # --- Check cancellation before emitting status ---
                if self.loop and self.loop.is_running() and not task.cancelled():
                    self.signals.processing_status.emit(u, f"{s}: {d}")


            # Use semaphore to control the number of concurrent LLM clients
            async with self.llm_semaphore:
                # --- Check cancellation before LLM ---
                if task.cancelled():
                    logger.info(f"Processing task for {url} cancelled before LLM call.")
                    raise asyncio.CancelledError()

                from src.services.llm_client import LLMClient

                llm_client = LLMClient(
                    base_url=self.llm_base_url,
                    api_key=self.llm_api_key,
                    async_mode=True,
                )
                logger.debug(f"Created LLM client for task {task_id}")

                saved_count, analysis_result_md, error_obj = (
                    await self.news_service._process_html_and_analyze(
                        url, html_content, source_info, status_callback, llm_client
                    )
                )

            # --- Check cancellation after LLM/service call ---
            if task.cancelled():
                logger.info(f"Processing task for {url} cancelled after service call.")
                raise asyncio.CancelledError()

            if error_obj:
                final_status = "Error"
                details = f"Processing Failed: {error_obj}"
            else:
                final_status = "Complete"
                details = f"Saved {saved_count} items."

        except asyncio.CancelledError:
            # --- Handle cancellation explicitly ---
            final_status = "Cancelled"
            details = "Task was cancelled during execution."
            analysis_result_md = ""  # No analysis result if cancelled
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
                final_analysis = analysis_result_md if final_status != "Cancelled" else ""
                self.signals.processing_finished.emit(
                    url,
                    final_status,
                    details,
                    final_analysis
                )
            else:
                logger.warning(f"Skipping final signal for {url} as loop is stopped.")

            # --- Remove future from tracking dict ---
            with self._futures_lock:
                if url in self._active_futures:
                    del self._active_futures[url]

    def submit_task(self, url: str, html_content: str, source_info: Dict[str, Any]):
        """Submits a processing task (coroutine) to the running event loop."""
        if self.loop and self.loop.is_running() and not self._cancel_event.is_set():
            logger.debug(f"Submitting processing task for {url} to worker event loop.")
            coro = self._do_process_task(url, html_content, source_info)
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            # --- Track the future ---
            with self._futures_lock:
                self._active_futures[url] = future

            return future
        else:
            logger.error(
                f"Cannot submit task for {url}: ProcessingWorker loop not running or stopping."
            )
            self.signals.processing_finished.emit(
                url, "Error", "Processing thread not ready", ""
            )
            return None

    def cancel_specific_tasks(self, urls: List[str]):
        """Requests cancellation of specific processing tasks by URL."""
        if not self.loop or not self.loop.is_running():
            logger.warning("ProcessingWorker loop not running, cannot cancel specific tasks.")
            return

        requesting_thread_id = threading.get_ident()
        logger.info(
            f"ProcessingWorker specific cancellation requested for {len(urls)} URLs (by thread {requesting_thread_id})."
        )

        futures_to_cancel = []
        with self._futures_lock:
            for url in urls:
                future = self._active_futures.get(url)
                if future and not future.done():
                    futures_to_cancel.append(future)

        if futures_to_cancel:
            logger.info(f"Scheduling cancellation for {len(futures_to_cancel)} specific processing futures.")
            for future in futures_to_cancel:
                self.loop.call_soon_threadsafe(future.cancel)
        else:
            logger.debug("No active processing futures found for the specified URLs to cancel.")

    def stop(self):
        """Stops the event loop and the thread, cancelling pending tasks."""
        thread_id = threading.get_ident()
        logger.info(f"Stop requested for ProcessingWorker ({thread_id}).")
        if self.loop and self.loop.is_running():
            # 1) Set general exit flag
            self._cancel_event.set()
            # 2) Cancel pending futures explicitly using the lock
            with self._futures_lock:
                futures_to_cancel_on_stop = list(self._active_futures.values())
            if futures_to_cancel_on_stop:
                logger.info(f"Cancelling {len(futures_to_cancel_on_stop)} processing futures during general stop.")
                for future in futures_to_cancel_on_stop:
                    if not future.done():
                        self.loop.call_soon_threadsafe(future.cancel)
            # 3) Stop event loop
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            logger.warning(
                f"ProcessingWorker ({thread_id}) loop not running or already stopped."
            )
