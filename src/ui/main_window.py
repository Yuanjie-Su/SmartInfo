#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main Window Interface Module
Implements the main user interface of the application
"""

import sys
import logging
from typing import Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QStatusBar, QMessageBox, QDialog # Added QDialog
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Slot # Added Slot
from qasync import QEventLoop

# Import tabs
from .tabs.news_tab import NewsTab
from .tabs.qa_tab import QATab
# SettingsTab is removed

# Import dialogs (assuming they are created)
from .dialogs.source_management_dialog import SourceManagementDialog
# Import other dialogs as they are created
# from .dialogs.category_management_dialog import CategoryManagementDialog
# from .dialogs.api_settings_dialog import ApiSettingsDialog
# from .dialogs.system_settings_dialog import SystemSettingsDialog

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main Window Class"""

    def __init__(self, services: Dict[str, Any], loop: QEventLoop):
        super().__init__()
        self.services = services
        self.loop = loop

        self.setWindowTitle("SmartInfo - Intelligent News Analysis")
        self.setMinimumSize(1200, 800)

        # No longer needed as SettingsTab is gone
        # self.news_sources_or_categories_changed = False

        self._setup_ui()
        logger.info("Main window initialization completed")

    def _setup_ui(self):
        """Set up user interface using injected services"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Create tabs (excluding SettingsTab) ---
        try:
            self.news_tab = NewsTab(self.services["news_service"])
            self.qa_tab = QATab(self.services["qa_service"])
            # SettingsTab is removed
        except KeyError as e:
            logger.critical(f"Service dictionary missing key: {e}.", exc_info=True)
            QMessageBox.critical(self, "Init Error", f"Service '{e}' not found.")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"Error initializing UI tabs: {e}", exc_info=True)
            QMessageBox.critical(self, "Init Error", f"Error creating UI tabs: {e}")
            sys.exit(1)

        # Add tabs to the widget
        self.tabs.addTab(self.news_tab, "News") # Simplified name
        self.tabs.addTab(self.qa_tab, "Q&A")

        # No longer needed
        # self.tabs.currentChanged.connect(self._on_tab_changed)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._create_menu_bar()

    # No longer needed
    # def _handle_settings_change(self): ...
    # def _on_tab_changed(self, index): ...
    # def _refresh_news_tab_filters(self): ...


    def _create_menu_bar(self):
        """Create menu bar"""
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")
        # export_action = QAction("Export Data", self)
        # export_action.triggered.connect(self._export_data)
        # file_menu.addAction(export_action)
        # file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit) # Standard shortcut
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Settings Menu ---
        settings_menu = menu_bar.addMenu("&Settings")

        manage_sources_action = QAction("Manage News Sources...", self)
        manage_sources_action.triggered.connect(self._open_source_manager)
        settings_menu.addAction(manage_sources_action)

        # Placeholder actions for other settings dialogs
        manage_categories_action = QAction("Manage Categories...", self)
        manage_categories_action.triggered.connect(self._open_category_manager) # Placeholder method
        settings_menu.addAction(manage_categories_action)

        settings_menu.addSeparator()

        api_config_action = QAction("API Configuration...", self)
        api_config_action.triggered.connect(self._open_api_config) # Placeholder method
        settings_menu.addAction(api_config_action)

        system_config_action = QAction("System Configuration...", self)
        system_config_action.triggered.connect(self._open_system_config) # Placeholder method
        settings_menu.addAction(system_config_action)


        # --- Help Menu ---
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # --- Settings Dialog Handlers ---

    @Slot()
    def _open_source_manager(self):
        """Opens the news source management dialog."""
        try:
            dialog = SourceManagementDialog(self.services["news_service"], self)
            # Connect signals from dialog if needed (e.g., to refresh news tab filters)
            # dialog.sources_changed.connect(self._refresh_news_tab_filters)
            dialog.exec() # Show modally
            # After dialog closes, refresh filters in news tab
            if hasattr(self, 'news_tab') and self.news_tab:
                 self.news_tab._load_filters()
        except Exception as e:
             logger.error(f"Error opening source management dialog: {e}", exc_info=True)
             QMessageBox.critical(self, "Error", f"Could not open source manager: {e}")

    # --- Placeholder Handlers for Other Settings ---
    @Slot()
    def _open_category_manager(self):
        # TODO: Create CategoryManagementDialog and implement this
        QMessageBox.information(self, "Not Implemented", "Category management dialog is not yet implemented.")
        # Example:
        # try:
        #     dialog = CategoryManagementDialog(self.services["news_service"], self)
        #     dialog.exec()
        #     if hasattr(self, 'news_tab') and self.news_tab: self.news_tab._load_filters()
        # except Exception as e: logger.error(...)

    @Slot()
    def _open_api_config(self):
        # TODO: Create ApiSettingsDialog and implement this
        QMessageBox.information(self, "Not Implemented", "API configuration dialog is not yet implemented.")
         # Example:
        # try:
        #     dialog = ApiSettingsDialog(self.services["setting_service"], self)
        #     dialog.exec()
        #     # Maybe update status bar or re-init LLM client?
        # except Exception as e: logger.error(...)

    @Slot()
    def _open_system_config(self):
         # TODO: Create SystemSettingsDialog and implement this
        QMessageBox.information(self, "Not Implemented", "System configuration dialog is not yet implemented.")
         # Example:
        # try:
        #     dialog = SystemSettingsDialog(self.services["setting_service"], self)
        #     dialog.exec()
        #     # Refresh relevant parts of the UI?
        # except Exception as e: logger.error(...)


    # --- Other Methods ---

    def _export_data(self):
        """Export data functionality (placeholder)"""
        self.status_bar.showMessage("Export data feature not implemented.")
        QMessageBox.information(self, "Info", "Export data feature not yet implemented.")

    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About SmartInfo",
            "SmartInfo - Intelligent News Analysis\nVersion: 1.1.0 (Refactored)\n"
        )

    def closeEvent(self, event):
        """Handle window close event"""
        # Ensure background tasks are handled (example for news_tab)
        if hasattr(self, 'news_tab') and self.news_tab.fetch_task and not self.news_tab.fetch_task.done():
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "A news fetch task is running. Are you sure you want to exit? The task will be cancelled.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            else:
                 logger.info("User requested exit during fetch, cancelling task.")
                 self.news_tab.fetch_task.cancel() # Cancel the task

        # Add similar checks for qa_tab if its task needs explicit handling on close
        if hasattr(self, 'qa_tab') and self.qa_tab._qa_task and not self.qa_tab._qa_task.done():
            logger.info("QA task running during exit, cancelling.")
            self.qa_tab._qa_task.cancel()

        # Standard exit confirmation (optional if task check is sufficient)
        reply = QMessageBox.question(
            self, "Confirm Exit", "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Application exiting.")
            # Cleanly stop the asyncio loop associated with qasync
            if hasattr(self, 'loop') and self.loop.is_running():
                logger.info("Stopping asyncio event loop.")
                self.loop.quit()
            event.accept()