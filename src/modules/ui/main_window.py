#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
主窗口界面模块
实现应用的主要用户界面
"""

import sys
import logging
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QPushButton, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QAction

from .tabs.news_tab import NewsTab
from .tabs.analysis_tab import AnalysisTab
from .tabs.qa_tab import QATab
from .tabs.settings_tab import SettingsTab

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("SmartInfo - 智能资讯分析与知识管理工具")
        self.setMinimumSize(1200, 800)
        
        self._setup_ui()
        logger.info("主窗口初始化完成")
    
    def _setup_ui(self):
        """设置用户界面"""
        # 设置中心部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(self.central_widget)
        
        # 创建选项卡控件
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # 创建各选项卡
        self.news_tab = NewsTab()
        self.analysis_tab = AnalysisTab()
        self.qa_tab = QATab()
        self.settings_tab = SettingsTab()
        
        # 添加选项卡
        self.tabs.addTab(self.news_tab, "资讯管理")
        self.tabs.addTab(self.analysis_tab, "智能分析")
        self.tabs.addTab(self.qa_tab, "智能问答")
        self.tabs.addTab(self.settings_tab, "系统设置")
        
        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        # 创建菜单栏
        self._create_menu_bar()
    
    def _create_menu_bar(self):
        """创建菜单栏"""
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件")
        
        export_action = QAction("导出数据", self)
        export_action.triggered.connect(self._export_data)
        file_menu.addAction(export_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = self.menuBar().addMenu("编辑")
        
        # 帮助菜单
        help_menu = self.menuBar().addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _export_data(self):
        """导出数据功能"""
        # 待实现
        self.status_bar.showMessage("导出数据功能开发中...")
    
    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 SmartInfo",
            "SmartInfo - 智能资讯分析与知识管理工具\n"
            "版本: 1.0.0\n"
            "一款面向科技研究人员、行业分析师和技术爱好者的\n"
            "智能资讯分析与知识管理工具"
        )
    
    def closeEvent(self, event):
        """关闭窗口事件处理"""
        reply = QMessageBox.question(
            self, 
            '确认退出', 
            "确定要退出应用吗?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            logger.info("应用程序正常退出")
            event.accept()
        else:
            event.ignore() 