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
styles_dir = os.path.join(current_dir, "ui", "styles")
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
from src.services.qa_service import QAService

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("smartinfo.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # 只保留控制台日志输出
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
        # Fetch keys using the service method
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
        # Use the appropriate key based on which service is intended
        # Assuming NewsService might use Volcano Engine based on original code
        llm_client = LLMClient(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=volcengine_api_key, # Use Volcano Engine key
            async_mode=True
        )

        # Instantiate services with repositories and LLM client
        news_service = NewsService(news_repo, source_repo, category_repo, llm_client)
        # QAService might use a different model/API key if intended, needs adjustment
        # For now, pass the same LLM client, but it might default to DeepSeek models internally
        # QA Service requires the LLM client
        qa_service = QAService(qa_repo, llm_client)

        logger.info("Services initialized successfully.")
        return {
            "setting_service": setting_service,
            "news_service": news_service,
            "qa_service": qa_service,
            "llm_client": llm_client,
        }
    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        sys.exit(f"Service Initialization Error: {e}")


def load_stylesheet(app: "QApplication"):
    """Loads the QSS stylesheet."""
    qss_file = os.path.join(styles_dir, "style.qss")
    try:
        with open(qss_file, "r", encoding="utf-8") as f:
            stylesheet = f.read()
            app.setStyleSheet(stylesheet)
            logger.info(f"Loaded stylesheet from {qss_file}")
    except FileNotFoundError:
        logger.warning(f"Stylesheet file not found: {qss_file}. Using default styles.")
    except Exception as e:
        logger.error(f"Error loading stylesheet: {e}", exc_info=True)


def run_gui(services: Dict[str, Any]):
    """Runs the PyQt GUI application"""
    logger.info("Starting GUI...")
    # Import GUI elements late to avoid issues if dependencies are missing initially
    try:
        from PySide6.QtWidgets import QApplication
        from qasync import QEventLoop

        # IMPORTANT: MainWindow needs refactoring to accept services
        from src.ui.main_window import MainWindow
    except ImportError as e:
        logger.critical(
            f"Failed to import GUI components (PySide6, qasync?): {e}", exc_info=True
        )
        sys.exit(f"GUI Import Error: {e}. Please ensure PySide6 and qasync are installed.")

    app = QApplication(sys.argv)
    app.setApplicationName("SmartInfo")

    # --- Load Stylesheet ---
    load_stylesheet(app)

    # Pass services to MainWindow (MainWindow needs modification)
    try:
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        window = MainWindow(services, loop)  # Pass services dict
        window.show()
        logger.info("MainWindow shown.")
        sys.exit(loop.run_forever())
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

        # --- Handle Command Line Arguments (Needs refinement based on services) ---
        if args.reset_database:
            logger.warning("Executing --reset-database argument...")
            confirm = input(
                "WARNING: This will delete ALL data. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                logger.info("Resetting all database tables...")
                # Example: Using service methods if available, otherwise direct repo calls
                try:
                     # Clear data via Repositories (as service methods might not exist for all clears)
                    QARepository().clear_history()
                    ApiKeyRepository().delete_all()
                    SystemConfigRepository().delete_all()
                    NewsRepository().clear_all() # Clears news table
                    # Need to clear sources and categories *before* news if FKs are strict, or handle deletion order
                    NewsSourceRepository()._execute("DELETE FROM news_sources", commit=True) # Direct execute might be needed if no clear_all
                    NewsCategoryRepository()._execute("DELETE FROM news_category", commit=True)

                    logger.info(
                        "Database reset complete (SQLite tables cleared via Repos)."
                    )
                    # Re-initialize default sources/categories if needed
                    # e.g., services["news_service"].initialize_defaults()
                except Exception as db_reset_err:
                     logger.error(f"Error resetting database tables: {db_reset_err}", exc_info=True)
            else:
                logger.info("Database reset aborted.")
            sys.exit(0) # Exit after CLI operations

        elif args.reset_sources:
            logger.warning("Executing --reset-sources. Functionality needs implementation.")
            # Example call: services["news_service"].reset_sources_to_default()
            sys.exit(0)

        elif args.clear_news:
            logger.warning("Executing --clear-news argument...")
            confirm = input(
                "WARNING: This will delete ALL news articles. Type 'YES' to confirm: "
            )
            if confirm == "YES":
                # Use NewsService method
                if services["news_service"].clear_all_news():
                    logger.info("Cleared news data from SQLite.")
                else:
                    logger.error("Failed to clear news data from SQLite.")
            else:
                logger.info("Clear news data aborted.")
            sys.exit(0)


        # --- Run the Application ---
        run_gui(services)

    except SystemExit: # Catch sys.exit() calls
         logger.info("Application exiting via sys.exit().")
    except Exception as e:
        logger.critical(
            f"An unhandled error occurred during application startup: {e}",
            exc_info=True,
        )
        # Attempt to show message box if GUI libraries are loaded
        try:
             from PySide6.QtWidgets import QMessageBox, QApplication
             # Need to ensure QApplication exists if error happens before run_gui
             if QApplication.instance() is None:
                  _ = QApplication([]) # Create temporary instance
             QMessageBox.critical(None, "Fatal Error", f"Application failed to start:\n{e}")
        except Exception:
             pass # Ignore if GUI cannot be shown
        sys.exit(f"Fatal Error: {e}")
    finally:
        logger.info("-------------------- Application Terminating --------------------")


if __name__ == "__main__":
    main()