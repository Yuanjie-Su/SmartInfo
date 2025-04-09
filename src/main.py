#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SmartInfo - Intelligent News Analysis and Knowledge Management Tool
Main Program Entry Point (Refactored Structure)
"""

import sys
import os
import logging
import argparse
import asyncio
from typing import Any, Dict

# --- Project Setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Early Imports (Config, Database, Repositories, Services, LLM Client) ---
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
from src.services.setting_service import SettingService
from src.services.news_service import NewsService
from src.services.analysis_service import AnalysisService
from src.services.qa_service import QAService

# --- Configure Logging ---
log_file_path = "smartinfo.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # Log to console as well
    ],
)
logger = logging.getLogger(__name__)
logger.info("-------------------- Application Starting --------------------")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="SmartInfo Tool")
    parser.add_argument(
        "--reset-sources", action="store_true", help="Reset news sources to default"
    )
    parser.add_argument(
        "--clear-news",
        action="store_true",
        help="Clear ALL news data (SQLite and Embeddings)",
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
    return parser.parse_args()


def setup_logging(level_name: str):
    """Sets the root logger level"""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    logger.info(f"Logging level set to {level_name.upper()}")


def initialize_services(
    config: AppConfig, db_manager: DatabaseConnectionManager
) -> Dict[str, Any]:
    """Initialize all application services"""
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

        # Initialize LLM Client (needs API key)
        deepseek_api_key = setting_service.get_api_key("deepseek")
        volcengine_api_key = setting_service.get_api_key("volcengine")
        if not deepseek_api_key:
            logger.warning(
                "DeepSeek API key not configured. LLM-dependent features may fail."
            )
        if not volcengine_api_key:
            logger.warning(
                "Volcano Engine API key not configured. LLM-dependent features may fail."
            )
        llm_client = LLMClient(
            base_url="https://ark.cn-beijing.volces.com/api/v3", api_key=volcengine_api_key, async_mode=True
        )  # Use async for UI

        news_service = NewsService(news_repo, source_repo, category_repo, llm_client)
        analysis_service = AnalysisService(news_repo, llm_client)

        qa_service = QAService(qa_repo, llm_client)

        logger.info("Services initialized successfully.")
        return {
            "setting_service": setting_service,
            "news_service": news_service,
            "analysis_service": analysis_service,
            "qa_service": qa_service,
        }
    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        sys.exit(f"Service Initialization Error: {e}")


def run_gui(services: Dict[str, Any]):
    """Runs the PyQt GUI application"""
    logger.info("Starting GUI...")
    # Import GUI elements late to avoid issues if dependencies are missing initially
    try:
        from PySide6.QtWidgets import QApplication

        # IMPORTANT: MainWindow needs refactoring to accept services
        from src.ui.main_window import MainWindow
    except ImportError as e:
        logger.critical(
            f"Failed to import GUI components (PySide6?): {e}", exc_info=True
        )
        sys.exit(f"GUI Import Error: {e}. Please ensure PySide6 is installed.")

    app = QApplication(sys.argv)
    app.setApplicationName("SmartInfo")

    # Pass services to MainWindow (MainWindow needs modification)
    try:
        window = MainWindow(services)  # Pass services dict
        window.show()
        logger.info("MainWindow shown.")
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Error running the GUI application: {e}", exc_info=True)
        sys.exit(f"GUI Runtime Error: {e}")


# --- Main Execution ---
def main():
    """Application main entry point"""
    args = parse_args()
    setup_logging(args.log_level)

    try:
        # 1. Initialize Configuration
        config = init_config()

        # 2. Initialize Database Connection Manager
        # This also ensures DB paths based on config are correct and tables exist
        db_manager = init_db_connection()

        # 3. Initialize Services
        services = initialize_services(config, db_manager)

        # --- Handle Command Line Arguments ---
        if args.reset_database:
            logger.warning("Executing --reset-database argument...")
            confirm = input(
                "WARNING: This will delete ALL data. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                logger.info("Resetting all database tables...")
                # Clear SQLite tables via repos
                QARepository().clear_history()
                ApiKeyRepository().delete_all()
                SystemConfigRepository().delete_all()
                NewsRepository().clear_all()
                NewsSourceRepository().delete_all()
                NewsCategoryRepository().delete_all()
                # Clear ChromaDB
                QAService(
                    config,
                    NewsRepository(),
                    QARepository(),
                    db_manager.get_chroma_client(),
                    services["llm_client"],
                ).clear_all_embeddings()  # Re-init QA service to clear
                logger.info(
                    "Database reset complete (manual repo calls). Consider dedicated service method."
                )
                # Re-initialize default sources? Need method in NewsService
                # services["news_service"].initialize_default_sources() # Example
            else:
                logger.info("Database reset aborted.")

        elif args.reset_sources:
            logger.info("Executing --reset-sources argument...")
            # Need method in NewsService
            # services["news_service"].reset_sources_to_default() # Example
            logger.warning(
                "Reset sources functionality needs implementation in NewsService."
            )

        elif args.clear_news:
            logger.warning("Executing --clear-news argument...")
            confirm = input(
                "WARNING: This will delete ALL news articles and embeddings. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                # Use NewsService and QAService methods
                if services["news_service"].clear_all_news():
                    logger.info("Cleared news data from SQLite.")
                else:
                    logger.error("Failed to clear news data from SQLite.")

                if services["qa_service"].clear_all_embeddings():
                    logger.info(
                        "Cleared news embeddings from ChromaDB and reset flags."
                    )
                else:
                    logger.error("Failed to clear news embeddings/reset flags.")
                logger.info("Clear news data operation complete.")
            else:
                logger.info("Clear news data aborted.")

        # --- Run the Application ---
        run_gui(services)

    except Exception as e:
        logger.critical(
            f"An unhandled error occurred during application startup: {e}",
            exc_info=True,
        )
        sys.exit(f"Fatal Error: {e}")
    finally:
        logger.info("-------------------- Application Terminating --------------------")


if __name__ == "__main__":
    # Ensure event loop runs for async operations if services require it at top level
    # For GUI apps, the Qt event loop usually handles this, but service init might need it.
    # If using async heavily outside GUI event handlers, consider:
    # asyncio.run(main())
    # But for PyQt, direct call is usually correct.
    main()
