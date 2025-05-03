#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Router for task management and monitoring endpoints.
Provides WebSocket connection for real-time task progress updates.
"""

import logging
import asyncio
from starlette.websockets import WebSocketState
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Path
from celery.result import AsyncResult

from core.ws_manager import ws_manager
from background.tasks.news_tasks import process_source_url_task_celery

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
    This endpoint polls Celery task states and sends updates to the client.

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

        # Send initial connection confirmation - REMOVED
        # await websocket.send_json({"event": "connected", "task_group_id": task_group_id, "message": "WebSocket connection established. Starting task monitoring."})

        # Get task data for this task group
        task_data = ws_manager.get_task_data(task_group_id)
        if not task_data or not task_data.get("task_ids"):
            logger.warning(f"No task data found for task_group_id: {task_group_id}")
            await websocket.send_json(
                {
                    "event": "error",
                    "task_group_id": task_group_id,
                    "message": "No tasks found for the specified task group ID.",
                }
            )
            return

        # Extract task IDs and source information
        task_ids = task_data.get("task_ids", [])
        source_info = task_data.get("source_info", {})

        logger.info(
            f"Monitoring {len(task_ids)} tasks for task_group_id: {task_group_id}"
        )

        # Task tracking
        active_tasks = set(task_ids)
        completed_tasks = set()
        failed_tasks = set()

        # Keep the connection alive and periodically check task states
        try:
            while (
                active_tasks and websocket.client_state != WebSocketState.DISCONNECTED
            ):
                logger.info(
                    f"Task group {task_group_id}: Checking {len(active_tasks)} active tasks..."
                )
                # Check each active task's state
                for task_id in list(active_tasks):
                    try:
                        logger.debug(f"Checking task ID: {task_id}")
                        # Get task result object
                        task_result = AsyncResult(task_id)
                        task_state = task_result.state
                        task_info = task_result.info
                        logger.debug(
                            f"Task {task_id} state: {task_state}, info: {task_info}"
                        )

                        # Get source info for this task
                        source_id = source_info.get(task_id, {}).get("source_id", None)
                        source_name = source_info.get(task_id, {}).get(
                            "source_name", "Unknown Source"
                        )

                        # Process based on task state
                        if task_state in ("PROGRESS", "STARTED") and isinstance(
                            task_info, dict
                        ):
                            # Task is still running, get progress info
                            # Include source information with the update
                            update_data = {
                                "source_id": source_id,
                                "source_name": source_name,
                                "status": "processing",
                                "step": task_info.get("step", "processing"),
                                "progress": task_info.get("progress", 0),
                                "message": task_info.get("message", "Processing..."),
                            }

                            # Add items_saved if available
                            if "items_saved" in task_info:
                                update_data["items_saved"] = task_info["items_saved"]

                            # Send update to client
                            logger.debug(
                                f"Sending update for task {task_id}: {update_data}"
                            )
                            await websocket.send_json(update_data)
                            logger.debug(f"Update sent for task {task_id}")

                        elif task_state == "SUCCESS":
                            # Task completed successfully
                            task_result_data = task_result.get() or {}

                            # Format completion message
                            update_data = {
                                "source_id": source_id,
                                "source_name": source_name,
                                "status": "complete",
                                "step": "complete",
                                "progress": 100,
                                "message": task_result_data.get(
                                    "message", "Task completed successfully."
                                ),
                            }

                            # Add items_saved if available
                            if "items_saved" in task_result_data:
                                update_data["items_saved"] = task_result_data[
                                    "items_saved"
                                ]

                            # Send final update
                            logger.debug(
                                f"Sending SUCCESS update for task {task_id}: {update_data}"
                            )
                            await websocket.send_json(update_data)
                            logger.debug(f"SUCCESS Update sent for task {task_id}")

                            # Mark task as completed
                            active_tasks.remove(task_id)
                            completed_tasks.add(task_id)

                        elif task_state in ("FAILURE", "REVOKED"):
                            # Task failed
                            error_message = "Task failed"
                            if hasattr(task_result, "traceback"):
                                error_message = f"Task failed: {task_result.traceback}"

                            # Send error update
                            update_data = {
                                "source_id": source_id,
                                "source_name": source_name,
                                "status": "error",
                                "step": "error",
                                "progress": 0,
                                "message": error_message,
                            }

                            logger.debug(
                                f"Sending FAILURE update for task {task_id}: {update_data}"
                            )
                            await websocket.send_json(update_data)
                            logger.debug(f"FAILURE Update sent for task {task_id}")

                            # Mark task as failed
                            active_tasks.remove(task_id)
                            failed_tasks.add(task_id)

                    except Exception as loop_error:
                        logger.error(
                            f"Error processing task {task_id} in WS loop: {loop_error}",
                            exc_info=True,
                        )
                        # 决定是否将错误通知前端或直接断开
                        await websocket.send_json(
                            {
                                "event": "error",
                                "task_id": task_id,
                                "message": f"Internal server error while monitoring task {task_id}.",
                            }
                        )
                        # 可以选择移除任务或继续监控其他任务
                        if task_id in active_tasks:
                            active_tasks.remove(task_id)
                        failed_tasks.add(task_id)  # 标记为失败

                # If all tasks are done, send final summary - REMOVED
                if not active_tasks:
                    logger.info(f"All tasks completed for group {task_group_id}.")
                    # await websocket.send_json({"event": "group_complete", "task_group_id": task_group_id, "total_sources": total_tasks, "successful": len(completed_tasks), "failed": len(failed_tasks), "message": f"All tasks completed. {len(completed_tasks)} successful, {len(failed_tasks)} failed."})
                    # Clean up task data
                    ws_manager.cleanup_task_data(task_group_id)
                    break

                # Wait before checking again (1 second)
                await asyncio.sleep(1)
                logger.debug(f"Task group {task_group_id}: Loop finished iteration.")

        except WebSocketDisconnect:
            logger.info(
                f"WebSocket client disconnected explicitly from task_group_id: {task_group_id}"
            )
        except Exception as e:
            logger.error(
                f"Unhandled exception in websocket_task_endpoint for {task_group_id}: {e}",
                exc_info=True,
            )
        finally:
            logger.warning(
                f"Executing finally block for task_group_id: {task_group_id}. Cleaning up connection."
            )
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
