# -*- coding: utf-8 -*-

"""
MainController orchestrates the core services and sub-controllers for the UI.
"""

from PySide6.QtCore import QObject, Signal
from src.services.news_service import NewsService
from src.services.setting_service import SettingService
from src.services.chat_service import ChatService
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
        chat_service: ChatService,
        parent=None,
    ):
        super().__init__(parent)
        # Inject service instances
        self.news_service = news_service
        self.setting_service = setting_service
        self.chat_service = chat_service

        # Create sub-controllers
        self.news_controller = NewsController(self.news_service)
        self.settings_controller = SettingsController(
            self.setting_service, self.news_service
        )

        # Initialize ChatController with ChatService
        self.chat_controller = ChatController(self.chat_service)

        # Connect settings controller signals to main controller signals
        self.settings_controller.external_settings_changed.connect(
            self.notify_settings_changed
        )

    def notify_settings_changed(self):
        """Emit a signal to notify other modules to refresh data when settings change."""
        self.settings_changed.emit()
