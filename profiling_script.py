#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Standalone script to profile the news fetching process using cProfile.
"""

import sys
import os
import logging
import asyncio
import cProfile
import pstats
import io
from typing import Dict, Any

# --- Project Setup ---
# Adjust the path if your script is located elsewhere relative to the src directory
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Assuming script is in project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, "src") not in sys.path:
    sys.path.insert(0, os.path.join(project_root, "src"))


# --- Early Imports (Config, Database, Repositories, Services, LLM Client) ---
# Ensure these imports match your project structure
try:
    from src.config import init_config, get_config, AppConfig
    from src.db.connection import (
        init_db_connection,
        get_db_connection_manager,
        DatabaseConnectionManager,
    )
    from src.db.repositories import (
        NewsRepository,
        NewsSourceRepository,
        NewsCategoryRepository,
        ApiKeyRepository,
        SystemConfigRepository,
        QARepository,
    )
    from src.services.llm_client import LLMClient
    from src.services.news_service import NewsService

    # Import other services if needed by NewsService initialization indirectly
except ImportError as e:
    print(
        f"Import Error: {e}. Please ensure the script is run from the correct directory"
        " and all project dependencies are installed."
    )
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,  # Set to DEBUG for more details
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Log to console
    ],
)
logger = logging.getLogger("ProfilingScript")


# --- Initialization Function ---
def initialize_app_for_profiling() -> Dict[str, Any]:
    """Initializes necessary components for profiling."""
    # Initialize configuration
    logger.info("Initializing configuration...")
    config = init_config()

    # Initialize database connection
    logger.info("Initializing database connection...")
    db_manager = init_db_connection()

    # Initialize LLM client (Requires API Key configuration, e.g., in .env file)
    logger.info("Initializing LLM client...")
    deepseek_api_key = config.get(
        "API_KEY_DEEPSEEK"
    )  # Assumes config handles env/db loading
    if not deepseek_api_key:
        logger.warning("DeepSeek API key not found. LLM operations will fail.")
    llm_client = LLMClient(
        base_url="https://api.deepseek.com",
        api_key=deepseek_api_key,
        async_mode=True,  # Must be async for NewsService async methods
    )

    # Initialize Repositories
    logger.info("Initializing repositories...")
    news_repo = NewsRepository()
    source_repo = NewsSourceRepository()
    category_repo = NewsCategoryRepository()

    # Initialize NewsService
    logger.info("Initializing NewsService...")
    news_service = NewsService(news_repo, source_repo, category_repo, llm_client)

    return {"news_service": news_service}


# --- Main Profiling Logic ---
async def profile_fetch_news(news_service: NewsService):
    """Runs the news fetching process to be profiled."""
    logger.info("Starting news fetch process for profiling...")
    # --- Call the function to profile ---
    # You can specify source_ids=None to fetch all, or provide a list of IDs
    saved_count = await news_service.fetch_news_from_sources(
        source_ids=None,  # Example: Fetch all sources
        on_item_saved=lambda item: logger.debug(
            f"Item saved (callback): {item.get('id')} - {item.get('title')}"
        ),
        on_fetch_complete=lambda count: logger.info(
            f"Fetch complete (callback): {count} items saved."
        ),
    )
    logger.info(f"Profiled fetch process finished. Total items saved: {saved_count}")


# --- Script Entry Point ---
if __name__ == "__main__":
    logger.info("--- Starting Profiling Script ---")

    try:
        # Initialize
        services = initialize_app_for_profiling()
        news_service = services["news_service"]

        # --- Setup cProfile ---
        profiler = cProfile.Profile()
        logger.info("Starting profiler...")
        profiler.enable()

        # --- Run the async function ---
        asyncio.run(profile_fetch_news(news_service))

        # --- Stop cProfile and print stats ---
        profiler.disable()
        logger.info("Profiler stopped. Processing results...")

        # Create a stream to capture stats output
        s = io.StringIO()
        # Sort stats by cumulative time ('cumulative') or total time ('tottime')
        stats = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
        stats.print_stats(30)  # Print top 30 functions

        # Print the captured stats
        print("\n--- cProfile Results (Top 30 by Cumulative Time) ---")
        print(s.getvalue())
        print("----------------------------------------------------")

        # Optional: Save stats to a file for more detailed analysis (e.g., with snakeviz)
        # stats_filename = "fetch_news_profile.prof"
        # profiler.dump_stats(stats_filename)
        # logger.info(f"Profile stats saved to {stats_filename}")
        # logger.info("You can visualize it using: snakeviz {stats_filename}")

    except RuntimeError as e:
        logger.error(f"RuntimeError: {e}", exc_info=True)
    except ImportError as e:
        logger.critical(f"Failed due to import error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        # Ensure DB connections are closed if atexit doesn't run properly in all scenarios
        try:
            db_manager = get_db_connection_manager()
            db_manager._cleanup()  # Call cleanup explicitly if needed
        except Exception:
            pass  # Ignore errors during cleanup
        logger.info("--- Profiling Script Finished ---")
