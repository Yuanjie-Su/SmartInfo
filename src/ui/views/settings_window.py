# -*- coding: utf-8 -*-
"""
Settings Window Module (Refactored to use SettingsController)
Provides a separate window for application settings management.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QStackedWidget,
    QPushButton,
    QWidget,
    QLabel,
    QLineEdit,
    QTableView,
    QHeaderView,
    QFormLayout,
    QComboBox,
    QMessageBox,
    QDialogButtonBox,
    QListWidgetItem,
    QInputDialog,
)
from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon

from src.ui.controllers.settings_controller import SettingsController

logger = logging.getLogger(__name__)


class SettingsWindow(QDialog):
    """
    A separate dialog window for managing all application settings (View Component).
    """

    # This signal is now emitted by the controller. Keep reference if MainWindow needs it.
    # settings_changed_signal = Signal() # Now handled by controller's external_settings_changed

    def __init__(
        self, controller: SettingsController, parent=None
    ):  # Inject Controller
        super().__init__(parent)
        self.controller = controller
        self._available_categories: List[str] = (
            []
        )  # Cache for category names used in dialogs

        self.setWindowTitle("设置")
        self.setMinimumSize(900, 650)
        self.setModal(True)

        self._setup_ui()
        self._connect_signals()

        # Initial data load triggered via controller
        self.controller.load_all_settings()
        logger.info("SettingsWindow initialized and requested initial data load.")

        # Select the first item by default
        if self.nav_list.count() > 0:
            self.nav_list.setCurrentRow(0)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Navigation ---
        nav_widget = QWidget()
        nav_widget.setObjectName("SettingsNav")
        nav_widget.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(15, 20, 15, 20)
        nav_layout.setSpacing(10)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("SettingsNavList")
        nav_items = [
            {"name": "API 设置", "icon": "🔑"},
            {"name": "资讯源管理", "icon": "📰"},
            {"name": "分类配置", "icon": "🗂️"},
            {"name": "系统配置", "icon": "⚙️"},
        ]
        for item_data in nav_items:
            item = QListWidgetItem(f" {item_data['icon']}  {item_data['name']}")
            self.nav_list.addItem(item)
        nav_layout.addWidget(self.nav_list)
        nav_layout.addStretch()

        # --- Right Content Area ---
        content_widget = QWidget()
        content_widget.setObjectName("SettingsContentContainer")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(25, 25, 25, 25)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("SettingsContentStack")

        # Create pages for the stack
        api_page = self._create_api_page()
        sources_page = self._create_sources_page()
        categories_page = self._create_categories_page()
        system_page = self._create_system_page()

        self.content_stack.addWidget(api_page)
        self.content_stack.addWidget(sources_page)
        self.content_stack.addWidget(categories_page)
        self.content_stack.addWidget(system_page)
        content_layout.addWidget(self.content_stack)

        # --- Bottom Buttons ---
        # Use standard Apply and Close buttons for non-modal feel if desired later
        # Or OK/Cancel for modal dialog behavior
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Use Ok instead of Save for modal dialog convention
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("应用并关闭")
        self.cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText("取消")

        content_layout.addWidget(button_box, 0, Qt.AlignmentFlag.AlignRight)

        main_layout.addWidget(nav_widget)
        main_layout.addWidget(content_widget, 1)

    def _connect_signals(self):
        # Navigation
        self.nav_list.currentRowChanged.connect(self.content_stack.setCurrentIndex)

        # Dialog Buttons
        self.ok_button.clicked.connect(
            self._trigger_save_settings_and_accept
        )  # Save then accept
        self.cancel_button.clicked.connect(self.reject)  # Just close

        # Controller Signals -> View Slots
        self.controller.settings_loaded.connect(self._display_general_settings)
        self.controller.sources_loaded.connect(self._display_sources)
        self.controller.categories_loaded.connect(
            self._display_categories_and_update_cache
        )
        self.controller.api_test_result.connect(self._handle_api_test_result)
        self.controller.settings_saved.connect(self._handle_save_result)
        self.controller.source_operation_finished.connect(self._show_operation_message)
        self.controller.category_operation_finished.connect(
            self._show_operation_message
        )
        self.controller.error_occurred.connect(self._show_error_message)

    # --- Page Creation Methods ---
    def _create_api_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        form_layout.addRow(QLabel("<b>DeepSeek API 配置</b>"))
        self.deepseek_api_key_input = QLineEdit()
        self.deepseek_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_api_key_input.setPlaceholderText(
            "输入 API Key (优先使用环境变量)"
        )
        self.deepseek_api_key_status = QLabel("状态: 未知")
        hbox_key = QHBoxLayout()
        hbox_key.addWidget(self.deepseek_api_key_input)
        hbox_key.addWidget(self.deepseek_api_key_status)
        form_layout.addRow("API Key (数据库):", hbox_key)

        test_deepseek_button = QPushButton("测试连接 (使用输入框中的Key)")
        # Connect button click to internal trigger method
        test_deepseek_button.clicked.connect(lambda: self._trigger_test_api("deepseek"))
        self.test_deepseek_button = test_deepseek_button  # Keep reference if needed
        form_layout.addRow("", test_deepseek_button)

        # Add placeholders for other APIs if needed (e.g., VolcEngine)

        layout.addStretch()
        return page

    def _create_sources_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        add_button = QPushButton("添加资讯源")
        add_button.clicked.connect(self._trigger_add_source)  # Connect to trigger
        buttons_layout.addWidget(add_button)

        edit_button = QPushButton("编辑所选")
        edit_button.clicked.connect(self._trigger_edit_source)  # Connect to trigger
        buttons_layout.addWidget(edit_button)

        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._trigger_delete_source)  # Connect to trigger
        buttons_layout.addWidget(delete_button)
        buttons_layout.addStretch()

        self.sources_table = QTableView()
        self.sources_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sources_table.setSortingEnabled(True)
        layout.addWidget(self.sources_table, 1)

        self._setup_sources_model()  # Setup model structure
        self.sources_table.doubleClicked.connect(
            self._trigger_edit_source
        )  # Connect double-click

        return page

    def _create_categories_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("管理资讯分类:"))
        info_layout.addWidget(QLabel("<font color='grey'>(双击编辑)</font>"))
        info_layout.addStretch()
        layout.addLayout(info_layout)
        layout.addWidget(
            QLabel(
                "<font color='red'>注意：删除分类将同时删除该分类下的所有资讯源。</font>"
            )
        )

        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)
        add_button = QPushButton("添加分类")
        add_button.clicked.connect(self._trigger_add_category)  # Connect to trigger
        buttons_layout.addWidget(add_button)

        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(
            self._trigger_delete_category
        )  # Connect to trigger
        buttons_layout.addWidget(delete_button)
        buttons_layout.addStretch()

        self.categories_table = QTableView()
        self.categories_table.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows
        )
        self.categories_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.categories_table.verticalHeader().setVisible(False)
        self.categories_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.categories_table.setSortingEnabled(True)
        layout.addWidget(self.categories_table, 1)

        self._setup_categories_model()  # Setup model structure
        self.categories_table.doubleClicked.connect(
            self._trigger_edit_category
        )  # Connect double-click

        return page

    def _create_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        form_layout.addRow(QLabel("<b>资讯获取设置</b>"))
        self.fetch_frequency_combo = QComboBox()
        self.fetch_frequency_combo.addItems(["manual", "hourly", "daily", "weekly"])
        self.fetch_frequency_combo.setToolTip(
            "自动获取功能尚未实现，当前仅为设置占位符。"
        )
        self.fetch_frequency_combo.setEnabled(False)  # Keep disabled
        form_layout.addRow("自动获取频率:", self.fetch_frequency_combo)

        form_layout.addRow(QLabel("<b>数据存储设置</b>"))
        self.data_dir_input = QLineEdit()
        self.data_dir_input.setReadOnly(True)
        self.data_dir_input.setStyleSheet("background-color: #f0f0f0;")
        form_layout.addRow("数据存储路径:", self.data_dir_input)

        self.reset_button = QPushButton("重置系统配置到默认")
        self.reset_button.setToolTip("将获取频率等重置为默认值")
        # Connect button click to internal trigger method
        self.reset_button.clicked.connect(self._trigger_reset_settings)
        form_layout.addRow("", self.reset_button)

        layout.addStretch()
        return page

    # --- Data Models Setup ---
    def _setup_sources_model(self):
        """Sets up the model and proxy for the sources table."""
        self.sources_model = QStandardItemModel(0, 3, self)
        self.sources_model.setHorizontalHeaderLabels(["名称", "URL", "分类"])
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)
        self.sources_table.setModel(self.sources_proxy_model)
        self.sources_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)  # Sort by name

    def _setup_categories_model(self):
        """Sets up the model and proxy for the categories table."""
        self.categories_model = QStandardItemModel(0, 2, self)
        self.categories_model.setHorizontalHeaderLabels(["分类名称", "资讯源数量"])
        self.categories_proxy_model = QSortFilterProxyModel(self)
        self.categories_proxy_model.setSourceModel(self.categories_model)
        self.categories_table.setModel(self.categories_proxy_model)
        self.categories_table.sortByColumn(
            0, Qt.SortOrder.AscendingOrder
        )  # Sort by name

    # --- Internal Trigger Methods (Called by UI Signals) ---

    def _trigger_save_settings_and_accept(self):
        """Gathers settings from UI and asks controller to save."""
        logger.info("Ok button clicked, gathering and triggering settings save.")
        settings_to_save = {
            "api_keys": {},
            "system": {},
        }
        # API Keys
        deepseek_key = self.deepseek_api_key_input.text().strip()
        # Only include if user entered something or wants to clear DB entry
        if (
            deepseek_key
            or self.deepseek_api_key_status.text()
            == "<font color='blue'>已从数据库加载</font>"
        ):
            settings_to_save["api_keys"]["deepseek"] = deepseek_key

        # System Settings (currently disabled)
        # settings_to_save['system']['fetch_frequency'] = self.fetch_frequency_combo.currentText()

        self.controller.save_general_settings(settings_to_save)
        # Don't accept yet, wait for controller signal _handle_save_result

    def _trigger_test_api(self, api_name: str):
        """Gathers API key from input and asks controller to test."""
        api_key = ""
        button_to_disable = None
        original_text = ""

        if api_name.lower() == "deepseek":
            api_key = self.deepseek_api_key_input.text().strip()
            button_to_disable = self.test_deepseek_button
            original_text = button_to_disable.text()
        # Add elif for other APIs...

        if not api_key:
            QMessageBox.warning(
                self,
                f"{api_name} API Key Missing",
                f"Please enter the {api_name} API Key to test.",
            )
            return

        if button_to_disable:
            button_to_disable.setEnabled(False)
            button_to_disable.setText("Testing...")

        # Store button reference to re-enable it in the result handler
        self._current_test_button = button_to_disable
        self._current_test_button_text = original_text

        self.controller.test_api_connection(api_name, api_key)

    def _trigger_add_source(self):
        """Shows the dialog to add a new source."""
        self._show_source_edit_dialog()  # Call helper without initial data

    def _trigger_edit_source(self, index=None):
        """Shows the dialog to edit the selected source."""
        if not isinstance(index, QModelIndex):  # If not triggered by double-click
            selected_indexes = self.sources_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(
                    self, "Selection Needed", "Please select a news source to edit."
                )
                return
            index = selected_indexes[0]  # Use the first selected row

        if not index.isValid():
            return

        source_proxy_index = self.sources_proxy_model.mapToSource(index)
        row = source_proxy_index.row()

        # Extract data from the underlying QStandardItemModel
        source_id_item = self.sources_model.item(
            row, 0
        )  # Assume ID is in UserRole of Name item
        name_item = self.sources_model.item(row, 0)
        url_item = self.sources_model.item(row, 1)
        category_item = self.sources_model.item(row, 2)

        if not all([source_id_item, name_item, url_item, category_item]):
            QMessageBox.critical(
                self, "Error", "Could not retrieve data for the selected source."
            )
            return

        source_id = source_id_item.data(Qt.ItemDataRole.UserRole)
        name = name_item.text()
        url = url_item.text()
        category_name = category_item.text()

        if source_id is None:
            QMessageBox.critical(
                self, "Error", "Could not retrieve ID for the selected source."
            )
            return

        initial_data = {
            "id": source_id,
            "name": name,
            "url": url,
            "category_name": category_name,
        }
        self._show_source_edit_dialog(initial_data)  # Call helper with data

    def _trigger_delete_source(self):
        """Confirms and triggers deletion of the selected source."""
        selected_indexes = self.sources_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(
                self, "Selection Needed", "Please select a news source to delete."
            )
            return

        source_proxy_index = self.sources_proxy_model.mapToSource(selected_indexes[0])
        row = source_proxy_index.row()

        source_id_item = self.sources_model.item(row, 0)
        name_item = self.sources_model.item(row, 0)

        if not source_id_item or not name_item:
            QMessageBox.critical(
                self, "Error", "Could not retrieve data for the selected source."
            )
            return

        source_id = source_id_item.data(Qt.ItemDataRole.UserRole)
        source_name = name_item.text()

        if source_id is None:
            QMessageBox.critical(
                self, "Error", "Could not retrieve ID for the selected source."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the source '{source_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.delete_news_source(source_id, source_name)

    def _trigger_add_category(self):
        """Opens input dialog to add a new category."""
        category_name, ok = QInputDialog.getText(
            self, "Add Category", "Enter new category name:"
        )
        if ok and category_name:
            category_name = category_name.strip()
            if not category_name:
                QMessageBox.warning(
                    self, "Input Error", "Category name cannot be empty."
                )
                return
            self.controller.add_category(category_name)
        elif ok:
            QMessageBox.warning(self, "Input Error", "Category name cannot be empty.")

    def _trigger_edit_category(self, index=None):
        """Opens input dialog to edit the selected category."""
        if not isinstance(index, QModelIndex):
            selected_indexes = self.categories_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(
                    self, "Selection Needed", "Please select a category to edit."
                )
                return
            index = selected_indexes[0]

        if not index.isValid():
            return

        source_proxy_index = self.categories_proxy_model.mapToSource(index)
        row = source_proxy_index.row()

        id_item = self.categories_model.item(row, 0)  # Name item holds ID
        name_item = self.categories_model.item(row, 0)

        if not id_item or not name_item:
            QMessageBox.critical(
                self, "Error", "Could not retrieve data for the selected category."
            )
            return

        category_id = id_item.data(Qt.ItemDataRole.UserRole)
        old_name = name_item.text()

        if category_id is None:
            QMessageBox.critical(
                self, "Error", "Could not retrieve ID for the selected category."
            )
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Edit Category",
            "Enter new category name:",
            QLineEdit.EchoMode.Normal,
            old_name,
        )
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(
                    self, "Input Error", "Category name cannot be empty."
                )
                return
            if new_name != old_name:
                self.controller.update_category(category_id, new_name)
        elif ok:
            QMessageBox.warning(self, "Input Error", "Category name cannot be empty.")

    def _trigger_delete_category(self):
        """Confirms and triggers deletion of the selected category."""
        selected_indexes = self.categories_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(
                self, "Selection Needed", "Please select a category to delete."
            )
            return

        source_proxy_index = self.categories_proxy_model.mapToSource(
            selected_indexes[0]
        )
        row = source_proxy_index.row()

        id_item = self.categories_model.item(row, 0)
        name_item = self.categories_model.item(row, 0)

        if not id_item or not name_item:
            QMessageBox.critical(
                self, "Error", "Could not retrieve data for the selected category."
            )
            return

        category_id = id_item.data(Qt.ItemDataRole.UserRole)
        category_name = name_item.text()

        if category_id is None:
            QMessageBox.critical(
                self, "Error", "Could not retrieve ID for the selected category."
            )
            return

        reply = QMessageBox.warning(  # Use warning icon
            self,
            "Confirm Delete",
            f"Are you sure you want to delete category '{category_name}'?\n\n"
            f"<font color='red'>WARNING:</font> This will also delete all news sources within this category! This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.delete_category(category_id, category_name)

    def _trigger_reset_settings(self):
        """Confirms and triggers reset of system settings."""
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Reset fetch frequency to default?\n(API Keys and data path are not affected)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.reset_system_settings()

    # --- View Update Slots (Called by Controller Signals) ---

    @Slot(dict)
    def _display_general_settings(self, settings_data: Dict[str, Any]):
        """Populates the API and System tabs with loaded settings."""
        logger.debug("Displaying general settings in UI.")
        # API Keys
        api_settings = settings_data.get("api_keys", {})
        self.deepseek_api_key_status.setText(
            f"<font color='{self._get_status_color(api_settings.get('deepseek_status'))}'>{api_settings.get('deepseek_status', 'Unknown')}</font>"
        )
        # Update placeholder based on status
        if "环境变量" in api_settings.get("deepseek_status", ""):
            self.deepseek_api_key_input.setPlaceholderText(
                "已从环境变量加载，此处输入可覆盖数据库"
            )
            self.deepseek_api_key_input.clear()
        elif "数据库" in api_settings.get("deepseek_status", ""):
            self.deepseek_api_key_input.setPlaceholderText("输入新 Key 可覆盖数据库")
        else:
            self.deepseek_api_key_input.setPlaceholderText("请输入 DeepSeek API Key")

        # System Settings
        system_settings = settings_data.get("system", {})
        fetch_freq = system_settings.get("fetch_frequency", "manual")
        index = self.fetch_frequency_combo.findText(fetch_freq)
        self.fetch_frequency_combo.setCurrentIndex(index if index >= 0 else 0)
        self.data_dir_input.setText(system_settings.get("data_dir", "N/A"))

    @Slot(list)
    def _display_sources(self, sources: List[Dict[str, Any]]):
        """Populates the sources table."""
        logger.debug(f"Displaying {len(sources)} sources in table.")
        self.sources_model.removeRows(0, self.sources_model.rowCount())
        for source in sources:
            name_item = QStandardItem(source.get("name", "N/A"))
            url_item = QStandardItem(source.get("url", "N/A"))
            cat_name_item = QStandardItem(source.get("category_name", "N/A"))

            # Store ID in the UserRole of the name item for easy retrieval
            name_item.setData(source.get("id"), Qt.ItemDataRole.UserRole)
            # Store category ID as well if needed later
            # cat_name_item.setData(source.get("category_id"), Qt.ItemDataRole.UserRole + 1)

            for item in [name_item, url_item, cat_name_item]:
                item.setEditable(False)  # Items are not directly editable

            self.sources_model.appendRow([name_item, url_item, cat_name_item])
        # self.sources_table.resizeColumnsToContents() # Resize if needed

    @Slot(list)
    def _display_categories_and_update_cache(
        self, categories: List[Tuple[int, str, int]]
    ):
        """Populates the categories table and updates the internal cache."""
        logger.debug(f"Displaying {len(categories)} categories in table.")
        self.categories_model.removeRows(0, self.categories_model.rowCount())
        self._available_categories.clear()  # Clear cache before repopulating

        for cat_id, cat_name, source_count in categories:
            name_item = QStandardItem(cat_name)
            count_item = QStandardItem(str(source_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Store ID in UserRole
            name_item.setData(cat_id, Qt.ItemDataRole.UserRole)
            name_item.setEditable(False)
            count_item.setEditable(False)

            self.categories_model.appendRow([name_item, count_item])
            self._available_categories.append(cat_name)  # Update cache

        self._available_categories.sort()  # Keep the cache sorted
        # self.categories_table.resizeColumnsToContents()

    @Slot(str, bool, str)
    def _handle_api_test_result(self, api_name: str, success: bool, message: str):
        """Handles the result of an API connection test."""
        logger.info(
            f"API test result for {api_name}: Success={success}, Msg='{message}'"
        )
        # Re-enable the button
        if hasattr(self, "_current_test_button") and self._current_test_button:
            self._current_test_button.setEnabled(True)
            if hasattr(self, "_current_test_button_text"):
                self._current_test_button.setText(self._current_test_button_text)
            self._current_test_button = None  # Clear reference

        if success:
            QMessageBox.information(
                self, f"{api_name} Connection Test", f"Success: {message}"
            )
        else:
            QMessageBox.warning(
                self, f"{api_name} Connection Test", f"Failed: {message}"
            )

    @Slot(bool, str)
    def _handle_save_result(self, success: bool, message: str):
        """Handles the result of saving settings."""
        if success:
            # If save was successful AND triggered by Ok button, accept the dialog
            if (
                self.sender() == self.ok_button or self.ok_button.isDown()
            ):  # Check if Ok triggered it
                logger.info("Settings saved successfully, accepting dialog.")
                self.accept()
            else:
                QMessageBox.information(
                    self, "Save Successful", message
                )  # Show info if saved by other means
        else:
            QMessageBox.warning(self, "Save Failed", message)

    @Slot(bool, str)
    def _show_operation_message(self, success: bool, message: str):
        """Shows feedback message for source/category operations."""
        if success:
            QMessageBox.information(self, "Operation Successful", message)
        else:
            QMessageBox.warning(self, "Operation Failed", message)

    @Slot(str, str)
    def _show_error_message(self, title: str, message: str):
        """Displays an error message box."""
        logger.warning(f"Displaying error: Title='{title}', Message='{message}'")
        QMessageBox.critical(self, title, message)

    # --- Helpers ---
    def _get_status_color(self, status_text: Optional[str]) -> str:
        """Helper to determine color for status labels."""
        if not status_text:
            return "red"
        if "环境变量" in status_text:
            return "green"
        if "数据库" in status_text:
            return "blue"
        if "未配置" in status_text:
            return "red"
        return "grey"  # Default for unknown

    def _show_source_edit_dialog(self, initial_data: Optional[Dict] = None):
        """Displays dialog for adding or editing a news source."""
        is_edit = initial_data is not None
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit News Source" if is_edit else "Add News Source")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        name_input = QLineEdit()
        url_input = QLineEdit()
        category_combo = QComboBox()
        category_combo.setEditable(True)
        # Use the cached list of category names
        category_combo.addItems(self._available_categories)

        if is_edit:
            name_input.setText(initial_data.get("name", ""))
            url_input.setText(initial_data.get("url", ""))
            cat_name = initial_data.get("category_name", "")
            index = category_combo.findText(cat_name)
            if index >= 0:
                category_combo.setCurrentIndex(index)
            else:
                category_combo.setCurrentText(
                    cat_name
                )  # Allow adding new category via edit
        else:
            name_input.setPlaceholderText("e.g., TechCrunch")
            url_input.setPlaceholderText("Must start with http:// or https://")
            category_combo.setCurrentIndex(-1)  # No default selection

        form_layout.addRow("Name (*):", name_input)
        form_layout.addRow("URL (*):", url_input)
        form_layout.addRow("Category (*):", category_combo)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        def on_accept():
            name = name_input.text().strip()
            url = url_input.text().strip()
            category_name = (
                category_combo.currentText().strip()
            )  # Get current text (might be new)

            if not name or not url or not category_name:
                QMessageBox.warning(
                    dialog, "Input Error", "Name, URL, and Category cannot be empty."
                )
                return
            if not url.startswith(("http://", "https://")):
                QMessageBox.warning(
                    dialog, "Input Error", "URL must start with http:// or https://."
                )
                return

            # Call the appropriate controller method
            if is_edit:
                source_id = initial_data["id"]
                self.controller.update_news_source(source_id, name, url, category_name)
            else:
                self.controller.add_news_source(name, url, category_name)

            dialog.accept()  # Close the dialog, feedback given via controller signal

        button_box.accepted.connect(on_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()  # Show the modal dialog
