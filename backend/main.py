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
from dotenv import load_dotenv
import logging

# Load environment variable configuration
load_dotenv()


from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Set up logging BEFORE other imports that might log
# Log INFO level and above to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
# Set logger level for httpx's warnings to WARNING to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# --- Core Application Imports ---
from config import config  # Import the global config instance
from db.connection import (
    init_db_connection,
    get_db_connection,
)
from db.repositories import SystemConfigRepository  # Needed for config init
from core.llm import LLMClientPool  # Import from new location
from api import api_router  # Import the main API router
from api.dependencies import (
    set_global_llm_pool,
    get_llm_pool_dependency,
)  # Import from new dependencies module


# --- Application Lifespan Management ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    - Initializes Database Connection Manager & loads persistent config.
    - Initializes LLM Client Pool.
    - Sets global LLM pool for dependency injection.
    - Cleans up resources on shutdown.
    """
    logger.info("Application lifespan starting...")
    db_manager = None
    llm_pool_instance = None

    # == Startup ==
    try:
        # 1. Initialize Database Connection Manager
        # This also creates the DB file and tables if they don't exist.
        logger.info("Initializing Database Connection Manager...")
        db_manager = await init_db_connection()
        logger.info("Database Connection Manager initialized successfully.")

        # 2. Initialize Configuration with DB access
        # Pass the repository instance to the config object to load/save settings
        logger.info("Loading persistent configuration from database...")
        sys_config_repo = SystemConfigRepository()
        await config.set_db_repo(sys_config_repo)  # This call now loads from DB
        logger.info("Persistent configuration loaded.")

        # 3. Initialize LLM Client Pool
        logger.info("Initializing LLM Client Pool...")
        # Use config values (env > db > defaults)
        api_key_to_use = config.get("LLM_API_KEY")
        base_url = config.get(
            "LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )  # Ensure default
        pool_size = config.get("LLM_POOL_SIZE", 3)  # Ensure default
        default_model = config.get("LLM_MODEL", "deepseek-v3-250324")  # Ensure default

        if not api_key_to_use:
            logger.warning(
                "No LLM API key found in config (env/db). LLM features will be limited."
            )

        llm_pool_instance = LLMClientPool(
            pool_size=pool_size,
            base_url=base_url,
            api_key=api_key_to_use,  # Can be None if no key found
            model=default_model,
        )
        # Set the global pool instance for the dependency injector in api/dependencies.py
        set_global_llm_pool(llm_pool_instance)
        logger.info(
            f"LLM Client Pool initialized (Size: {pool_size}, Base URL: {base_url}, Model: {default_model})."
        )
        # Note: Actual client connections within the pool are lazy-initialized on first use.

    except Exception as e:
        logger.critical(f"Application startup failed: {e}", exc_info=True)
        # Perform cleanup even if startup fails partially
        if llm_pool_instance:
            await llm_pool_instance.close()  # Close pool if it was created
        if db_manager:
            await db_manager._cleanup()  # Use manager's async cleanup
        raise RuntimeError("Application startup failed.") from e

    # Yield control to the running application
    yield

    # == Shutdown ==
    logger.info("Application lifespan shutting down...")
    if llm_pool_instance:
        logger.info("Closing LLM client pool...")
        try:
            await llm_pool_instance.close()
            logger.info("LLM client pool closed.")
        except Exception as e:
            logger.error(f"Error closing LLM pool: {e}", exc_info=True)
    else:
        logger.info("LLM client pool was not initialized, skipping closure.")

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
    # Use the dependency function from dependencies
    # Note: This checks the *global* pool set during lifespan
    llm_pool: Optional[LLMClientPool] = Depends(
        get_llm_pool_dependency, use_cache=False
    ),
):
    """
    Health check endpoint that validates database connection and LLM services.
    Returns various diagnostic information.
    """
    # Check basic application availability
    app_status = "ok"
    version = "1.0.0"  # Consider making this dynamic

    # Check database connection status
    db_status = "unknown"
    try:
        # Get a DB connection from the pool and test it by executing a simple query
        conn = await get_db_connection()
        if conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
                db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
        logger.warning(f"Health check - DB connection failed: {e}")

    # Check LLM service status
    llm_status = "not_initialized"
    llm_pool_size = 0
    if llm_pool:
        try:
            llm_status = "initialized"
            llm_pool_size = llm_pool.pool_size
            # We don't do a test connection here to avoid overhead
            # For a deep health check, there's a separate endpoint
        except Exception as e:
            llm_status = f"error: {str(e)}"
            logger.warning(f"Health check - LLM status check failed: {e}")

    # Return detailed health information
    return {
        "status": (
            "healthy"
            if (app_status == "ok" and db_status == "connected")
            else "degraded"
        ),
        "api_version": version,
        "components": {
            "app": {"status": app_status},
            "database": {"status": db_status},
            "llm_service": {
                "status": llm_status,
                "pool_size": llm_pool_size,
            },
        },
        "timestamp": config.utc_now().isoformat(),
    }


# --- Execution Entry Point ---


def start_api():
    """
    Function to start the API directly (used when run as module).
    Can be configured with environment variables:
    - HOST: The host to bind to (default: 127.0.0.1)
    - PORT: The port to bind to (default: 8000)
    - RELOAD: Whether to auto-reload on code changes (default: False)
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

    logger.info(f"Starting SmartInfo API on {host}:{port} (reload: {reload_enabled})")
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
    )


if __name__ == "__main__":
    start_api()
