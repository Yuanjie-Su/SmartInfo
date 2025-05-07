#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
WebSocket connection manager for real-time progress updates.
Manages active WebSocket connections for task groups and handles message broadcasting.
"""

import logging
from typing import Dict, List, Set, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for task progress updates.
    Maps task_group_ids to active WebSocket connections.
    Handles connection, disconnection, and broadcasting of progress updates.
    """

    def __init__(self):
        """Initialize an empty connection manager."""
        # Maps task_group_id to a set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Maps task_group_id to task group metadata (user_id, celery_task_ids, etc.)
        self.task_group_metadata: Dict[str, Dict[str, Any]] = {}  # Renamed task_data
        logger.info("WebSocket ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, task_group_id: str):
        """
        Accept a new WebSocket connection and associate it with a task_group_id.

        Args:
            websocket: The WebSocket connection to accept and track
            task_group_id: Identifier for the task group this connection is monitoring
        """
        # Remove the redundant websocket.accept() call
        # Create a new set if this is the first connection for this task_group_id
        if task_group_id not in self.active_connections:
            self.active_connections[task_group_id] = set()

        # Add this connection to the set for this task_group_id
        self.active_connections[task_group_id].add(websocket)
        logger.info(
            f"Client connected to task_group_id: {task_group_id}, active connections: {len(self.active_connections[task_group_id])}"
        )

    async def disconnect(self, websocket: WebSocket, task_group_id: str):
        """
        Remove a WebSocket connection from the tracked connections.

        Args:
            websocket: The WebSocket connection to remove
            task_group_id: The task group ID this connection was monitoring
        """
        # Remove the connection if it exists
        if task_group_id in self.active_connections:
            try:
                self.active_connections[task_group_id].remove(websocket)
                logger.info(
                    f"Client disconnected from task_group_id: {task_group_id}, remaining connections: {len(self.active_connections[task_group_id])}"
                )

                # Clean up empty sets to avoid memory leaks
                if not self.active_connections[task_group_id]:
                    del self.active_connections[task_group_id]
                    logger.info(f"Removed empty task_group_id: {task_group_id}")
            except KeyError:
                # Websocket wasn't in the set, which is fine
                pass

    async def send_update(self, task_group_id: str, data: Dict[str, Any]):
        """
        Send a progress update to all clients monitoring a specific task group.

        Args:
            task_group_id: The task group ID to broadcast to
            data: Dictionary containing the update data to send
        """
        if task_group_id not in self.active_connections:
            logger.warning(f"No active connections for task_group_id: {task_group_id}")
            return

        # Track disconnected websockets to remove later
        disconnected_websockets = set()

        # Send message to all connected clients for this task group
        # Iterate over a copy of the set in case disconnect is called during iteration
        for websocket in set(self.active_connections[task_group_id]):
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error(f"Error sending update to WebSocket: {e}")
                disconnected_websockets.add(websocket)

        # Clean up any disconnected websockets
        for websocket in disconnected_websockets:
            await self.disconnect(websocket, task_group_id)

    async def store_task_group_metadata(
        self, task_group_id: str, data: Dict[str, Any]
    ):  # Renamed method
        """
        Store task group metadata associated with a task group.

        Args:
            task_group_id: The task group ID
            data: Dictionary containing metadata (user_id, celery_task_ids, etc.)
        """
        self.task_group_metadata[task_group_id] = data  # Use renamed dictionary
        logger.info(f"Stored task group metadata for task_group_id: {task_group_id}")

    def get_task_group_metadata(
        self, task_group_id: str
    ) -> Optional[Dict[str, Any]]:  # Renamed method
        """
        Retrieve task group metadata for a task group.

        Args:
            task_group_id: The task group ID

        Returns:
            Dictionary containing task group metadata or None if not found
        """
        return self.task_group_metadata.get(task_group_id)  # Use renamed dictionary

    def cleanup_task_group_data(self, task_group_id: str):  # Renamed method
        """
        Remove task group metadata for a completed task group.

        Args:
            task_group_id: The task group ID to clean up
        """
        if task_group_id in self.task_group_metadata:  # Use renamed dictionary
            del self.task_group_metadata[task_group_id]  # Use renamed dictionary
            logger.info(
                f"Cleaned up task group metadata for task_group_id: {task_group_id}"
            )


# Global instance of the connection manager
ws_manager = ConnectionManager()
