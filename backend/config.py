# backend/config.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Application Configuration Module
- Loads settings from environment variables and a user preference table in the database.
- Provides access to configuration values throughout the application.
"""

import logging
import os
import dotenv
import sys
from typing import Any, Optional

dotenv.load_dotenv()

# Configure module-level logger
logger = logging.getLogger(__name__)


class AppConfig:
    """
    Manages application configuration settings loaded from environment variables.
    """

    def __init__(self):
        """Initialize configuration."""
        # --- Load Database Configuration from Environment Variables ---
        self._db_user = os.getenv("DB_USER")
        self._db_password = os.getenv("DB_PASSWORD")
        self._db_name = os.getenv("DB_NAME")
        self._db_host = os.getenv("DB_HOST", "localhost")
        self._db_port = os.getenv("DB_PORT", "5432")  # Default PostgreSQL port

        # --- Validate Required Database Configuration ---
        required_db_vars = {
            "DB_USER": self._db_user,
            "DB_PASSWORD": self._db_password,
            "DB_NAME": self._db_name,
        }
        missing_vars = [key for key, value in required_db_vars.items() if not value]

        if missing_vars:
            error_message = (
                f"Missing required database environment variables: {', '.join(missing_vars)}. "
                "Please set them in your .env file or environment."
            )
            logger.critical(error_message)
            sys.exit(1)

        logger.info(
            f"Database connection configured for: postgresql://{self._db_user}:***@{self._db_host}:{self._db_port}/{self._db_name}"
        )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value. Only supports DB connection keys.
        For other keys, returns the provided default.
        """
        db_connection_keys = {
            "DB_USER": self._db_user,
            "DB_PASSWORD": self._db_password,
            "DB_NAME": self._db_name,
            "DB_HOST": self._db_host,
            "DB_PORT": self._db_port,
        }
        if key in db_connection_keys:
            logger.debug(f"Config: Returning direct attribute for '{key}'.")
            # Attempt to return correct type for port
            if key == "DB_PORT":
                try:
                    return int(db_connection_keys[key])
                except (ValueError, TypeError):
                    logger.warning(
                        f"Could not convert DB_PORT '{db_connection_keys[key]}' to int. Returning as string."
                    )
                    return db_connection_keys[key]  # Fallback to string
            return db_connection_keys[key]

        # For any other key, return the provided default
        logger.debug(
            f"Config: Key '{key}' not a DB config key. Returning provided default."
        )
        return default

    # --- Properties for Database Connection ---
    @property
    def db_user(self) -> Optional[str]:
        return self._db_user

    @property
    def db_password(self) -> Optional[str]:
        return self._db_password

    @property
    def db_name(self) -> Optional[str]:
        return self._db_name

    @property
    def db_host(self) -> str:
        return self._db_host

    @property
    def db_port(self) -> int:
        try:
            return int(self._db_port)
        except (ValueError, TypeError):
            logger.warning(
                f"DB_PORT '{self._db_port}' is not a valid integer. Defaulting to 5432."
            )
            return 5432  # Return default int port if conversion fails


# Create a single, globally accessible instance of AppConfig
config = AppConfig()
