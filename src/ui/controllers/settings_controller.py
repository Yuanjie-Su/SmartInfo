# src/ui/controllers/settings_controller.py

"""
SettingsController orchestrates the business logic and UI updates for the Settings Tab.

Core responsibilities:
- Load and save settings from/to the database.
- Test API connections.
- Manage news source and category operations.
- Handle system settings reset.
- Emit signals to update the UI based on changes.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from src.services.setting_service import SettingService
from src.services.news_service import NewsService
from src.config import API_KEY_DEEPSEEK  # Import necessary constants

logger = logging.getLogger(__name__)


class SettingsController(QObject):
    """Controller for the Settings Window/Dialog"""

    # Signals to update the View
    settings_loaded = Signal(dict)  # General settings (API keys status, system config)
    sources_loaded = Signal(list)  # List of source dicts
    categories_loaded = Signal(list)  # List of category tuples (id, name, count)
    api_test_result = Signal(str, bool, str)  # api_name, success, message
    settings_saved = Signal(bool, str)  # success, message
    source_operation_finished = Signal(bool, str)  # success, message
    category_operation_finished = Signal(bool, str)  # success, message
    error_occurred = Signal(str, str)  # title, message

    # Signal emitted when sources/categories changed that affect other parts of UI
    external_settings_changed = Signal()

    def __init__(
        self, setting_service: SettingService, news_service: NewsService, parent=None
    ):
        super().__init__(parent)
        self._setting_service = setting_service
        self._news_service = news_service

    def load_all_settings(self):
        """Loads all settings needed for the dialog."""
        self.load_general_settings()
        self.load_sources()
        self.load_categories()

    def load_general_settings(self):
        """Loads API key status and system config."""
        try:
            settings_data = {
                "api_keys": {},
                "system": {},
            }
            # API Key Status (example for DeepSeek)
            deepseek_key_status = "未配置"
            env_key = self._setting_service._config.get(
                API_KEY_DEEPSEEK
            )  # Access config via service if needed
            if env_key:
                deepseek_key_status = "已从环境变量加载"
            elif self._setting_service._api_key_repo.get_key(
                "deepseek"
            ):  # Access repo via service
                deepseek_key_status = "已从数据库加载"
            settings_data["api_keys"]["deepseek_status"] = deepseek_key_status
            # Add other API keys similarly...

            # System Config
            settings_data["system"][
                "fetch_frequency"
            ] = self._setting_service.get_fetch_frequency()
            settings_data["system"]["data_dir"] = self._setting_service.get_data_dir()
            # Add other system settings...

            self.settings_loaded.emit(settings_data)

        except Exception as e:
            logger.error(f"Error loading general settings: {e}", exc_info=True)
            self.error_occurred.emit(
                "Load Error", f"Failed to load general settings: {e}"
            )

    def save_general_settings(self, settings_data: Dict[str, Any]):
        """Saves API keys and system config."""
        # Expects data like: {'api_keys': {'deepseek': 'key_value'}, 'system': {'fetch_frequency': 'daily'}}
        logger.info("Saving general settings via controller...")
        all_success = True
        messages = []

        try:
            # Save API Keys (example DeepSeek)
            deepseek_key = settings_data.get("api_keys", {}).get("deepseek")
            if (
                deepseek_key is not None
            ):  # Allow empty string to clear DB key if no env var
                if deepseek_key:
                    if not self._setting_service.save_api_key("deepseek", deepseek_key):
                        all_success = False
                        messages.append("Failed to save DeepSeek API Key.")
                elif not self._setting_service._config.get(
                    API_KEY_DEEPSEEK
                ):  # Check env var
                    # Only delete from DB if input is empty AND no env var exists
                    if not self._setting_service.delete_api_key_from_db("deepseek"):
                        all_success = False
                        messages.append("Failed to delete DeepSeek API Key from DB.")

            # Save System Settings (example fetch frequency) - currently disabled in UI
            # freq = settings_data.get('system', {}).get('fetch_frequency')
            # if freq and not self._setting_service.save_fetch_frequency(freq):
            #     all_success = False
            #     messages.append("Failed to save fetch frequency.")

            # ... save other settings ...

            if all_success:
                messages.append("General settings saved successfully.")
                # Reload to update status labels etc.
                self.load_general_settings()
            self.settings_saved.emit(all_success, "\n".join(messages))

        except Exception as e:
            logger.error(f"Error saving general settings: {e}", exc_info=True)
            self.settings_saved.emit(False, f"Error saving settings: {e}")

    def test_api_connection(self, api_name: str, api_key: str):
        """Tests API connection."""
        # Note: This might block the UI if not run in a thread.
        # Consider using AsyncTaskRunner if tests are slow.
        logger.info(f"Testing connection for {api_name} via controller...")
        if not api_key:
            self.api_test_result.emit(api_name, False, "API Key cannot be empty.")
            return

        try:
            result_dict = {}
            if api_name.lower() == "deepseek":
                result_dict = self._setting_service.test_deepseek_connection(api_key)
            # Add other API tests here...
            else:
                result_dict = {
                    "success": False,
                    "error": "Test not implemented for this API",
                }

            success = result_dict.get("success", False)
            message = result_dict.get("response") or result_dict.get(
                "error", "Unknown test result"
            )
            if success and "latency" in result_dict:
                message += f" (Latency: {result_dict['latency']}s)"
            self.api_test_result.emit(api_name, success, message)

        except Exception as e:
            logger.error(
                f"Error testing API connection for {api_name}: {e}", exc_info=True
            )
            self.api_test_result.emit(api_name, False, f"Testing failed: {e}")

    def load_sources(self):
        try:
            sources = self._news_service.get_all_sources()
            self.sources_loaded.emit(sources)
        except Exception as e:
            logger.error(f"Failed to load news sources: {e}", exc_info=True)
            self.error_occurred.emit("Load Error", f"Could not load news sources: {e}")

    def load_categories(self):
        try:
            categories = self._news_service.get_all_categories_with_counts()
            self.categories_loaded.emit(categories)
        except Exception as e:
            logger.error(f"Failed to load categories: {e}", exc_info=True)
            self.error_occurred.emit("Load Error", f"Could not load categories: {e}")

    def add_news_source(self, name: str, url: str, category_name: str):
        try:
            new_id = self._news_service.add_source(name, url, category_name)
            success = new_id is not None
            message = (
                f"Source '{name}' added successfully."
                if success
                else f"Failed to add source '{name}' (URL might exist)."
            )
            self.source_operation_finished.emit(success, message)
            if success:
                self.load_sources()  # Reload sources
                self.load_categories()  # Reload categories (counts change)
                self.external_settings_changed.emit()  # Notify main window
        except Exception as e:
            logger.error(f"Error adding source '{name}': {e}", exc_info=True)
            self.source_operation_finished.emit(False, f"Error adding source: {e}")

    def update_news_source(
        self, source_id: int, name: str, url: str, category_name: str
    ):
        try:
            success = self._news_service.update_source(
                source_id, name, url, category_name
            )
            message = (
                f"Source '{name}' updated successfully."
                if success
                else f"Failed to update source '{name}'."
            )
            self.source_operation_finished.emit(success, message)
            if success:
                self.load_sources()
                self.load_categories()
                self.external_settings_changed.emit()
        except Exception as e:
            logger.error(f"Error updating source ID {source_id}: {e}", exc_info=True)
            self.source_operation_finished.emit(False, f"Error updating source: {e}")

    def delete_news_source(self, source_id: int, source_name: str):
        try:
            success = self._news_service.delete_source(source_id)
            message = (
                f"Source '{source_name}' deleted successfully."
                if success
                else f"Failed to delete source '{source_name}'."
            )
            self.source_operation_finished.emit(success, message)
            if success:
                self.load_sources()
                self.load_categories()
                self.external_settings_changed.emit()
        except Exception as e:
            logger.error(f"Error deleting source ID {source_id}: {e}", exc_info=True)
            self.source_operation_finished.emit(False, f"Error deleting source: {e}")

    def add_category(self, name: str):
        try:
            new_id = self._news_service.add_category(name)
            success = new_id is not None
            message = (
                f"Category '{name}' added successfully."
                if success
                else f"Failed to add category '{name}' (already exists?)."
            )
            self.category_operation_finished.emit(success, message)
            if success:
                self.load_categories()  # Reload categories
                self.external_settings_changed.emit()
        except Exception as e:
            logger.error(f"Error adding category '{name}': {e}", exc_info=True)
            self.category_operation_finished.emit(False, f"Error adding category: {e}")

    def update_category(self, category_id: int, new_name: str):
        try:
            success = self._news_service.update_category(category_id, new_name)
            message = (
                f"Category updated to '{new_name}'."
                if success
                else f"Failed to update category (name '{new_name}' might exist)."
            )
            self.category_operation_finished.emit(success, message)
            if success:
                self.load_categories()
                self.load_sources()  # Source category names change
                self.external_settings_changed.emit()
        except Exception as e:
            logger.error(
                f"Error updating category ID {category_id}: {e}", exc_info=True
            )
            self.category_operation_finished.emit(
                False, f"Error updating category: {e}"
            )

    def delete_category(self, category_id: int, category_name: str):
        try:
            success = self._news_service.delete_category(category_id)
            message = (
                f"Category '{category_name}' and its sources deleted."
                if success
                else f"Failed to delete category '{category_name}'."
            )
            self.category_operation_finished.emit(success, message)
            if success:
                self.load_categories()
                self.load_sources()
                self.external_settings_changed.emit()
        except Exception as e:
            logger.error(
                f"Error deleting category ID {category_id}: {e}", exc_info=True
            )
            self.category_operation_finished.emit(
                False, f"Error deleting category: {e}"
            )

    def reset_system_settings(self):
        """Resets embedding model, fetch frequency to defaults."""
        # This seems to belong more in SettingService, but controller triggers it
        try:
            if (
                self._setting_service.reset_settings_to_defaults()
            ):  # Assuming this method exists/is added
                self.load_general_settings()  # Reload settings into UI
                self.settings_saved.emit(True, "System settings reset to defaults.")
            else:
                self.settings_saved.emit(
                    False, "Failed to reset system settings in database."
                )
        except Exception as e:
            logger.error(f"Error resetting system settings: {e}", exc_info=True)
            self.error_occurred.emit("Reset Error", f"Failed to reset settings: {e}")
