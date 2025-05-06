#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Security Utilities Module
Provides functions for password hashing and JWT handling.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from jose import jwt, JWTError
import bcrypt

# JWT Configuration
# !! IMPORTANT: Replace this with a strong, randomly generated key !!
# Consider loading from environment variables or a config file for production.
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_insecure_default_secret_key_replace_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 6000  # Token validity period


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its hashed version using bcrypt."""
    try:
        plain_password_bytes = plain_password.encode("utf-8")
        hashed_password_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)
    except ValueError:
        # Handles cases where the hash is potentially malformed for bcrypt
        return False
    except Exception:
        # Log unexpected errors if necessary
        # logger.exception("Error during password verification")
        return False


def get_password_hash(password: str) -> str:
    """Hashes a plain password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")  # Store the hash as a string


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a JWT access token.

    Args:
        data: The data payload to encode in the token (e.g., user ID or username).
        expires_delta: Optional timedelta object for token expiration.
                       Defaults to ACCESS_TOKEN_EXPIRE_MINUTES if None.

    Returns:
        The encoded JWT access token as a string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """
    Decodes a JWT access token.

    Args:
        token: The JWT token string to decode.

    Returns:
        The decoded payload as a dictionary if the token is valid and not expired,
        otherwise None. Returns None also if any JWTError occurs.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        # Handles invalid signature, expired token, etc.
        return None
