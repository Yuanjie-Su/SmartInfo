#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资讯管理选项卡
实现资讯的获取、查看、删除和编辑功能
"""

import logging
import os
import sqlite3
import asyncio
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QComboBox,
    QLabel,
    QLineEdit,
    QSplitter,
    QTextEdit,
    QHeaderView,
    QMessageBox,
    QProgressDialog,
    QApplication,
)
from PySide6.QtCore import (
    Qt,
    QSortFilterProxyModel,
    Signal,
    Slot,
    QRunnable,
    QThreadPool,
    QObject,
)
from PySide6.QtGui import QStandardItemModel, QStandardItem

from ....config.config import get_config
from ....modules.news_fetch.news_fetcher import fetch_and_save_all

logger = logging.getLogger(__name__)


# 用于在后台线程中运行异步任务的类
class AsyncTaskRunner(QRunnable):
    """在QThreadPool中运行异步任务的类"""

    class Signals(QObject):
        """用于发送信号的嵌套类"""

        finished = Signal(object)  # 任务完成信号，携带结果
        error = Signal(Exception)  # 任务出错信号，携带异常

    def __init__(self, coro):
        """初始化异步任务运行器

        Args:
            coro: 要运行的协程对象
        """
        super().__init__()
        self.coro = coro
        self.signals = self.Signals()

    def run(self):
        """运行协程"""
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 运行协程并获取结果
            result = loop.run_until_complete(self.coro)
            # 发送完成信号
            self.signals.finished.emit(result)
        except Exception as e:
            # 发送错误信号
            logger.error(f"异步任务执行失败: {str(e)}", exc_info=True)
            self.signals.error.emit(e)
        finally:
            # 关闭事件循环
            loop.close()


class NewsTab(QWidget):
    """资讯管理选项卡"""

    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.db_path = os.path.join(self.config.get("data_dir"), "smartinfo.db")
        self._ensure_db_table()
        self._setup_ui()
        self._load_news()
        self._load_filters()

    def _ensure_db_table(self):
        """确保数据库表存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建资讯表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                publish_date TEXT,
                analyzed INTEGER DEFAULT 0
            )
            """
            )

            # 创建资讯源表
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS news_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                parser_code TEXT
            )
            """
            )

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"确保数据库表存在失败: {str(e)}", exc_info=True)

    def _setup_ui(self):
        """设置用户界面"""
        main_layout = QVBoxLayout(self)

        # 创建顶部工具栏
        toolbar_layout = QHBoxLayout()
        main_layout.addLayout(toolbar_layout)

        # 添加获取资讯按钮
        self.fetch_button = QPushButton("获取资讯")
        self.fetch_button.clicked.connect(self._fetch_news)
        toolbar_layout.addWidget(self.fetch_button)

        # 添加资讯分类过滤器
        toolbar_layout.addWidget(QLabel("分类:"))
        self.category_filter = QComboBox()
        # 初始只添加"全部"，其他分类在_load_filters中加载
        self.category_filter.addItem("全部")
        toolbar_layout.addWidget(self.category_filter)

        # 添加资讯源过滤器
        toolbar_layout.addWidget(QLabel("来源:"))
        self.source_filter = QComboBox()
        self.source_filter.addItems(["全部"])
        toolbar_layout.addWidget(self.source_filter)

        # 添加搜索框
        toolbar_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索")
        toolbar_layout.addWidget(self.search_input)

        # 创建分割器
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)

        # 创建资讯表格
        self.news_table = QTableView()
        self.news_table.setSelectionBehavior(QTableView.SelectRows)
        self.news_table.setSelectionMode(QTableView.SingleSelection)
        self.news_table.verticalHeader().setVisible(False)
        self.news_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        splitter.addWidget(self.news_table)

        # 创建资讯预览区域
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.addWidget(QLabel("资讯预览:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        splitter.addWidget(preview_widget)

        # 设置拉伸因子
        splitter.setSizes([600, 200])

        # 创建表格模型
        self.create_table_model()

        # 创建底部工具栏
        bottom_toolbar = QHBoxLayout()
        main_layout.addLayout(bottom_toolbar)

        # 添加编辑按钮
        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self._edit_news)
        bottom_toolbar.addWidget(self.edit_button)

        # 添加删除按钮
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self._delete_news)
        bottom_toolbar.addWidget(self.delete_button)

        # 添加发送到分析按钮
        self.analyze_button = QPushButton("发送到分析")
        self.analyze_button.clicked.connect(self._send_to_analysis)
        bottom_toolbar.addWidget(self.analyze_button)

        # 右侧伸缩
        bottom_toolbar.addStretch()

        # 添加导出按钮
        self.export_button = QPushButton("导出")
        self.export_button.clicked.connect(self._export_news)
        bottom_toolbar.addWidget(self.export_button)

        # 添加刷新按钮
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._load_news)
        bottom_toolbar.addWidget(self.refresh_button)

    def create_table_model(self):
        """创建表格模型"""
        # 创建模型
        self.model = QStandardItemModel(0, 5, self)
        self.model.setHorizontalHeaderLabels(["标题", "来源", "分类", "日期", "已分析"])

        # 创建代理模型用于过滤和排序
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # 在所有列中搜索

        # 设置表格使用代理模型
        self.news_table.setModel(self.proxy_model)

        # 连接表格选择信号
        self.news_table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        # 连接过滤器和搜索框信号
        self.category_filter.currentTextChanged.connect(self._apply_filters)
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)

    def _fetch_news(self):
        """获取资讯"""
        try:
            # 禁用获取按钮，防止重复点击
            self.fetch_button.setEnabled(False)

            # 获取选中的分类
            selected_category = self.category_filter.currentText()
            selected_sources = None

            if selected_category != "全部":
                # 获取指定分类的资讯源信息
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name, url, category FROM news_sources WHERE category = ?",
                        (selected_category,),
                    )
                    selected_sources = cursor.fetchall()
                    conn.close()
                except Exception as e:
                    logger.error(f"获取指定分类资讯源失败: {str(e)}", exc_info=True)
                    selected_sources = None
            else:
                # 从数据库获取全部分类
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, url, category FROM news_sources")
                    selected_sources = cursor.fetchall()

                    if not selected_sources:  # 如果没有任何分类，不进行过滤
                        selected_sources = None

                    conn.close()
                except Exception as e:
                    logger.error(f"获取资讯源失败: {str(e)}", exc_info=True)
                    selected_sources = None  # 出错时不进行分类过滤

            if selected_sources is None:
                QMessageBox.critical(self, "错误", "没有可用的资讯源")
                return

            selected_sources = [
                {"name": name, "url": url, "category": category}
                for name, url, category in selected_sources
            ]

            # 创建进度对话框
            self.progress = QProgressDialog("正在获取资讯...", "取消", 0, 100, self)
            self.progress.setWindowTitle("资讯获取")
            self.progress.setWindowModality(Qt.WindowModal)
            self.progress.setValue(10)
            self.progress.show()
            QApplication.processEvents()  # 确保UI更新

            # 使用异步任务运行器执行异步获取操作
            runner = AsyncTaskRunner(fetch_and_save_all(selected_sources))

            # 连接信号
            runner.signals.finished.connect(self._on_fetch_completed)
            runner.signals.error.connect(self._on_fetch_error)

            # 启动任务
            QThreadPool.globalInstance().start(runner)

        except Exception as e:
            # 恢复按钮状态
            self.fetch_button.setEnabled(True)

            # 关闭进度对话框
            if hasattr(self, "progress") and self.progress:
                self.progress.close()

            # 显示错误消息
            logger.error(f"获取资讯初始化失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"获取资讯失败: {str(e)}")

    def _on_fetch_completed(self, result):
        """异步获取完成的回调函数

        Args:
            result: 获取结果，保存的资讯数量
        """
        # 更新进度条
        if hasattr(self, "progress") and self.progress:
            self.progress.setValue(100)
            self.progress.close()

        # 重新加载资讯和过滤器
        self._load_news()
        self._load_filters()

        # 恢复按钮状态
        self.fetch_button.setEnabled(True)

        # 显示结果
        QMessageBox.information(self, "获取完成", f"成功获取了 {result} 条资讯")

    def _on_fetch_error(self, error):
        """异步获取出错的回调函数

        Args:
            error: 捕获的异常
        """
        # 更新进度条
        if hasattr(self, "progress") and self.progress:
            self.progress.close()

        # 恢复按钮状态
        self.fetch_button.setEnabled(True)

        # 显示错误消息
        logger.error(f"获取资讯失败: {str(error)}", exc_info=True)
        QMessageBox.critical(self, "错误", f"获取资讯失败: {str(error)}")

    def _load_news(self):
        """从数据库加载资讯"""
        try:
            # 清空现有数据
            self.model.removeRows(0, self.model.rowCount())

            # 打开数据库连接
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询资讯数据
            cursor.execute(
                "SELECT id, title, source, category, publish_date, analyzed, link, content "
                "FROM news ORDER BY publish_date DESC"
            )

            rows = cursor.fetchall()
            self.news_data = {}  # 存储ID到完整数据的映射

            # 填充表格
            for row in rows:
                (
                    news_id,
                    title,
                    source,
                    category,
                    publish_date,
                    analyzed,
                    link,
                    content,
                ) = row

                # 存储完整数据
                self.news_data[news_id] = {
                    "id": news_id,
                    "title": title,
                    "source": source,
                    "category": category,
                    "publish_date": publish_date,
                    "analyzed": bool(analyzed),
                    "url": link,  # 保持前端代码兼容性，仍使用url作为键名
                    "content": content,
                }

                # 添加到表格
                row_items = [
                    QStandardItem(title),
                    QStandardItem(source),
                    QStandardItem(category),
                    QStandardItem(publish_date),
                    QStandardItem("是" if analyzed else "否"),
                ]

                # 设置数据ID
                for item in row_items:
                    item.setData(news_id, Qt.UserRole)

                self.model.appendRow(row_items)

            conn.close()

            logger.info(f"已加载 {len(rows)} 条资讯")
        except Exception as e:
            logger.error(f"加载资讯失败: {str(e)}", exc_info=True)

    def _load_filters(self):
        """加载过滤器选项"""
        try:
            # 打开数据库连接
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 保存当前选择的分类和来源
            current_category = self.category_filter.currentText()
            current_source = self.source_filter.currentText()

            # 查询所有分类
            cursor.execute("SELECT DISTINCT category FROM news ORDER BY category")
            categories = [row[0] for row in cursor.fetchall()]

            # 查询所有来源
            cursor.execute("SELECT DISTINCT source FROM news ORDER BY source")
            sources = [row[0] for row in cursor.fetchall()]

            # 更新分类过滤器
            self.category_filter.clear()
            self.category_filter.addItem("全部")
            self.category_filter.addItems(categories)

            # 更新来源过滤器
            self.source_filter.clear()
            self.source_filter.addItem("全部")
            self.source_filter.addItems(sources)

            # 尝试恢复之前的选择
            cat_index = self.category_filter.findText(current_category)
            if cat_index >= 0:
                self.category_filter.setCurrentIndex(cat_index)

            src_index = self.source_filter.findText(current_source)
            if src_index >= 0:
                self.source_filter.setCurrentIndex(src_index)

            conn.close()
        except Exception as e:
            logger.error(f"加载过滤器选项失败: {str(e)}", exc_info=True)

    def _edit_news(self):
        """编辑资讯"""
        # 获取选中行
        indexes = self.news_table.selectionModel().selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "提示", "请先选择一条资讯")
            return

        # 获取资讯ID
        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)

        # 待实现编辑对话框
        QMessageBox.information(self, "提示", f"资讯编辑功能开发中 (ID: {news_id})")

    def _delete_news(self):
        """删除资讯"""
        # 获取选中行
        indexes = self.news_table.selectionModel().selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "提示", "请先选择一条资讯")
            return

        # 获取资讯ID
        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条资讯吗?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 删除资讯
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
            conn.commit()
            conn.close()

            # 重新加载数据
            self._load_news()
            self._load_filters()

            QMessageBox.information(self, "成功", "资讯已删除")
        except Exception as e:
            logger.error(f"删除资讯失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"删除资讯失败: {str(e)}")

    def _send_to_analysis(self):
        """发送到分析选项卡"""
        # 获取选中行
        indexes = self.news_table.selectionModel().selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "提示", "请先选择一条资讯")
            return

        # 获取资讯ID
        source_index = self.proxy_model.mapToSource(indexes[0])
        news_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)

        # 待实现发送到分析
        QMessageBox.information(self, "提示", f"发送到分析功能开发中 (ID: {news_id})")

    def _export_news(self):
        """导出资讯"""
        # 待实现
        QMessageBox.information(self, "提示", "资讯导出功能开发中")

    def _on_selection_changed(self, selected, deselected):
        """处理选择变更事件"""
        # 获取选中行
        indexes = selected.indexes()
        if not indexes:
            return

        # 获取原始模型索引
        source_index = self.proxy_model.mapToSource(indexes[0])
        # 获取资讯ID
        news_id = self.model.item(source_index.row(), 0).data(Qt.UserRole)

        # 显示详细信息
        if news_id in self.news_data:
            news = self.news_data[news_id]
            self.preview_text.setHtml(
                f"<h3>{news['title']}</h3>"
                f"<p><b>来源:</b> {news['source']}</p>"
                f"<p><b>分类:</b> {news['category']}</p>"
                f"<p><b>发布日期:</b> {news['publish_date']}</p>"
                f"<p><b>链接:</b> <a href='{news['url']}'>{news['url']}</a></p>"
                f"<p><b>已分析:</b> {'是' if news['analyzed'] else '否'}</p>"
                f"<hr>"
                f"<p>{news['content']}</p>"
            )

    def _apply_filters(self):
        """应用过滤器"""
        try:
            category = self.category_filter.currentText()
            source = self.source_filter.currentText()
            search_text = self.search_input.text()

            # 重置过滤器
            self.proxy_model.setFilterFixedString("")

            # 应用文本过滤
            if search_text:
                self.proxy_model.setFilterFixedString(search_text)

            # 应用分类和来源过滤
            for row in range(self.model.rowCount()):
                # 获取行数据
                row_visible = True
                row_category = self.model.item(row, 2).text()
                row_source = self.model.item(row, 1).text()

                # 应用分类过滤
                if category != "全部" and row_category != category:
                    row_visible = False

                # 应用来源过滤
                if source != "全部" and row_source != source:
                    row_visible = False

                # 设置行可见性
                self.news_table.setRowHidden(row, not row_visible)
        except Exception as e:
            logger.error(f"应用过滤器失败: {str(e)}", exc_info=True)
