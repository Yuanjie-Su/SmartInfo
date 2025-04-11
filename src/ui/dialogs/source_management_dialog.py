# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Optional, Tuple, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableView, QHeaderView,
    QDialogButtonBox, QMessageBox, QComboBox, QLineEdit, QFormLayout, QInputDialog
)
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem

from src.services.news_service import NewsService

logger = logging.getLogger(__name__)

class SourceManagementDialog(QDialog):
    """Dialog for managing news sources."""

    def __init__(self, news_service: NewsService, parent=None):
        super().__init__(parent)
        self._news_service = news_service
        self.available_categories = [] # Cache
        self.setWindowTitle("Manage News Sources")
        self.setMinimumSize(700, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)

        self._setup_ui()
        self._load_sources_and_categories()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        add_button = QPushButton("Add Source")
        add_button.clicked.connect(self._add_news_source)
        buttons_layout.addWidget(add_button)

        edit_button = QPushButton("Edit Selected")
        edit_button.clicked.connect(self._edit_selected_news_source)
        buttons_layout.addWidget(edit_button)

        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self._delete_selected_news_source)
        buttons_layout.addWidget(delete_button)

        buttons_layout.addStretch()

        # Setup table and model
        self.sources_table = QTableView()
        self.sources_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sources_table.setSortingEnabled(True)
        self.sources_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sources_table, 1)

        self._setup_sources_model()
        self.sources_table.doubleClicked.connect(self._edit_selected_news_source)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


    def _setup_sources_model(self):
        self.sources_model = QStandardItemModel(0, 3, self)
        self.sources_model.setHorizontalHeaderLabels(["Name", "URL", "Category"])
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)
        self.sources_table.setModel(self.sources_proxy_model)

    def _load_sources_and_categories(self):
        """Loads sources and category names."""
        self._load_news_sources()
        self._update_available_categories()

    def _load_news_sources(self):
        """Loads news sources from the service into the table."""
        logger.info("Loading news sources for dialog...")
        try:
            self.sources_model.removeRows(0, self.sources_model.rowCount())
            sources = self._news_service.get_all_sources()

            for source in sources:
                name_item = QStandardItem(source.get("name", "N/A"))
                url_item = QStandardItem(source.get("url", "N/A"))
                cat_name_item = QStandardItem(source.get("category_name", "N/A"))
                name_item.setData(source.get("id"), Qt.ItemDataRole.UserRole)
                cat_name_item.setData(source.get("category_id"), Qt.ItemDataRole.UserRole + 1) # Store cat ID

                self.sources_model.appendRow([name_item, url_item, cat_name_item])

            logger.info(f"Loaded {len(sources)} news sources into dialog table.")
        except Exception as e:
            logger.error(f"Failed to load news sources for dialog: {e}", exc_info=True)
            QMessageBox.warning(self, "Warning", f"Failed to load news sources: {str(e)}")

    def _update_available_categories(self):
        """Update the cached list of available categories."""
        try:
            categories = self._news_service.get_all_categories() # List[Tuple[int, str]]
            self.available_categories = sorted([cat[1] for cat in categories])
            logger.debug(f"Updated available categories list for dialog: {self.available_categories}")
        except Exception as e:
            logger.error(f"Failed to update available categories list for dialog: {e}", exc_info=True)

    def _add_news_source(self):
        self._show_source_edit_dialog()

    def _edit_selected_news_source(self, index=None):
        """Edit the selected news source"""
        if not isinstance(index, Qt.QModelIndex):
            selected_indexes = self.sources_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(self, "Select Source", "Please select a source to edit.")
                return
            index = selected_indexes[0]

        source_index = self.sources_proxy_model.mapToSource(index)
        row = source_index.row()

        source_id = self.sources_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.sources_model.item(row, 0).text()
        url = self.sources_model.item(row, 1).text()
        category_name = self.sources_model.item(row, 2).text()

        if source_id is None:
            QMessageBox.critical(self, "Error", "Could not get source ID.")
            return

        initial_data = {"id": source_id, "name": name, "url": url, "category_name": category_name}
        self._show_source_edit_dialog(initial_data)

    def _delete_selected_news_source(self):
        """Delete the selected news source"""
        selected_indexes = self.sources_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "Select Source", "Please select a source to delete.")
            return

        source_index = self.sources_proxy_model.mapToSource(selected_indexes[0])
        source_id = self.sources_model.item(source_index.row(), 0).data(Qt.ItemDataRole.UserRole)
        source_name = self.sources_model.item(source_index.row(), 0).text()

        if source_id is None:
            QMessageBox.critical(self, "Error", "Could not get source ID.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete", f"Delete source '{source_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._news_service.delete_source(source_id):
                    QMessageBox.information(self, "Success", "Source deleted.")
                    self._load_sources_and_categories() # Refresh
                    # TODO: Emit a signal if MainWindow needs immediate notification
                else:
                    QMessageBox.warning(self, "Failure", "Failed to delete source.")
            except Exception as e:
                logger.error(f"Error deleting source ID {source_id}: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Error deleting source: {str(e)}")

    def _show_source_edit_dialog(self, initial_data: Optional[Dict] = None):
        """Display dialog for adding or editing a news source"""
        is_edit = initial_data is not None
        dialog = QDialog(self) # Make it a child of the main dialog
        dialog.setWindowTitle("Edit Source" if is_edit else "Add Source")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        name_input = QLineEdit()
        url_input = QLineEdit()
        category_combo = QComboBox()
        category_combo.setEditable(True)
        category_combo.addItems(self.available_categories) # Use cached list

        if is_edit:
            name_input.setText(initial_data.get("name", ""))
            url_input.setText(initial_data.get("url", ""))
            cat_name = initial_data.get("category_name", "")
            index = category_combo.findText(cat_name)
            if index >= 0: category_combo.setCurrentIndex(index)
            else: category_combo.setCurrentText(cat_name)
        else:
            name_input.setPlaceholderText("e.g., Tech News Site")
            url_input.setPlaceholderText("https://...")
            category_combo.setCurrentIndex(-1)

        form_layout.addRow("Name (*):", name_input)
        form_layout.addRow("URL (*):", url_input)
        form_layout.addRow("Category (*):", category_combo)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        def on_accept():
            name = name_input.text().strip()
            url = url_input.text().strip()
            category_name = category_combo.currentText().strip()

            if not name or not url or not category_name:
                QMessageBox.warning(dialog, "Input Error", "Name, URL, and Category are required.")
                return
            if not url.startswith(("http://", "https://")):
                QMessageBox.warning(dialog, "Input Error", "URL must start with http:// or https://.")
                return

            try:
                success = False
                if is_edit:
                    source_id = initial_data["id"]
                    success = self._news_service.update_source(source_id, name, url, category_name)
                else:
                    new_id = self._news_service.add_source(name, url, category_name)
                    success = new_id is not None

                if success:
                    dialog.accept() # Close inner dialog
                    self._load_sources_and_categories() # Refresh table and category list in parent dialog
                    # TODO: Emit signal?
                else:
                    QMessageBox.warning(self, "Failure", f"Failed to save source '{name}'. URL might exist.")

            except Exception as e:
                logger.error(f"Error saving news source: {e}", exc_info=True)
                QMessageBox.critical(dialog, "Error", f"Error saving source: {str(e)}")

        button_box.accepted.connect(on_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()