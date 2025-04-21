# -*- coding: utf-8 -*-

"""
MainController orchestrates the core services and sub-controllers for the UI.
"""

from PySide6.QtCore import QObject, Signal
from src.services.news_service import NewsService
from src.services.qa_service import QAService
from src.services.setting_service import SettingService
from .news_controller import NewsController
from .settings_controller import SettingsController
from .qa_controller import QAController


class MainController(QObject):
    """
    MainController manages core services and sub-controllers for the UI.
    """

    settings_changed = Signal()

    def __init__(
        self,
        news_service: NewsService,
        qa_service: QAService,
        setting_service: SettingService,
        parent=None,
    ):
        super().__init__(parent)
        # Inject service instances
        self.news_service = news_service
        self.qa_service = qa_service
        self.setting_service = setting_service
        # Generate sub-controllers
        self.news_controller = NewsController(self.news_service, self.setting_service)
        self.settings_controller = SettingsController(
            self.setting_service, self.news_service
        )
        self.qa_controller = QAController(self.qa_service)

        # Connect settings controller signal to main controller signal if needed
        self.settings_controller.external_settings_changed.connect(
            self.notify_settings_changed
        )

    def notify_settings_changed(self):
        """Emits a signal to notify other modules to refresh data when settings change."""
        self.settings_changed.emit()
