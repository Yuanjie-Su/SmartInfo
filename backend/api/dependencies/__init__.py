# backend/api/dependencies/__init__.py

from api.dependencies.dependencies import (
    # Connection
    get_db_connection_context_dependency,
    get_current_active_user,
    # Repositories
    get_api_key_repository,
    get_chat_repository,
    get_message_repository,
    get_news_repository,
    get_news_category_repository,
    get_news_source_repository,
    get_user_preference_repository,
    # Services
    get_chat_service,
    get_news_service,
    get_setting_service,
)
