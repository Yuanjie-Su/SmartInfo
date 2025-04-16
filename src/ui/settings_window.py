# -*- coding: utf-8 -*-
"""
Settings Window Module
Provides a separate window for application settings management.
"""

import logging
from typing import Dict, Any, Optional, List  # Added List

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
    QListWidgetItem,  # Added QListWidgetItem
    QInputDialog,
)
from PySide6.QtCore import Qt, Signal, QSize, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem

# Assuming services are passed during instantiation
from src.services.setting_service import SettingService
from src.services.news_service import NewsService
from src.config import (
    CONFIG_KEY_EMBEDDING_MODEL,
    CONFIG_KEY_FETCH_FREQUENCY,
    API_KEY_DEEPSEEK,
)


logger = logging.getLogger(__name__)


class SettingsWindow(QDialog):
    """
    A separate dialog window for managing all application settings.
    """

    # Signal emitted when settings that affect other tabs (like sources/categories) are changed
    settings_changed_signal = Signal()

    def __init__(
        self, setting_service: SettingService, news_service: NewsService, parent=None
    ):
        super().__init__(parent)
        self._setting_service = setting_service
        self._news_service = news_service
        self.available_categories = []  # Cache for category names used in dialogs

        self.setWindowTitle("设置")
        self.setMinimumSize(800, 600)
        self.setModal(True)  # Make it modal for now

        self._setup_ui()
        self._connect_signals()

        # Initial data load
        self._load_settings()  # Load general settings like API keys, models
        self._load_sources_and_categories()  # Load data for sources/categories tabs

        # Select the first item by default
        self.nav_list.setCurrentRow(0)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # No margins for the main layout
        main_layout.setSpacing(0)  # No spacing between nav and content

        # --- Left Navigation ---
        nav_widget = QWidget()
        nav_widget.setObjectName("SettingsNav")
        nav_widget.setFixedWidth(180)  # Adjust width as needed
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(5)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("SettingsNavList")
        # Add navigation items
        self.nav_list.addItem("API 设置")
        self.nav_list.addItem("资讯源管理")
        self.nav_list.addItem("分类配置")
        self.nav_list.addItem("系统配置")
        # Style the list widget if needed via QSS
        self.nav_list.setIconSize(QSize(16, 16))  # Example icon size

        nav_layout.addWidget(self.nav_list)
        nav_layout.addStretch()  # Pushes list items up

        # --- Right Content Area ---
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("SettingsContentStack")

        # Create pages for the stack
        api_page = self._create_api_tab()
        sources_page = self._create_sources_tab()
        categories_page = self._create_categories_tab()
        system_page = self._create_system_tab()

        self.content_stack.addWidget(api_page)
        self.content_stack.addWidget(sources_page)
        self.content_stack.addWidget(categories_page)
        self.content_stack.addWidget(system_page)

        # --- Bottom Buttons ---
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.save_button = QPushButton("保存设置")  # General save for relevant settings
        self.save_button.setToolTip("保存 API Key, 嵌入模型, 获取频率等设置")
        self.close_button = QPushButton("关闭")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.close_button)

        # Combine content stack and buttons
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(15, 15, 15, 15)  # Padding for content area
        content_layout.addWidget(self.content_stack)
        content_layout.addLayout(button_layout)

        # Add nav and content to main layout
        main_layout.addWidget(nav_widget)
        main_layout.addLayout(content_layout, 1)  # Content takes stretch factor 1

    def _connect_signals(self):
        self.nav_list.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.save_button.clicked.connect(self._save_and_accept)
        self.close_button.clicked.connect(self.reject)

    # --- Page Creation Methods (Migrated from SettingsTab) ---

    def _create_api_tab(self) -> QWidget:  # Return QWidget
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
        self.deepseek_api_key_status = QLabel("状态: 未知")  # Status label
        hbox_key = QHBoxLayout()
        hbox_key.addWidget(self.deepseek_api_key_input)
        hbox_key.addWidget(self.deepseek_api_key_status)
        form_layout.addRow("API Key (数据库):", hbox_key)

        test_deepseek_button = QPushButton("测试连接 (使用输入框中的Key)")
        test_deepseek_button.clicked.connect(self._test_api_connection)
        form_layout.addRow("", test_deepseek_button)

        layout.addStretch()
        return page

    def _create_sources_tab(self) -> QWidget:  # Return QWidget
        page = QWidget()
        layout = QVBoxLayout(page)
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        add_button = QPushButton("添加资讯源")
        add_button.clicked.connect(self._add_news_source)
        buttons_layout.addWidget(add_button)

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
        self.sources_table.doubleClicked.connect(self._edit_selected_news_source)

        return page

    def _create_categories_tab(self) -> QWidget:  # Return QWidget
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
        add_button.clicked.connect(self._add_category)
        buttons_layout.addWidget(add_button)

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
        self.categories_table.doubleClicked.connect(self._edit_selected_category)

        return page

    def _create_system_tab(self) -> QWidget:  # Return QWidget
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
        self.fetch_frequency_combo.setEnabled(False)  # Disable until implemented
        form_layout.addRow("自动获取频率:", self.fetch_frequency_combo)

        form_layout.addRow(QLabel("<b>数据存储设置</b>"))
        self.data_dir_input = QLineEdit()
        self.data_dir_input.setReadOnly(True)
        self.data_dir_input.setStyleSheet(
            "background-color: #f0f0f0;"
        )  # Indicate read-only
        # change_dir_button = QPushButton("修改路径")
        # change_dir_button.clicked.connect(self._change_data_dir) # Method needs migration
        # change_dir_button.setEnabled(False) # Disable until implemented
        hbox_dir = QHBoxLayout()
        hbox_dir.addWidget(self.data_dir_input)
        # hbox_dir.addWidget(change_dir_button)
        form_layout.addRow("数据存储路径:", hbox_dir)  # Button removed for now

        # backup_button = QPushButton("立即备份数据")
        # backup_button.clicked.connect(self._backup_data) # Method needs migration
        # backup_button.setEnabled(False) # Disable until implemented
        # form_layout.addRow("数据备份:", backup_button) # Button removed for now

        # Add Reset Button here?
        self.reset_button = QPushButton("重置系统配置到默认")
        self.reset_button.setToolTip("将嵌入模型, 获取频率等重置为默认值")
        self.reset_button.clicked.connect(
            self._reset_settings
        )  # Method needs migration
        form_layout.addRow("", self.reset_button)

        layout.addStretch()
        return page

    # --- Data Models Setup (Migrated) ---
    def _setup_sources_model(self):
        self.sources_model = QStandardItemModel(0, 3, self)
        self.sources_model.setHorizontalHeaderLabels(["名称", "URL", "分类"])
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)
        self.sources_table.setModel(self.sources_proxy_model)

    def _setup_categories_model(self):
        self.categories_model = QStandardItemModel(0, 2, self)
        self.categories_model.setHorizontalHeaderLabels(["分类名称", "资讯源数量"])
        self.categories_proxy_model = QSortFilterProxyModel(self)
        self.categories_proxy_model.setSourceModel(self.categories_model)
        self.categories_table.setModel(self.categories_proxy_model)

    # --- Logic Methods (Placeholder - Need Full Migration) ---
    # These methods need to be fully migrated from SettingsTab
    # Ensure they use self._setting_service and self._news_service correctly

    def _load_settings(self):
        logger.info("Loading settings into Settings Window UI...")

        # --- System Tab ---
        fetch_freq = self._setting_service.get_fetch_frequency()
        index = self.fetch_frequency_combo.findText(fetch_freq)
        if index >= 0:
            self.fetch_frequency_combo.setCurrentIndex(index)
        else:
            self.fetch_frequency_combo.setCurrentIndex(0)  # Default to manual

        self.data_dir_input.setText(self._setting_service.get_data_dir())
        logger.info("Settings loaded into Settings Window UI.")

    def _save_and_accept(self):
        """尝试保存设置，如果成功则接受对话框"""
        if self._save_settings():  # 调用现有的保存逻辑
            self.accept()  # 只有保存成功才关闭并返回 Accepted

    def _save_settings(self):
        logger.info("Saving settings from Settings Window...")
        save_successful = True
        try:
            # API Key (Save from API Tab)
            api_key = self.deepseek_api_key_input.text().strip()
            if api_key:
                logger.info("Saving DeepSeek API key from input field to database.")
                if not self._setting_service.save_api_key("deepseek", api_key):
                    save_successful = False
                    QMessageBox.warning(
                        self, "保存失败", "保存 DeepSeek API Key 到数据库失败。"
                    )
                else:
                    self._update_api_key_status()  # Update status after saving
            elif not self._setting_service._config.get(API_KEY_DEEPSEEK):
                if self._setting_service._api_key_repo.get_key("deepseek"):
                    logger.info(
                        "Clearing DeepSeek API key from database as input is empty and no env var."
                    )
                    if not self._setting_service.delete_api_key("deepseek"):
                        save_successful = False
                        QMessageBox.warning(
                            self, "保存失败", "从数据库删除 DeepSeek API Key 失败。"
                        )
                    else:
                        self._update_api_key_status()

            # Embedding Model (Save from API Tab)
            selected_embedding_model = self.embedding_model_combo.currentText()
            if not self._setting_service.save_embedding_model(selected_embedding_model):
                save_successful = False
                QMessageBox.warning(self, "保存失败", "保存嵌入模型设置失败。")

            # Fetch Frequency (Save from System Tab)
            # selected_freq = self.fetch_frequency_combo.currentText() # Currently disabled
            # if not self._setting_service.save_fetch_frequency(selected_freq):
            #     save_successful = False
            #     QMessageBox.warning(self, "保存失败", "保存获取频率设置失败。")

            if save_successful:
                QMessageBox.information(self, "成功", "设置已保存。")
                # Potentially emit signal if needed, e.g., if embedding model changed
                # self.settings_changed_signal.emit() # Decide if this is needed here
            else:
                logger.warning("One or more settings failed to save.")

        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"保存设置时发生错误: {str(e)}")
            save_successful = False

        return save_successful

    def _load_sources_and_categories(self):
        """Loads both sources and categories data using services."""
        self._load_news_sources()
        self._load_categories()
        self._update_available_categories()

    def _load_news_sources(self):
        """Loads news sources from the service into the sources table."""
        # (Migration of _load_news_sources from SettingsTab required here)
        logger.info("(SettingsWindow) Loading news sources...")
        try:
            self.sources_model.removeRows(0, self.sources_model.rowCount())
            sources = self._news_service.get_all_sources()  # List[Dict]

            for source in sources:
                name_item = QStandardItem(source.get("name", "N/A"))
                url_item = QStandardItem(source.get("url", "N/A"))
                cat_name_item = QStandardItem(source.get("category_name", "N/A"))

                name_item.setData(source.get("id"), Qt.ItemDataRole.UserRole)
                cat_name_item.setData(
                    source.get("category_id"), Qt.ItemDataRole.UserRole
                )

                for item in [name_item, url_item, cat_name_item]:
                    item.setEditable(False)

                self.sources_model.appendRow([name_item, url_item, cat_name_item])
            logger.info(f"(SettingsWindow) Loaded {len(sources)} news sources.")
        except Exception as e:
            logger.error(
                f"(SettingsWindow) Failed to load news sources: {e}", exc_info=True
            )
            QMessageBox.warning(self, "警告", f"加载资讯源失败: {str(e)}")

    def _load_categories(self):
        """Load categories from the service into the categories table"""
        # (Migration of _load_categories from SettingsTab required here)
        logger.info("(SettingsWindow) Loading categories...")
        try:
            self.categories_model.removeRows(0, self.categories_model.rowCount())
            categories_with_counts = (
                self._news_service.get_all_categories_with_counts()
            )  # List[Tuple[int, str, int]]

            for cat_id, cat_name, source_count in categories_with_counts:
                name_item = QStandardItem(cat_name)
                count_item = QStandardItem(str(source_count))
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                name_item.setData(cat_id, Qt.ItemDataRole.UserRole)
                name_item.setEditable(False)
                count_item.setEditable(False)

                self.categories_model.appendRow([name_item, count_item])
            logger.info(
                f"(SettingsWindow) Loaded {len(categories_with_counts)} categories."
            )
        except Exception as e:
            logger.error(
                f"(SettingsWindow) Failed to load categories: {e}", exc_info=True
            )
            QMessageBox.warning(self, "警告", f"加载分类列表失败: {str(e)}")

    def _update_available_categories(self):
        """Update the cached list of available categories for dropdowns"""
        # (Migration of _update_available_categories from SettingsTab required here)
        try:
            categories = (
                self._news_service.get_all_categories()
            )  # List[Tuple[int, str]]
            self.available_categories = sorted([cat[1] for cat in categories])
            logger.debug(
                f"(SettingsWindow) Updated available categories: {self.available_categories}"
            )
        except Exception as e:
            logger.error(
                f"(SettingsWindow) Failed to update available categories list: {e}",
                exc_info=True,
            )

    def _add_news_source(self):
        """Add a new news source"""
        # (Migration of _add_news_source/_show_source_edit_dialog from SettingsTab required here)
        self._show_source_edit_dialog()

    def _edit_selected_news_source(self, index=None):
        """Edit the selected news source"""
        # (Migration of _edit_selected_news_source/_show_source_edit_dialog from SettingsTab required here)
        if not isinstance(index, QModelIndex):  # Check if index is QModelIndex
            selected_indexes = self.sources_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(self, "提示", "请先选择要编辑的资讯源。")
                return
            index = selected_indexes[0]

        source_index = self.sources_proxy_model.mapToSource(index)
        row = source_index.row()

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
        # (Migration of _delete_selected_news_source from SettingsTab required here)
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
                    self._load_sources_and_categories()  # Refresh sources & categories
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
        # (Migration of _show_source_edit_dialog from SettingsTab required here)
        is_edit = initial_data is not None
        dialog = QDialog(self)  # Parent to SettingsWindow
        dialog.setWindowTitle("编辑资讯源" if is_edit else "添加资讯源")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        name_input = QLineEdit()
        url_input = QLineEdit()
        category_combo = QComboBox()
        category_combo.setEditable(True)
        category_combo.addItems(self.available_categories)  # Use cached list

        if is_edit:
            name_input.setText(initial_data.get("name", ""))
            url_input.setText(initial_data.get("url", ""))
            cat_name = initial_data.get("category_name", "")
            index = category_combo.findText(cat_name)
            if index >= 0:
                category_combo.setCurrentIndex(index)
            else:
                category_combo.setCurrentText(cat_name)
        else:
            name_input.setPlaceholderText("例如：科技日报")
            url_input.setPlaceholderText("必须以 http:// 或 https:// 开头")
            category_combo.setCurrentIndex(-1)

        form_layout.addRow("名称 (*):", name_input)
        form_layout.addRow("URL (*):", url_input)
        form_layout.addRow("分类 (*):", category_combo)

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
                    dialog.accept()
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

    def _add_category(self):
        """Add a new category"""
        # (Migration of _add_category from SettingsTab required here)
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
        elif ok:
            QMessageBox.warning(self, "输入错误", "分类名称不能为空。")

    def _edit_selected_category(self, index=None):
        """Edit the selected category"""
        # (Migration of _edit_selected_category from SettingsTab required here)
        if not isinstance(index, QModelIndex):  # Check if index is QModelIndex
            selected_indexes = self.categories_table.selectionModel().selectedRows()
            if not selected_indexes:
                QMessageBox.warning(self, "提示", "请先选择要编辑的分类。")
                return
            index = selected_indexes[0]

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
                return

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
        # (Migration of _delete_selected_category from SettingsTab required here)
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

        reply = QMessageBox.warning(  # Use warning icon
            self,
            "确认删除",
            f"确定要删除分类 '{category_name}' 吗？\\n\\n<font color='red'>警告：</font>这将同时删除该分类下的<b>所有资讯源</b>！此操作无法撤销。",
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

    def _reset_settings(self):
        """Reset system settings (embedding model, fetch frequency) to defaults."""
        # (Migration of _reset_settings from SettingsTab required here)
        logger.info("Resetting system settings to default...")
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要将嵌入模型和获取频率重置为默认值吗？\\n(API Key 不受影响)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._setting_service.reset_system_settings()  # Assumes service has this method
                # Reload settings into UI after reset
                self._load_settings()
                QMessageBox.information(self, "成功", "系统配置已重置为默认值。")
            except Exception as e:
                logger.error(f"Error resetting settings: {e}", exc_info=True)
                QMessageBox.critical(self, "错误", f"重置设置时出错: {str(e)}")

    def _test_api_connection(self):
        """Test DeepSeek API connection using the key in the input field."""
        # (Migration of _test_api_connection from SettingsTab required here)
        api_key = self.deepseek_api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(
                self, "API Key缺失", "请输入 DeepSeek API Key 进行测试。"
            )
            return

        # Find the button to disable/re-enable it
        button = self.sender()  # Get the button that triggered the signal
        original_text = ""
        if isinstance(button, QPushButton):
            original_text = button.text()
            button.setEnabled(False)
            button.setText("测试中...")
        else:
            button = None  # Not a button?

        # Use a separate thread or QTimer to avoid freezing UI? For simplicity, run directly for now
        # Be aware this might freeze the UI if the network call is slow
        self._execute_api_test(api_key, button, original_text)

    def _execute_api_test(self, api_key, button_widget, original_button_text):
        # (Migration of _execute_api_test from SettingsTab required here)
        try:
            # Assume SettingService has a method to test the key
            is_valid = self._setting_service.test_deepseek_api(api_key)
            if is_valid:
                QMessageBox.information(self, "连接成功", "DeepSeek API 连接测试成功！")
            else:
                QMessageBox.warning(
                    self,
                    "连接失败",
                    "DeepSeek API 连接测试失败，请检查 API Key 和网络连接。",
                )
        except Exception as e:
            logger.error(f"Error testing DeepSeek API connection: {e}", exc_info=True)
            QMessageBox.critical(self, "测试错误", f"测试 API 连接时发生错误: {str(e)}")
        finally:
            # Re-enable button
            if button_widget:
                button_widget.setEnabled(True)
                button_widget.setText(original_button_text)

    def _update_api_key_status(self):
        """Update the API key status label"""
        # (Migration of _update_api_key_status from SettingsTab required here)
        try:
            # Check environment first
            env_key = self._setting_service._config.get(
                API_KEY_DEEPSEEK
            )  # Access config via service
            if env_key:
                self.deepseek_api_key_status.setText(
                    "<font color='green'>已从环境变量加载</font>"
                )
                self.deepseek_api_key_input.setPlaceholderText(
                    "已从环境变量加载，此处输入可覆盖数据库"
                )
                self.deepseek_api_key_input.clear()
            else:
                # Check database via service
                db_key = self._setting_service._api_key_repo.get_key(
                    "deepseek"
                )  # Access repo via service
                if db_key:
                    self.deepseek_api_key_status.setText(
                        "<font color='blue'>已从数据库加载</font>"
                    )
                    self.deepseek_api_key_input.setPlaceholderText(
                        "输入新 Key 可覆盖数据库"
                    )
                    # self.deepseek_api_key_input.setText(db_key) # Optional: Populate field
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

    # --- Need to migrate these if functionality is kept ---
    # def _change_data_dir(self): pass
    # def _backup_data(self): pass
    # from PySide6.QtGui import QStandardItem # Add this import if needed
    # from PySide6.QtWidgets import QInputDialog # Add this import if needed
    # from PySide6.QtCore import QModelIndex # Add this import if needed


# Example Usage (if run standalone for testing)
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    # Mock services for testing
    class MockSettingService:
        _config = {}
        _api_key_repo = type("obj", (object,), {"get_key": lambda s, k: None})()

        def get_embedding_model(self):
            return "sentence-transformers/all-MiniLM-L6-v2"

        def get_fetch_frequency(self):
            return "manual"

        def get_data_dir(self):
            return "/mock/data/dir"

        def save_api_key(self, service, key):
            logger.info(f"Mock save API key {service}")
            return True

        def delete_api_key(self, service):
            logger.info(f"Mock delete API key {service}")
            return True

        def save_embedding_model(self, model):
            logger.info(f"Mock save embed model {model}")
            return True

        def reset_system_settings(self):
            logger.info("Mock reset system settings")

        def test_deepseek_api(self, key):
            logger.info(f"Mock test API key {key[:4]}...")
            return True

    class MockNewsService:
        def get_all_sources(self):
            return [
                {
                    "id": 1,
                    "name": "Source A",
                    "url": "http://a.com",
                    "category_id": 10,
                    "category_name": "Tech",
                }
            ]

        def get_all_categories_with_counts(self):
            return [(10, "Tech", 1), (20, "News", 0)]

        def get_all_categories(self):
            return [(10, "Tech"), (20, "News")]

        def add_source(self, n, u, c):
            logger.info(f"Mock add source {n}")
            return 2

        def update_source(self, i, n, u, c):
            logger.info(f"Mock update source {i}")
            return True

        def delete_source(self, i):
            logger.info(f"Mock delete source {i}")
            return True

        def add_category(self, n):
            logger.info(f"Mock add category {n}")
            return 30

        def update_category(self, i, n):
            logger.info(f"Mock update category {i}")
            return True

        def delete_category(self, i):
            logger.info(f"Mock delete category {i}")
            return True

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    settings_dialog = SettingsWindow(MockSettingService(), MockNewsService())
    settings_dialog.show()
    sys.exit(app.exec())
