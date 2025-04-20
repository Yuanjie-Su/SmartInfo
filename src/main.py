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
from typing import Any, Dict
from PySide6.QtWidgets import QApplication

# --- Project Setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Early Imports (Config, Database, Repositories, Services, LLM Client) ---
from src.config import init_config, AppConfig
from src.db.connection import init_db_connection
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


def initialize_services(config: AppConfig) -> Dict[str, Any]:
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
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=volcengine_api_key,
            async_mode=True,
        )  # Use async for UI

        news_service = NewsService(news_repo, source_repo, category_repo)
        qa_service = QAService(qa_repo, llm_client)

        logger.info("Services initialized successfully.")
        return {
            "setting_service": setting_service,
            "news_service": news_service,
            "qa_service": qa_service,
        }
    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        sys.exit(f"Service Initialization Error: {e}")


def run_gui(app: QApplication, services: Dict[str, Any]):
    """Runs the PyQt GUI application"""
    logger.info("Starting GUI...")
    # Import GUI elements late to avoid issues if dependencies are missing initially
    try:
        from src.ui.views.main_window import MainWindow
    except ImportError as e:
        logger.critical(
            f"Failed to import GUI components (PySide6?): {e}", exc_info=True
        )
        sys.exit(f"GUI Import Error: {e}. Please ensure PySide6 is installed.")

    app.setApplicationName("SmartInfo")

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
    logger.info("-------------------- Application Starting --------------------")
    args = parse_args()
    setup_logging(args.log_level)

    try:
        # 1. Initialize Configuration
        config = init_config()

        # 2. Initialize QApplication
        app = QApplication(sys.argv)

        # 3. Initialize Database Connection Manager
        # This also ensures DB paths based on config are correct and tables exist
        init_db_connection()

        # 4. Initialize Services
        services = initialize_services(config)

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
                logger.info(
                    "Database reset complete (manual repo calls). Consider dedicated service method."
                )
                # Re-initialize default sources? Need method in NewsService
                # services["news_service"].initialize_default_sources() # Example
            else:
                logger.info("Database reset aborted.")

        elif args.reset_sources:
            logger.info("Executing --reset-sources argument...")
            confirm = input(
                "WARNING: This will delete ALL news sources. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                NewsSourceRepository().delete_all()
                logger.info("All news sources reseted.")
            else:
                logger.info("Reset news sources aborted.")

        elif args.clear_news:
            logger.warning("Executing --clear-news argument...")
            confirm = input(
                "WARNING: This will delete ALL news articles and embeddings. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                NewsRepository().clear_all()
                logger.info("Cleared news data from SQLite.")
            else:
                logger.info("Clear news data aborted.")

        # --- Run the Application ---
        run_gui(app, services)

    except Exception as e:
        logger.critical(
            f"An unhandled error occurred during application startup: {e}",
            exc_info=True,
        )
        sys.exit(f"Fatal Error: {e}")
    finally:
        logger.info("-------------------- Application Terminating --------------------")


if __name__ == "__main__":
    main()
