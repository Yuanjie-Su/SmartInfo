# File: /home/cator/project/SmartInfo/backend/db/schema_constants.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Schema Constants Module
Defines database schema constants used across the application
"""

# Table names
USERS_TABLE = "users"
NEWS_CATEGORY_TABLE = "news_category"
NEWS_SOURCES_TABLE = "news_sources"
NEWS_TABLE = "news"
API_CONFIG_TABLE = "api_config"
USER_PREFERENCES_TABLE = "user_preferences"
CHATS_TABLE = "chats"
MESSAGES_TABLE = "messages"
FETCH_HISTORY_TABLE = "fetch_history"

# --- Table Column Constants Grouped by Class ---


class Users:
    TABLE_NAME = USERS_TABLE
    ID = "id"
    USERNAME = "username"
    HASHED_PASSWORD = "hashed_password"


class NewsCategory:
    TABLE_NAME = NEWS_CATEGORY_TABLE
    ID = "id"
    NAME = "name"
    USER_ID = "user_id"


class NewsSource:
    TABLE_NAME = NEWS_SOURCES_TABLE
    ID = "id"
    NAME = "name"
    URL = "url"
    CATEGORY_ID = "category_id"
    USER_ID = "user_id"


class News:
    TABLE_NAME = NEWS_TABLE
    ID = "id"
    TITLE = "title"
    URL = "url"
    SOURCE_NAME = "source_name"
    CATEGORY_NAME = "category_name"
    SOURCE_ID = "source_id"
    CATEGORY_ID = "category_id"
    SUMMARY = "summary"
    ANALYSIS = "analysis"
    DATE = "date"
    CONTENT = "content"
    USER_ID = "user_id"
    TASK_GROUP_ID = "task_group_id"


class ApiConfig:
    TABLE_NAME = API_CONFIG_TABLE
    ID = "id"
    MODEL = "model"
    BASE_URL = "base_url"
    API_KEY = "api_key"
    CONTEXT = "context"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    DESCRIPTION = "description"
    CREATED_DATE = "created_date"
    MODIFIED_DATE = "modified_date"
    USER_ID = "user_id"


class UserPreferences:
    TABLE_NAME = USER_PREFERENCES_TABLE
    KEY = "config_key"
    VALUE = "config_value"
    DESCRIPTION = "description"
    USER_ID = "user_id"


class Chats:
    TABLE_NAME = CHATS_TABLE
    ID = "id"
    TITLE = "title"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    USER_ID = "user_id"


class Messages:
    TABLE_NAME = MESSAGES_TABLE
    ID = "id"
    CHAT_ID = "chat_id"
    SENDER = "sender"
    CONTENT = "content"
    TIMESTAMP = "timestamp"
    SEQUENCE_NUMBER = "sequence_number"
    DEFAULT_SEQUENCE_NUMBER = 0


class FetchHistory:
    TABLE_NAME = FETCH_HISTORY_TABLE
    ID = "id"
    USER_ID = "user_id"
    SOURCE_ID = "source_id"
    RECORD_DATE = "record_date"
    ITEMS_SAVED_TODAY = "items_saved_today"
    LAST_UPDATED_AT = "last_updated_at"
    LAST_BATCH_TASK_GROUP_ID = "last_batch_task_group_id"
