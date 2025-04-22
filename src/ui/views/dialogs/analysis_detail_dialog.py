#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
AnalysisDetailDialog - Used to display news details and analysis content
- Displays the title, link, publication time, and summary of the news
- Displays analysis content, supporting real-time updates of streaming analysis results
- Connects to the Controller's analysis signals to receive streaming analysis results
"""

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLabel,
    QWidget,
    QApplication,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor, QFont, QDesktopServices
from PySide6.QtCore import QUrl

logger = logging.getLogger(__name__)

class AnalysisDetailDialog(QDialog):
    """Dialog to display news details and analysis content, supporting LLM streaming analysis display"""

    def __init__(self, news_id: int, controller, parent=None):
        super().__init__(parent)
        self.news_id = news_id
        self.controller = controller
        self.first_chunk_received = False

        self.accumulated_text = ""  # Store accumulated content

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Create user interface"""
        self.setWindowTitle("News Analysis Details")
        self.setMinimumSize(800, 600)
        self.setModal(False)
        
        # Set window flags to allow minimize, maximize, and system menu
        current_flags = self.windowFlags()
        new_flags = (
            current_flags
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowFlags(new_flags)
        
        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        
        # --- Details Area ---
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        
        # Title
        self.title_label = QLabel("Loading...")
        self.title_label.setWordWrap(True)
        title_font = QFont("Microsoft YaHei", 14, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        details_layout.addWidget(self.title_label)
        
        # Source and Date
        source_date_link_layout = QHBoxLayout()
        
        # Create a consistent font for metadata elements
        metadata_font = QFont("Microsoft YaHei", 11)
        
        # Source label
        self.source_label = QLabel("Source Loading...")
        self.source_label.setFont(metadata_font)
        
        # Date label
        self.date_label = QLabel("Date Loading...")
        self.date_label.setFont(metadata_font)
        
        # Link icon button
        self.link_button = QPushButton("🔗")
        self.link_button.setFont(QFont("Microsoft YaHei", 12))
        self.link_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.link_button.setStyleSheet("""
            text-align: center;
            padding: 2px;
            min-height: 20px;
            max-height: 20px;
            min-width: 20px;
            max-width: 20px;
            border: none;
            background-color: transparent;
        """)
        self.link_button.clicked.connect(self._open_link)
        
        # Add widgets to the layout
        source_date_link_layout.addWidget(self.source_label)
        source_date_link_layout.addWidget(self.date_label)
        source_date_link_layout.addWidget(self.link_button)
        source_date_link_layout.addStretch()
        details_layout.addLayout(source_date_link_layout)
        
        content_font = QFont("Microsoft YaHei", 11)

        # Summary Title
        summary_title = QLabel("Summary:")
        summary_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        details_layout.addWidget(summary_title)
        
        # Summary Content
        self.summary_display = QTextEdit()
        self.summary_display.setReadOnly(True)
        self.summary_display.setMaximumHeight(120)
        self.summary_display.setStyleSheet("""
            background-color: #f9f9f9;
            border: 1px solid #e0e4e7;
            border-radius: 5px;
            padding: 8px;
        """)
        self.summary_display.setFont(content_font)
        details_layout.addWidget(self.summary_display)
        
        main_layout.addWidget(details_widget)
        
        # --- Analysis Area ---
        analysis_title = QLabel("Analysis:")
        analysis_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        main_layout.addWidget(analysis_title)
        
        # Improved Markdown Text Display
        self.analysis_display = QTextBrowser()
        self.analysis_display.setReadOnly(True)
        self.analysis_display.setMinimumHeight(250)
        self.summary_display.setStyleSheet("""
            background-color: #f9f9f9;
            border: 1px solid #e0e4e7;
            border-radius: 5px;
            padding: 8px;
        """)
        self.analysis_display.setFont(content_font)

        # Enable link clicking and text selection
        self.analysis_display.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )

        main_layout.addWidget(self.analysis_display, 1)  # Analysis area occupies remaining space

    def _connect_signals(self):
        """Connect controller signals to dialog slot functions"""
        if hasattr(self.controller, "analysis_chunk_received"):
            self.controller.analysis_chunk_received.connect(self._handle_analysis_chunk)
        else:
            logger.error("Controller is missing necessary signal: analysis_chunk_received")

    def set_details(self, title: str, url: str, date: str, summary: str, source_name: str):
        """Set news details (title, link, etc.)"""
        self.title_label.setText(title)
        self.source_label.setText(f"{source_name}")
        self.date_label.setText(f"{date}")
        self.news_url = url
        self.link_button.setToolTip(url)
        self.summary_display.setPlainText(summary)
        
        # Update window title
        self.setWindowTitle(f"News Analysis - {title[:30]}...")

    def set_analysis_content(self, content: str):
        """Set analysis content (for initial display or complete replacement)"""
        self.accumulated_text = content  # Update accumulated content
        
        if QApplication.instance().thread() != self.thread():
            # If called from a non-GUI thread, use invokeMethod to ensure thread safety
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
        """Safely set analysis content in the GUI thread"""
        try:
            # Process and render the markdown content
            self.analysis_display.setMarkdown(content)
            
            # Move cursor to the beginning to ensure proper scrolling from the top
            self.analysis_display.moveCursor(QTextCursor.MoveOperation.Start)
            self.analysis_display.ensureCursorVisible()
        except Exception as e:
            logger.error(f"Error setting analysis content: {e}", exc_info=True)
            self.analysis_display.setPlainText(f"Error displaying content: {str(e)}\n\nOriginal content:\n{content}")

    @Slot(int, str)
    def _handle_analysis_chunk(self, news_id: int, chunk_text: str):
        """Handle analysis text chunk received from the controller"""
        # Check if news_id matches the current dialog
        if news_id != self.news_id:
            return
            
        try:
            # If this is the first chunk, clear the loading prompt
            if not self.first_chunk_received:
                self.analysis_display.clear()
                self.accumulated_text = ""
                self.first_chunk_received = True
            
            # Accumulate the markdown content
            self.accumulated_text += chunk_text
            
            # Render the accumulated content
            self.analysis_display.setMarkdown(self.accumulated_text)
            
        except Exception as e:
            logger.error(f"Error handling analysis chunk: {e}", exc_info=True)

    def _open_link(self):
        """Open news link"""
        if self.news_url:
            QDesktopServices.openUrl(QUrl(self.news_url))