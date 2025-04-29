# backend/core/llm/pool.py
# -*- coding: utf-8 -*-

"""
Manages a pool of asynchronous LLMClient instances for efficient resource reuse.
Handles lazy initialization and provides a context manager for acquiring clients.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, AsyncGenerator

# Import AsyncLLMClient from the refactored client module
from .client import AsyncLLMClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-v3-250324"


class LLMClientPool:
    """
    Manages a pool of AsyncLLMClient instances.

    Provides thread-safe lazy initialization and an async context manager
    for acquiring and automatically releasing client instances.
    """

    def __init__(
        self,
        pool_size: int,
        base_url: str,
        api_key: str,
        context_window: int = 40960,
        max_tokens: int = 2048,
        model: Optional[str] = DEFAULT_MODEL,
        timeout: int = 60,
        max_retries_client: int = 3,  # Retries configured within each client
    ):
        """
        Initializes the pool configuration. Pool is initialized lazily on first use.

        Args:
            pool_size: The desired number of AsyncLLMClient instances in the pool.
            base_url: The base URL for the LLM API (passed to clients).
            api_key: The API key for the LLM service (passed to clients).
            model: The default LLM model name (passed to clients).
            timeout: Request timeout in seconds (passed to clients).
            max_retries_client: Max retries for transient errors within each client instance.
        """
        if pool_size <= 0:
            raise ValueError("Pool size must be a positive integer.")

        self._pool_size = pool_size
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._context_window = context_window
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries_client = max_retries_client

        self._clients: List[AsyncLLMClient] = []  # Stores references for closing
        self._queue: Optional[asyncio.Queue[AsyncLLMClient]] = (
            None  # Holds available clients
        )
        # Use asyncio.Lock for async operations within the pool itself
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._initializing = False  # Flag to prevent concurrent initialization attempts

    async def _initialize_pool(self):
        """Initializes the client queue and creates client instances."""
        # This method assumes the _init_lock is already held
        if self._initialized or self._initializing:
            return

        self._initializing = True
        logger.info(f"Initializing LLMClientPool (Size: {self._pool_size})...")
        try:
            self._queue = asyncio.Queue(maxsize=self._pool_size)
            clients_created = []
            for i in range(self._pool_size):
                try:
                    # Use AsyncLLMClient directly instead of LLMClient with async_mode=True
                    client = AsyncLLMClient(
                        base_url=self._base_url,
                        api_key=self._api_key,
                        model=self._model,
                        timeout=self._timeout,
                        max_retries=self._max_retries_client,
                    )
                    clients_created.append(client)
                    await self._queue.put(client)
                    logger.debug(
                        f"Created AsyncLLMClient {i+1}/{self._pool_size} and added to pool queue."
                    )
                except Exception as client_error:
                    logger.error(
                        f"Failed to create AsyncLLMClient instance {i+1}: {client_error}",
                        exc_info=True,
                    )
                    # Clean up already created clients in this attempt if one fails
                    for created_client in clients_created:
                        await created_client.close()
                    self._queue = None  # Reset queue
                    self._initializing = False
                    raise RuntimeError(
                        "Failed to create all clients for the pool."
                    ) from client_error

            self._clients = clients_created  # Store references only if all are created
            self._initialized = True
            logger.info("LLMClientPool initialized successfully.")

        except Exception as e:
            logger.error(f"LLMClientPool initialization failed: {e}", exc_info=True)
            # Ensure state is reset
            self._clients = []
            self._queue = None
            self._initialized = False
            raise  # Re-raise the exception
        finally:
            self._initializing = False

    async def _ensure_initialized(self):
        """Ensures the pool is initialized, performing lazy initialization if needed."""
        if self._initialized:
            return
        # Use async lock to prevent race conditions during initialization
        async with self._init_lock:
            # Double-check after acquiring the lock
            if not self._initialized:
                await self._initialize_pool()

    async def acquire(self) -> AsyncLLMClient:
        """
        Acquires an AsyncLLMClient instance from the pool.

        Waits if the pool is empty. Ensures pool is initialized.
        Should be used with `release` or preferably within the `context` manager.

        Returns:
            An available AsyncLLMClient instance.

        Raises:
            RuntimeError: If the pool is not initialized or fails to initialize.
        """
        await self._ensure_initialized()  # Perform lazy initialization if needed

        if not self._queue:
            raise RuntimeError(
                "LLMClientPool is not initialized or initialization failed."
            )

        logger.debug("Acquiring AsyncLLMClient from pool...")
        try:
            # Wait indefinitely for a client to become available
            client = await self._queue.get()
            self._queue.task_done()  # Notify queue that task is processed
            logger.debug(
                f"AsyncLLMClient acquired. Pool availability: {self._queue.qsize()}/{self._pool_size}"
            )
            return client
        except Exception as e:
            logger.exception("Error acquiring AsyncLLMClient from pool", exc_info=True)
            raise RuntimeError("Failed to acquire AsyncLLMClient from pool.") from e

    async def release(self, client: AsyncLLMClient):
        """
        Releases an AsyncLLMClient instance back into the pool.

        Args:
            client: The AsyncLLMClient instance to release.
        """
        if not self._initialized or not self._queue:
            logger.warning(
                "Attempting to release client to an uninitialized or closed pool. Closing client instead."
            )
            await client.close()  # Attempt to close the client directly
            return

        try:
            await self._queue.put(client)
            logger.debug(
                f"AsyncLLMClient released back to pool. Pool availability: {self._queue.qsize()}/{self._pool_size}"
            )
        except Exception as e:
            logger.error(
                f"Failed to release AsyncLLMClient back to pool: {e}. Attempting to close client.",
                exc_info=True,
            )
            await client.close()  # Close if putting back failed

    @asynccontextmanager
    async def context(self) -> AsyncGenerator[AsyncLLMClient, None]:
        """
        Provides an asynchronous context manager for using a client from the pool.
        Handles acquisition and release automatically.

        Example:
            async with llm_pool.context() as client:
                response = await client.get_completion_content(...)
        """
        client = await self.acquire()
        try:
            yield client
        finally:
            await self.release(client)

    async def close(self):
        """Closes all client connections managed by the pool."""
        # Use the async lock to ensure thread safety during close
        async with self._init_lock:
            if not self._initialized:
                logger.info("LLMClientPool already closed or was never initialized.")
                return

            logger.info(
                f"Closing LLMClientPool and {len(self._clients)} client instances..."
            )
            # Wait for all tasks using the pool to complete (optional, depends on desired shutdown behavior)
            # if self._queue:
            #     await self._queue.join() # Wait for queue to empty

            close_tasks = [client.close() for client in self._clients if client]
            results = await asyncio.gather(*close_tasks, return_exceptions=True)

            closed_count = 0
            error_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error closing AsyncLLMClient instance {i+1}: {result}",
                        exc_info=result,
                    )
                    error_count += 1
                else:
                    closed_count += 1

            logger.info(
                f"LLMClientPool closed. Clients closed: {closed_count}, Errors: {error_count}"
            )

            # Reset state
            self._clients.clear()
            self._queue = None
            self._initialized = False

    # --- Convenience methods to execute directly using the pool ---

    async def get_completion_content(self, *args, **kwargs) -> Optional[str]:
        """Acquires a client, performs non-streaming completion, and releases."""
        async with self.context() as client:
            return await client.get_completion_content(*args, **kwargs)

    async def stream_completion_content(
        self, *args, **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Acquires a client, performs streaming completion, and releases upon generator exhaustion.

        Note: The client is held until the generator returned by this method is fully consumed or closed.
        """
        # Acquire client outside the generator function scope
        client = await self.acquire()
        try:
            # Create the inner generator that uses the acquired client
            async def streamer():
                try:
                    async for chunk in client.stream_completion_content(
                        *args, **kwargs
                    ):
                        yield chunk
                finally:
                    # Release the client only when the streamer finishes or is closed
                    await self.release(client)
                    logger.debug(
                        "AsyncLLMClient released after stream completion/closure."
                    )

            # Return the inner generator
            return streamer()
        except Exception as e:
            # Release the client if stream initiation failed
            await self.release(client)
            logger.error(
                "Failed to initiate stream in pool convenience method.", exc_info=True
            )
            # Re-raise or handle as appropriate. Re-raising is often best.
            raise e

    # --- Pool Status Methods ---

    def get_pool_size(self) -> int:
        """Returns the configured size of the pool."""
        return self._pool_size

    def get_available_count(self) -> int:
        """Returns the number of currently available clients in the queue."""
        if not self._queue:
            return 0
        return self._queue.qsize()

    def is_initialized(self) -> bool:
        """Returns True if the pool has been initialized."""
        return self._initialized
