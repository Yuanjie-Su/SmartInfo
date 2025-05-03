#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery Worker Initialization
This module initializes the Celery worker with the necessary task dependencies.
Run with: celery -A celery_worker worker --loglevel=info
"""

import asyncio
import logging
import os
import sys
import threading
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
from background.celery_app import celery_app
from celery.signals import (
    worker_init,
    worker_ready,
    celeryd_init,
    worker_process_init,
    worker_before_create_process,
    worker_shutting_down,
    heartbeat_sent,
    worker_shutdown,
    worker_process_shutdown,
)

# Import task dependencies initialization
from background.tasks.news_tasks import (
    init_task_dependencies,
    _llm_pool,
    _news_repo,
    _source_repo,
)

# Import database and LLM components
from db.connection import init_db_connection, DatabaseConnectionManager
from db.repositories import NewsRepository, NewsSourceRepository
from core.llm import LLMClientPool
from config import config
from db.repositories import SystemConfigRepository

_worker_db_manager: Optional[DatabaseConnectionManager] = None


@celeryd_init.connect
def celeryd_init_handler(sender=None, conf=None, **kwargs):
    """
    Signal handler for Celery worker initialization.
    This is the first signal sent when a worker starts, and can be used to set node-specific configurations.
    """
    logger.info(f"Worker node {sender} initializing...")

    # Set node-specific configurations
    if conf:
        # Set different configurations based on node name
        if sender and "news_worker" in sender:
            # Set specific configurations for news processing node
            conf.worker_prefetch_multiplier = 1
        elif sender and "analysis_worker" in sender:
            # Set specific configurations for analysis node
            conf.worker_prefetch_multiplier = 1
            conf.task_time_limit = 3600  # Analysis tasks may take longer

    logger.info(f"Worker node {sender} initialization configuration completed")


@worker_init.connect
def worker_init_handler(**kwargs):
    """
    Signal handler for worker initialization before starting.
    This is called before the worker starts, and can be used for resource preparation.
    """
    logger.info("Worker process initialization...")

    try:
        # Here you can perform any global resource initialization logic
        # For example, setting global variables, configuration validation, etc.

        # Check necessary environment variables
        required_vars = ["LLM_API_KEY", "LLM_BASE_URL", "DATABASE_URL"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            logger.warning(
                f"Missing critical environment variable(s): {', '.join(missing_vars)}"
            )

    except Exception as e:
        logger.error(f"Worker initialization error: {e}", exc_info=True)


@celery_app.on_after_configure.connect
def setup_worker_dependencies(sender, **kwargs):
    logger.info("Configuring Celery worker dependencies...")
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(_setup_async_dependencies())
    except Exception as e:
        logger.critical(
            f"CRITICAL FAILURE during worker dependency setup: {e}", exc_info=True
        )
        # Stop the worker process if setup fails critically
        sys.exit(1)  # Exit worker if setup fails


async def _setup_async_dependencies():
    logger.info("Running async dependency setup...")
    # Explicitly declare intent to modify globals if not done in init_task_dependencies
    # global _llm_pool, _news_repo, _source_repo

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
        global _news_repo, _source_repo
        _news_repo = NewsRepository()
        _source_repo = NewsSourceRepository()
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

        global _llm_pool
        _llm_pool = LLMClientPool(
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
        init_task_dependencies(_llm_pool, _news_repo, _source_repo)
        logger.info("init_task_dependencies called.")

    except Exception as e:
        # Log the specific error that occurred during setup
        logger.error(f"Error during async dependency setup: {e}", exc_info=True)
        raise  # Re-raise the exception to be caught by the outer handler


@worker_ready.connect
def worker_ready_handler(**kwargs):
    """
    Signal handler for when the worker is ready to accept tasks.
    This is called when all initialization is complete and the worker can start accepting tasks.
    """
    logger.info("Worker is now ready and can accept tasks")


@worker_process_init.connect
def worker_process_init_handler(**kwargs):
    """
    Signal handler for when a worker process is being created.
    This is called when each worker subprocess starts, and is suitable for setting up each process's resources.
    """
    logger.info("Worker process initialization in progress...")


@worker_before_create_process.connect
def worker_before_create_process_handler(**kwargs):
    """
    Signal handler for when a prefork pool is creating a new subprocess before fork.
    This can be used to clean up instances that do not behave well in fork.
    """
    logger.info("Preparing to create new worker process...")

    # Here you can clean up resources that should not be shared
    # For example: Closing database connections, cleaning channels, etc.

    # Example: If there are any global channels or connections to clean up
    try:
        # Clean up any possible global channels or connections
        # If there are any global resources to clean up before fork, do it here
        pass
    except Exception as e:
        logger.warning(f"Error cleaning up resources: {e}")


@heartbeat_sent.connect
def heartbeat_handler(sender, **kwargs):
    """
    Signal handler for when Celery sends a worker heartbeat.
    This can be used for periodic health checks.
    """
    # This function will be called frequently, so set log level to debug
    logger.debug("Sent worker heartbeat")


@worker_process_shutdown.connect
def worker_process_shutdown_handler(**kwargs):
    """
    Signal handler for when a worker process is shutting down.
    This is called when the worker process is terminating, and can be used for cleanup.
    """
    logger.info("Worker process is shutting down...")


@worker_shutting_down.connect
def worker_shutting_down_handler(sig=None, how=None, exitcode=None, **kwargs):
    """
    Signal handler for when a worker starts shutting down process.
    Provides detailed information about the shutdown, such as signal and shutdown method.
    """
    logger.info(
        f"Worker shutting down...(signal:{sig}, method:{how}, exit code:{exitcode})"
    )

    # Perform any critical pre-shutdown tasks here
    # For example: Saving state, completing critical operations, etc.

    # Different actions can be taken based on shutdown method
    if how == "warm":
        logger.info("Executing warm shutdown - waiting for tasks to complete")
    elif how == "cold":
        logger.info("Executing cold shutdown - terminating quickly")


@worker_shutdown.connect
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
