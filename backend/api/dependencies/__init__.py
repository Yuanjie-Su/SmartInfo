# backend/api/dependencies/__init__.py

from backend.api.dependencies.dependencies import (
    # Connection
    get_db_connection_dependency,
    # LLM Pool
    set_global_llm_pool,
    get_llm_pool_dependency,
    # Repositories
    get_api_key_repository,
    get_chat_repository,
    get_message_repository,
    get_news_repository,
    get_news_category_repository,
    get_news_source_repository,
    get_system_config_repository,
    # Services
    get_chat_service,
    get_news_service,
    get_setting_service,
)
