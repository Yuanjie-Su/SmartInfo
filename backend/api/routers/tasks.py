#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Router for task management and monitoring endpoints.
Provides WebSocket connection for real-time task progress updates.
"""

import logging
import asyncio
import json
from starlette.websockets import WebSocketState
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Path, Query, Depends
from celery.result import AsyncResult
from typing import Optional
import redis.asyncio as redis

from core.ws_manager import ws_manager
from core.security import decode_access_token
from db.repositories.user_repository import UserRepository
from api.dependencies.dependencies import get_user_repository, get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


async def redis_message_listener(
    websocket: WebSocket, pubsub: redis.client.PubSub, task_group_id: str
):
    """
    Continuously listen for messages from Redis PubSub channel and forward them to WebSocket clients.

    Args:
        websocket: The WebSocket connection object
        pubsub: Redis PubSub instance already subscribed to the channel
        task_group_id: Task group ID for logging and identifying the connection
    """
    try:
        while True:
            # Wait for messages with a timeout to prevent blocking forever
            message = await pubsub.get_message(timeout=1.0)
            if message is not None and message["type"] == "message":
                try:
                    # Parse the JSON message from Redis
                    update_data = json.loads(message["data"])

                    # Check connection state before sending
                    if websocket.client_state == WebSocketState.CONNECTED:
                        # Forward the message to WebSocket clients
                        await ws_manager.send_update(task_group_id, update_data)
                    else:
                        logger.warning(
                            f"WebSocket for {task_group_id} disconnected before sending update: {update_data.get('event')}"
                        )
                        break  # Exit the loop if WebSocket is disconnected

                    # Cleanup task group data after sending the final message
                    if update_data.get("event") == "overall_batch_completed":
                        logger.info(
                            f"Overall completion message received for {task_group_id}. Cleaning up metadata."
                        )
                        ws_manager.cleanup_task_group_data(task_group_id)
                        # Note: We continue the listener to handle any disconnection gracefully

                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to decode JSON message from Redis for {task_group_id}: {message['data']}"
                    )
                except Exception as send_err:
                    logger.error(
                        f"Error sending WebSocket update for {task_group_id}: {send_err}"
                    )

            # Short sleep to prevent CPU spinning
            await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        logger.info(f"Redis listener for {task_group_id} cancelled.")
    except redis.RedisError as redis_err:
        logger.error(f"Redis error in listener for {task_group_id}: {redis_err}")
    except Exception as e:
        logger.exception(f"Unexpected error in Redis listener for {task_group_id}: {e}")
    finally:
        logger.info(f"Exiting Redis listener loop for {task_group_id}.")


@router.websocket("/ws/tasks/group/{task_group_id}")
async def websocket_task_group_endpoint(
    websocket: WebSocket,
    task_group_id: str = Path(..., description="Task group ID to monitor"),
    token: Optional[str] = Query(
        None, description="JWT access token for authentication"
    ),
):
    """
    WebSocket endpoint for monitoring task group progress in real-time.

    Clients connect to this endpoint with a task_group_id and receive
    progress updates for all tasks within that group via Redis Pub/Sub.

    Args:
        websocket: The WebSocket connection
        task_group_id: Task group ID to monitor
        token: JWT access token for authentication
    """
    pubsub = None
    listener_task = None
    channel_name = f"task_progress:{task_group_id}"

    try:
        # Accept the connection immediately
        await websocket.accept()

        # Get dependencies manually since FastAPI's dependency injection might
        # not handle WebSocket context correctly
        user_repo = await get_user_repository()

        # Get Redis client from app state
        app = websocket.scope["app"]
        if not hasattr(app.state, "redis_client"):
            logger.error("Redis client not available in app state")
            await websocket.send_json(
                {"event": "error", "message": "Redis client not available"}
            )
            await websocket.close(code=1011, reason="Internal server error")
            return

        redis_client = app.state.redis_client

        # 验证令牌
        if not token:
            logger.warning(
                f"WebSocket connection attempt without token for task_group_id: {task_group_id}"
            )
            await websocket.close(code=4001, reason="Authentication required")
            return

        # 解码令牌以验证身份
        payload = decode_access_token(token)
        if not payload:
            logger.warning(
                f"WebSocket connection attempt with invalid token for task_group_id: {task_group_id}"
            )
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

        # 获取用户ID并验证用户存在
        user_id = payload.get("sub")
        if not user_id:
            logger.warning(
                f"WebSocket connection attempt with token missing user ID for task_group_id: {task_group_id}"
            )
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

        # 验证用户存在
        user = await user_repo.get_user_by_id(int(user_id))
        if not user:
            logger.warning(
                f"WebSocket connection attempt with non-existent user ID: {user_id} for task_group_id: {task_group_id}"
            )
            await websocket.close(code=4001, reason="User not found")
            return

        # Get task group metadata and verify user has access
        task_group_metadata = ws_manager.get_task_group_metadata(
            task_group_id
        )  # Use new ws_manager method
        if not task_group_metadata:
            logger.warning(
                f"No task group metadata found for task_group_id: {task_group_id}"
            )
            await websocket.send_json(
                {
                    "event": "error",
                    "task_group_id": task_group_id,
                    "message": "No task group found for the specified ID.",
                }
            )
            await websocket.close(code=4004, reason="Task group not found")
            return

        # Verify task group ownership
        group_user_id = task_group_metadata.get("user_id")
        if group_user_id != int(user_id):
            logger.warning(
                f"Unauthorized WebSocket access attempt: User {user_id} tried to access task group for user {group_user_id} (task_group_id: {task_group_id})"
            )
            await websocket.close(code=4003, reason="Unauthorized access to task group")
            return

        # All checks passed, register the WebSocket connection with the manager
        await ws_manager.connect(websocket, task_group_id)
        logger.info(
            f"WebSocket connection established for task_group_id: {task_group_id}, user_id: {user_id}"
        )

        # Initialize Redis PubSub and subscribe to the channel
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(channel_name)
        logger.info(f"Subscribed to Redis channel: {channel_name}")

        # Start the background listener task
        listener_task = asyncio.create_task(
            redis_message_listener(websocket, pubsub, task_group_id)
        )
        logger.info(f"Started Redis listener task for {task_group_id}")

        # Keep the connection alive until disconnected
        try:
            while websocket.client_state != WebSocketState.DISCONNECTED:
                await asyncio.sleep(10)  # Check state less frequently
        except WebSocketDisconnect:
            logger.info(
                f"WebSocket client disconnected explicitly from task_group_id: {task_group_id}"
            )

    except Exception as e:
        logger.error(
            f"Unhandled exception in websocket_task_group_endpoint for {task_group_id}: {e}",
            exc_info=True,
        )
        # Attempt to send a final error message before closing
        try:
            await websocket.send_json(
                {
                    "event": "error",
                    "task_group_id": task_group_id,
                    "message": f"Internal server error: {str(e)}",
                }
            )
        except Exception:
            pass  # Ignore errors sending error message

    finally:
        logger.warning(
            f"Executing finally block for task_group_id: {task_group_id}. Cleaning up connection."
        )

        # Cancel the listener task if it's running
        if listener_task and not listener_task.done():
            try:
                listener_task.cancel()
                try:
                    await listener_task  # Wait for cancellation
                except asyncio.CancelledError:
                    logger.info(
                        f"Redis listener task for {task_group_id} successfully cancelled."
                    )
                except Exception as e:
                    logger.error(f"Error waiting for listener task cancellation: {e}")
            except Exception as e:
                logger.error(f"Error cancelling Redis listener task: {e}")

        # Unsubscribe and close PubSub
        if pubsub:
            try:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
                logger.info(f"Unsubscribed from Redis channel: {channel_name}")
            except Exception as e:
                logger.error(f"Error closing Redis PubSub: {e}")

        # Disconnect from the WebSocket manager
        await ws_manager.disconnect(websocket, task_group_id)
        logger.info(f"WebSocket disconnected from manager for {task_group_id}")

        # Ensure metadata cleanup if final message wasn't received
        if ws_manager.get_task_group_metadata(task_group_id):
            logger.warning(
                f"WebSocket for {task_group_id} disconnected before cleanup triggered by final message. Cleaning up metadata now."
            )
            ws_manager.cleanup_task_group_data(task_group_id)
