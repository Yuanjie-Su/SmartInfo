#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery Worker Initialization
This module initializes the Celery worker with the necessary task dependencies.
Run with: celery -A backend.celery_worker worker --loglevel=info
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Import Celery app
from backend.celery_app import celery_app

# Import task dependencies initialization
from backend.tasks.news_tasks import (
    init_task_dependencies,
    _llm_pool,
    _news_repo,
    _source_repo,
)

# Import database and LLM components
from backend.db.connection import init_db_connection, DatabaseConnectionManager
from backend.db.repositories import NewsRepository, NewsSourceRepository
from backend.core.llm import LLMClientPool
from backend.config import config
from backend.db.repositories import SystemConfigRepository

_worker_db_manager: Optional[DatabaseConnectionManager] = None


@celery_app.on_after_configure.connect
def setup_worker_dependencies(sender, **kwargs):
    logger.info("Configuring Celery worker dependencies...")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(_setup_async_dependencies())
        # Explicitly check if globals were set after setup attempt
        if not _llm_pool:
            logger.critical(
                "FATAL: LLM pool is not set after setup attempt! Worker may not function."
            )
            raise RuntimeError("Failed to set up worker dependencies.")
        if not _news_repo:
            logger.critical(
                "FATAL: News repository is not set after setup attempt! Worker may not function."
            )
            raise RuntimeError("Failed to set up worker dependencies.")
        if not _source_repo:
            logger.critical(
                "FATAL: Source repository is not set after setup attempt! Worker may not function."
            )
            raise RuntimeError("Failed to set up worker dependencies.")
        if not all((_llm_pool, _news_repo, _source_repo)):
            logger.critical(
                "FATAL: Dependencies are still None after setup attempt! Worker may not function."
            )
            # Optionally raise an error here to stop the worker if dependencies are critical
            raise RuntimeError("Failed to set up worker dependencies.")
        else:
            logger.info("Worker dependencies appear to be set successfully.")
    except Exception as e:
        logger.critical(
            f"CRITICAL FAILURE during worker dependency setup: {e}", exc_info=True
        )
        # Stop the worker process if setup fails critically
        import sys

        sys.exit(1)  # Exit worker if setup fails


async def _setup_async_dependencies():
    logger.info("Running async dependency setup...")
    # Explicitly declare intent to modify globals if not done in init_task_dependencies
    # global _llm_pool, _news_repo, _source_repo

    llm_pool_instance = None
    news_repo_instance = None
    source_repo_instance = None

    try:
        logger.info("Initializing database connection...")
        global _worker_db_manager
        _worker_db_manager = await init_db_connection()
        logger.info("Database connection initialized")

        logger.info("Loading configuration...")
        sys_config_repo = SystemConfigRepository()
        await config.set_db_repo(sys_config_repo)
        logger.info("Configuration loaded")

        logger.info("Initializing repositories...")
        news_repo_instance = NewsRepository()
        source_repo_instance = NewsSourceRepository()
        logger.info("Repositories initialized")

        logger.info("Initializing LLM Client Pool...")
        api_key = config.get("LLM_API_KEY")
        base_url = config.get("LLM_BASE_URL")  # Rely on config default if not set
        pool_size = config.get("LLM_POOL_SIZE")  # Rely on config default if not set
        default_model = config.get("LLM_MODEL")  # Rely on config default if not set
        # Make sure context_window and max_tokens are defined in config or have defaults
        context_window = config.get("LLM_CONTEXT_WINDOW", 128000)  # Example default
        max_tokens = config.get("LLM_MAX_TOKENS", 4096)  # Example default

        if not api_key:
            logger.warning("LLM_API_KEY not found in config. LLM features limited.")
        if not base_url:
            logger.error(
                "LLM_BASE_URL not found in config. LLM pool cannot be initialized."
            )
            raise ValueError("LLM_BASE_URL is not configured.")
        if not isinstance(pool_size, int) or pool_size <= 0:
            logger.error(
                f"Invalid LLM_POOL_SIZE: {pool_size}. Must be a positive integer."
            )
            raise ValueError("Invalid LLM_POOL_SIZE.")
        if not default_model:
            logger.error(
                "LLM_MODEL not found in config. LLM pool cannot be initialized."
            )
            raise ValueError("LLM_MODEL is not configured.")
        if not isinstance(context_window, int) or context_window <= 0:
            logger.error(
                f"Invalid LLM_CONTEXT_WINDOW: {context_window}. Must be a positive integer."
            )
            raise ValueError("Invalid LLM_CONTEXT_WINDOW.")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            logger.error(
                f"Invalid LLM_MAX_TOKENS: {max_tokens}. Must be a positive integer."
            )
            raise ValueError("Invalid LLM_MAX_TOKENS.")

        llm_pool_instance = LLMClientPool(
            pool_size=pool_size,
            base_url=base_url,
            api_key=api_key,
            model=default_model,
            context_window=context_window,  # Pass needed args
            max_tokens=max_tokens,  # Pass needed args
        )
        logger.info(
            f"LLM Client Pool initialized (Size: {pool_size}, Model: {default_model})"
        )

        logger.info("Calling init_task_dependencies...")
        # Pass the successfully created instances
        init_task_dependencies(
            llm_pool_instance, news_repo_instance, source_repo_instance
        )
        logger.info("init_task_dependencies called.")

    except Exception as e:
        # Log the specific error that occurred during setup
        logger.error(f"Error during async dependency setup: {e}", exc_info=True)
        raise  # Re-raise the exception to be caught by the outer handler


@celery_app.signals.worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    """Signal handler for cleaning up resources when the worker shuts down."""
    logger.info("Celery worker shutting down. Cleaning up resources...")

    # Cleanup LLM Pool
    if _llm_pool:
        logger.info("Closing LLM pool...")
        try:
            # Running async code from a sync signal handler. asyncio.run() is preferred.
            asyncio.run(_llm_pool.close())
            logger.info("LLM pool closed.")
        except RuntimeError as e:
            logger.warning(
                f"Could not run async LLM pool close cleanly (may be expected if loop closed): {e}"
            )
        except Exception as e:
            logger.error(f"Error closing LLM pool during shutdown: {e}", exc_info=True)
    else:
        logger.info("LLM pool was not initialized, skipping cleanup.")

    # Cleanup Database Connection Manager
    if _worker_db_manager:
        logger.info("Closing database connection manager...")
        try:
            # Use asyncio.run() to execute the async cleanup method
            asyncio.run(_worker_db_manager._cleanup())
            logger.info("Database connection manager resources released.")
        except RuntimeError as e:
            logger.warning(
                f"Could not run async DB manager cleanup cleanly (may be expected if loop closed): {e}"
            )
        except Exception as e:
            logger.error(
                f"Error closing database connection manager during shutdown: {e}",
                exc_info=True,
            )
    else:
        logger.info(
            "Database connection manager was not initialized, skipping cleanup."
        )

    logger.info("Worker shutdown cleanup finished.")
