# src/ui/dialogs/fetch_progress_dialog.py

import logging
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QDialogButtonBox,
    QApplication,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
    QProgressBar,
    QLabel,
    QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont

logger = logging.getLogger(__name__)


class FetchProgressDialog(QDialog):
    """Dialog to show the progress of fetching news from multiple sources."""

    # Signal emitted when a view button is clicked, passing the URL
    view_llm_output_requested = Signal(str)

    # Column constants
    COL_NAME = 0
    COL_URL = 1
    COL_STATUS = 2
    COL_ACTION = 3

    # Estimated total steps for a successful fetch per URL
    TOTAL_EXPECTED_STEPS = 12

    def __init__(self, sources: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("News Fetch Progress")
        self.setMinimumSize(900, 500)
        self.sources_map: Dict[str, int] = {}  # url -> row_index
        # Track whether fetch tasks are running to avoid AttributeError in closeEvent
        self.is_running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 表格容器
        table_container = QWidget()
        table_container.setObjectName("FetchProgressContainer")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(5, 5, 5, 5)

        self.table = QTableWidget()
        self.table.setObjectName("FetchProgressTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Source", "URL", "Progress", "Action"])

        # Table basic configuration: no grid, elide text, no selection, fixed row height and column widths
        self.table.setShowGrid(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        # Horizontal header alignment, fixed resize mode and height
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # Fixed resize for all columns
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        # Header padding top/bottom controlled by style.qss, set minimum height for padding
        self.table.horizontalHeader().setMinimumHeight(54)
        self.table.verticalHeader().setDefaultSectionSize(72)
        self.table.horizontalHeader().setStretchLastSection(True)
        # Fixed column widths
        self.table.setColumnWidth(self.COL_NAME, 180)
        self.table.setColumnWidth(self.COL_URL, 320)
        self.table.setColumnWidth(self.COL_STATUS, 200)
        self.table.setColumnWidth(self.COL_ACTION, 110)
        # Non-editable and unsortable
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(False)
        # header padding, font and border styling moved to style.qss

        self.populate_table(sources)
        table_layout.addWidget(self.table)
        layout.addWidget(table_container, 1)

        # Create a ButtonBox without actual buttons, just for layout
        button_box = QDialogButtonBox(self)
        layout.addWidget(button_box) # Add to main layout

    def populate_table(self, sources: List[Dict[str, Any]]):
        """Fills the table with the initial source list."""
        self.table.setRowCount(0)  # Clear existing rows
        self.sources_map.clear()
        self.table.setRowCount(len(sources))

        for idx, source_info in enumerate(sources):
            url = source_info.get("url", f"invalid_url_{idx}")
            self.sources_map[url] = idx

            # Empty cell for index (no checkbox)
            empty_item = QTableWidgetItem("")
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name_item = QTableWidgetItem(source_info.get("name", "N/A"))
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            url_item = QTableWidgetItem(url)
            url_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            # 使用进度条替换status列
            progress = QProgressBar()
            progress.setObjectName(f"progress_{idx}")
            progress.setRange(
                0, self.TOTAL_EXPECTED_STEPS
            )  # Set range based on expected steps
            progress.setValue(0)  # Initial value is 0
            progress.setFormat("Waiting")  # Initial text
            progress.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center text

            self.table.setCellWidget(idx, self.COL_STATUS, progress)

            # Set items
            self.table.setItem(idx, self.COL_NAME, name_item)
            self.table.setItem(idx, self.COL_URL, url_item)

            # Add a flat view button, initially disabled
            view_button = QPushButton("View")
            view_button.setFlat(True)
            view_button.setEnabled(False)
            # Connect view button to emit view signal
            view_button.clicked.connect(
                lambda _=None, u=url: self._emit_view_request(u)
            )
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            action_layout.addWidget(view_button)
            self.table.setCellWidget(idx, self.COL_ACTION, action_widget)

        # url -> status update count
        self.status_history = {s["url"]: 0 for s in sources}
        # url -> is_final_status
        self.final_status_flag = {s["url"]: False for s in sources}

        # Dynamic resizing removed: use fixed widths configured in init

    @Slot(str, str, bool)
    def update_status(self, url: str, status: str, is_final_status: bool):
        """Updates the status and progress bar for a given URL."""
        # Mark tasks as running on any status update
        self.is_running = True

        if url in self.sources_map:
            if self.final_status_flag.get(url, False):
                return

            row = self.sources_map[url]

            # --- Progress Bar Update ---
            progress_widget = self.table.cellWidget(row, self.COL_STATUS)
            if isinstance(progress_widget, QProgressBar):
                progress = progress_widget
            else:
                # Fallback: create if it wasn't there (shouldn't happen with new init)
                logger.warning(f"Progress bar not found for {url}, creating new one.")
                progress = QProgressBar()
                progress.setRange(0, self.TOTAL_EXPECTED_STEPS)
                progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, self.COL_STATUS, progress)

            # Calculate progress value
            self.status_history[url] += 1
            progress_value = self.status_history[url]

            if is_final_status:
                self.final_status_flag[url] = True
                # Clear running flag when all tasks have completed
                if all(self.final_status_flag.values()):
                    self.is_running = False

                # 根据状态更改进度条颜色
                if "失败" in status or "错误" in status:
                    progress.setStyleSheet(
                        """
                        QProgressBar {
                            border: none;
                            border-radius: 6px;
                            background-color: #E8E8E8;
                        }
                        QProgressBar::chunk {
                            background-color: #dc3545;
                            border-radius: 6px;
                        }
                    """
                    )
                elif "成功" in status:
                    progress.setStyleSheet(
                        """
                        QProgressBar {
                            border: none;
                            border-radius: 6px;
                            background-color: #E8E8E8;
                        }
                        QProgressBar::chunk {
                            background-color: #9CAE7C;
                            border-radius: 6px;
                        }
                    """
                    )
            else:
                # Ensure value doesn't exceed max before final status
                progress_value = min(progress_value, self.TOTAL_EXPECTED_STEPS)

            progress.setValue(progress_value)
            progress.setFormat(f"{status}")
            # Set tooltip to show just current status
            progress.setToolTip(
                f"{status} ({progress_value}/{self.TOTAL_EXPECTED_STEPS})"
            )

            # --- Action Button Update ---
            if is_final_status:
                current_widget = self.table.cellWidget(row, self.COL_ACTION)
                button_container = None
                view_button = None

                # Find existing button or create new one
                if (
                    isinstance(current_widget, QWidget)
                    and current_widget.layout()
                    and isinstance(
                        current_widget.layout().itemAt(0).widget(), QPushButton
                    )
                ):
                    # It's the container with the button
                    button_container = current_widget
                    view_button = current_widget.layout().itemAt(0).widget()
                elif isinstance(
                    current_widget, QPushButton
                ):  # Should not happen with container setup
                    view_button = current_widget
                    # Need to wrap it in a container for alignment
                    button_container = QWidget()
                    button_layout = QHBoxLayout(button_container)
                    button_layout.addWidget(view_button)
                    button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    button_layout.setContentsMargins(2, 2, 2, 2)
                    self.table.setCellWidget(row, self.COL_ACTION, button_container)
                else:
                    # Replace placeholder or unexpected widget
                    view_button = QPushButton("View")
                    view_button.setFlat(True)
                    view_button.setToolTip(f"查看 {url} 的分析结果")
                    # Disconnect previous lambda if any before connecting new one
                    try:
                        view_button.clicked.disconnect()
                    except RuntimeError:
                        pass  # No connection existed
                    view_button.clicked.connect(
                        lambda *args, u=url: self._emit_view_request(u)
                    )

                    button_container = QWidget()
                    button_layout = QHBoxLayout(button_container)
                    button_layout.addWidget(view_button)
                    button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    button_layout.setContentsMargins(2, 2, 2, 2)
                    self.table.setCellWidget(row, self.COL_ACTION, button_container)

                # Ensure button is enabled
                if view_button:
                    view_button.setEnabled(True)

        else:
            logger.warning(f"URL '{url}' not found in progress table map.")

    def _emit_view_request(self, url: str):
        """Helper function to emit the signal."""
        logger.debug(f"View button clicked for URL: {url}")
        self.view_llm_output_requested.emit(url)

    def closeEvent(self, event):
        # Ask for confirmation if tasks are still running
        if getattr(self, 'is_running', False):
            reply = QMessageBox.question(
                self,
                "Confirm Close",
                "Fetch tasks are in progress. Are you sure you want to close the window and cancel the tasks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # Proceed with default close behavior
        super().closeEvent(event)

    def reject(self):
        """Override reject (called on Escape or Close button if standard box used)"""
        logger.debug("FetchProgressDialog reject triggered, hiding.")
        self.hide()  # Just hide
