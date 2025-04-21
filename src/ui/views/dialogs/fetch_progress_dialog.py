# src/ui/views/dialogs/fetch_progress_dialog.py
# -*- coding: utf-8 -*-

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
    # --- Signal emitted when stop is requested for specific tasks ---
    tasks_stop_requested = Signal(list) # Emits list of URLs to stop

    # --- Column constants ---
    COL_CHECKBOX = 0
    COL_NAME = 1
    COL_URL = 2
    COL_STATUS = 3
    COL_ACTION = 4

    # Estimated total steps for a successful fetch per URL
    TOTAL_EXPECTED_STEPS = 12

    def __init__(self, sources: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("News Fetch Progress")
        self.setMinimumSize(950, 500)
        self.sources_map: Dict[str, int] = {}  # url -> row_index
        self.is_running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # table container
        table_container = QWidget()
        table_container.setObjectName("FetchProgressContainer")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(5, 5, 5, 5)

        self.table = QTableWidget()
        self.table.setObjectName("FetchProgressTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "Source", "URL", "Progress", "Action"])

        # Table basic configuration: no grid, elide text, no selection, fixed row height and column widths
        self.table.setShowGrid(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        # Horizontal header alignment, fixed resize mode and height
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # Fixed resize for all columns
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        # Header padding top/bottom controlled by style.qss, set minimum height for padding
        self.table.horizontalHeader().setMinimumHeight(54)
        self.table.verticalHeader().setDefaultSectionSize(72) # Fixed typo setDefaultSectionSize
        # --- Column widths ---
        self.table.setColumnWidth(self.COL_CHECKBOX, 40) # Width for checkbox
        self.table.setColumnWidth(self.COL_NAME, 180)
        self.table.setColumnWidth(self.COL_URL, 320)
        self.table.setColumnWidth(self.COL_STATUS, 200)
        self.table.setColumnWidth(self.COL_ACTION, 110)

        self.table.horizontalHeader().setStretchLastSection(True) # Adjust if needed
        # Non-editable and unsortable
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Fixed typo NoEditTriggers
        self.table.setSortingEnabled(False)
        # header padding, font and border styling moved to style.qss

        self.populate_table(sources)
        table_layout.addWidget(self.table)
        layout.addWidget(table_container, 1)

        # --- Add Stop Selected Button ---
        button_layout = QHBoxLayout() # Layout for buttons at the bottom
        self.stop_button = QPushButton("Stop Selected")
        self.stop_button.setToolTip("Stop the selected fetch tasks.")
        self.stop_button.clicked.connect(self._handle_stop_selected)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch() # Push button to the left

        layout.addLayout(button_layout) # Add the button layout

    def populate_table(self, sources: List[Dict[str, Any]]):
        """Fills the table with the initial source list."""
        self.table.setRowCount(0)  # Clear existing rows
        self.sources_map.clear()
        self.table.setRowCount(len(sources))

        for idx, source_info in enumerate(sources):
            url = source_info.get("url", f"invalid_url_{idx}")
            self.sources_map[url] = idx

            # --- Checkbox Item ---
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.CheckState.Unchecked)
            checkbox_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, self.COL_CHECKBOX, checkbox_item)

            # --- Existing Items (Indices Shifted) ---
            name_item = QTableWidgetItem(source_info.get("name", "N/A"))
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            url_item = QTableWidgetItem(url)
            url_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            progress = QProgressBar()
            progress.setObjectName(f"progress_{idx}")
            progress.setRange(
                0, self.TOTAL_EXPECTED_STEPS
            )
            progress.setValue(0)
            progress.setFormat("Waiting")
            progress.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setCellWidget(idx, self.COL_STATUS, progress)

            # Set items
            self.table.setItem(idx, self.COL_NAME, name_item)
            self.table.setItem(idx, self.COL_URL, url_item)

            # Add a flat view button, initially disabled
            view_button = QPushButton("View")
            view_button.setFlat(True)
            view_button.setEnabled(False)
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
        # Mark tasks as running on any status update, unless the status is explicitly final "Cancelled"
        if not (is_final_status and "Cancelled" in status):
             self.is_running = True

        if url in self.sources_map:
            row = self.sources_map[url]

            # --- Check if already marked final to prevent updates after cancellation/completion ---
            if self.final_status_flag.get(url, False):
                # Allow updating status to 'Cancelled' even if already marked final otherwise
                if "Cancelled" not in status:
                     logger.debug(f"Ignoring status update for {url} because it's already final: {status}")
                     return
                # If status is Cancelled, ensure progress bar reflects it
                is_final_status = True # Force final state for Cancelled status

            progress_widget = self.table.cellWidget(row, self.COL_STATUS)
            if isinstance(progress_widget, QProgressBar):
                progress = progress_widget
            else:
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
                # Clear running flag only when *all* tasks have completed or been cancelled
                if all(self.final_status_flag.values()):
                    self.is_running = False
                # Set value to max on success/complete, potentially 0 or specific value on error/cancel
                if "成功" in status or "Complete" in status:
                    progress_value = self.TOTAL_EXPECTED_STEPS
                elif "Cancelled" in status:
                    progress_value = 0 # Reset progress on cancellation
                    progress.setStyleSheet(
                        """
                        QProgressBar { border: none; border-radius: 6px; background-color: #E8E8E8; }
                        QProgressBar::chunk { background-color: #6c757d; border-radius: 6px; } /* Grey for cancelled */
                        """
                    )
                else: # Error/Failure
                     progress_value = max(0, progress_value -1) # Keep current progress or slightly back
                     progress.setStyleSheet(
                         """
                         QProgressBar { border: none; border-radius: 6px; background-color: #E8E8E8; }
                         QProgressBar::chunk { background-color: #dc3545; border-radius: 6px; } /* Red for error */
                         """
                     )

                # Update progress bar style for success if not already set for error/cancel
                if "成功" in status or "Complete" in status:
                     progress.setStyleSheet(
                         """
                         QProgressBar { border: none; border-radius: 6px; background-color: #E8E8E8; }
                         QProgressBar::chunk { background-color: #9CAE7C; border-radius: 6px; } /* Green for success */
                         """
                     )
            else:
                # Ensure value doesn't exceed max before final status
                progress_value = min(progress_value, self.TOTAL_EXPECTED_STEPS)
                # Reset style for ongoing progress
                progress.setStyleSheet("") # Use default stylesheet

            progress.setValue(progress_value)
            progress.setFormat(f"{status}")
            progress.setToolTip(
                f"{status} ({progress_value}/{self.TOTAL_EXPECTED_STEPS})"
            )

            # --- Action Button Update ---
            # Enable view button only on successful completion
            action_cell_widget = self.table.cellWidget(row, self.COL_ACTION)
            if isinstance(action_cell_widget, QWidget) and action_cell_widget.layout():
                 view_button = action_cell_widget.layout().itemAt(0).widget()
                 if isinstance(view_button, QPushButton):
                     view_button.setEnabled(is_final_status and ("Complete" in status or "成功" in status))

            # --- Disable Checkbox on Final Status ---
            checkbox_item = self.table.item(row, self.COL_CHECKBOX)
            if checkbox_item and is_final_status:
                checkbox_item.setFlags(checkbox_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable) # Remove checkable flag
                checkbox_item.setCheckState(Qt.CheckState.Unchecked) # Ensure it's unchecked


        else:
            logger.warning(f"URL '{url}' not found in progress table map.")

    def _emit_view_request(self, url: str):
        """Helper function to emit the signal."""
        logger.debug(f"View button clicked for URL: {url}")
        self.view_llm_output_requested.emit(url)

    # --- Handler for Stop Selected Button ---
    @Slot()
    def _handle_stop_selected(self):
        """Handles the click event of the 'Stop Selected' button."""
        urls_to_stop = []
        rows_to_remove_indices = []

        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, self.COL_CHECKBOX)
            # Check if item exists, is enabled, and is checked
            if checkbox_item and \
               checkbox_item.flags() & Qt.ItemFlag.ItemIsEnabled and \
               checkbox_item.checkState() == Qt.CheckState.Checked:

                url_item = self.table.item(row, self.COL_URL)
                if url_item:
                    url = url_item.text()
                    if url and url not in urls_to_stop: # Avoid duplicates if any
                        urls_to_stop.append(url)
                        rows_to_remove_indices.append(row)

        if not urls_to_stop:
            QMessageBox.information(self, "Stop Tasks", "No tasks selected to stop.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Stop",
            f"Are you sure you want to stop the selected {len(urls_to_stop)} task(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Requesting stop for URLs: {urls_to_stop}")
            # Emit the signal to the controller
            self.tasks_stop_requested.emit(urls_to_stop)

            # Visually remove the rows from the table *after* emitting the signal
            # Iterate in reverse to avoid index shifting issues
            for row_index in sorted(rows_to_remove_indices, reverse=True):
                # Also remove from the internal map to prevent future updates to removed rows
                url_item = self.table.item(row_index, self.COL_URL)
                if url_item:
                    url_to_remove = url_item.text()
                    if url_to_remove in self.sources_map:
                        del self.sources_map[url_to_remove]
                    if url_to_remove in self.status_history:
                        del self.status_history[url_to_remove]
                    if url_to_remove in self.final_status_flag:
                         del self.final_status_flag[url_to_remove] # Important: update final flag state

                self.table.removeRow(row_index)

            # Re-index the sources_map after removals
            self._reindex_sources_map()

            # Maybe update the overall running status if all remaining tasks are now final
            if all(self.final_status_flag.get(url, False) for url in self.sources_map.keys()):
                 self.is_running = False


    # --- Helper to re-index map after row removal ---
    def _reindex_sources_map(self):
        """Updates the URL to row index mapping after rows are removed."""
        new_map = {}
        for row in range(self.table.rowCount()):
            url_item = self.table.item(row, self.COL_URL)
            if url_item:
                url = url_item.text()
                new_map[url] = row
        self.sources_map = new_map


    def closeEvent(self, event):
        # Ask for confirmation if tasks are still running
        # Check the is_running flag which is now updated more accurately
        if self.is_running:
            reply = QMessageBox.question(
                self,
                "Confirm Close",
                "Fetch tasks might still be in progress. Are you sure you want to close the window and attempt to cancel them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            else:
                # If closing while running, emit stop signal for *all* currently active tasks
                active_urls = [url for url, is_final in self.final_status_flag.items() if not is_final]
                if active_urls:
                     logger.info(f"Close requested while running. Emitting stop for active URLs: {active_urls}")
                     self.tasks_stop_requested.emit(active_urls)

        # Proceed with default close behavior
        super().closeEvent(event)
