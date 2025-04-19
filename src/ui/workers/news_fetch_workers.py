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

    # Signal to indicate ALL processing tasks are completed (can be useful)
    # all_processing_complete = Signal() # 可选，如果需要一个总完成信号


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

    def run(self):
        worker_id = threading.get_ident()
        logger.info(
            f"InitialCrawlerWorker ({worker_id}) started for {len(self.urls_with_info)} URLs."
        )

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._crawler_instance = (
                PlaywrightCrawler()
            )  # Initialize PlaywrightCrawler here

            self._main_task = self._loop.create_task(self._crawl_tasks_async())
            self._loop.run_until_complete(self._main_task)

        except asyncio.CancelledError:
            logger.info(f"InitialCrawlerWorker ({worker_id}) main task was cancelled.")
            if self._loop and self._loop.is_running():
                self._loop.run_until_complete(self._shutdown_crawler())

        except Exception as e:
            logger.error(
                f"({worker_id}) Exception running InitialCrawlerWorker event loop: {e}",
                exc_info=True,
            )
            if self._loop and self._loop.is_running():
                self._loop.run_until_complete(self._shutdown_crawler())

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
        """The main async method that performs crawling."""
        worker_id = threading.get_ident()
        if not self._crawler_instance:
            logger.error(f"({worker_id}) Crawler instance not available.")
            return

        urls_to_crawl = [info["url"] for info in self.urls_with_info]
        source_map = {info["url"]: info for info in self.urls_with_info}
        tasks_processed_count = 0

        try:
            async for result in self._crawler_instance.process_urls(
                urls_to_crawl, scroll_pages=False
            ):
                if self.is_cancelled():
                    logger.info(
                        f"Initial crawl ({worker_id}) cancelled during processing loop."
                    )
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

                if self.is_cancelled():
                    break

                if error:
                    self.signals.initial_crawl_status.emit(
                        url, f"Crawled - Failed: {error}"
                    )
                elif html:
                    self.signals.initial_crawl_status.emit(url, "Crawled - Success")
                    self.signals.html_ready.emit(url, html, source_info)
                else:
                    self.signals.initial_crawl_status.emit(
                        url, "Crawled - Failed: No content"
                    )

        except asyncio.CancelledError:
            logger.info(f"({worker_id}) _crawl_tasks_async caught CancelledError.")
        except Exception as e:
            logger.error(
                f"({worker_id}) Error in _crawl_tasks_async: {e}", exc_info=True
            )
        finally:
            await self._shutdown_crawler()
            logger.info(
                f"({worker_id}) Initial crawl task generator finished/cancelled after {tasks_processed_count} results."
            )

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

    def __init__(self, news_service: NewsService, signals: WorkerSignals, parent=None):
        super().__init__(parent)
        self.news_service = news_service
        self.signals = signals
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_ready = threading.Event()
        self._futures = set()
        logger.info("ProcessingWorker (QThread) initialized.")

    def run(self):
        thread_id = threading.get_ident()
        logger.info(f"ProcessingWorker ({thread_id}) thread starting...")
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._is_ready.set()
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

            saved_count, analysis_result_md, error_obj = (
                await self.news_service._process_html_and_analyze(
                    url, html_content, source_info, status_callback
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
            logger.debug(
                f"Requesting cancellation of {len(self._futures)} tracked futures ({thread_id})."
            )
            cancelled_count = 0
            for future in list(self._futures):
                if not future.done():
                    future.cancel()
                    cancelled_count += 1
            if cancelled_count > 0:
                logger.info(f"Requested cancellation for {cancelled_count} futures.")

            logger.debug(
                f"Requesting event loop stop via call_soon_threadsafe ({thread_id})."
            )
            self.loop.call_soon_threadsafe(self.loop.stop)
        else:
            logger.warning(
                f"ProcessingWorker ({thread_id}) loop not running or already stopped."
            )
