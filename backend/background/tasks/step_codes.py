#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Step codes for news fetching task progress reporting.
These codes are used to represent different stages of the news fetching process
in a more bandwidth-efficient manner when sending progress updates via WebSocket.
"""

# Task step codes
PREPARING = 1
CRAWLING = 2
EXTRACTING_LINKS = 3
ANALYZING = 4
SAVING = 5
COMPLETE = 6
ERROR = 7
SKIPPED = 8
