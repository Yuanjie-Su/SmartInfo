# backend/main.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main application file for the SmartInfo Backend.
Sets up the FastAPI application, manages application lifespan (DB connection, LLM pool),
and includes the main API router.
"""

import sys
import os
from contextlib import asynccontextmanager
from typing import Optional
import asyncpg
from dotenv import load_dotenv
import logging
import argparse  # Add argparse for potential future direct script execution
import redis.asyncio as redis

# Load environment variable configuration
load_dotenv()


from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- Logging Setup ---
# Determine log level from environment variable or default to INFO
log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
if not isinstance(log_level, int):  # Fallback if getattr fails or returns non-int
    print(
        f"Warning: Invalid LOG_LEVEL '{log_level_name}'. Defaulting to INFO.",
        file=sys.stderr,
    )
    log_level = logging.INFO

# Set up logging BEFORE other imports that might log
logging.basicConfig(
    level=log_level,  # Use the determined log level
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
# Set logger level for httpx's warnings to WARNING to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
# Set uvicorn access log level based on our setting if desired (optional)
# logging.getLogger("uvicorn.access").setLevel(log_level)


logger = logging.getLogger(__name__)


# --- Core Application Imports ---
from config import config  # Import the global config instance
from db.connection import (
    init_db_connection,
    get_db_connection_context,
)
from db.repositories import UserPreferenceRepository  # 更新为用户偏好仓库
from core.llm import LLMClientPool  # Import from new location
from api import api_router  # Import the main API router


# --- Application Lifespan Management ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    - Initializes Database Connection Manager & loads persistent config.
    - Initializes LLM Client Pool.
    - Initializes Redis Connection Pool for WebSocket communication.
    - Sets global LLM pool for dependency injection.
    - Cleans up resources on shutdown.
    """
    logger.info("Application lifespan starting...")
    db_manager = None

    # == Startup ==
    try:
        # 1. Initialize Database Connection Manager
        # This also creates the DB file and tables if they don't exist.
        logger.info("Initializing Database Connection Manager...")
        db_manager = await init_db_connection()
        logger.info("Database Connection Manager initialized successfully.")

        # 2. Initialize Redis connection pool for WebSocket communication
        logger.info("Initializing Redis connection pool...")
        app.state.redis_pool = redis.ConnectionPool.from_url(
            os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            decode_responses=True,  # Decode responses for easier handling
        )
        app.state.redis_client = redis.Redis(connection_pool=app.state.redis_pool)
        logger.info("Async Redis client initialized.")

    except Exception as e:
        logger.critical(f"Application startup failed: {e}", exc_info=True)
        # Perform cleanup even if startup fails partially
        if db_manager:
            await db_manager._cleanup()  # Use manager's async cleanup

        # Cleanup Redis if it was initialized
        if hasattr(app.state, "redis_client"):
            await app.state.redis_client.close()
        if hasattr(app.state, "redis_pool"):
            await app.state.redis_pool.disconnect()

        raise RuntimeError("Application startup failed.") from e

    # Yield control to the running application
    yield

    # == Shutdown ==
    logger.info("Application lifespan shutting down...")

    # Close Redis connection
    if hasattr(app.state, "redis_client"):
        try:
            await app.state.redis_client.close()
            logger.info("Async Redis client closed.")
        except Exception as e:
            logger.error(f"Error closing Redis client: {e}", exc_info=True)

    if hasattr(app.state, "redis_pool"):
        try:
            await app.state.redis_pool.disconnect()
            logger.info("Async Redis connection pool disconnected.")
        except Exception as e:
            logger.error(f"Error disconnecting Redis pool: {e}", exc_info=True)

    if db_manager:
        logger.info("Closing database connection...")
        try:
            # 使用异步清理方法
            await db_manager._cleanup()
            logger.info("Database connection resources released.")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}", exc_info=True)
    else:
        logger.info(
            "Database connection manager was not initialized, skipping cleanup."
        )

    logger.info("Application lifespan finished.")


# --- FastAPI Application Setup ---

# Create FastAPI app instance with lifespan manager
app = FastAPI(
    title="SmartInfo Backend",
    description="API for news aggregation, analysis, and chat features.",
    version="1.0.0",  # Consider making version dynamic
    lifespan=lifespan,
)

