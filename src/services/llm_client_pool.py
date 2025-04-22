# src/services/llm_client_pool.py
# -*- coding: utf-8 -*-

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

class LLMClientPool:
    """
    Manages a pool of asynchronous LLMClient instances.
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
        self._queue: asyncio.Queue[LLMClient] = asyncio.Queue(maxsize=pool_size)
        self._lock = asyncio.Lock() # To protect _clients list during init/close
        self._initialized = False

    async def initialize(self):
        """Creates the client instances and populates the pool."""
        async with self._lock:
            if self._initialized:
                logger.warning("LLMClientPool already initialized.")
                return

            logger.info(f"Initializing LLMClientPool with size {self._pool_size}...")
            for i in range(self._pool_size):
                try:
                    # Ensure clients are created in async mode
                    client = LLMClient(
                        base_url=self._base_url,
                        api_key=self._api_key,
                        async_mode=True
                    )
                    self._clients.append(client)
                    await self._queue.put(client)
                    logger.debug(f"Created and added LLMClient {i+1}/{self._pool_size} to pool.")
                except Exception as e:
                    logger.error(f"Failed to create LLMClient instance {i+1}: {e}", exc_info=True)
                    # Decide if initialization should fail completely or proceed with fewer clients
                    raise RuntimeError(f"Failed to initialize LLMClientPool due to client creation error: {e}") from e
            self._initialized = True
            logger.info("LLMClientPool initialized successfully.")

    async def _acquire(self) -> LLMClient:
        """Acquires a client from the pool, waiting if none are available."""
        if not self._initialized:
            raise RuntimeError("LLMClientPool is not initialized. Call initialize() first.")
        logger.debug("Attempting to acquire LLMClient from pool...")
        client = await self._queue.get()
        logger.debug(f"Acquired LLMClient. Pool size: {self._queue.qsize()} available.")
        return client

    async def _release(self, client: LLMClient):
        """Releases a client back into the pool."""
        if not self._initialized:
             logger.warning("Attempting to release client to an uninitialized or closed pool.")
             return # Avoid putting back into a potentially closed pool
        await self._queue.put(client)
        logger.debug(f"Released LLMClient back to pool. Pool size: {self._queue.qsize()} available.")

    @asynccontextmanager
    async def context(self):
        """Provides an async context manager to acquire and release a client."""
        client = await self._acquire()
        try:
            yield client
        finally:
            await self._release(client)

    async def close(self):
        """Closes all underlying clients in the pool."""
        async with self._lock:
            if not self._initialized:
                logger.info("LLMClientPool already closed or not initialized.")
                return

            logger.info(f"Closing LLMClientPool (closing {len(self._clients)} clients)...")
            close_tasks = []
            # Try to close clients we created
            for client in self._clients:
                if hasattr(client._client, 'aclose'): # Check if underlying client has aclose
                     logger.debug(f"Scheduling aclose for client connected to {client.base_url}")
                     # Add the close coroutine to a list
                     close_tasks.append(client._client.aclose())
                elif hasattr(client, 'close'): # Fallback if we add a close method to LLMClient
                    logger.debug(f"Scheduling close for LLMClient connected to {client.base_url}")
                    # Assuming LLMClient.close() is async
                    close_tasks.append(client.close())


            # Run all close tasks concurrently
            if close_tasks:
                results = await asyncio.gather(*close_tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Error closing LLMClient instance {i+1}: {result}", exc_info=result)

            # Clear internal state
            self._clients.clear()
            # Empty the queue - clients might still be in use, but we won't add them back
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._initialized = False # Mark as closed
            logger.info("LLMClientPool closed.")

    def get_pool_size(self) -> int:
        return self._pool_size

    def get_available_count(self) -> int:
        """Returns the number of currently available clients in the pool."""
        return self._queue.qsize() 