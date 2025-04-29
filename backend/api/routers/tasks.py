#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Router for task management and monitoring endpoints.
Provides WebSocket connection for real-time task progress updates.
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Path

from backend.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/tasks/{task_group_id}")
async def websocket_task_endpoint(
    websocket: WebSocket,
    task_group_id: str = Path(
        ..., description="Unique identifier for the task group to monitor"
    ),
):
    """
    WebSocket endpoint for monitoring task progress in real-time.

    Clients connect to this endpoint with a task_group_id and receive
    progress updates for all tasks associated with that group ID.

    Args:
        websocket: The WebSocket connection
        task_group_id: Unique identifier for the task group to monitor
    """
    try:
        # Accept and register the WebSocket connection
        await ws_manager.connect(websocket, task_group_id)
        logger.info(
            f"WebSocket connection established for task_group_id: {task_group_id}"
        )

        # Send initial connection confirmation
        await websocket.send_json(
            {
                "event": "connected",
                "task_group_id": task_group_id,
                "message": "WebSocket connection established. Waiting for task updates.",
            }
        )

        # Keep the connection alive until client disconnects
        try:
            # Wait for client to disconnect
            while True:
                # This will block until the client sends a message or disconnects
                # We don't actually need to process incoming messages for this use case,
                # but we need to listen for them to detect disconnection
                data = await websocket.receive_text()
                # Just log it for now
                logger.debug(f"Received message from client: {data}")
        except WebSocketDisconnect:
            # Client disconnected, clean up
            logger.info(
                f"WebSocket client disconnected from task_group_id: {task_group_id}"
            )
        finally:
            # Ensure we clean up the connection when it ends
            await ws_manager.disconnect(websocket, task_group_id)

    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {e}", exc_info=True)
        # Attempt to disconnect if we haven't already
        try:
            await ws_manager.disconnect(websocket, task_group_id)
        except Exception:
            # Ignore errors in cleanup during an error
            pass
