#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SmartInfo - Intelligent News Analysis and Knowledge Management Tool
Main Program Entry Point (Refactored Structure with FastAPI)
Uses a dedicated async context manager for DB lifecycle.
CLI operations complete, then server starts (does not exit after CLI).
"""

import sys
import os
import logging
import argparse
import asyncio
from contextlib import asynccontextmanager # For lifespan and db manager
from typing import Any, Dict, Optional

# --- Project Setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- FastAPI & Web Server Imports ---
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Early Imports (Config, Database, Repositories, Services, LLM Client) ---
from backend.config import API_KEY_DEEPSEEK, API_KEY_VOLCENGINE, init_config, get_config, AppConfig
# Import the manager class and get_db (services/repos still use get_db)
from backend.db.connection import AsyncDatabaseConnectionManager, get_db 
from backend.db.repositories import (
    NewsRepository,
    NewsSourceRepository,
    NewsCategoryRepository,
    ApiKeyRepository,
    SystemConfigRepository,
    QARepository,
)
from backend.services.llm_client import LLMClient
from backend.services.setting_service import SettingService
from backend.services.news_service import NewsService
from backend.services.qa_service import QAService

# --- API Routers ---
from backend.api.routers import news_router, qa_router, settings_router

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("smartinfo.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
# Moved startup log to main()

# --- Argument Parser ---
def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="SmartInfo API Server")
    parser.add_argument(
        "--reset-sources", action="store_true", help="Reset news sources to default"
    )
    parser.add_argument(
        "--clear-news",
        action="store_true",
        help="Clear ALL news data (SQLite)",
    )
    parser.add_argument(
        "--reset-database",
        action="store_true",
        help="Reset the entire database (ALL data)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to run the API server on",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the API server on",
    )
    return parser.parse_args()

# --- Logging Setup ---
def setup_logging(level_name: str):
    """Sets the root logger level"""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    logger.info(f"Logging level set to {level_name.upper()}")


# --- Dedicated Database Lifecycle Manager ---
@asynccontextmanager
async def database_lifecycle():
    """Manages the global database connection lifecycle."""
    db_manager: Optional[AsyncDatabaseConnectionManager] = None
    try:
        logger.info("Entering database lifecycle: Initializing DB Manager...")
        # Initialize the singleton instance and establish connection
        db_manager = await AsyncDatabaseConnectionManager.get_instance() 
        await db_manager.get_connection() # Ensure connection is active
        logger.info("DB Manager initialized and connection ready.")
        # Yield control to the block within 'async with database_lifecycle():'
        yield db_manager 
    except Exception as e:
        logger.critical(f"Database lifecycle setup failed: {e}", exc_info=True)
        # Re-raise to prevent application from proceeding without DB
        raise RuntimeError("DB Lifecycle Setup Failed") from e
    finally:
        # This block executes when exiting the 'async with' block,
        # either normally or due to an exception.
        if db_manager:
            logger.info("Exiting database lifecycle: Closing connection...")
            try:
                # Attempt to close the database connection
                await db_manager.close()
                logger.info("Database connection closed by lifecycle manager.")
            except RuntimeError as e:
                # Catch specific RuntimeError
                if "Event loop is closed" in str(e):
                    # If the "Event loop is closed" error occurs during closing, log a warning and ignore
                    # This failure is usually harmless as the application is exiting
                    logger.warning(f"Ignoring expected 'Event loop is closed' error during final DB close: {e}")
                else:
                    # Log unexpected RuntimeError and possibly re-raise
                    logger.error(f"Unexpected RuntimeError during DB close: {e}", exc_info=True)
                    # raise # Optionally re-raise other runtime errors
            except Exception as e:
                # Catch other possible exceptions
                logger.error(f"Unexpected error during DB close: {e}", exc_info=True)
                # raise # Optionally re-raise other exceptions
        else:
            # This case indicates failure during the 'try' block
            logger.warning("DB Manager instance was not available during cleanup.")

# --- Modified FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager for non-DB related tasks."""
    # Startup: Perform NON-DB related startup tasks here if any
    logger.info("Application lifespan startup...")
    # Example: Initialize some other resource if needed
    # app.state.some_other_resource = await initialize_other_resource()
    
    yield # Application runs here

    logger.info("Application lifespan shutdown...")
    # Example: Cleanup other resource
    # if hasattr(app.state, 'some_other_resource'):
    #     await app.state.some_other_resource.close()
    
