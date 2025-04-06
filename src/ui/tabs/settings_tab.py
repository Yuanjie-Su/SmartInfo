#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
System Settings Tab (Refactored)
Implements API configuration, news source management and other system settings (using Service Layer)
"""

import logging
import os
from typing import List, Dict, Optional, Tuple, Any  # Added for type hints

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QLabel,
    QLineEdit,
    QTableView,
    QHeaderView,
    QFormLayout,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QInputDialog,
    QDialog,
    QDialogButtonBox,  # Added for dialogs
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, QTimer, Signal  # Added Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor  # Added QColor

from src.services.setting_service import SettingService
from src.services.news_service import NewsService

from src.config import (
    CONFIG_KEY_EMBEDDING_MODEL,
    CONFIG_KEY_FETCH_FREQUENCY,
    API_KEY_DEEPSEEK,
)

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """System Settings Tab (Refactored)"""

    # Signal emitted when settings that affect other tabs (like sources/categories) are changed
    settings_changed_signal = Signal()

    def __init__(
        self, setting_service: SettingService, news_service: NewsService
    ):  # Inject services
        super().__init__()
        self._setting_service = setting_service
        self._news_service = news_service
        self.available_categories = []  # Cache for category names used in dialogs
        self._setup_ui()
        self._load_settings()  # Load settings from service
        self._load_sources_and_categories()  # Load data for tables/combos

    def _setup_ui(self):
        """Set up user interface"""
        main_layout = QVBoxLayout(self)
        settings_tabs = QTabWidget()
        main_layout.addWidget(settings_tabs)

        # Create tabs
        api_tab = self._create_api_tab()
        sources_tab = self._create_sources_tab()
        categories_tab = self._create_categories_tab()
        system_tab = self._create_system_tab()

        settings_tabs.addTab(api_tab, "API 设置")
        settings_tabs.addTab(sources_tab, "资讯源管理")
        settings_tabs.addTab(categories_tab, "分类配置")
        settings_tabs.addTab(system_tab, "系统配置")

        # Bottom actions
        actions_layout = QHBoxLayout()
        main_layout.addLayout(actions_layout)

        self.save_button = QPushButton("保存所有设置")
        self.save_button.setToolTip("保存 API Key, 嵌入模型, 获取频率等设置")
        self.save_button.clicked.connect(self._save_settings)
        actions_layout.addWidget(self.save_button)

        self.reset_button = QPushButton("重置系统配置")
        self.reset_button.setToolTip("将嵌入模型, 获取频率等重置为默认值")
        self.reset_button.clicked.connect(self._reset_settings)
        actions_layout.addWidget(self.reset_button)

        actions_layout.addStretch()

    # --- API Settings Tab ---
    def _create_api_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        form_layout.addRow(QLabel("<b>DeepSeek API 配置</b>"))
        self.deepseek_api_key_input = QLineEdit()
        self.deepseek_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_api_key_input.setPlaceholderText(
            "输入 API Key (优先使用环境变量)"
        )
        self.deepseek_api_key_status = QLabel("状态: 未知")  # Status label
        hbox_key = QHBoxLayout()
        hbox_key.addWidget(self.deepseek_api_key_input)
        hbox_key.addWidget(self.deepseek_api_key_status)
        form_layout.addRow("API Key (数据库):", hbox_key)

        test_deepseek_button = QPushButton("测试连接 (使用输入框中的Key)")
        test_deepseek_button.clicked.connect(self._test_api_connection)
        form_layout.addRow("", test_deepseek_button)

        layout.addSpacing(20)
        form_layout.addRow(QLabel("<b>嵌入模型配置</b>"))
        self.embedding_model_combo = QComboBox()
        # TODO: Make this list dynamic or configurable?
        self.embedding_model_combo.addItems(
            [
                "sentence-transformers/all-MiniLM-L6-v2",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "BAAI/bge-large-zh-v1.5",  # Example Chinese model
                "moka-ai/m3e-base",  # Example smaller multilingual
            ]
        )
        form_layout.addRow("嵌入模型:", self.embedding_model_combo)

        layout.addStretch()
        return tab

    # --- Sources Management Tab ---
    def _create_sources_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        add_button = QPushButton("添加资讯源")
        add_button.clicked.connect(self._add_news_source)
        buttons_layout.addWidget(add_button)

        # Add Edit Button
        edit_button = QPushButton("编辑所选")
        edit_button.clicked.connect(self._edit_selected_news_source)
        buttons_layout.addWidget(edit_button)

        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._delete_selected_news_source)
        buttons_layout.addWidget(delete_button)

        buttons_layout.addStretch()

        # Setup table and model
        self.sources_table = QTableView()
        self.sources_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sources_table.setSortingEnabled(True)
        layout.addWidget(self.sources_table, 1)

        self._setup_sources_model()
        # Connect double-click to edit
        self.sources_table.doubleClicked.connect(self._edit_selected_news_source)

        return tab

    def _setup_sources_model(self):
        self.sources_model = QStandardItemModel(0, 3, self)
        self.sources_model.setHorizontalHeaderLabels(["名称", "URL", "分类"])
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)
        self.sources_table.setModel(self.sources_proxy_model)

    def _load_sources_and_categories(self):
        """Loads both sources and categories data using services."""
        self._load_news_sources()
        self._load_categories()
        self._update_available_categories()  # Update cache for dialogs

    def _load_news_sources(self):
        """Loads news sources from the service into the sources table."""
        logger.info("Loading news sources...")
        try:
            self.sources_model.removeRows(0, self.sources_model.rowCount())
            # Fetch List[Dict] from service
            sources = self._news_service.get_all_sources()

            for source in sources:
                name_item = QStandardItem(source.get("name", "N/A"))
                url_item = QStandardItem(source.get("url", "N/A"))
                cat_name_item = QStandardItem(source.get("category_name", "N/A"))

                # Store ID in the first column's item data
                name_item.setData(source.get("id"), Qt.ItemDataRole.UserRole)
                # Store Category ID in the third column's item data
                cat_name_item.setData(
                    source.get("category_id"), Qt.ItemDataRole.UserRole
                )

                # Make items non-editable
                for item in [name_item, url_item, cat_name_item]:
                    item.setEditable(False)

                self.sources_model.appendRow([name_item, url_item, cat_name_item])

            logger.info(f"Loaded {len(sources)} news sources into table.")
        except Exception as e:
            logger.error(f"Failed to load news sources: {e}", exc_info=True)
            QMessageBox.warning(self, "警告", f"加载资讯源失败: {str(e)}")

    def _add_news_source(self):
        """Add a new news source"""
        self._show_source_edit_dialog()  # Use common dialog method

    def _edit_selected_news_source(self, index=None):
        """Edit the selected news source"""
        if not isinstance(
            index, Qt.QModelIndex
        ):  # Check if called by button or double-click
            selected_indexes = self.sources_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(self, "提示", "请先选择要编辑的资讯源。")
                return
            index = selected_indexes[0]  # Use first selected row

        # Map proxy index to source model index
        source_index = self.sources_proxy_model.mapToSource(index)
        row = source_index.row()

        # Get data from the model
        source_id = self.sources_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.sources_model.item(row, 0).text()
        url = self.sources_model.item(row, 1).text()
        category_name = self.sources_model.item(row, 2).text()

        if source_id is None:
            QMessageBox.critical(self, "错误", "无法获取所选资讯源的ID。")
            return

        initial_data = {
            "id": source_id,
            "name": name,
            "url": url,
            "category_name": category_name,
        }
        self._show_source_edit_dialog(initial_data)

    def _delete_selected_news_source(self):
        """Delete the selected news source"""
        selected_indexes = self.sources_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "警告", "请先选择要删除的资讯源。")
            return

        source_index = self.sources_proxy_model.mapToSource(selected_indexes[0])
        source_id = self.sources_model.item(source_index.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        source_name = self.sources_model.item(source_index.row(), 0).text()

        if source_id is None:
            QMessageBox.critical(self, "错误", "无法获取所选资讯源的ID。")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除资讯源 '{source_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._news_service.delete_source(source_id):
                    logger.info(f"Deleted news source ID {source_id}")
                    QMessageBox.information(self, "成功", "资讯源已删除。")
                    self._load_news_sources()  # Refresh sources table
                    self._load_categories()  # Refresh categories table (counts change)
                    self.settings_changed_signal.emit()  # Notify main window
                else:
                    QMessageBox.warning(self, "失败", "删除资讯源失败，请查看日志。")
            except Exception as e:
                logger.error(
                    f"Error deleting news source ID {source_id}: {e}", exc_info=True
                )
                QMessageBox.critical(self, "错误", f"删除资讯源时出错: {str(e)}")

    def _show_source_edit_dialog(self, initial_data: Optional[Dict] = None):
        """Display dialog for adding or editing a news source"""
        is_edit = initial_data is not None
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑资讯源" if is_edit else "添加资讯源")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        name_input = QLineEdit()
        url_input = QLineEdit()
        category_combo = QComboBox()
        category_combo.setEditable(True)  # Allow adding new categories
        category_combo.addItems(self.available_categories)  # Use cached list

        if is_edit:
            name_input.setText(initial_data.get("name", ""))
            url_input.setText(initial_data.get("url", ""))
            # Set combo box to current category
            cat_name = initial_data.get("category_name", "")
            index = category_combo.findText(cat_name)
            if index >= 0:
                category_combo.setCurrentIndex(index)
            else:
                category_combo.setCurrentText(cat_name)  # Add if not exists
        else:
            name_input.setPlaceholderText("例如：科技日报")
            url_input.setPlaceholderText("必须以 http:// 或 https:// 开头")
            category_combo.setCurrentIndex(-1)  # No initial selection

        form_layout.addRow("名称 (*):", name_input)
        form_layout.addRow("URL (*):", url_input)
        form_layout.addRow("分类 (*):", category_combo)

        # Add standard buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        def on_accept():
            name = name_input.text().strip()
            url = url_input.text().strip()
            category_name = category_combo.currentText().strip()

            if not name or not url or not category_name:
                QMessageBox.warning(dialog, "输入错误", "名称、URL 和分类不能为空。")
                return
            if not url.startswith(("http://", "https://")):
                QMessageBox.warning(
                    dialog,
                    "输入错误",
                    "URL 格式无效，必须以 http:// 或 https:// 开头。",
                )
                return

            try:
                success = False
                if is_edit:
                    source_id = initial_data["id"]
                    success = self._news_service.update_source(
                        source_id, name, url, category_name
                    )
                else:
                    new_id = self._news_service.add_source(name, url, category_name)
                    success = new_id is not None

                if success:
                    dialog.accept()  # Close dialog first
                    QMessageBox.information(
                        self,
                        "成功",
                        f"资讯源 '{name}' 已{'更新' if is_edit else '添加'}。",
                    )
                    self._load_sources_and_categories()  # Refresh tables and category list
                    self.settings_changed_signal.emit()  # Notify main window
                else:
                    QMessageBox.warning(
                        self,
                        "失败",
                        f"保存资讯源 '{name}' 失败，URL 可能已存在或发生错误。",
                    )

            except Exception as e:
                logger.error(f"Error saving news source: {e}", exc_info=True)
                QMessageBox.critical(self, "错误", f"保存资讯源时出错: {str(e)}")

        button_box.accepted.connect(on_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()

    # --- Categories Tab ---
    def _create_categories_tab(self):
        """Create the categories management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
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
        add_button.clicked.connect(self._add_category)
        buttons_layout.addWidget(add_button)
        # Edit button is redundant due to double-click
        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._delete_selected_category)
        buttons_layout.addWidget(delete_button)
        buttons_layout.addStretch()

        # Setup table and model
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

        self._setup_categories_model()
        # Connect double-click to edit
        self.categories_table.doubleClicked.connect(self._edit_selected_category)

        return tab

    def _setup_categories_model(self):
        """Set up the categories table model"""
        self.categories_model = QStandardItemModel(0, 2, self)
        self.categories_model.setHorizontalHeaderLabels(["分类名称", "资讯源数量"])
        self.categories_proxy_model = QSortFilterProxyModel(self)
        self.categories_proxy_model.setSourceModel(self.categories_model)
        self.categories_table.setModel(self.categories_proxy_model)

    def _load_categories(self):
        """Load categories from the service into the categories table"""
        logger.info("Loading categories...")
        try:
            self.categories_model.removeRows(0, self.categories_model.rowCount())
            # Fetch List[Tuple[int, str, int]] from service
            categories_with_counts = self._news_service.get_all_categories_with_counts()

            for cat_id, cat_name, source_count in categories_with_counts:
                name_item = QStandardItem(cat_name)
                count_item = QStandardItem(str(source_count))
                count_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )  # Center count

                # Store ID in the first column's item data
                name_item.setData(cat_id, Qt.ItemDataRole.UserRole)

                # Make items non-editable directly in the table
                name_item.setEditable(False)
                count_item.setEditable(False)

                self.categories_model.appendRow([name_item, count_item])

            logger.info(f"Loaded {len(categories_with_counts)} categories into table.")
        except Exception as e:
            logger.error(f"Failed to load categories: {e}", exc_info=True)
            QMessageBox.warning(self, "警告", f"加载分类列表失败: {str(e)}")

    def _add_category(self):
        """Add a new category"""
        category_name, ok = QInputDialog.getText(
            self, "添加分类", "请输入新的分类名称:"
        )
        if ok and category_name:
            category_name = category_name.strip()
            if not category_name:
                QMessageBox.warning(self, "输入错误", "分类名称不能为空。")
                return
            try:
                new_id = self._news_service.add_category(category_name)
                if new_id is not None:
                    QMessageBox.information(
                        self, "成功", f"分类 '{category_name}' 已添加。"
                    )
                    self._load_sources_and_categories()  # Refresh both tables and available list
                    self.settings_changed_signal.emit()  # Notify main window
                else:
                    QMessageBox.warning(
                        self, "失败", f"添加分类 '{category_name}' 失败，可能已存在。"
                    )
            except Exception as e:
                logger.error(
                    f"Error adding category '{category_name}': {e}", exc_info=True
                )
                QMessageBox.critical(self, "错误", f"添加分类时出错: {str(e)}")
        elif ok:  # User pressed OK but entered nothing
            QMessageBox.warning(self, "输入错误", "分类名称不能为空。")

    def _edit_selected_category(self, index=None):
        """Edit the selected category"""
        if not isinstance(
            index, Qt.QModelIndex
        ):  # Check if called by button or double-click
            selected_indexes = self.categories_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(self, "提示", "请先选择要编辑的分类。")
                return
            index = selected_indexes[0]  # Use first selected row

        source_index = self.categories_proxy_model.mapToSource(index)
        category_id = self.categories_model.item(source_index.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        old_name = self.categories_model.item(source_index.row(), 0).text()

        if category_id is None:
            QMessageBox.critical(self, "错误", "无法获取所选分类的ID。")
            return

        new_name, ok = QInputDialog.getText(
            self, "编辑分类", "请输入新的分类名称:", QLineEdit.EchoMode.Normal, old_name
        )

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "输入错误", "分类名称不能为空。")
                return
            if new_name == old_name:
                return  # No change

            try:
                if self._news_service.update_category(category_id, new_name):
                    QMessageBox.information(
                        self, "成功", f"分类已从 '{old_name}' 更新为 '{new_name}'。"
                    )
                    self._load_sources_and_categories()  # Refresh tables and list
                    self.settings_changed_signal.emit()  # Notify main window
                else:
                    QMessageBox.warning(
                        self, "失败", f"更新分类失败，新名称 '{new_name}' 可能已存在。"
                    )
            except Exception as e:
                logger.error(
                    f"Error updating category ID {category_id}: {e}", exc_info=True
                )
                QMessageBox.critical(self, "错误", f"更新分类时出错: {str(e)}")
        elif ok:
            QMessageBox.warning(self, "输入错误", "分类名称不能为空。")

    def _delete_selected_category(self):
        """Delete the selected category"""
        selected_indexes = self.categories_table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.warning(self, "警告", "请先选择要删除的分类。")
            return

        source_index = self.categories_proxy_model.mapToSource(selected_indexes[0])
        category_id = self.categories_model.item(source_index.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        category_name = self.categories_model.item(source_index.row(), 0).text()

        if category_id is None:
            QMessageBox.critical(self, "错误", "无法获取所选分类的ID。")
            return

        reply = QMessageBox.warning(  # Use warning icon for destructive action
            self,
            "确认删除",
            f"确定要删除分类 '{category_name}' 吗？\n\n<font color='red'>警告：</font>这将同时删除该分类下的<b>所有资讯源</b>！此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._news_service.delete_category(category_id):
                    logger.info(f"Deleted category ID {category_id} and its sources.")
                    QMessageBox.information(
                        self, "成功", f"分类 '{category_name}' 及其资讯源已删除。"
                    )
                    self._load_sources_and_categories()  # Refresh tables and list
                    self.settings_changed_signal.emit()  # Notify main window
                else:
                    QMessageBox.warning(self, "失败", "删除分类失败，请查看日志。")
            except Exception as e:
                logger.error(
                    f"Error deleting category ID {category_id}: {e}", exc_info=True
                )
                QMessageBox.critical(self, "错误", f"删除分类时出错: {str(e)}")

    def _update_available_categories(self):
        """Update the cached list of available categories for dropdowns"""
        try:
            categories = (
                self._news_service.get_all_categories()
            )  # List[Tuple[int, str]]
            self.available_categories = sorted([cat[1] for cat in categories])
            logger.debug(
                f"Updated available categories list: {self.available_categories}"
            )
        except Exception as e:
            logger.error(
                f"Failed to update available categories list: {e}", exc_info=True
            )
            # Keep the old list?

    # --- System Settings Tab ---
    def _create_system_tab(self):
        """Create the system settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        form_layout.addRow(QLabel("<b>资讯获取设置</b>"))
        self.fetch_frequency_combo = QComboBox()
        self.fetch_frequency_combo.addItems(["manual", "hourly", "daily", "weekly"])
        self.fetch_frequency_combo.setToolTip(
            "自动获取功能尚未实现，当前仅为设置占位符。"
        )
        self.fetch_frequency_combo.setEnabled(False)  # Disable until implemented
        form_layout.addRow("自动获取频率:", self.fetch_frequency_combo)

        form_layout.addRow(QLabel("<b>数据存储设置</b>"))
        self.data_dir_input = QLineEdit()
        self.data_dir_input.setReadOnly(True)
        self.data_dir_input.setStyleSheet(
            "background-color: #f0f0f0;"
        )  # Indicate read-only
        change_dir_button = QPushButton("修改路径")
        change_dir_button.clicked.connect(self._change_data_dir)
        change_dir_button.setEnabled(False)  # Disable until implemented
        hbox_dir = QHBoxLayout()
        hbox_dir.addWidget(self.data_dir_input)
        hbox_dir.addWidget(change_dir_button)
        form_layout.addRow("数据存储路径:", hbox_dir)

        # Backup button (placeholder)
        backup_button = QPushButton("立即备份数据")
        backup_button.clicked.connect(self._backup_data)
        backup_button.setEnabled(False)  # Disable until implemented
        form_layout.addRow("数据备份:", backup_button)

        layout.addStretch()
        return tab

    def _load_settings(self):
        """Load settings from the service"""
        logger.info("Loading settings into UI...")
        try:
            # API Key (show placeholder/status, don't store key directly in UI variable)
            self._update_api_key_status()

            # Embedding Model
            emb_model = self._setting_service.get_embedding_model()
            index = self.embedding_model_combo.findText(emb_model)
            if index >= 0:
                self.embedding_model_combo.setCurrentIndex(index)
            else:
                logger.warning(
                    f"Saved embedding model '{emb_model}' not found in dropdown. Adding it."
                )
                self.embedding_model_combo.addItem(emb_model)
                self.embedding_model_combo.setCurrentText(emb_model)

            # Fetch Frequency
            fetch_freq = self._setting_service.get_fetch_frequency()
            index = self.fetch_frequency_combo.findText(fetch_freq)
            if index >= 0:
                self.fetch_frequency_combo.setCurrentIndex(index)
            else:
                self.fetch_frequency_combo.setCurrentIndex(0)  # Default to manual

            # Data Directory
            self.data_dir_input.setText(self._setting_service.get_data_dir())

            logger.info("Settings loaded into UI.")

        except Exception as e:
            logger.error(f"Failed to load settings into UI: {e}", exc_info=True)
            QMessageBox.warning(self, "加载错误", f"加载设置失败: {str(e)}")

    def _update_api_key_status(self):
        """Update the API key status label"""
        try:
            # Check environment first via config
            env_key = self._setting_service._config.get(API_KEY_DEEPSEEK)
            if env_key:
                self.deepseek_api_key_status.setText(
                    "<font color='green'>已从环境变量加载</font>"
                )
                self.deepseek_api_key_input.setPlaceholderText(
                    "已从环境变量加载，此处输入可覆盖数据库"
                )
                self.deepseek_api_key_input.clear()  # Don't show DB key if env key exists
            else:
                # Check database via service
                db_key = self._setting_service._api_key_repo.get_key(
                    "deepseek"
                )  # Directly check repo here
                if db_key:
                    self.deepseek_api_key_status.setText(
                        "<font color='blue'>已从数据库加载</font>"
                    )
                    self.deepseek_api_key_input.setPlaceholderText(
                        "输入新 Key 可覆盖数据库"
                    )
                    # Optionally populate the field if you want users to see/edit the DB key
                    # self.deepseek_api_key_input.setText(db_key) # Be careful with showing keys
                else:
                    self.deepseek_api_key_status.setText(
                        "<font color='red'>未配置</font>"
                    )
                    self.deepseek_api_key_input.setPlaceholderText(
                        "请输入 DeepSeek API Key"
                    )
        except Exception as e:
            logger.error(f"Error updating API key status: {e}", exc_info=True)
            self.deepseek_api_key_status.setText(
                "<font color='orange'>状态检查错误</font>"
            )

    def _save_settings(self):
        """Save all settings"""
        logger.info("Saving settings...")
        save_successful = True
        try:
            # Save API Key (only if input is not empty, saves to DB)
            api_key = self.deepseek_api_key_input.text().strip()
            if api_key:
                logger.info("Saving DeepSeek API key from input field to database.")
                if not self._setting_service.save_api_key("deepseek", api_key):
                    save_successful = False
                    QMessageBox.warning(
                        self, "保存失败", "保存 DeepSeek API Key 到数据库失败。"
                    )
                else:
                    # Clear the input field after successful save to DB? Optional.
                    # self.deepseek_api_key_input.clear()
                    self._update_api_key_status()  # Update status after saving
            elif not self._setting_service._config.get(API_KEY_DEEPSEEK):
                # If no env key exists and user cleared the input, attempt to delete DB key
                if self._setting_service._api_key_repo.get_key("deepseek"):
                    logger.info(
                        "API key input cleared and no env key found, deleting key from database."
                    )
                    if not self._setting_service.delete_api_key_from_db("deepseek"):
                        logger.warning(
                            "Failed to delete DeepSeek API key from database."
                        )
                        # Don't necessarily fail the whole save for this
                    else:
                        self._update_api_key_status()

            # Save Embedding Model
            embedding_model = self.embedding_model_combo.currentText()
            if not self._setting_service.save_embedding_model(embedding_model):
                save_successful = False
                QMessageBox.warning(self, "保存失败", "保存嵌入模型设置失败。")

            # Save Fetch Frequency
            fetch_freq = self.fetch_frequency_combo.currentText()
            if not self._setting_service.save_fetch_frequency(fetch_freq):
                save_successful = False
                QMessageBox.warning(self, "保存失败", "保存获取频率设置失败。")

            # Data Dir is read-only for now, no need to save

            if save_successful:
                QMessageBox.information(self, "成功", "设置已保存。")
                self.settings_changed_signal.emit()  # Signal potentially embedding model change etc.
            else:
                QMessageBox.warning(
                    self, "部分失败", "部分设置未能成功保存，请检查日志。"
                )

        except Exception as e:
            logger.error(f"Failed to save settings: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"保存设置时发生错误: {str(e)}")

    def _reset_settings(self):
        """Reset settings to defaults"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置系统配置 (嵌入模型, 获取频率等) 为默认值吗？\nAPI密钥和资讯源不会被重置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self._setting_service.reset_settings_to_defaults():
                    QMessageBox.information(self, "成功", "系统配置已重置为默认值。")
                    self._load_settings()  # Reload settings into UI
                    self.settings_changed_signal.emit()
                else:
                    QMessageBox.warning(self, "失败", "重置系统配置失败。")
            except Exception as e:
                logger.error(f"Error resetting system settings: {e}", exc_info=True)
                QMessageBox.critical(self, "错误", f"重置设置时发生错误: {str(e)}")

    def _test_api_connection(self):
        """Test the API connection using the provided key"""
        api_key_to_test = self.deepseek_api_key_input.text().strip()
        if not api_key_to_test:
            # If input is empty, maybe test the loaded key (env or db)?
            api_key_to_test = self._setting_service.get_api_key("deepseek")
            if not api_key_to_test:
                QMessageBox.warning(
                    self, "警告", "请输入或配置 DeepSeek API Key 以进行测试。"
                )
                return
            else:
                logger.info("Testing loaded DeepSeek API Key (Env/DB).")
        else:
            logger.info("Testing DeepSeek API Key from input field.")

        # Show status indicator (reuse the existing status label logic if desired)
        test_button = self.sender()  # Get the button that triggered the signal
        if test_button:
            original_text = test_button.text()
            test_button.setEnabled(False)
            test_button.setText("测试中...")

        # Use QTimer to make the test call non-blocking for the UI thread
        QTimer.singleShot(
            100,
            lambda: self._execute_api_test(api_key_to_test, test_button, original_text),
        )

    def _execute_api_test(self, api_key, button_widget, original_button_text):
        """Execute the API connection test"""
        result = None
        try:
            result = self._setting_service.test_deepseek_connection(api_key)
        except Exception as e:
            logger.error(
                f"Error calling test_deepseek_connection service: {e}", exc_info=True
            )
            result = {"success": False, "error": f"测试调用失败: {str(e)}"}
        finally:
            # Restore button state
            if button_widget:
                button_widget.setEnabled(True)
                button_widget.setText(original_button_text)

            # Show result message box
            if result and result.get("success"):
                latency = result.get("latency", "N/A")
                message = f"DeepSeek API 连接测试成功！\n延迟: {latency} 秒"
                QMessageBox.information(self, "连接成功", message)
            else:
                error_msg = (
                    result.get("error", "未知错误") if result else "测试未返回结果"
                )
                QMessageBox.critical(
                    self, "连接失败", f"DeepSeek API 连接测试失败:\n{error_msg}"
                )

    def _change_data_dir(self):
        """Change the data directory"""
        # TODO: Implement data directory changing logic
        # - Show file dialog to select new directory
        # - Validate the directory
        # - **Crucially:** Need a way to migrate the existing DB and Chroma data
        #   or warn the user that they need to move it manually.
        # - Update config using setting_service.save_setting(CONFIG_KEY_DATA_DIR, new_path)
        # - May require application restart.
        QMessageBox.information(self, "提示", "修改数据路径功能正在开发中。")

    def _backup_data(self):
        """Backup application data"""
        # TODO: Implement data backup logic
        # - Identify DB file path (config.db_path)
        # - Identify ChromaDB path (config.chroma_db_path)
        # - Allow user to select backup destination
        # - Copy files/directories (handle potential locking issues?)
        # - Consider compressing the backup.
        QMessageBox.information(self, "提示", "数据备份功能正在开发中。")
