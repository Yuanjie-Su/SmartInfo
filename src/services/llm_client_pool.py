# src/services/llm_client_pool.py
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading  # Use threading lock for acquire synchronization
from contextlib import asynccontextmanager
from typing import List, Optional

from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class LLMClientPool:
    """
    Manages a pool of asynchronous LLMClient instances with lazy initialization.
    """

    def __init__(self, pool_size: int, base_url: str, api_key: Optional[str]):
        """
        Initializes the pool.

        Args:
            pool_size: The number of LLMClient instances in the pool.
            base_url: The base URL for the LLM API.
            api_key: The API key for the LLM service.
        """
        if pool_size <= 0:
            raise ValueError("Pool size must be positive")

        self._pool_size = pool_size
        self._base_url = base_url
        self._api_key = api_key
        self._clients: List[LLMClient] = []
        self._queue: Optional[asyncio.Queue[LLMClient]] = None  # Initialize queue later
        self._init_lock = threading.Lock()  # Lock for thread-safe initialization
        self._initialized = False
        self._loop = None  # Store the loop where clients were created

    async def _ensure_initialized(self):
        """Initializes the pool if not already done. Coroutine."""
        # This check is outside the lock for performance, but the critical
        # initialization part is inside the lock (double-checked locking)
        if self._initialized:
            return

        # Acquire the thread lock to ensure only one thread initializes
        with self._init_lock:
            # Double-check if another thread initialized while waiting for the lock
            if self._initialized:
                return

            logger.info(
                f"Lazy initializing LLMClientPool with size {self._pool_size}..."
            )
            try:
                self._loop = (
                    asyncio.get_running_loop()
                )  # Get loop from the current async context
                self._queue = asyncio.Queue(maxsize=self._pool_size)
                clients_to_add = []
                for i in range(self._pool_size):
                    # Ensure clients are created in async mode
                    client = LLMClient(
                        base_url=self._base_url, api_key=self._api_key, async_mode=True
                    )
                    clients_to_add.append(client)
                    await self._queue.put(client)  # Put into queue immediately
                    logger.debug(
                        f"Created and added LLMClient {i+1}/{self._pool_size} to pool."
                    )

                self._clients.extend(clients_to_add)  # Store references for closing
                self._initialized = True
                logger.info("LLMClientPool lazy initialized successfully.")
            except Exception as e:
                logger.error(
                    f"Failed to lazy initialize LLMClientPool: {e}", exc_info=True
                )
                # Reset state on failure
                self._clients = []
                self._queue = None
                self._initialized = False
                raise RuntimeError(f"LLMClientPool initialization failed: {e}") from e

    async def _acquire(self) -> LLMClient:
        """Acquires a client, initializing the pool if necessary."""
        # Ensure pool is initialized (this is now an async method)
        await self._ensure_initialized()

        if not self._queue:  # Check if initialization failed
            raise RuntimeError(
                "LLMClientPool is not initialized or initialization failed."
            )

        logger.debug("Attempting to acquire LLMClient from pool...")
        client = await self._queue.get()
        logger.debug(f"Acquired LLMClient. Pool size: {self._queue.qsize()} available.")
        return client

    async def _release(self, client: LLMClient):
        """Releases a client back into the pool."""
        if not self._initialized or not self._queue:
            logger.warning(
                "Attempting to release client to an uninitialized or closed pool."
            )
            # Try to close the client if we can't put it back
            if hasattr(client._client, "close"):
                try:
                    await client._client.close()
                except Exception:
                    pass
            return

        await self._queue.put(client)
        logger.debug(
            f"Released LLMClient back to pool. Pool size: {self._queue.qsize()} available."
        )

    @asynccontextmanager
    async def context(self):
        """Provides an async context manager to acquire and release a client."""
        # Acquire calls _ensure_initialized internally now
        client = await self._acquire()
        try:
            yield client
        finally:
            await self._release(client)

    async def close(self):
        """Closes all underlying clients in the pool if initialized."""
        # Use the same lock as initialization to prevent race conditions during shutdown
        with self._init_lock:
            if not self._initialized:
                logger.info("LLMClientPool closing: Pool was not initialized.")
                return

            if not self._clients:
                logger.info("LLMClientPool closing: No clients were created.")
                self._initialized = False  # Mark as closed
                return

            logger.info(
                f"Closing LLMClientPool (closing {len(self._clients)} clients)..."
            )
            close_tasks = []
            for client in self._clients:
                if hasattr(client._client, "close"):
                    logger.debug(
                        f"Scheduling close for client connected to {client.base_url}"
                    )
                    close_tasks.append(client._client.close())
                # Add other close methods if necessary

            # Run all close tasks concurrently
            if close_tasks:
                # Use the loop where clients were created if available
                loop_to_use = self._loop or asyncio.get_event_loop()
                # Ensure we run gather within the correct loop context
                # Running gather directly might be sufficient if close is called from async context
                try:
                    results = await asyncio.gather(*close_tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(
                                f"Error closing LLMClient instance {i+1}: {result}",
                                exc_info=result,
                            )
                except RuntimeError as e:
                    logger.error(
                        f"Error running gather during pool close: {e}. This might happen if called from a closed loop.",
                        exc_info=True,
                    )

            # Clear internal state
            self._clients.clear()
            self._queue = None  # Allow garbage collection
            self._initialized = False  # Mark as closed
            logger.info("LLMClientPool closed.")

    def get_pool_size(self) -> int:
        return self._pool_size

    def get_available_count(self) -> int:
        """Returns the number of currently available clients in the pool."""
        if not self._queue:
            return 0
        return self._queue.qsize()