# --- Service Initialization ---
def initialize_services(
    config: AppConfig
) -> Dict[str, Any]:
    logger.info("Initializing services...")
    try:
        # Repositories 
        news_repo = NewsRepository()
        source_repo = NewsSourceRepository()
        category_repo = NewsCategoryRepository()
        api_key_repo = ApiKeyRepository()
        system_config_repo = SystemConfigRepository()
        qa_repo = QARepository()

        # Services
        setting_service = SettingService(config, api_key_repo, system_config_repo)

        # LLM Clients
        deepseek_api_key = config.get(API_KEY_DEEPSEEK)
        volcengine_api_key = config.get(API_KEY_VOLCENGINE)

        if not deepseek_api_key:
             logger.warning("DeepSeek API key not configured.")
        if not volcengine_api_key:
             logger.warning("Volcano Engine API key not configured.")

        llm_client_volc = LLMClient(
             base_url="https://ark.cn-beijing.volces.com/api/v3",
             api_key=volcengine_api_key,
             async_mode=True
        )
        llm_client_deepseek = LLMClient(
            base_url="https://api.deepseek.com/v1",
            api_key=deepseek_api_key,
            async_mode=True
        )

        # Instantiate services
        news_service = NewsService(news_repo, source_repo, category_repo, llm_client_volc)
        qa_service = QAService(qa_repo, llm_client_deepseek) 

        logger.info("Services initialized successfully.")
        return {
            "setting_service": setting_service,
            "news_service": news_service,
            "qa_service": qa_service,
            "llm_client_volc": llm_client_volc,
            "llm_client_deepseek": llm_client_deepseek,
        }
    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        sys.exit(f"Service Initialization Error: {e}")

