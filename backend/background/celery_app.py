#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Celery Application Configuration
Configures Celery to use Redis as both message broker and result backend.
Used for background task processing of news fetching and analysis.
"""

import os
from celery import Celery
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Get Redis URL from environment or use default
BROKER_URL = os.getenv("REDIS_BROKER_URL", "redis://127.0.0.1:6379/0")
BACKEND_URL = os.getenv("REDIS_BACKEND_URL", "redis://127.0.0.1:6379/1")

# Create the Celery app
celery_app = Celery(
    "background",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=["background.tasks.news_tasks"],
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # Prevents worker from fetching too many tasks at once
)


# This allows you to run celery with: celery -A backend.background.celery_app worker --loglevel=info
if __name__ == "__main__":
    celery_app.start()