# Add CORS middleware
# Configure origins according to your frontend deployment
origins = [
    "http://localhost:3000",  # 本地环回地址
    "http://172.18.0.1:3000",  # WSL/Docker 虚拟地址
    "http://192.168.0.107:3000",  # 局域网IP请求
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Use specific origins in production
    # allow_origins=["*"], # Use "*" for development/testing if needed, less secure
    allow_credentials=True,
    allow_methods=["*"],  # Allows all standard methods
    allow_headers=["*"],  # Allows all headers
)

# Include the main API router (which includes versioned routers)
# All API endpoints will be under /api path
app.include_router(api_router, prefix="/api")


# --- Root and Health Check Endpoints ---


@app.get("/", tags=["General"], summary="Root Endpoint")
async def read_root():
    """Provides a simple welcome message indicating the backend is running."""
    return {"message": "Welcome to the SmartInfo Backend API!"}


@app.get("/health", tags=["General"], summary="Health Check")
async def health_check(
    db_context=Depends(get_db_connection_context),  # Inject DB context manager
):
    """
    Health check endpoint to verify the API is running and the database is reachable.
    """
    db_status = "unknown"
    try:
        # Acquire connection using the context manager
        async with db_context as conn:
            # Execute a simple query to check the connection
            await conn.fetchval("SELECT 1")
            db_status = "connected"
            logger.debug("Database health check successful.")
    except (asyncpg.PostgresError, OSError, TimeoutError) as e:
        # Catch specific DB errors, network errors, or timeouts
        db_status = f"error: {type(e).__name__} - {str(e)}"
        logger.error(
            f"Database health check failed: {db_status}", exc_info=False
        )  # Log less verbosely for health check failures
    except Exception as e:
        # Catch any other unexpected errors
        db_status = f"unexpected_error: {type(e).__name__} - {str(e)}"
        logger.error(
            f"Unexpected error during database health check: {db_status}", exc_info=True
        )

    # Return the overall API status and the database status
    # API is considered 'healthy' if it's responding, even if DB has issues.
    # Clients can check the db_status field for dependency health.
    return {"api_status": "healthy", "database_status": db_status}


@app.get("/redis-test", tags=["General"], summary="Redis Connection Test")
async def redis_test(request: Request):
    """
    Test endpoint to verify the Redis connection is working correctly.
    """
    try:
        # Get Redis client directly from app state
        redis_client = request.app.state.redis_client

        # Ping Redis to ensure connection is alive
        await redis_client.ping()

        # Try a simple publish/subscribe operation
        test_channel = "redis_test_channel"
        test_message = "Hello Redis!"

        # Create a pubsub instance and subscribe to test channel
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(test_channel)

        # Publish a test message
        await redis_client.publish(test_channel, test_message)

        # Get the published message
        message = await pubsub.get_message(
            timeout=1.0
        )  # First message is subscribe confirmation
        message = await pubsub.get_message(
            timeout=1.0
        )  # Second message is our published message

        # Clean up
        await pubsub.unsubscribe(test_channel)
        await pubsub.close()

        # Return success result
        return {
            "redis_status": "connected",
            "pubsub_test": (
                "success" if message and message["data"] == test_message else "failed"
            ),
            "message_received": message["data"] if message else None,
        }
    except Exception as e:
        return {"redis_status": "error", "error": str(e)}


# --- Execution Entry Point ---


def start_api():
    """
    Function to start the API directly (used when run as module).
    Can be configured with environment variables:
    - HOST: The host to bind to (default: 0.0.0.0)
    - PORT: The port to bind to (default: 8000)
    - RELOAD: Whether to auto-reload on code changes (default: False)
    - LOG_LEVEL: Logging level (e.g., DEBUG, INFO, WARNING) - Handled globally now
    """
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    reload_enabled = os.environ.get("RELOAD", "").lower() in (
        "true",
        "1",
        "t",
        "y",
        "yes",
    )
    # Log level for uvicorn itself. Match our app's log level.
    uvicorn_log_level = logging.getLevelName(log_level).lower()

    logger.info(
        f"Starting SmartInfo API on {host}:{port} (reload: {reload_enabled}, log level: {uvicorn_log_level})"
    )
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=uvicorn_log_level,  # Pass log level to uvicorn
    )


if __name__ == "__main__":
    # Although uvicorn main:app bypasses this, keep it for potential direct execution
    # You could add argparse here if needed for direct script runs
    start_api()
