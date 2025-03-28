#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
系统设置选项卡
实现API配置、资讯源管理等系统设置功能
"""

import logging
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget, QLabel, QLineEdit, QTableView,
    QHeaderView, QFormLayout, QComboBox, QMessageBox,
    QFileDialog, QCheckBox
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
        self._setup_ui()
        self._load_settings()  # 加载已保存的设置
    
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
        
        # 创建领域配置选项卡
        categories_tab = self._create_categories_tab()
        settings_tabs.addTab(categories_tab, "领域配置")
        
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
        test_deepseek_button.clicked.connect(lambda: self._test_api_connection("deepseek"))
        form_layout.addRow("", test_deepseek_button)
        
        # 添加分隔空间
        layout.addSpacing(20)
        
        # 嵌入模型设置
        form_layout.addRow(QLabel("<b>嵌入模型配置</b>"))
        
        self.embedding_model = QComboBox()
        self.embedding_model.addItems(["sentence-transformers/all-MiniLM-L6-v2", 
                                     "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                                     "本地模型 (较小体积)"])
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
        
        # 导入导出按钮
        import_button = QPushButton("导入")
        import_button.clicked.connect(self._import_sources)
        buttons_layout.addWidget(import_button)
        
        export_button = QPushButton("导出")
        export_button.clicked.connect(self._export_sources)
        buttons_layout.addWidget(export_button)
        
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
        self.sources_model = QStandardItemModel(0, 5, self)
        self.sources_model.setHorizontalHeaderLabels(["名称", "URL", "类型", "分类", "活跃"])
        
        # 创建代理模型用于过滤和排序
        self.sources_proxy_model = QSortFilterProxyModel(self)
        self.sources_proxy_model.setSourceModel(self.sources_model)
        
        # 设置表格使用代理模型
        self.sources_table.setModel(self.sources_proxy_model)
        
        # 添加示例数据
        self._add_sample_sources()
    
    def _add_sample_sources(self):
        """添加示例资讯源数据"""
        sample_sources = [
            ["TechDaily", "https://techdaily.com/feed", "RSS", "技术", "是"],
            ["ScienceWeekly", "https://scienceweekly.com/feed", "RSS", "科学", "是"],
            ["AI News", "https://ainews.com/rss", "RSS", "人工智能", "是"]
        ]
        
        for name, url, type_, category, active in sample_sources:
            self.sources_model.appendRow([
                QStandardItem(name),
                QStandardItem(url),
                QStandardItem(type_),
                QStandardItem(category),
                QStandardItem(active)
            ])
    
    def _create_categories_tab(self):
        """创建领域配置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 添加说明标签
        layout.addWidget(QLabel("设置您关注的资讯领域，只有匹配这些领域的资讯会被获取和分析："))
        
        # 创建复选框网格
        categories_layout = QVBoxLayout()
        layout.addLayout(categories_layout)
        
        # 添加多个领域复选框
        self.category_checkboxes = {}
        categories = [
            "技术", "科学", "金融", "医疗", "人工智能", 
            "量子计算", "芯片技术", "区块链", "新能源", "生物技术"
        ]
        
        for category in categories:
            checkbox = QCheckBox(category)
            checkbox.setChecked(True)  # 默认选中
            categories_layout.addWidget(checkbox)
            self.category_checkboxes[category] = checkbox
        
        # 添加自定义领域输入区域
        form_layout = QFormLayout()
        layout.addLayout(form_layout)
        
        self.new_category = QLineEdit()
        form_layout.addRow("添加自定义领域:", self.new_category)
        
        add_category_button = QPushButton("添加")
        add_category_button.clicked.connect(self._add_custom_category)
        form_layout.addRow("", add_category_button)
        
        # 添加弹性空间
        layout.addStretch()
        
        return tab
    
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
        self.data_dir.setText(os.path.join(os.path.expanduser('~'), 'SmartInfo', 'data'))
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
    
    def _add_news_source(self):
        """添加新的资讯源"""
        # 待实现
        QMessageBox.information(self, "提示", "添加资讯源功能开发中")
    
    def _delete_news_source(self):
        """删除所选资讯源"""
        # 待实现
        QMessageBox.information(self, "提示", "删除资讯源功能开发中")
    
    def _import_sources(self):
        """导入资讯源"""
        # 待实现
        QMessageBox.information(self, "提示", "导入资讯源功能开发中")
    
    def _export_sources(self):
        """导出资讯源"""
        # 待实现
        QMessageBox.information(self, "提示", "导出资讯源功能开发中")
    
    def _add_custom_category(self):
        """添加自定义领域"""
        # 待实现
        QMessageBox.information(self, "提示", "添加自定义领域功能开发中")
    
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
                status_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
                status_label.setAlignment(Qt.AlignCenter)
                
                # 获取窗口中心位置
                pos = self.mapToGlobal(self.rect().center()) - status_label.rect().center()
                status_label.move(self.mapFromGlobal(pos))
                status_label.show()
                
                # 设置测试按钮状态
                test_button = self.sender()
                if test_button:
                    original_text = test_button.text()
                    test_button.setEnabled(False)
                    test_button.setText("测试中...")
                
                # 创建一个定时器，刷新UI
                QTimer.singleShot(100, lambda: self._process_api_test(api_name, api_key, status_label, test_button, original_text if test_button else "测试连接"))
            else:
                QMessageBox.warning(self, "错误", f"不支持的API类型: {api_name}")
                
        except Exception as e:
            logger.error(f"API连接测试失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"API连接测试失败: {str(e)}")
    
    def _process_api_test(self, api_name, api_key, status_label, test_button, original_button_text):
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
                success_box = QMessageBox(QMessageBox.Information, "成功", success_message, QMessageBox.Ok, self)
                success_box.setModal(False)
                success_box.show()
            else:
                # 测试失败 - 使用非阻塞消息框显示
                error_message = f"API连接测试失败: {result.get('error', '未知错误')}"
                error_box = QMessageBox(QMessageBox.Critical, "错误", error_message, QMessageBox.Ok, self)
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
            error_box = QMessageBox(QMessageBox.Critical, "错误", f"处理API测试结果失败: {str(e)}", QMessageBox.Ok, self)
            error_box.setModal(False)
            error_box.show()
    
    def _load_settings(self):
        """从数据库加载设置"""
        try:
            # 加载API密钥
            deepseek_api_key = api_manager.get_api_key("deepseek")
            if deepseek_api_key:
                self.deepseek_api_key.setText(deepseek_api_key)
            
            # TODO: 加载其他设置
            
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
            
            # TODO: 保存其他设置
            
            QMessageBox.information(self, "成功", "设置已保存")
        except Exception as e:
            logger.error(f"保存设置失败: {str(e)}", exc_info=True)
            QMessageBox.critical(self, "错误", f"保存设置失败: {str(e)}")
    
    def _reset_settings(self):
        """重置为默认设置"""
        # 待实现
        QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有设置为默认值吗？这将会丢失所有当前配置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        ) 