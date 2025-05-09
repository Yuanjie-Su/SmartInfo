#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main Window Interface Module
Implements the main user interface of the application
"""

import sys
import logging
from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStatusBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QLabel,
)
from PySide6.QtCore import Signal, Slot, Qt

# Import tabs
from .tabs.news_tab import NewsTab
from .tabs.qa_tab import QATab
from .settings_window import SettingsWindow
from ..controllers.main_controller import MainController

logger = logging.getLogger(__name__)


class NavigationBar(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavigationBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(10)

        # Navigation buttons - top buttons (News and Chat)
        self.buttons = []
        top_btn_names = ["News", "Chat"]
        top_btn_icons = ["📰", "💬"]  # Use Unicode characters as icons

        for idx, (name, icon) in enumerate(zip(top_btn_names, top_btn_icons)):
            btn = QPushButton(f"{icon}  {name}")
            btn.setObjectName(f"NavBtn_{name}")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("text-align: center;")
            btn.clicked.connect(lambda checked, i=idx: self.on_btn_clicked(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        # Intermediate flexible space
        layout.addStretch(1)

        # Navigation buttons - bottom settings button
        settings_btn = QPushButton(f"⚙️  Settings")
        settings_btn.setObjectName("NavBtn_Settings")
        settings_btn.setCheckable(True)
        settings_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        settings_btn.setStyleSheet("text-align: center;")
        settings_btn.clicked.connect(lambda checked: self.on_btn_clicked(2))
        layout.addWidget(settings_btn)
        self.buttons.append(settings_btn)

        # Add version information at the bottom
        version_label = QLabel("v1.0.0")
        version_label.setObjectName("VersionLabel")  # Added Object Name
        layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignHCenter)

        # Select the first item by default
        self.buttons[0].setChecked(True)

    def on_btn_clicked(self, idx):
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == idx)
        self.page_changed.emit(idx)


class MainWindow(QMainWindow):
    """Main Window Class"""

    def __init__(self, services: Dict[str, Any]):
        super().__init__()
        self.services = services
        # Initialize main controller, inject services to decouple UI and business logic
        self.main_controller = MainController(
            self.services["news_service"],
            self.services["qa_service"],
            self.services["setting_service"],
        )

        self.setWindowTitle("SmartInfo - Minimalist")  # Updated Title
        self.setMinimumSize(1100, 700)  # Adjusted minimum size slightly

        # Flag to indicate if news sources or categories changed in settings
        self.news_sources_or_categories_changed = False

        self._setup_ui()
        logger.info("Main window initialization completed")

    def _setup_ui(self):
        """Set up user interface using injected services"""
        # Central widget and main horizontal layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Container (Navigation) ---
        nav_container = QWidget()
        # Optional: Set object name for styling
        nav_container.setObjectName("NavigationContainer")
        nav_container.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        # Instantiate and add the NavigationBar to its container
        self.nav_bar = NavigationBar()
        nav_layout.addWidget(self.nav_bar)
        # Add the navigation container to the main layout
        main_layout.addWidget(nav_container)

        # --- Right Container (Content Stack) ---
        content_container = QWidget()
        # Optional: Set object name for styling
        content_container.setObjectName("ContentContainer")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        # Instantiate and add the QStackedWidget to the content container
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        # Add the content container to the main layout
        main_layout.addWidget(content_container)

        # Set stretch factors: Navigation fixed width, Content expands
        main_layout.setStretch(0, 0)  # Stretch factor for nav_container
        main_layout.setStretch(1, 1)  # Stretch factor for content_container

        # --- Create and Add Pages to Stack ---
        try:
            self.news_tab = NewsTab(self.main_controller.news_controller)
            self.qa_tab = QATab(self.main_controller.qa_controller)

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
            sys.exit(1)
        except Exception as e:
            logger.critical(
                f"Unexpected error initializing UI tabs: {e}", exc_info=True
            )
            QMessageBox.critical(
                self, "Initialization Error", f"Error creating UI tabs: {e}"
            )
            sys.exit(1)

        # Add pages to the stack widget inside the content_container
        self.stack.addWidget(self.news_tab)
        self.stack.addWidget(self.qa_tab)
        # Set default page
        self.stack.setCurrentIndex(0)

        # --- Connect Signals ---
        # Connect navigation bar signal to handle page changes
        self.nav_bar.page_changed.connect(self._handle_navigation_request)

        # --- Load Stylesheet ---
        # Ensure this happens after all UI elements are created and added
        self._load_stylesheet()

        # --- Settings Window Instance ---
        self.settings_window_instance: Optional[SettingsWindow] = None

    @Slot(int)
    def _handle_navigation_request(self, index: int):
        """Handle page change requests from the navigation bar"""
        logger.debug(f"Navigation requested for index: {index}")

        if index == 0:  # News Tab
            self.stack.setCurrentIndex(index)
            # If settings changed, refresh News Tab filters
            if self.news_sources_or_categories_changed:
                self._refresh_news_tab_filters()
        elif index == 1:  # QA Tab
            self.stack.setCurrentIndex(index)
            # Load QA history
            if hasattr(self, "qa_tab") and self.qa_tab:
                self.qa_tab.load_history()
        elif index == 2:  # Settings Dialog
            logger.info("Settings button clicked. Opening SettingsWindow.")
            try:
                # If SettingsWindow instance doesn't exist or is closed, create a new one
                if (
                    self.settings_window_instance is None
                    or not self.settings_window_instance.isVisible()
                ):
                    logger.debug("Creating new SettingsWindow instance.")
                    # Ensure correct services are passed
                    self.settings_window_instance = SettingsWindow(
                        controller=self.main_controller.settings_controller,
                        parent=self,
                    )
                    # Connect SettingsWindow signal back to MainWindow
                    self.main_controller.settings_controller.external_settings_changed.connect(
                        self._handle_settings_change
                    )
                else:
                    logger.debug(
                        "SettingsWindow instance already exists and is visible."
                    )

                # Show modal dialog and wait for it to close
                self.settings_window_instance.exec()  # Use exec() for modal dialog

            except KeyError as e:
                error_msg = f"Cannot open settings: Missing required service '{e}'."
                logger.error(error_msg)
                QMessageBox.critical(self, "Error", error_msg)
            except Exception as e:
                error_msg = f"Error opening settings window: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, "Error", error_msg)
        else:
            logger.warning(f"Unhandled navigation index: {index}")

        # Ensure the correct nav button remains checked after settings dialog closes
        current_stack_index = self.stack.currentIndex()
        for i, btn in enumerate(self.nav_bar.buttons):
            # Check the button corresponding to the current stack index (or settings if index is 2)
            btn.setChecked(i == (index if index == 2 else current_stack_index))

    def _handle_settings_change(self):
        """Slot to handle signal from SettingsTab when sources/categories change."""
        logger.info(
            "Received settings change signal (sources/categories potentially updated)."
        )
        self.news_sources_or_categories_changed = True
        # Check if the NewsTab is currently visible, if so, refresh it immediately
        if self.stack.currentIndex() == 0:  # Index of NewsTab
            self._refresh_news_tab_filters()

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self,
            "Confirm exit",
            "Are you sure you want to exit the program?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("User confirmed exit. Performing cleanup...")

            # --- Explicitly call cleanup methods for tabs ---
            try:
                if hasattr(self, "news_tab") and hasattr(
                    self.news_tab, "perform_cleanup"
                ):
                    logger.info("Calling NewsTab cleanup...")
                    if not self.news_tab.perform_cleanup():
                        # Optional: Handle case where cleanup fails/timeouts
                        logger.error(
                            "NewsTab cleanup reported issues. Application might not exit cleanly."
                        )

            except Exception as cleanup_err:
                logger.error(f"Error during tab cleanup: {cleanup_err}", exc_info=True)

            logger.info("Cleanup finished. Accepting close event.")
            event.accept()  # Accept the close event AFTER cleanup attempt
        else:
            logger.info("User cancelled exit.")
            event.ignore()

    # Removed _on_tab_changed as it's handled within _handle_navigation_request

    def _refresh_news_tab_filters(self):
        """Refreshes filters on the news tab."""
        if hasattr(self, "news_tab") and self.news_tab:
            logger.info("Refreshing news tab filters due to settings change.")
            self.news_tab.controller.load_filter_options()  # 调用控制器的方法加载过滤器
            self.news_sources_or_categories_changed = False  # Reset flag
        else:
            logger.warning(
                "Attempted to refresh news tab filters, but tab object doesn't exist."
            )

    def _load_stylesheet(self):
        """加载全局QSS样式文件"""
        import os

        qss_path = os.path.join(os.path.dirname(__file__), "..", "styles", "style.qss")
        try:
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    style_content = f.read()
                    self.setStyleSheet(style_content)
                    logger.info(f"加载样式文件成功: {qss_path}")
            else:
                logger.warning(f"样式文件不存在: {qss_path}")
        except Exception as e:
            logger.error(f"加载样式文件出错: {e}", exc_info=True)
