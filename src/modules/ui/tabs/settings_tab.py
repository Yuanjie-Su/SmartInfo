#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
系统设置选项卡
实现API配置、资讯源管理等系统设置功能
"""

from email.mime import application
import logging
import os
import json
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
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem

# 导入API客户端
from src.utils.api_client import api_client
from src.utils.api_manager import api_manager

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """系统设置选项卡"""

    def __init__(self):
        super().__init__()
        self.edit_dialog = None  # 添加对话框引用变量
        self.available_categories = []  # 添加分类列表变量
        self._setup_ui()
        self._load_settings()  # 加载已保存的设置
        self._update_source_category_combobox()  # 初始化分类下拉列表

    def _setup_ui(self):
        """设置用户界面"""
        # 创建主布局
        main_layout = QVBoxLayout(self)

        # 创建设置选项卡控件
        settings_tabs = QTabWidget()
        main_layout.addWidget(settings_tabs)

        # 创建API设置选项卡
        api_tab = self._create_api_tab()
        settings_tabs.addTab(api_tab, "API设置")

        # 创建资讯源管理选项卡
        sources_tab = self._create_sources_tab()
        settings_tabs.addTab(sources_tab, "资讯源管理")

        # 创建分类配置选项卡
        categories_tab = self._create_categories_tab()
        settings_tabs.addTab(categories_tab, "分类配置")

        # 创建系统配置选项卡
        system_tab = self._create_system_tab()
        settings_tabs.addTab(system_tab, "系统配置")

        # 底部操作按钮
        actions_layout = QHBoxLayout()
        main_layout.addLayout(actions_layout)

        # 添加保存按钮
        self.save_button = QPushButton("保存所有设置")
        self.save_button.clicked.connect(self._save_settings)
        actions_layout.addWidget(self.save_button)

        # 添加重置按钮
        self.reset_button = QPushButton("重置为默认")
        self.reset_button.clicked.connect(self._reset_settings)
        actions_layout.addWidget(self.reset_button)

        # 添加右侧弹性空间
        actions_layout.addStretch()

    def _create_api_tab(self):
        """创建API设置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建表单布局
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # DeepSeek API 设置
        form_layout.addRow(QLabel("<b>DeepSeek API 配置</b>"))
        self.deepseek_api_key = QLineEdit()
        self.deepseek_api_key.setEchoMode(QLineEdit.Password)
        self.deepseek_api_key.setPlaceholderText("请输入 DeepSeek API Key")
        form_layout.addRow("API Key:", self.deepseek_api_key)

        # 测试按钮
        test_deepseek_button = QPushButton("测试连接")
        test_deepseek_button.clicked.connect(
            lambda: self._test_api_connection("deepseek")
        )
        form_layout.addRow("", test_deepseek_button)

        # 添加分隔空间
        layout.addSpacing(20)

        # 嵌入模型设置
        form_layout.addRow(QLabel("<b>嵌入模型配置</b>"))

        self.embedding_model = QComboBox()
        self.embedding_model.addItems(
            [
                "sentence-transformers/all-MiniLM-L6-v2",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "本地模型 (较小体积)",
            ]
        )
        form_layout.addRow("嵌入模型:", self.embedding_model)

        # 添加弹性空间
        layout.addStretch()

        return tab

    def _create_sources_tab(self):
        """创建资讯源管理选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 顶部操作按钮
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        # 添加新资讯源按钮
        add_button = QPushButton("添加资讯源")
        add_button.clicked.connect(self._add_news_source)
        buttons_layout.addWidget(add_button)

        # 删除资讯源按钮
        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._delete_news_source)
        buttons_layout.addWidget(delete_button)

        # 添加右侧弹性空间
        buttons_layout.addStretch()

        # 创建资讯源表格
        self.sources_table = QTableView()
        self.sources_table.setSelectionBehavior(QTableView.SelectRows)
        self.sources_table.setSelectionMode(QTableView.SingleSelection)
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.sources_table, 1)

        # 创建表格模型
        self._create_sources_model()

        return tab

    def _create_sources_model(self):
        """创建资讯源表格模型"""
        # 创建模型
        self.sources_model = QStandardItemModel(0, 3, self)
        self.sources_model.setHorizontalHeaderLabels(["名称", "URL", "分类"])

        # 创建代理模型用于过滤和排序
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)

        # 设置表格使用代理模型
        self.sources_table.setModel(self.sources_proxy_model)

        # 加载资讯源数据
        self._load_news_sources()

    def _load_news_sources(self):
        """从数据库加载资讯源数据"""
        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 清空现有数据
            self.sources_model.removeRows(0, self.sources_model.rowCount())

            # 连接数据库
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 查询所有资讯源
            cursor.execute("SELECT id, name, url, category FROM news_sources")
            sources = cursor.fetchall()

            # 添加到表格
            for source_id, name, url, category in sources:
                self.sources_model.appendRow(
                    [QStandardItem(name), QStandardItem(url), QStandardItem(category)]
                )
                # 存储ID作为用户数据
                self.sources_model.item(self.sources_model.rowCount() - 1, 0).setData(
                    source_id, Qt.UserRole
                )

            conn.close()

            logger.info(f"已加载 {len(sources)} 个资讯源")
        except Exception as e:
            logger.error(f"加载资讯源失败: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "警告", f"加载资讯源失败: {str(e)}")

    def _add_news_source(self):
        """添加新的资讯源"""
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QFormLayout,
            QDialogButtonBox,
        )

        # 确保分类列表已更新
        self._update_source_category_combobox()

        # 创建对话框
        dialog = QDialog(self)
        self.edit_dialog = dialog  # 保存对话框引用以便能在保存后关闭
        dialog.setWindowTitle("添加资讯源")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 创建表单
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # 添加输入字段
        name_input = QLineEdit()
        name_input.setPlaceholderText("请输入资讯源名称")
        form_layout.addRow("名称:", name_input)

        url_input = QLineEdit()
        url_input.setPlaceholderText("请输入资讯源URL")
        form_layout.addRow("URL:", url_input)

        category_input = QComboBox()
        category_input.setEditable(True)
        if hasattr(self, "available_categories") and self.available_categories:
            category_input.addItems(self.available_categories)
        else:
            # 如果没有可用分类，添加默认分类
            default_categories = [
                "学术动态",
                "前沿技术",
                "市场应用",
                "产业动态",
                "政策法规",
                "行业资讯",
                "研究报告",
                "技术创新",
            ]
            category_input.addItems(default_categories)
        form_layout.addRow("分类:", category_input)

        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            name = name_input.text().strip()
            url = url_input.text().strip()
            category = category_input.currentText().strip()

            # 验证输入
            if not name or not url or not category:
                QMessageBox.warning(self, "警告", "请填写所有字段")
                return

            # 验证URL格式
            if not url.startswith(("http://", "https://")):
                QMessageBox.warning(self, "警告", "URL必须以http://或https://开头")
                return

            # 添加到数据库
            self._save_news_source(None, name, url, category)

    def _edit_news_source(self, index):
        """编辑资讯源"""
        # 获取选中行的数据
        row = self.sources_proxy_model.mapToSource(index).row()
        source_id = self.sources_model.item(row, 0).data(Qt.UserRole)
        name = self.sources_model.item(row, 0).text()
        url = self.sources_model.item(row, 1).text()
        category = self.sources_model.item(row, 2).text()

        # 确保分类列表已更新
        self._update_source_category_combobox()

        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QFormLayout,
            QDialogButtonBox,
        )

        # 创建对话框
        dialog = QDialog(self)
        self.edit_dialog = dialog  # 保存对话框引用以便能在保存后关闭
        dialog.setWindowTitle("编辑资讯源")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 创建表单
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # 添加输入字段
        name_input = QLineEdit()
        name_input.setText(name)
        form_layout.addRow("名称:", name_input)

        url_input = QLineEdit()
        url_input.setText(url)
        form_layout.addRow("URL:", url_input)

        category_input = QComboBox()
        category_input.setEditable(True)
        if hasattr(self, "available_categories") and self.available_categories:
            category_input.addItems(self.available_categories)
        else:
            # 如果没有可用分类，添加默认分类
            default_categories = [
                "学术动态",
                "AI工具应用",
                "前沿技术",
                "市场应用",
                "技术",
            ]
            category_input.addItems(default_categories)
        # 设置当前分类
        index = category_input.findText(category)
        if index >= 0:
            category_input.setCurrentIndex(index)
        else:
            category_input.setCurrentText(category)
            form_layout.addRow("分类:", category_input)

        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            new_name = name_input.text().strip()
            new_url = url_input.text().strip()
            new_category = category_input.currentText().strip()

            # 验证输入
            if not new_name or not new_url or not new_category:
                QMessageBox.warning(self, "警告", "请填写所有字段")
                return

            # 验证URL格式
            if not new_url.startswith(("http://", "https://")):
                QMessageBox.warning(self, "警告", "URL必须以http://或https://开头")
                return

            # 更新数据库
            self._save_news_source(source_id, new_name, new_url, new_category)

    def _save_news_source(self, source_id, name, url, category):
        """保存资讯源"""
        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 连接数据库
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            if source_id:
                cursor.execute(
                    "UPDATE news_sources SET name = ?, url = ?, category = ? WHERE id = ?",
                    (name, url, category, source_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO news_sources (name, url, category) VALUES (?, ?, ?)",
                    (name, url, category),
                )

            # 提交事务
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"保存资讯源失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"保存资讯源失败: {str(e)}")

    def _delete_news_source(self):
        """删除所选资讯源"""
        # 获取选中的行
        indexes = self.sources_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.warning(self, "警告", "请先选择要删除的资讯源")
            return

        # 确认删除
        if (
            QMessageBox.question(
                self,
                "确认删除",
                "确定要删除所选资讯源吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 获取选中行的ID
            row = self.sources_proxy_model.mapToSource(indexes[0]).row()
            source_id = self.sources_model.item(row, 0).data(Qt.UserRole)

            # 连接数据库
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 删除资讯源
            cursor.execute("DELETE FROM news_sources WHERE id = ?", (source_id,))

            # 提交事务
            conn.commit()
            conn.close()

            # 重新加载资讯源数据
            self._load_news_sources()

            QMessageBox.information(self, "成功", "资讯源已删除")
        except Exception as e:
            logger.error(f"删除资讯源失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"删除资讯源失败: {str(e)}")

    def _test_source_parser(self):
        """测试所选资讯源的解析器"""
        # 获取选中的行
        indexes = self.sources_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.warning(self, "警告", "请先选择要测试的资讯源")
            return

        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 获取选中行的ID
            row = self.sources_proxy_model.mapToSource(indexes[0]).row()
            source_id = self.sources_model.item(row, 0).data(Qt.UserRole)

            # 连接数据库
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 查询资讯源
            cursor.execute(
                "SELECT name, url, parser_code FROM news_sources WHERE id = ?",
                (source_id,),
            )
            source = cursor.fetchone()

            if not source:
                QMessageBox.warning(self, "警告", "未找到所选资讯源")
                return

            name, url, parser_code = source

            if not parser_code:
                QMessageBox.warning(
                    self,
                    "警告",
                    f"资讯源 {name} 尚未生成解析代码，请先编辑资讯源更新URL",
                )
                return

            # 显示进度对话框
            progress_dialog = QMessageBox(self)
            progress_dialog.setWindowTitle("请稍候")
            progress_dialog.setText(f"正在测试资讯源 {name} 的解析器...")
            progress_dialog.setStandardButtons(QMessageBox.NoButton)
            progress_dialog.show()
            QApplication.processEvents()

            # 实际测试解析器
            try:
                from src.utils.url_analyzer import url_analyzer

                # 获取URL内容
                success, content = url_analyzer.fetch_url_content(url)
                if not success:
                    QMessageBox.warning(self, "警告", f"获取URL内容失败: {content}")
                    return

                # 临时文件
                import tempfile
                import os

                # 创建临时文件
                with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
                    f.write(parser_code.encode("utf-8"))
                    temp_file = f.name

                try:
                    # 动态导入
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(
                        "parser_module", temp_file
                    )
                    parser_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(parser_module)

                    # 调用解析函数
                    results = parser_module.parse_website(content)

                    # 关闭进度对话框
                    progress_dialog.close()

                    # 显示结果
                    if not results:
                        QMessageBox.warning(self, "测试结果", f"解析器未找到任何内容")
                        return

                    # 显示前5个结果
                    result_text = (
                        f"解析成功! 找到 {len(results)} 条资讯\n\n前5条资讯:\n\n"
                    )
                    for i, item in enumerate(results[:5], 1):
                        result_text += f"{i}. {item.get('title', '无标题')}\n"
                        result_text += f"   链接: {item.get('url', '无链接')}\n"
                        result_text += (
                            f"   日期: {item.get('publish_date', '无日期')}\n\n"
                        )

                    QMessageBox.information(self, "测试结果", result_text)
                finally:
                    # 删除临时文件
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            except Exception as e:
                logger.error(f"测试解析器失败: {str(e)}", exc_info=True)
                QMessageBox.critical(self, "错误", f"测试解析器失败: {str(e)}")
        except Exception as e:
            logger.error(f"测试资讯源解析器失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"测试资讯源解析器失败: {str(e)}")
        finally:
            # 确保进度对话框关闭
            if "progress_dialog" in locals():
                progress_dialog.close()

    def _create_categories_tab(self):
        """创建分类配置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 添加说明标签
        layout.addWidget(QLabel("管理资讯分类，您可以添加、编辑或删除分类："))
        layout.addWidget(
            QLabel(
                "<font color='red'>注意：删除分类将同时删除该分类下的所有资讯源</font>"
            )
        )

        # 顶部操作按钮
        buttons_layout = QHBoxLayout()
        layout.addLayout(buttons_layout)

        # 添加新分类按钮
        add_button = QPushButton("添加分类")
        add_button.clicked.connect(self._add_category)
        buttons_layout.addWidget(add_button)

        # 编辑分类按钮
        edit_button = QPushButton("编辑所选")
        edit_button.clicked.connect(self._edit_category)
        buttons_layout.addWidget(edit_button)

        # 删除分类按钮
        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._delete_category)
        buttons_layout.addWidget(delete_button)

        # 添加右侧弹性空间
        buttons_layout.addStretch()

        # 创建分类表格
        self.categories_table = QTableView()
        self.categories_table.setSelectionBehavior(QTableView.SelectRows)
        self.categories_table.setSelectionMode(QTableView.SingleSelection)
        self.categories_table.verticalHeader().setVisible(False)
        self.categories_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        layout.addWidget(self.categories_table, 1)

        # 创建表格模型
        self._create_categories_model()

        return tab

    def _create_categories_model(self):
        """创建分类表格模型"""
        # 创建模型
        self.categories_model = QStandardItemModel(0, 2, self)
        self.categories_model.setHorizontalHeaderLabels(["分类名称", "资讯源数量"])

        # 创建代理模型用于过滤和排序
        self.categories_proxy_model = QSortFilterProxyModel(self)
        self.categories_proxy_model.setSourceModel(self.categories_model)

        # 设置表格使用代理模型
        self.categories_table.setModel(self.categories_proxy_model)

        # 连接双击信号以编辑分类
        self.categories_table.doubleClicked.connect(self._edit_category)

        # 加载分类数据
        self._load_categories()

    def _load_categories(self):
        """从数据库加载分类数据"""
        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 清空现有数据
            self.categories_model.removeRows(0, self.categories_model.rowCount())

            # 连接数据库
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 查询所有分类及其对应的资讯源数量
            cursor.execute(
                """
                SELECT category, COUNT(id) 
                FROM news_sources 
                GROUP BY category 
                ORDER BY category
                """
            )
            categories = cursor.fetchall()

            # 添加到表格
            for category, source_count in categories:
                self.categories_model.appendRow(
                    [
                        QStandardItem(category),
                        QStandardItem(str(source_count)),
                    ]
                )

            conn.close()

            logger.info(f"已加载 {len(categories)} 个分类")
        except Exception as e:
            logger.error(f"加载分类失败: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "警告", f"加载分类失败: {str(e)}")

    def _add_category(self):
        """添加新的分类"""
        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QFormLayout,
            QDialogButtonBox,
        )

        # 创建对话框
        dialog = QDialog(self)
        self.edit_dialog = dialog  # 保存对话框引用以便能在保存后关闭
        dialog.setWindowTitle("添加分类")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout(dialog)

        # 创建表单
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # 添加输入字段
        category_input = QLineEdit()
        category_input.setPlaceholderText("请输入分类名称")
        form_layout.addRow("分类名称:", category_input)

        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            category = category_input.text().strip()

            # 验证输入
            if not category:
                QMessageBox.warning(self, "警告", "分类名称不能为空")
                return

            # 检查分类是否已存在
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            try:
                conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
                cursor = conn.cursor()

                # 查询分类是否存在
                cursor.execute(
                    "SELECT COUNT(*) FROM news_sources WHERE category = ?", (category,)
                )
                count = cursor.fetchone()[0]

                if count > 0:
                    QMessageBox.warning(self, "警告", f"分类 '{category}' 已存在")
                    return

                # 这里我们不直接插入分类，而是在用户添加资讯源时自动创建
                # 但可以添加一个空的资讯源作为占位符
                cursor.execute(
                    """
                    INSERT INTO news_sources (name, url, category, type)
                    VALUES ('分类占位符', 'https://example.com', ?, 'rss')
                    """,
                    (category,),
                )

                conn.commit()
                conn.close()

                # 重新加载分类数据
                self._load_categories()

                # 重新加载资讯源分类下拉列表
                self._update_source_category_combobox()

                QMessageBox.information(self, "成功", f"已添加分类 '{category}'")
            except Exception as e:
                logger.error(f"添加分类失败: {str(e)}", exc_info=True)
                QMessageBox.critical(self, "错误", f"添加分类失败: {str(e)}")

    def _edit_category(self, index=None):
        """编辑分类"""
        # 获取选中行
        if not index:
            indexes = self.categories_table.selectionModel().selectedRows()
            if not indexes:
                QMessageBox.warning(self, "警告", "请先选择要编辑的分类")
                return
            index = indexes[0]

        # 获取分类名称
        row = self.categories_proxy_model.mapToSource(index).row()
        old_category = self.categories_model.item(row, 0).text()

        from PySide6.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QFormLayout,
            QDialogButtonBox,
        )

        # 创建对话框
        dialog = QDialog(self)
        self.edit_dialog = dialog  # 保存对话框引用以便能在保存后关闭
        dialog.setWindowTitle("编辑分类")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout(dialog)

        # 创建表单
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # 添加输入字段
        category_input = QLineEdit()
        category_input.setText(old_category)
        form_layout.addRow("分类名称:", category_input)

        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            new_category = category_input.text().strip()

            # 验证输入
            if not new_category:
                QMessageBox.warning(self, "警告", "分类名称不能为空")
                return

            # 如果没有变化则不更新
            if new_category == old_category:
                return

            # 更新数据库中的分类
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            try:
                conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
                cursor = conn.cursor()

                # 检查新分类名是否已存在
                if new_category != old_category:
                    cursor.execute(
                        "SELECT COUNT(*) FROM news_sources WHERE category = ?",
                        (new_category,),
                    )
                    count = cursor.fetchone()[0]
                    if count > 0:
                        QMessageBox.warning(
                            self, "警告", f"分类 '{new_category}' 已存在"
                        )
                        return

                # 更新资讯源表中的分类
                cursor.execute(
                    "UPDATE news_sources SET category = ? WHERE category = ?",
                    (new_category, old_category),
                )

                conn.commit()
                conn.close()

                # 重新加载分类数据
                self._load_categories()

                # 重新加载资讯源列表
                self._load_news_sources()

                # 更新资讯源分类下拉列表
                self._update_source_category_combobox()

                QMessageBox.information(
                    self, "成功", f"已将分类 '{old_category}' 更新为 '{new_category}'"
                )
            except Exception as e:
                logger.error(f"编辑分类失败: {str(e)}", exc_info=True)
                QMessageBox.critical(self, "错误", f"编辑分类失败: {str(e)}")

    def _delete_category(self):
        """删除分类"""
        # 获取选中行
        indexes = self.categories_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.warning(self, "警告", "请先选择要删除的分类")
            return

        # 获取分类名称
        row = self.categories_proxy_model.mapToSource(indexes[0]).row()
        category = self.categories_model.item(row, 0).text()
        source_count = int(self.categories_model.item(row, 1).text())

        # 确认删除
        message = f"确定要删除分类 '{category}' 吗？"
        if source_count > 0:
            message += f"\n\n该分类下有 {source_count} 个资讯源，删除分类将同时删除这些资讯源。"

        reply = QMessageBox.question(
            self,
            "确认删除",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        # 删除分类及其下的所有资讯源
        import sqlite3
        from src.database.db_init import DEFAULT_SQLITE_DB_PATH

        try:
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 删除该分类下的所有资讯源
            cursor.execute("DELETE FROM news_sources WHERE category = ?", (category,))

            conn.commit()
            conn.close()

            # 重新加载分类数据
            self._load_categories()

            # 重新加载资讯源列表
            self._load_news_sources()

            # 更新资讯源分类下拉列表
            self._update_source_category_combobox()

            QMessageBox.information(
                self, "成功", f"已删除分类 '{category}' 及其下的所有资讯源"
            )
        except Exception as e:
            logger.error(f"删除分类失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"删除分类失败: {str(e)}")

    def _update_source_category_combobox(self):
        """更新添加/编辑资讯源对话框中的分类下拉框"""
        try:
            import sqlite3
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH

            # 获取所有分类
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT category FROM news_sources ORDER BY category"
            )
            categories = [row[0] for row in cursor.fetchall()]
            conn.close()

            # 存储分类列表供添加/编辑资讯源时使用
            self.available_categories = categories

            logger.info(f"已更新资讯源分类列表，共 {len(categories)} 个分类")
        except Exception as e:
            logger.error(f"更新资讯源分类列表失败: {str(e)}", exc_info=True)

    def _create_system_tab(self):
        """创建系统配置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 创建表单布局
        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        # 资讯获取频率设置
        form_layout.addRow(QLabel("<b>资讯获取设置</b>"))

        self.fetch_frequency = QComboBox()
        self.fetch_frequency.addItems(["手动获取", "每小时", "每6小时", "每天", "每周"])
        form_layout.addRow("获取频率:", self.fetch_frequency)

        # 数据存储设置
        form_layout.addRow(QLabel("<b>数据存储设置</b>"))

        # 修改数据存储路径
        self.data_dir = QLineEdit()
        self.data_dir.setText(
            os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
        )
        self.data_dir.setReadOnly(True)
        form_layout.addRow("数据存储路径:", self.data_dir)

        # 添加修改路径按钮
        change_dir_button = QPushButton("修改路径")
        change_dir_button.clicked.connect(self._change_data_dir)
        form_layout.addRow("", change_dir_button)

        # 添加备份按钮
        backup_button = QPushButton("立即备份数据")
        backup_button.clicked.connect(self._backup_data)
        form_layout.addRow("数据备份:", backup_button)

        # 添加弹性空间
        layout.addStretch()

        return tab

    def _change_data_dir(self):
        """修改数据存储路径"""
        # 待实现
        QMessageBox.information(self, "提示", "修改数据路径功能开发中")

    def _backup_data(self):
        """备份数据"""
        # 待实现
        QMessageBox.information(self, "提示", "数据备份功能开发中")

    def _test_api_connection(self, api_name):
        """测试API连接"""
        try:
            if api_name == "deepseek":
                api_key = self.deepseek_api_key.text().strip()
                if not api_key:
                    QMessageBox.warning(self, "警告", "请先输入DeepSeek API Key")
                    return

                # 创建状态标签，作为临时状态显示
                status_label = QLabel("正在测试API连接，请稍候...", self)
                status_label.setStyleSheet(
                    "background-color: #f0f0f0; padding: 10px; border-radius: 5px;"
                )
                status_label.setAlignment(Qt.AlignCenter)

                # 获取窗口中心位置
                pos = (
                    self.mapToGlobal(self.rect().center())
                    - status_label.rect().center()
                )
                status_label.move(self.mapFromGlobal(pos))
                status_label.show()

                # 设置测试按钮状态
                test_button = self.sender()
                if test_button:
                    original_text = test_button.text()
                    test_button.setEnabled(False)
                    test_button.setText("测试中...")

                # 创建一个定时器，刷新UI
                QTimer.singleShot(
                    100,
                    lambda: self._process_api_test(
                        api_name,
                        api_key,
                        status_label,
                        test_button,
                        original_text if test_button else "测试连接",
                    ),
                )
            else:
                QMessageBox.warning(self, "错误", f"不支持的API类型: {api_name}")

        except Exception as e:
            logger.error(f"API连接测试失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"API连接测试失败: {str(e)}")

    def _process_api_test(
        self, api_name, api_key, status_label, test_button, original_button_text
    ):
        """处理API测试过程"""
        try:
            # 调用API客户端进行测试
            result = api_client.test_api_connection(api_name, api_key)

            # 删除状态标签
            if status_label:
                status_label.hide()
                status_label.deleteLater()

            # 恢复按钮状态
            if test_button:
                test_button.setEnabled(True)
                test_button.setText(original_button_text)

            if result["success"]:
                # 测试成功 - 使用非阻塞消息框显示
                success_message = (
                    f"DeepSeek API连接测试成功!\n\n"
                    f"模型: {result.get('model', 'deepseek-chat')}\n"
                    f"响应: {result.get('response', '').strip()[:100] + '...' if len(result.get('response', '')) > 100 else result.get('response', '')}\n"
                    f"延迟: {result.get('latency', 0)}秒"
                )
                success_box = QMessageBox(
                    QMessageBox.Information,
                    "成功",
                    success_message,
                    QMessageBox.Ok,
                    self,
                )
                success_box.setModal(False)
                success_box.show()
            else:
                # 测试失败 - 使用非阻塞消息框显示
                error_message = f"API连接测试失败: {result.get('error', '未知错误')}"
                error_box = QMessageBox(
                    QMessageBox.Critical, "错误", error_message, QMessageBox.Ok, self
                )
                error_box.setModal(False)
                error_box.show()
        except Exception as e:
            # 恢复按钮状态
            if test_button:
                test_button.setEnabled(True)
                test_button.setText(original_button_text)

            # 删除状态标签
            if status_label:
                status_label.hide()
                status_label.deleteLater()

            logger.error(f"处理API测试结果失败: {str(e)}", exc_info=True)
            error_box = QMessageBox(
                QMessageBox.Critical,
                "错误",
                f"处理API测试结果失败: {str(e)}",
                QMessageBox.Ok,
                self,
            )
            error_box.setModal(False)
            error_box.show()

    def _load_settings(self):
        """从数据库加载设置"""
        try:
            # 加载API密钥
            deepseek_api_key = api_manager.get_api_key("deepseek")
            if deepseek_api_key:
                self.deepseek_api_key.setText(deepseek_api_key)

            # 加载系统配置
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH
            import sqlite3

            logger.info(f"加载系统配置: {DEFAULT_SQLITE_DB_PATH}")
            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 查询嵌入模型配置
            cursor.execute(
                "SELECT config_value FROM system_config WHERE config_key = 'embedding_model'"
            )
            result = cursor.fetchone()
            if result:
                embedding_model = result[0]
                index = self.embedding_model.findText(embedding_model)
                if index >= 0:
                    self.embedding_model.setCurrentIndex(index)

            # 查询获取频率配置
            cursor.execute(
                "SELECT config_value FROM system_config WHERE config_key = 'fetch_frequency'"
            )
            result = cursor.fetchone()
            if result:
                fetch_frequency = result[0]
                index = self.fetch_frequency.findText(fetch_frequency)
                if index >= 0:
                    self.fetch_frequency.setCurrentIndex(index)

            # 查询数据目录配置
            cursor.execute(
                "SELECT config_value FROM system_config WHERE config_key = 'data_dir'"
            )
            result = cursor.fetchone()
            if result:
                data_dir = result[0]
                self.data_dir.setText(data_dir)

            conn.close()

        except Exception as e:
            logger.error(f"加载设置失败: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "警告", f"加载设置失败: {str(e)}")

    def _save_settings(self):
        """保存所有设置"""
        try:
            # 保存API密钥
            deepseek_api_key = self.deepseek_api_key.text().strip()
            if deepseek_api_key:
                api_manager.save_api_key("deepseek", deepseek_api_key)

            # 保存其他设置
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH
            import sqlite3
            from datetime import datetime

            # 当前时间
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 保存嵌入模型配置
            embedding_model = self.embedding_model.currentText()
            self._save_system_config(
                cursor, "embedding_model", embedding_model, "嵌入模型设置", now
            )

            # 保存获取频率配置
            fetch_frequency = self.fetch_frequency.currentText()
            self._save_system_config(
                cursor, "fetch_frequency", fetch_frequency, "资讯获取频率设置", now
            )

            # 保存数据目录配置
            data_dir = self.data_dir.text().strip()
            if data_dir:
                self._save_system_config(
                    cursor, "data_dir", data_dir, "数据存储路径", now
                )

            conn.commit()
            conn.close()

            QMessageBox.information(self, "成功", "设置已保存")
        except Exception as e:
            logger.error(f"保存设置失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"保存设置失败: {str(e)}")

    def _save_system_config(self, cursor, key, value, description, timestamp):
        """
        保存系统配置

        Args:
            cursor: 数据库游标
            key: 配置键
            value: 配置值
            description: 描述
            timestamp: 时间戳
        """
        # 检查是否已存在配置
        cursor.execute("SELECT id FROM system_config WHERE config_key = ?", (key,))
        result = cursor.fetchone()

        if result:
            # 更新现有配置
            cursor.execute(
                "UPDATE system_config SET config_value = ?, description = ?, modified_date = ? WHERE config_key = ?",
                (value, description, timestamp, key),
            )
        else:
            # 插入新配置
            cursor.execute(
                "INSERT INTO system_config (config_key, config_value, description, modified_date) VALUES (?, ?, ?, ?)",
                (key, value, description, timestamp),
            )

    def _reset_settings(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有设置为默认值吗？这将会丢失所有当前配置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 重置API密钥
            api_manager.delete_api_key("deepseek")
            self.deepseek_api_key.clear()

            # 重置其他设置
            from src.database.db_init import DEFAULT_SQLITE_DB_PATH
            import sqlite3

            conn = sqlite3.connect(DEFAULT_SQLITE_DB_PATH)
            cursor = conn.cursor()

            # 删除所有系统配置
            cursor.execute("DELETE FROM system_config")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='system_config'")

            conn.commit()
            conn.close()

            # 重置界面上的设置
            self.embedding_model.setCurrentIndex(0)
            self.fetch_frequency.setCurrentIndex(0)
            self.data_dir.setText(
                os.path.join(os.path.expanduser("~"), "SmartInfo", "data")
            )

            QMessageBox.information(self, "成功", "所有设置已重置为默认值")
        except Exception as e:
            logger.error(f"重置设置失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"重置设置失败: {str(e)}")
