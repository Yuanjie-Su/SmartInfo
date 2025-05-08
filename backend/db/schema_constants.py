# File: /home/cator/project/SmartInfo/backend/db/schema_constants.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Schema Constants Module
Defines database schema constants used across the application
"""

# Table names
NEWS_CATEGORY_TABLE = "news_category"
NEWS_SOURCES_TABLE = "news_sources"
NEWS_TABLE = "news"
API_CONFIG_TABLE = "api_config"
USER_PREFERENCES_TABLE = "user_preferences"
CHATS_TABLE = "chats"
MESSAGES_TABLE = "messages"
USERS_TABLE = "users"
FETCH_HISTORY_TABLE = "fetch_history"  # New Table

# News category table column names
NEWS_CATEGORY_ID = "id"
NEWS_CATEGORY_NAME = "name"
NEWS_CATEGORY_USER_ID = "user_id"

# News sources table column names
NEWS_SOURCE_ID = "id"
NEWS_SOURCE_NAME = "name"
NEWS_SOURCE_URL = "url"
NEWS_SOURCE_CATEGORY_ID = "category_id"
NEWS_SOURCE_USER_ID = "user_id"

# Chat table column names
CHAT_ID = "id"
CHAT_TITLE = "title"
CHAT_CREATED_AT = "created_at"
CHAT_UPDATED_AT = "updated_at"
CHAT_USER_ID = "user_id"

# Message table column names
MESSAGE_ID = "id"
MESSAGE_CHAT_ID = "chat_id"
MESSAGE_SENDER = "sender"
MESSAGE_CONTENT = "content"
MESSAGE_TIMESTAMP = "timestamp"
MESSAGE_SEQUENCE_NUMBER = "sequence_number"

# API Config table column names
API_CONFIG_ID = "id"
API_CONFIG_MODEL = "model"
API_CONFIG_BASE_URL = "base_url"
API_CONFIG_API_KEY = "api_key"
API_CONFIG_CONTEXT = "context"
API_CONFIG_MAX_OUTPUT_TOKENS = "max_output_tokens"
API_CONFIG_DESCRIPTION = "description"
API_CONFIG_CREATED_DATE = "created_date"
API_CONFIG_MODIFIED_DATE = "modified_date"
API_CONFIG_USER_ID = "user_id"

# User Preferences table column names
USER_PREFERENCE_KEY = "config_key"
USER_PREFERENCE_VALUE = "config_value"
USER_PREFERENCE_DESCRIPTION = "description"
USER_PREFERENCE_USER_ID = "user_id"

# News table column names
NEWS_ID = "id"
NEWS_TITLE = "title"
NEWS_URL = "url"
NEWS_SOURCE_NAME = "source_name"
NEWS_CATEGORY_NAME = "category_name"
NEWS_SOURCE_ID = "source_id"
NEWS_CATEGORY_ID = "category_id"
NEWS_SUMMARY = "summary"
NEWS_ANALYSIS = "analysis"
NEWS_DATE = "date"
NEWS_CONTENT = "content"
NEWS_USER_ID = "user_id"

# Users Table
USERS_ID = "id"
USERS_USERNAME = "username"
USERS_HASHED_PASSWORD = "hashed_password"

# Fetch History Table
FETCH_HISTORY_ID = "id"
FETCH_HISTORY_USER_ID = "user_id"
FETCH_HISTORY_SOURCE_ID = "source_id"
FETCH_HISTORY_RECORD_DATE = "record_date"  # DATE type
FETCH_HISTORY_ITEMS_SAVED_TODAY = "items_saved_today"  # Cumulative count for the day
FETCH_HISTORY_LAST_UPDATED_AT = (
    "last_updated_at"  # Timestamp of last update for this record
)
FETCH_HISTORY_LAST_BATCH_TASK_GROUP_ID = (
    "last_batch_task_group_id"  # Optional: Track which task group last updated
)

# Default values
DEFAULT_SEQUENCE_NUMBER = 0
