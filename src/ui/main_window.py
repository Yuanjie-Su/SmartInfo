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
from PySide6.QtCore import Signal, Slot, Qt

# Import tabs
from .tabs.news_tab import NewsTab
from .tabs.qa_tab import QATab
from .settings_window import SettingsWindow

logger = logging.getLogger(__name__)


class NavigationBar(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setObjectName("NavigationBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(15)

        # 导航按钮 - 顶部按钮（News和Chat）
        self.buttons = []
        top_btn_names = ["News", "Chat"]
        top_btn_icons = ["📰", "💬"]  # 使用Unicode字符作为图标

        for idx, (name, icon) in enumerate(zip(top_btn_names, top_btn_icons)):
            btn = QPushButton(f" {icon}  {name}")
            btn.setObjectName(f"NavBtn_{name}")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(45)
            btn.clicked.connect(lambda i=idx: self.on_btn_clicked(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        # 中间的伸缩空间
        layout.addStretch(1)

        # 导航按钮 - 底部的设置按钮
        settings_btn = QPushButton(f" ⚙️  Settings")
        settings_btn.setObjectName("NavBtn_Settings")
        settings_btn.setCheckable(True)
        settings_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        settings_btn.setMinimumHeight(45)
        settings_btn.clicked.connect(
            lambda checked: self.on_btn_clicked(2)
        )  # 索引2对应设置
        layout.addWidget(settings_btn)
        self.buttons.append(settings_btn)

        # 底部添加版本信息
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 12px;")
        layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignHCenter)

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

        self.setWindowTitle("SmartInfo - 智能资讯分析和知识管理工具")
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
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        main_layout.addWidget(content_container)
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

    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
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
        try:
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                    logger.info(f"加载样式文件成功: {qss_path}")
            else:
                logger.warning(f"样式文件不存在: {qss_path}")
        except Exception as e:
            logger.error(f"加载样式文件出错: {e}", exc_info=True)
