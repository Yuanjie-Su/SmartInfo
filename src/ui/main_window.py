#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Main Window Interface Module
Implements the main user interface of the application
"""

import sys
import logging
from typing import Dict, Any, Optional  # Added for type hinting

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
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal, Slot

# Import refactored tabs
from .tabs.news_tab import NewsTab
from .tabs.qa_tab import QATab
from .settings_window import SettingsWindow

# Assuming service classes are imported in main.py and passed
# No direct service imports here

logger = logging.getLogger(__name__)


class NavigationBar(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setObjectName("NavigationBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        # 导航按钮
        self.buttons = []
        btn_names = ["News", "Chat", "Settings"]
        for idx, name in enumerate(btn_names):
            btn = QPushButton(name)
            btn.setObjectName(f"NavBtn_{name}")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked, i=idx: self.on_btn_clicked(i))
            layout.addWidget(btn)
            self.buttons.append(btn)
        layout.addStretch(1)
        # 默认选中第一个
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
        # 主体分栏布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧导航栏
        self.nav_bar = NavigationBar()
        main_layout.addWidget(self.nav_bar)

        # 右侧内容区（StackedWidget）
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)

        # --- 创建页面 ---
        try:
            # NewsTab needs NewsService and potentially SettingService for initial filter load
            self.news_tab = NewsTab(self.services["news_service"])
            # QATab needs QAService
            self.qa_tab = QATab(self.services["qa_service"])

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

        # 添加页面到栈
        self.stack.addWidget(self.news_tab)
        self.stack.addWidget(self.qa_tab)
        # 默认显示第一个页面
        self.stack.setCurrentIndex(0)

        # 连接导航栏按钮点击信号
        self.nav_bar.page_changed.connect(self._handle_navigation_request)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._create_menu_bar()
        # 加载全局样式
        self._load_stylesheet()

        self.settings_window_instance: Optional[SettingsWindow] = None

    @Slot(int)
    def _handle_navigation_request(self, index: int):
        """处理来自导航栏的页面切换请求"""
        logger.debug(f"Navigation requested for index: {index}")

        if index == 0:  # News Tab
            self.stack.setCurrentIndex(0)
            # 如果设置已更改，刷新 News Tab 的过滤器
            if self.news_sources_or_categories_changed:
                self._refresh_news_tab_filters()
        elif index == 1:  # QA Tab
            self.stack.setCurrentIndex(1)
            # 加载 QA 历史记录
            if hasattr(self, "qa_tab") and self.qa_tab:
                self.qa_tab.load_history()
        elif index == 2:  # Settings Dialog
            logger.info("Settings button clicked. Opening SettingsWindow.")
            try:
                # 如果 SettingsWindow 实例不存在或已被关闭，则创建新的实例
                if (
                    self.settings_window_instance is None
                    or not self.settings_window_instance.isVisible()
                ):
                    logger.debug("Creating new SettingsWindow instance.")
                    # 确保传递了正确的 services
                    self.settings_window_instance = SettingsWindow(
                        setting_service=self.services["setting_service"],
                        news_service=self.services["news_service"],
                        parent=self,  # 设置父窗口为 MainWindow
                    )
                    # 将 SettingsWindow 的信号连接回 MainWindow
                    self.settings_window_instance.settings_changed_signal.connect(
                        self._handle_settings_change
                    )
                else:
                    logger.debug(
                        "SettingsWindow instance already exists and is visible."
                    )

                # 显示模态对话框并等待其关闭
                self.settings_window_instance.exec()

            except KeyError as e:
                error_msg = f"无法打开设置：缺少必要的服务 '{e}'。"
                logger.error(error_msg)
                QMessageBox.critical(self, "错误", error_msg)
            except Exception as e:
                error_msg = f"打开设置窗口时出错: {e}"
                logger.error(error_msg, exc_info=True)
                QMessageBox.critical(self, "错误", error_msg)
        else:
            logger.warning(f"未处理的导航索引: {index}")

    def _handle_settings_change(self):
        """Slot to handle signal from SettingsTab when sources/categories change."""
        logger.info(
            "Received settings change signal (sources/categories potentially updated)."
        )
        self.news_sources_or_categories_changed = True
        # Check if the NewsTab is currently visible, if so, refresh it immediately
        if self.stack.currentIndex() == 0:  # Index of NewsTab
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

    def _load_stylesheet(self):
        """加载全局QSS样式文件"""
        import os

        qss_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
