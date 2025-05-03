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
    SystemConfigRepository,
)
from core.llm import AsyncLLMClient  # Corrected import path
from config import config

# --- Process-Specific Global Variables ---
# These will hold instances unique to each worker process.
# They are initialized to None and set by worker_process_init.
_process_db_manager: Optional[DatabaseConnectionManager] = None
_process_llm_client: Optional[AsyncLLMClient] = None
_process_news_repo: Optional[NewsRepository] = None
_process_source_repo: Optional[NewsSourceRepository] = None

# --- Async Setup/Cleanup Functions ---


async def _setup_process_dependencies_async():
    """Asynchronously initializes resources for a single worker process."""
    global _process_db_manager, _process_llm_client, _process_news_repo, _process_source_repo
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Setting up dependencies for worker process...")

    try:
        # 1. Initialize Database Connection Manager (process-specific)
        # Use the singleton pattern but ensure initialization happens async
        _process_db_manager = await init_db_connection()
        logger.info(f"[PID:{pid}] Database connection initialized.")

        # 2. Load Configuration (needs DB access)
        # Config might already be loaded by main process, but reload ensures
        # process-specific DB access is confirmed.
        sys_config_repo = (
            SystemConfigRepository()
        )  # Uses the process's connection via get_db_connection
        await config.set_db_repo(sys_config_repo)
        logger.info(f"[PID:{pid}] Configuration loaded/verified.")

        # 3. Initialize Repositories (use the process's connection implicitly)
        _process_news_repo = NewsRepository()
        _process_source_repo = NewsSourceRepository()
        logger.info(f"[PID:{pid}] Repositories initialized.")

        # 4. Initialize LLM Client (process-specific)
        # Use config values (env > db > defaults) loaded above
        api_key = config.get("LLM_API_KEY")
        base_url = config.get("LLM_BASE_URL")
        model = config.get("LLM_MODEL")
        # Get context window, attempt conversion to int, provide default
        context_window_val = config.get("LLM_CONTEXT_WINDOW", 8100)
        try:
            context_window = int(context_window_val)
        except (ValueError, TypeError):
            pid = os.getpid()  # Get pid for logging if needed here
            logger.warning(
                f"[PID:{pid}] Invalid value '{context_window_val}' for LLM_CONTEXT_WINDOW. Using default 8100."
            )
            context_window = 8100  # Default integer value

        # Get max tokens, attempt conversion to int, provide default
        max_output_tokens_val = config.get("LLM_MAX_OUTPUT_TOKENS", 4000)
        try:
            max_output_tokens = int(max_output_tokens_val)
        except (ValueError, TypeError):
            pid = os.getpid()  # Get pid for logging if needed here
            logger.warning(
                f"[PID:{pid}] Invalid value '{max_output_tokens_val}' for LLM_MAX_OUTPUT_TOKENS. Using default 4000."
            )
            max_output_tokens = 4000  # Default integer value
        timeout = 60  # Or get from config if needed
        max_retries = 3  # Or get from config if needed

        if not api_key or not base_url or not model:
            logger.error(
                f"[PID:{pid}] LLM configuration incomplete (API Key, Base URL, or Model missing). Cannot create LLM Client."
            )
            # Decide if worker process should exit or continue without LLM
            # For now, we'll let it continue but log the error. Tasks needing LLM will fail.
            _process_llm_client = None
        else:
            # NOTE: Changed from LLMClientPool to single AsyncLLMClient per process
            # If pooling is still desired *within* a process (less common), adjust here.
            _process_llm_client = AsyncLLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                context_window=context_window,
                max_output_tokens=max_output_tokens,
                timeout=timeout,
                max_retries=max_retries,
            )
            # Note: AsyncLLMClient does not need explicit async init, client created on first use.
            logger.info(f"[PID:{pid}] AsyncLLMClient configured (Model: {model}).")

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
    global _process_db_manager, _process_llm_client, _process_news_repo, _process_source_repo
    pid = os.getpid()
    logger.info(f"[PID:{pid}] Cleaning up dependencies for worker process...")

    # Close LLM Client
    if _process_llm_client:
        try:
            logger.info(f"[PID:{pid}] Closing LLM client...")
            await _process_llm_client.close()
            logger.info(f"[PID:{pid}] LLM client closed.")
        except Exception as e:
            logger.error(f"[PID:{pid}] Error closing LLM client: {e}", exc_info=True)
        finally:
            _process_llm_client = None

    # Repositories don't typically need explicit closing, they use the connection manager.

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

    # Clear repo references (optional, good practice)
    _process_news_repo = None
    _process_source_repo = None

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