# --- FastAPI App Creation ---
def create_app(services: Dict[str, Any]) -> FastAPI:
    """Create and configure the FastAPI application"""
    app = FastAPI(
        title="SmartInfo API",
        description="Intelligent News Analysis and Knowledge Management API",
        version="1.0.0",
        lifespan=lifespan # Use the MODIFIED lifespan (or None if empty)
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add services to app state for dependency injection
    app.state.services = services
    
    # Register routers
    app.include_router(news_router.router, prefix="/api/news", tags=["news"])
    app.include_router(qa_router.router, prefix="/api/qa", tags=["qa"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
    
    @app.get("/")
    async def root():
        return {"message": "SmartInfo API is running"}
    
    return app

# --- Async Helper for CLI DB Operations ---
async def run_db_operations(args) -> bool:
    """
    Runs async DB operations based on CLI flags using Repository methods.
    """
    try: # Wrap potentially failing operations
        if args.reset_database:
            logger.warning("Executing --reset-database argument...")
            confirm = input("WARNING: This will delete ALL data from ALL tables. Type 'YES' to confirm: ")
            if confirm == "YES":
                logger.info("Resetting all database tables via Repository methods...")

                # Get repository instances for reset_database
                qa_repo: QARepository = QARepository()
                api_key_repo: ApiKeyRepository = ApiKeyRepository()
                system_config_repo: SystemConfigRepository = SystemConfigRepository()
                news_repo: NewsRepository = NewsRepository()
                source_repo: NewsSourceRepository = NewsSourceRepository()
                category_repo: NewsCategoryRepository = NewsCategoryRepository()

                # Call clear/delete methods for each repository
                logger.debug("Clearing QA History...")
                await qa_repo.clear_history()
                logger.debug("Clearing API Config...")
                await api_key_repo.delete_all()
                logger.debug("Clearing System Config...")
                await system_config_repo.delete_all()
                logger.debug("Clearing News...")
                await news_repo.clear_all()
                logger.debug("Clearing News Sources...")
                await source_repo.delete_all()
                logger.debug("Clearing News Categories...")
                await category_repo.delete_all()

                logger.info("Database reset complete using repository methods.")
            else:
                logger.info("Database reset aborted.")
            return True # Indicate CLI action was handled

        elif args.reset_sources:
            logger.warning("Executing --reset-sources argument...")
            confirm = input("WARNING: This will delete ALL existing news sources and categories, then add defaults. Type 'YES' to confirm: ")
            if confirm == "YES":
                logger.info("Resetting news sources and categories to default via Repository methods...")

                # Get repository instances for reset_sources
                source_repo: NewsSourceRepository = NewsSourceRepository()
                category_repo: NewsCategoryRepository = NewsCategoryRepository()

                # Delete existing sources and categories using repository methods
                logger.debug("Clearing News Sources...")
                await source_repo.delete_all()
                logger.debug("Clearing News Categories...")
                await category_repo.delete_all()

                logger.info("Existing sources and categories cleared.")
            else:
                logger.info("Reset sources aborted.")
            return True # Indicate CLI action was handled

        elif args.clear_news:
            logger.warning("Executing --clear-news argument...")
            confirm = input("WARNING: This will delete ALL news articles. Type 'YES' to confirm: ")
            if confirm == "YES":
                logger.info("Clearing news data via Repository method...")

                # Get repository instance for clear_news
                news_repo: NewsRepository = NewsRepository()
                await news_repo.clear_all()

                logger.info("Cleared news data using repository method.")
            else:
                logger.info("Clear news data aborted.")
            return True # Indicate CLI action was handled

    except Exception as e:
        # Log any unexpected error during the operations
        logger.error(f"An error occurred during CLI DB operation using repositories: {e}", exc_info=True)
        # Repositories handle their own rollback on error within _execute
        # Ensure function returns True if it was meant to handle a CLI arg, even on error
        if args.reset_database or args.reset_sources or args.clear_news:
            return True

    # If no relevant CLI argument was matched
    return False


# --- Core Application Runner (MODIFIED) ---
async def run_app(args):
    """Contains the core application logic (CLI operations AND Server run)."""
    # NOTE: This function runs *inside* the database_lifecycle context

    # 1. Initialize Configuration (already done)
    config = get_config()

    # 2. Initialize Services (safe now)
    services = initialize_services(config)

    # 3. Handle CLI DB operations
    cli_handled = await run_db_operations(args)
    if cli_handled:
        logger.info(f"CLI operation ({' '.join(sys.argv[1:])}) handled. Proceeding to start server...")

    # 4. Always proceed to run the server, even after a CLI operation
    logger.info("Starting FastAPI server...")
    # Pass services to the app factory
    app = create_app(services) 

    # Run FastAPI server using uvicorn's programmatic API
    uv_config = uvicorn.Config(
        app, 
        host=args.host, 
        port=args.port, 
        log_level=args.log_level.lower()
    )
    server = uvicorn.Server(uv_config)
    
    # Running the server blocks here until shutdown (e.g., Ctrl+C)
    await server.serve() 
    
    logger.info("FastAPI server has shut down.")


# --- Main Execution ---
def main():
    """Application main entry point"""
    print("-------------------- Application Starting --------------------")
    args = parse_args()
    setup_logging(args.log_level)
    logger.info(f"Parsed arguments: {args}")

    exit_code = 0
    try:
        # Initialize config *before* entering the async context
        init_config()

        # Define the main async execution flow using the database lifecycle manager
        async def async_main_wrapper():
             async with database_lifecycle():
                 await run_app(args)

        # Run the main async flow
        asyncio.run(async_main_wrapper())

    except SystemExit as e:
         logger.info(f"Application exiting via sys.exit({e.code}).")
         exit_code = e.code if isinstance(e.code, int) else 1
    except RuntimeError as e: 
         logger.critical(f"Runtime error during execution: {e}", exc_info=True)
         exit_code = 1 
    except KeyboardInterrupt:
         logger.info("Application interrupted by user (Ctrl+C).")
         exit_code = 0 # Usually considered a normal exit
    except Exception as e:
        logger.critical(f"An unhandled error occurred: {e}", exc_info=True)
        exit_code = 1
    finally:
        logger.info(f"-------------------- Application Terminating (Exit Code: {exit_code}) --------------------")
        
    # Explicitly exit with the determined code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()