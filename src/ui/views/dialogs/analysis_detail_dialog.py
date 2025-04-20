 #!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
AnalysisDetailDialog - 用于显示新闻详情和分析内容
- 显示新闻的标题、链接、发布时间、摘要
- 显示分析内容，支持实时更新流式分析结果
- 连接到Controller的分析信号，接收流式分析结果
"""

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLabel,
    QScrollArea,
    QWidget,
    QApplication,
    QPushButton,
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor, QFont, QDesktopServices
from PySide6.QtCore import QUrl

logger = logging.getLogger(__name__)

class AnalysisDetailDialog(QDialog):
    """显示新闻详情和分析内容的对话框，支持LLM流式分析展示"""

    def __init__(self, news_id: int, controller, parent=None):
        super().__init__(parent)
        self.news_id = news_id
        self.controller = controller
        self.first_chunk_received = False
        
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """创建用户界面"""
        self.setWindowTitle("新闻分析详情")
        self.setMinimumSize(800, 600)
        self.setModal(False)
        
        # 设置窗口标志，允许最小化、最大化和系统菜单
        current_flags = self.windowFlags()
        new_flags = (
            current_flags
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowFlags(new_flags)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- 详情区域 ---
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        
        # 标题
        self.title_label = QLabel("加载中...")
        self.title_label.setWordWrap(True)
        title_font = QFont("Microsoft YaHei", 14, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        details_layout.addWidget(self.title_label)
        
        # 来源和日期
        source_date_layout = QHBoxLayout()
        self.source_label = QLabel("来源: 加载中...")
        self.date_label = QLabel("日期: 加载中...")
        source_date_layout.addWidget(self.source_label)
        source_date_layout.addWidget(self.date_label)
        source_date_layout.addStretch()
        details_layout.addLayout(source_date_layout)
        
        # 链接
        link_layout = QHBoxLayout()
        link_layout.setSpacing(5)
        link_label = QLabel("链接:")
        self.link_button = QPushButton("点击打开原文链接")
        self.link_button.setStyleSheet("text-align: left;")
        self.link_button.clicked.connect(self._open_link)
        self.news_link = ""  # 存储链接URL
        link_layout.addWidget(link_label)
        link_layout.addWidget(self.link_button, 1)
        details_layout.addLayout(link_layout)
        
        # 摘要标题
        summary_title = QLabel("摘要:")
        summary_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        details_layout.addWidget(summary_title)
        
        # 摘要内容
        self.summary_display = QTextEdit()
        self.summary_display.setReadOnly(True)
        self.summary_display.setMaximumHeight(120)
        self.summary_display.setStyleSheet("""
            background-color: #f9f9f9;
            border: 1px solid #e0e4e7;
            border-radius: 5px;
            padding: 8px;
        """)
        details_layout.addWidget(self.summary_display)
        
        main_layout.addWidget(details_widget)
        
        # 分隔线
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #e0e4e7;")
        main_layout.addWidget(separator)
        
        # --- 分析区域 ---
        analysis_title = QLabel("分析:")
        analysis_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        main_layout.addWidget(analysis_title)
        
        self.analysis_display = QTextEdit()
        self.analysis_display.setReadOnly(True)
        self.analysis_display.setMinimumHeight(250)
        self.analysis_display.setStyleSheet("""
            background-color: #ffffff;
            border: 1px solid #e0e4e7;
            border-radius: 5px;
            padding: 10px;
            color: #2a3142;
        """)
        analysis_font = QFont("Microsoft YaHei", 11)
        self.analysis_display.setFont(analysis_font)
        main_layout.addWidget(self.analysis_display, 1)  # 分析区域占用剩余空间

    def _connect_signals(self):
        """连接控制器信号到对话框槽函数"""
        if hasattr(self.controller, "analysis_chunk_received"):
            self.controller.analysis_chunk_received.connect(self._handle_analysis_chunk)
        else:
            logger.error("控制器缺少必要的信号: analysis_chunk_received")

    def set_details(self, title: str, link: str, date: str, summary: str, source_name: str):
        """设置新闻详情（标题、链接等）"""
        self.title_label.setText(title)
        self.source_label.setText(f"来源: {source_name}")
        self.date_label.setText(f"日期: {date}")
        self.news_link = link
        self.link_button.setToolTip(link)
        self.summary_display.setPlainText(summary)
        
        # 更新窗口标题
        self.setWindowTitle(f"新闻分析 - {title[:30]}...")

    def set_analysis_content(self, content: str):
        """设置分析内容（用于初始显示或完整替换）"""
        if QApplication.instance().thread() != self.thread():
            # 如果是从非GUI线程调用，使用invokeMethod确保线程安全
            QMetaObject.invokeMethod(
                self,
                "_set_analysis_content_on_gui",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, content),
            )
        else:
            self._set_analysis_content_on_gui(content)

    @Slot(str)
    def _set_analysis_content_on_gui(self, content: str):
        """在GUI线程中安全地设置分析内容"""
        try:
            self.analysis_display.setMarkdown(content)
            self.analysis_display.moveCursor(QTextCursor.MoveOperation.Start)
            self.analysis_display.ensureCursorVisible()
        except Exception as e:
            logger.error(f"设置分析内容时出错: {e}", exc_info=True)
            self.analysis_display.setPlainText(f"显示内容时出错: {str(e)}\n\n原始内容:\n{content}")

    @Slot(int, str)
    def _handle_analysis_chunk(self, news_id: int, chunk_text: str):
        """处理从控制器接收到的分析文本块"""
        # 检查news_id是否匹配当前对话框
        if news_id != self.news_id:
            return
            
        try:
            # 如果是第一个块，清除加载提示
            if not self.first_chunk_received:
                self.analysis_display.clear()
                self.first_chunk_received = True
                
            # 将光标移到末尾并插入新内容
            cursor = self.analysis_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.analysis_display.setTextCursor(cursor)
            
            # 支持Markdown格式
            current_text = self.analysis_display.toMarkdown()
            updated_text = current_text + chunk_text
            self.analysis_display.setMarkdown(updated_text)
            
            # 确保滚动到最新位置
            self.analysis_display.ensureCursorVisible()
        except Exception as e:
            logger.error(f"处理分析块时出错: {e}", exc_info=True)

    def _open_link(self):
        """打开新闻链接"""
        if self.news_link:
            QDesktopServices.openUrl(QUrl(self.news_link))