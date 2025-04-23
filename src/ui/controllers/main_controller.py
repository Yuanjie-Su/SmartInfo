# -*- coding: utf-8 -*-

"""
MainController orchestrates the core services and sub-controllers for the UI.
"""

from PySide6.QtCore import QObject, Signal
from src.services.news_service import NewsService
from src.services.setting_service import SettingService
from src.services.chat_service import ChatService
from src.db.repositories import ChatRepository, MessageRepository
from .news_controller import NewsController
from .settings_controller import SettingsController
from .chat_controller import ChatController


class MainController(QObject):
    """
    MainController manages core services and sub-controllers for the UI.
    """

    settings_changed = Signal()

    def __init__(
        self,
        news_service: NewsService,
        setting_service: SettingService,
        parent=None,
    ):
        super().__init__(parent)
        # 注入服务实例
        self.news_service = news_service
        self.setting_service = setting_service
        
        # 创建聊天服务及其依赖的仓库
        self.chat_repo = ChatRepository()
        self.message_repo = MessageRepository()

        # 创建ChatService实例
        self.chat_service = ChatService(
            chat_repo=self.chat_repo,
            message_repo=self.message_repo,
        )
        
        # 创建子控制器
        self.news_controller = NewsController(self.news_service, self.setting_service)
        self.settings_controller = SettingsController(
            self.setting_service, self.news_service
        )
        
        # 使用ChatService初始化ChatController
        self.chat_controller = ChatController(self.chat_service)

        # 连接设置控制器信号到主控制器信号
        self.settings_controller.external_settings_changed.connect(
            self.notify_settings_changed
        )

    def notify_settings_changed(self):
        """在设置变更时发出信号通知其他模块刷新数据。"""
        self.settings_changed.emit()
