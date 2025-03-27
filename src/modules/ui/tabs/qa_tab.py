#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能问答选项卡
实现基于知识库的智能问答功能
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLineEdit, QLabel, QListWidget,
    QListWidgetItem, QSplitter, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)

class QATab(QWidget):
    """智能问答选项卡"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.chat_history = []
    
    def _setup_ui(self):
        """设置用户界面"""
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter, 1)
        
        # 创建左侧问答历史列表部分
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.addWidget(QLabel("历史问答:"))
        
        # 创建历史问答列表
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        history_layout.addWidget(self.history_list)
        
        # 添加清空历史按钮
        clear_button = QPushButton("清空历史")
        clear_button.clicked.connect(self._clear_history)
        history_layout.addWidget(clear_button)
        
        main_splitter.addWidget(history_widget)
        
        # 创建右侧对话部分
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        
        # 创建聊天内容显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        chat_layout.addWidget(self.chat_display, 1)
        
        # 创建用户输入区域
        input_layout = QHBoxLayout()
        
        # 添加问题输入框
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("请输入您的问题...")
        self.question_input.returnPressed.connect(self._send_question)
        input_layout.addWidget(self.question_input, 1)
        
        # 添加发送按钮
        send_button = QPushButton("发送")
        send_button.clicked.connect(self._send_question)
        input_layout.addWidget(send_button)
        
        chat_layout.addLayout(input_layout)
        
        main_splitter.addWidget(chat_widget)
        
        # 设置分割比例
        main_splitter.setSizes([300, 700])
        
        # 添加一些示例历史问答
        self._add_sample_history()
        
        # 显示欢迎信息
        self._show_welcome_message()
    
    def _add_sample_history(self):
        """添加示例历史问答"""
        sample_questions = [
            "量子计算最新进展是什么？",
            "大模型技术的主要应用场景有哪些？",
            "自动驾驶技术存在哪些挑战？"
        ]
        
        for question in sample_questions:
            item = QListWidgetItem(question)
            self.history_list.addItem(item)
    
    def _show_welcome_message(self):
        """显示欢迎信息"""
        welcome_message = (
            "欢迎使用 SmartInfo 智能问答系统！\n\n"
            "您可以基于已收集的资讯内容，向我提问任何相关问题。\n"
            "系统将通过知识库检索结合大模型智能分析，为您提供精准答案。\n\n"
            "示例问题：\n"
            "- 最近在AI领域有哪些重要进展？\n"
            "- 请总结一下量子计算的现状和未来发展趋势\n"
            "- 芯片技术的最新突破有哪些？\n\n"
            "开始向我提问吧！"
        )
        self.chat_display.setText(welcome_message)
    
    def _send_question(self):
        """发送用户问题"""
        # 获取用户输入的问题
        question = self.question_input.text().strip()
        if not question:
            return
        
        # 清空输入框
        self.question_input.clear()
        
        # 将问题添加到聊天显示区域
        self._add_message_to_chat("用户", question)
        
        # 将问题添加到历史列表
        if question not in [self.history_list.item(i).text() for i in range(self.history_list.count())]:
            self.history_list.addItem(QListWidgetItem(question))
        
        # 模拟系统回答（实际应用中将调用知识库检索和大模型API）
        self._simulate_answer(question)
    
    def _simulate_answer(self, question):
        """模拟系统回答"""
        # 显示"正在思考"状态
        self.chat_display.append("\n<b>系统正在思考...</b>")
        
        # 在实际应用中，这里将异步调用知识库检索和大模型API生成回答
        # 这里仅作界面演示
        
        # 根据不同问题模拟不同回答
        if "AI" in question or "人工智能" in question:
            answer = (
                "最近AI领域的重要进展主要集中在以下几个方面：\n\n"
                "1. 大型语言模型（LLM）的能力持续提升，模型规模已达到数万亿参数级别\n"
                "2. 多模态模型成为主流，能同时处理文本、图像、音频和视频\n"
                "3. 推理优化技术取得突破，大幅降低了模型部署的硬件要求\n"
                "4. AI辅助编程工具开始广泛应用于实际开发过程\n"
                "5. 生成式AI在创意内容创作领域应用迅速扩展\n\n"
                "这些进展正在深刻改变各行各业的工作方式和生产效率。"
            )
        elif "量子计算" in question:
            answer = (
                "量子计算的现状与发展趋势：\n\n"
                "现状：\n"
                "- 目前最先进的量子计算机已达到100+量子比特\n"
                "- 谷歌、IBM、百度等科技巨头和初创公司积极投入研发\n"
                "- 量子霸权（量子优越性）已在特定问题上得到证明\n"
                "- 量子纠错仍是主要技术瓶颈之一\n\n"
                "发展趋势：\n"
                "1. 硬件架构将向更稳定、更可扩展的方向发展\n"
                "2. 量子算法研究将更关注实际应用场景\n"
                "3. 量子云服务将成为主流访问方式\n"
                "4. 混合量子-经典计算将成为过渡阶段的主要模式\n"
                "5. 材料科学、药物研发、金融模拟等领域将最先受益"
            )
        elif "芯片" in question:
            answer = (
                "芯片技术的最新突破主要包括：\n\n"
                "1. 先进制程工艺：台积电已量产3nm工艺，2nm工艺正在研发中\n"
                "2. 三维堆叠技术：通过垂直堆叠提升单位面积内晶体管密度\n"
                "3. 新型半导体材料：碳纳米管、石墨烯等新材料研究取得进展\n"
                "4. 专用AI芯片：针对特定AI任务优化的芯片架构大幅提升能效比\n"
                "5. 光子计算芯片：利用光信号代替电信号，大幅提升数据处理速度\n\n"
                "这些技术突破正持续推动计算能力的提升，为AI、自动驾驶等新兴领域提供算力支持。"
            )
        else:
            answer = (
                f"关于{question}的回答：\n\n"
                "我理解您的问题，但目前知识库中没有足够相关信息。在实际应用中，"
                "系统会基于收集的资讯进行实时语义检索，并结合大模型分析生成回答。\n\n"
                "您可以尝试收集更多相关领域的资讯，或者尝试询问其他技术相关问题。"
            )
        
        # 将回答添加到聊天显示区域
        # 先移除"正在思考"提示
        current_text = self.chat_display.toHtml()
        current_text = current_text.replace("\n<b>系统正在思考...</b>", "")
        self.chat_display.setHtml(current_text)
        
        # 添加实际回答
        self._add_message_to_chat("系统", answer)
        
        # 保存到聊天历史
        self.chat_history.append({"question": question, "answer": answer})
    
    def _add_message_to_chat(self, sender, message):
        """添加消息到聊天显示区域"""
        # 设置发送者样式
        if sender == "用户":
            sender_style = "color: #4285F4; font-weight: bold;"
        else:
            sender_style = "color: #0F9D58; font-weight: bold;"
        
        # 添加消息到聊天显示区域
        self.chat_display.append(f"\n<span style='{sender_style}'>{sender}:</span>")
        self.chat_display.append(message)
        
        # 滚动到底部
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )
    
    def _on_history_item_clicked(self, item):
        """点击历史问题项处理"""
        question = item.text()
        
        # 可以选择直接重新提问，或者显示历史问答
        reply = QMessageBox.question(
            self,
            "历史问题",
            f"是否重新提问：\n{question}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.question_input.setText(question)
    
    def _clear_history(self):
        """清空历史记录"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.history_list.clear()
            self.chat_history = [] 