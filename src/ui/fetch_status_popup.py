# src/ui/fetch_status_popup.py
# -*- coding: utf-8 -*-

import logging
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QApplication, QAbstractItemView,
    QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QMetaObject, Q_ARG

logger = logging.getLogger(__name__)

class FetchStatusPopup(QDialog):
    """
    A dialog to display the fetching status for each URL.
    """
    _URL_COL = 0
    _STATUS_COL = 1
    _DETAILS_COL = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fetch News Status")
        self.setMinimumSize(800, 400) # Adjust size as needed

        # Standard window flags
        current_flags = self.windowFlags()
        new_flags = current_flags | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowSystemMenuHint
        self.setWindowFlags(new_flags)

        self._layout = QVBoxLayout(self)

        # --- Table Widget ---
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["URL", "Status", "Details"])
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.status_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.status_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Read-only
        self.status_table.verticalHeader().setVisible(False)

        # Set column widths (adjust as needed)
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(self._URL_COL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._STATUS_COL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self._DETAILS_COL, QHeaderView.ResizeMode.ResizeToContents)
        # Allow last column to stretch more if needed
        # header.setStretchLastSection(True)

        self._layout.addWidget(self.status_table, 1) # Table takes most space

        # Use a dictionary to map URL to its row index for quick updates
        self._url_row_map: Dict[str, int] = {}

        # --- Close Button ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject) # Connect Close button to hide
        self._layout.addWidget(self.button_box)

    def initialize_urls(self, urls: List[str]):
        """Populate the table with URLs and set initial status."""
        self.clear_display()
        self.status_table.setRowCount(len(urls))
        self._url_row_map = {} # Reset map

        for row, url in enumerate(urls):
            url_item = QTableWidgetItem(url)
            status_item = QTableWidgetItem("Pending")
            details_item = QTableWidgetItem("")

            self.status_table.setItem(row, self._URL_COL, url_item)
            self.status_table.setItem(row, self._STATUS_COL, status_item)
            self.status_table.setItem(row, self._DETAILS_COL, details_item)

            self._url_row_map[url] = row # Store URL to row mapping

        self.status_table.resizeColumnsToContents() # Adjust columns initially

    @Slot(str, str, str)
    def update_url_status(self, url: str, status: str, details: str = ""):
        """Updates the status and details for a specific URL in the table."""
        # Ensure this runs on the GUI thread
        if QApplication.instance().thread() != self.thread():
            QMetaObject.invokeMethod(self, "update_url_status", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(str, url), Q_ARG(str, status), Q_ARG(str, details))
            return

        if url in self._url_row_map:
            row = self._url_row_map[url]
            status_item = self.status_table.item(row, self._STATUS_COL)
            details_item = self.status_table.item(row, self._DETAILS_COL)

            if status_item:
                status_item.setText(status)
            else: # Should not happen if initialized correctly
                self.status_table.setItem(row, self._STATUS_COL, QTableWidgetItem(status))

            if details_item:
                details_item.setText(details)
            else: # Should not happen
                 self.status_table.setItem(row, self._DETAILS_COL, QTableWidgetItem(details))

            # Optional: Change row color based on status (e.g., red for error)
            if "error" in status.lower():
                for col in range(self.status_table.columnCount()):
                    item = self.status_table.item(row, col)
                    if item: item.setBackground(Qt.GlobalColor.red) # Light red
            elif "complete" in status.lower():
                 for col in range(self.status_table.columnCount()):
                    item = self.status_table.item(row, col)
                    if item: item.setBackground(Qt.GlobalColor.green) # Light green

            # self.status_table.resizeColumnsToContents() # Resizing frequently can be slow

        else:
            logger.warning(f"Attempted to update status for unknown URL: {url}")

    def clear_display(self):
        """Clears the table and resets the state."""
        self.status_table.setRowCount(0)
        self._url_row_map = {}
        self.setWindowTitle("Fetch News Status") # Reset title

    def set_final_status(self, status: str, is_error: bool = False):
        """Sets the overall final status, reflected in the window title."""
        log_level = logging.ERROR if is_error else logging.INFO
        logger.log(log_level, f"Fetch Status Popup Final Status: {status}")
        if is_error:
            self.setWindowTitle(f"Fetch Error - {status}")
        else:
            self.setWindowTitle(f"Fetch Complete - {status}")

    # --- Methods for Hiding ---
    def reject(self):
        logger.debug("Fetch status popup reject triggered, hiding instead.")
        self.hide()

    def closeEvent(self, event):
        logger.debug("Fetch status popup closeEvent triggered, hiding instead.")
        self.hide()
        event.ignore()