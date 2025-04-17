# src/ui/async_runner.py
# -*- coding: utf-8 -*-
import asyncio
import logging
from PySide6.QtCore import QRunnable, QObject, Signal

logger = logging.getLogger(__name__)


class AsyncTaskRunner(QRunnable):
    """Class for running asynchronous tasks in QThreadPool"""

    class Signals(QObject):
        """Nested class for emitting signals"""

        finished = Signal(object)  # Task completion signal with result
        error = Signal(Exception)  # Task error signal with exception
        progress = Signal(object)  # Optional progress signal

    def __init__(self, coro, *args, **kwargs):
        """Initialize the async task runner
        Args:
            coro: Coroutine function to run (callable)
            *args: Positional arguments to pass to the coroutine function
            **kwargs: Keyword arguments to pass to the coroutine function
        """
        super().__init__()
        self.coro_func = coro
        self.args = args
        self.kwargs = kwargs
        self.signals = self.Signals()
        self.is_cancelled = False

    def run(self):
        """Run the coroutine"""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Pass args and kwargs to the awaitable coro_func
            # Also pass self.signals.progress if the coro supports progress reporting
            if "progress_callback" in self.coro_func.__code__.co_varnames:
                self.kwargs["progress_callback"] = self.signals.progress.emit

            coro_obj = self.coro_func(*self.args, **self.kwargs)
            result = loop.run_until_complete(coro_obj)
            if not self.is_cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            if not self.is_cancelled:
                logger.error(f"Async task execution failed: {str(e)}", exc_info=True)
                self.signals.error.emit(e)
        finally:
            if loop:
                try:
                    # Cancel remaining tasks in the loop before closing
                    tasks = asyncio.all_tasks(loop)
                    for task in tasks:
                        task.cancel()
                    # Allow tasks to be cancelled
                    loop.run_until_complete(
                        asyncio.gather(*tasks, return_exceptions=True)
                    )
                    loop.close()
                    asyncio.set_event_loop(None)  # Reset the event loop for the thread
                except Exception as close_err:
                    logger.error(
                        f"Error closing async event loop: {close_err}", exc_info=True
                    )

    def cancel(self):
        self.is_cancelled = True
        # Further cancellation logic might be needed depending on the async task
