#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main Window Interface Module
Implements the main user interface of the application
"""

import sys
import logging
from typing import Dict, Any  # Added for type hinting

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QStatusBar,
    QMessageBox,
)
from PySide6.QtGui import QAction
from qasync import QEventLoop

# Import refactored tabs
from .tabs.news_tab import NewsTab
from .tabs.qa_tab import QATab
from .tabs.settings_tab import SettingsTab

# Assuming service classes are imported in main.py and passed
# No direct service imports here

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main Window Class"""

    def __init__(self, services: Dict[str, Any], loop: QEventLoop):
        super().__init__()
        self.services = services
        self.loop = loop

        self.setWindowTitle(
            "SmartInfo - Intelligent News Analysis and Knowledge Management Tool"
        )
        self.setMinimumSize(1200, 800)

        # Flag to indicate if news sources or categories changed in settings
        self.news_sources_or_categories_changed = False

        self._setup_ui()
        logger.info("Main window initialization completed")

    def _setup_ui(self):
        """Set up user interface using injected services"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Create tabs and inject required services ---
        try:
            # NewsTab needs NewsService and potentially SettingService for initial filter load
            self.news_tab = NewsTab(self.services["news_service"])
            # QATab needs QAService
            self.qa_tab = QATab(self.services["qa_service"])
            # SettingsTab needs SettingService and NewsService
            self.settings_tab = SettingsTab(
                self.services["setting_service"], self.services["news_service"]
            )

            # Connect signal from settings tab if sources/categories change
            self.settings_tab.settings_changed_signal.connect(
                self._handle_settings_change
            )

        except KeyError as e:
            logger.critical(
                f"Service dictionary missing required key: {e}. Cannot initialize UI.",
                exc_info=True,
            )
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Required service '{e}' not found. Application cannot start.",
            )
            # Exit or disable tabs? Exiting is safer.
            sys.exit(1)  # Or raise an exception
        except Exception as e:
            logger.critical(
                f"Unexpected error initializing UI tabs: {e}", exc_info=True
            )
            QMessageBox.critical(
                self, "Initialization Error", f"Error creating UI tabs: {e}"
            )
            sys.exit(1)

        # Add tabs to the widget
        self.tabs.addTab(self.news_tab, "News Management")
        self.tabs.addTab(self.qa_tab, "Q&A")
        self.tabs.addTab(self.settings_tab, "Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._create_menu_bar()

    def _handle_settings_change(self):
        """Slot to handle signal from SettingsTab when sources/categories change."""
        logger.info(
            "Received settings change signal (sources/categories potentially updated)."
        )
        self.news_sources_or_categories_changed = True
        # Check if the NewsTab is currently visible, if so, refresh it immediately
        if self.tabs.currentIndex() == 0:  # Index of NewsTab
            self._refresh_news_tab_filters()

    def _create_menu_bar(self):
        """Create menu bar"""
        file_menu = self.menuBar().addMenu("File")
        export_action = QAction("Export Data", self)
        export_action.triggered.connect(self._export_data)
        file_menu.addAction(export_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("Edit")
        # Add edit actions if needed

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _export_data(self):
        """Export data functionality (placeholder)"""
        # TODO: Implement using service layer if needed
        self.status_bar.showMessage("Export data feature in development...")
        QMessageBox.information(
            self, "Info", "Export data feature not yet implemented."
        )

    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About SmartInfo",
            "SmartInfo - Intelligent News Analysis and Knowledge Management Tool\n"
            "Version: 1.0.0\n"
            "An intelligent tool for tech researchers, analysts, and enthusiasts.",
        )

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Application exited normally by user.")
            # Perform any cleanup needed before closing services (DB connection closes via atexit)
            if hasattr(self, 'loop'):
                self.loop.quit()
            event.accept()
        else:
            event.ignore()

    def _on_tab_changed(self, index):
        """Handles tab change event."""
        logger.debug(f"Tab changed to index {index}")
        # If switched to News tab AND settings indicated a change, refresh filters
        if index == 0 and self.news_sources_or_categories_changed:  # Index 0 is NewsTab
            self._refresh_news_tab_filters()

        # Add actions for other tabs if needed when they become active
        elif index == 1:  # QA Tab
            self.qa_tab.load_history()  # Add this method to QATab

    def _refresh_news_tab_filters(self):
        """Refreshes filters on the news tab."""
        if hasattr(self, "news_tab") and self.news_tab:
            logger.info("Refreshing news tab filters due to settings change.")
            self.news_tab._load_filters()  # Call the filter loading method directly
            self.news_sources_or_categories_changed = False  # Reset flag
        else:
            logger.warning(
                "Attempted to refresh news tab filters, but tab object doesn't exist."
            )
