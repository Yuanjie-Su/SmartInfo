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
        # Maps task_group_id to task data (task IDs and source info)
        self.task_data: Dict[str, Dict[str, Any]] = {}
        logger.info("WebSocket ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, task_group_id: str):
        """
        Accept a new WebSocket connection and associate it with a task_group_id.

        Args:
            websocket: The WebSocket connection to accept and track
            task_group_id: Identifier for the task group this connection is monitoring
        """

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
        for websocket in self.active_connections[task_group_id]:
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error(f"Error sending update to WebSocket: {e}")
                disconnected_websockets.add(websocket)

        # Clean up any disconnected websockets
        for websocket in disconnected_websockets:
            await self.disconnect(websocket, task_group_id)

    async def store_task_data(self, task_group_id: str, data: Dict[str, Any]):
        """
        Store task data associated with a task group.

        Args:
            task_group_id: The task group ID
            data: Dictionary containing task IDs and source information
        """
        self.task_data[task_group_id] = data
        logger.info(f"Stored task data for task_group_id: {task_group_id}")

    def get_task_data(self, task_group_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve task data for a task group.

        Args:
            task_group_id: The task group ID

        Returns:
            Dictionary containing task data or None if not found
        """
        return self.task_data.get(task_group_id)

    def cleanup_task_data(self, task_group_id: str):
        """
        Remove task data for a completed task group.

        Args:
            task_group_id: The task group ID to clean up
        """
        if task_group_id in self.task_data:
            del self.task_data[task_group_id]
            logger.info(f"Cleaned up task data for task_group_id: {task_group_id}")


# Global instance of the connection manager
ws_manager = ConnectionManager()
