#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery Worker Initialization
This module initializes the Celery worker and manages resources per worker process
using signals.
Run with: celery -A background.celery_worker worker --loglevel=info
"""

import asyncio
import logging
import os
from typing import Optional
from db.repositories.api_key_repository import ApiKeyRepository
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Import Celery app BEFORE trying to access it for signals
from background.celery_app import celery_app

# Import signals AFTER celery_app is defined/imported
from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
)

# Import necessary components for dependency creation
from db.connection import DatabaseConnectionManager, init_db_connection
from db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    UserPreferenceRepository,
)
from core.llm import AsyncLLMClient  # Corrected import path
from config import config

# --- Process-Specific Global Variables ---
# These will hold instances unique to each worker process.
# They are initialized to None and set by worker_process_init.
_process_db_manager: Optional[DatabaseConnectionManager] = None
_process_news_repo: Optional[NewsRepository] = None
_process_source_repo: Optional[NewsSourceRepository] = None
_process_api_key_repo: Optional[ApiKeyRepository] = None  # Add ApiKeyRepository

# --- Async Setup/Cleanup Functions ---


async def _setup_process_dependencies_async():
    """Asynchronously initializes resources for a single worker process."""
    global _process_db_manager, _process_news_repo, _process_source_repo, _process_api_key_repo
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Setting up dependencies for worker process...")

    try:
        # 1. Initialize Database Connection Manager (process-specific)
        # Use the singleton pattern but ensure initialization happens async
        _process_db_manager = await init_db_connection()
        logger.info(f"[PID:{pid}] Database connection initialized.")

        # 2. Initialize Repositories (use the process's connection implicitly)
        _process_news_repo = NewsRepository()
        _process_source_repo = NewsSourceRepository()
        _process_api_key_repo = ApiKeyRepository()  # Initialize ApiKeyRepository
        logger.info(f"[PID:{pid}] Repositories initialized.")

        logger.info(f"[PID:{pid}] Worker process dependencies setup complete.")

    except Exception as e:
        logger.error(
            f"[PID:{pid}] Error during async dependency setup: {e}", exc_info=True
        )
        # Ensure cleanup if setup fails partially
        await _cleanup_process_dependencies_async()
        raise  # Reraise to potentially stop the worker process if critical


async def _cleanup_process_dependencies_async():
    """Asynchronously cleans up resources for a single worker process."""
    global _process_db_manager, _process_news_repo, _process_source_repo, _process_api_key_repo
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Cleaning up dependencies for worker process...")

    # Repositories don't typically need explicit closing, they use the connection manager.
    # Clear repo references (optional, good practice)
    _process_news_repo = None
    _process_source_repo = None
    _process_api_key_repo = None  # Clear ApiKeyRepository reference

    # Close Database Connection
    if _process_db_manager:
        try:
            logger.info(f"[PID:{pid}] Closing database connection...")
            # Access the protected cleanup method if needed, or rely on its atexit
            # Using the explicit manager ensures connection for *this process* is closed.
            await _process_db_manager._cleanup()  # Call the async cleanup
            logger.info(f"[PID:{pid}] Database connection closed.")
        except Exception as e:
            logger.error(
                f"[PID:{pid}] Error closing database connection: {e}", exc_info=True
            )
        finally:
            _process_db_manager = None  # Important to clear the reference

    logger.info(f"[PID:{pid}] Worker process dependencies cleanup complete.")


# --- Signal Handlers ---


@worker_process_init.connect(weak=False)
def worker_process_init_handler(**kwargs):
    """
    Signal handler: Initialize resources when a worker process starts.
    Runs the async setup function.
    """
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Worker process init signal received.")
    try:
        # Run the async setup function synchronously using asyncio.run()
        # This creates a new event loop for the setup if one doesn't exist
        asyncio.run(_setup_process_dependencies_async())
        logger.info(f"[PID:{pid}] Worker process async setup completed successfully.")
    except Exception as e:
        logger.critical(
            f"[PID:{pid}] Worker process initialization failed critically: {e}",
            exc_info=True,
        )
        # Depending on the error, you might want to exit the process
        # For example: sys.exit(1)
        # Be cautious with exiting, ensure it doesn't break Celery's management.


@worker_process_shutdown.connect(weak=False)
def worker_process_shutdown_handler(**kwargs):
    """
    Signal handler: Clean up resources when a worker process shuts down.
    Runs the async cleanup function.
    """
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Worker process shutdown signal received.")
    try:
        # Run the async cleanup function synchronously using asyncio.run()
        asyncio.run(_cleanup_process_dependencies_async())
        logger.info(f"[PID:{pid}] Worker process async cleanup completed successfully.")
    except Exception as e:
        logger.error(
            f"[PID:{pid}] Error during worker process cleanup: {e}", exc_info=True
        )


# --- (Optional) Other Signals ---
# You might keep celeryd_init if you need node-level setup, but often
# worker_process_init is sufficient for resource management.

# @celeryd_init.connect
# def celeryd_init_handler(sender=None, conf=None, **kwargs):
#     logger.info(f"Worker node {sender} initializing...")
#     # Node-level setup if needed

# @worker_init.connect
# def worker_init_handler(**kwargs):
#      logger.info("Main worker initialization...")
#      # Main process setup if needed (runs before process forking)
