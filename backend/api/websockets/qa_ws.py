# backend/api/websockets/qa_ws.py
"""
WebSocket handlers for QA-related operations (Streaming).
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

# Corrected service import path if needed
from backend.services.qa_service import QAService
from backend.api.dependencies import get_qa_service
# Schemas used for requests and updates
from backend.api.schemas.qa import QARequest, QAProgressUpdate, QAHistory
from backend.api.websockets.connection_manager import connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/qa")
async def qa_websocket(
    websocket: WebSocket,
    qa_service: QAService = Depends(get_qa_service)
):
    """
    WebSocket endpoint for streaming Q&A operations.

    Receives:
    - {"command": "ask_question", "data": {"question": "...", ...}}
    - {"command": "get_qa_history", "data": {"limit": 50, "offset": 0}}

    Sends:
    - {"type": "connection_established", "client_id": "..."}
    - {"type": "qa_stream", "data": QAProgressUpdate} (partial answers)
    - {"type": "qa_complete", "data": QAProgressUpdate} (final status)
    - {"type": "qa_history", "data": List[QAHistory]}
    - {"type": "error", "message": "..."}
    """
    client_id = str(uuid.uuid4())
    await connection_manager.connect(websocket, client_id, group="qa")
    logger.info(f"QA WebSocket connection established for client {client_id}")

    try:
        # Send connection confirmation
        await connection_manager.send_personal_message(
            {"type": "connection_established", "client_id": client_id},
            client_id
        )

        # Listen for messages
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                command = message.get("command")
                payload = message.get("data", {})

                logger.debug(f"Client {client_id} sent command: {command}, payload: {payload}")

                if command == "ask_question":
                    request = QARequest(**payload) # Validate request data

                    if not request.question or not request.question.strip():
                         await connection_manager.send_personal_message(
                             {"type": "error", "message": "Question cannot be empty"}, client_id
                         )
                         continue

                    logger.info(f"Client {client_id} asking question (streaming): '{request.question[:50]}...'")
                    # Call the streaming service method
                    stream_generator = await qa_service.answer_question_streaming(
                        question=request.question
                        # Note: Current service method doesn't use context_ids or use_history
                    )

                    if stream_generator:
                        full_answer_for_final_update = "" # Collect for final message if needed
                        try:
                            async for chunk in stream_generator:
                                full_answer_for_final_update += chunk
                                update = QAProgressUpdate(
                                    status="in_progress",
                                    partial_answer=chunk,
                                    message="Generating answer..."
                                )
                                await connection_manager.send_personal_message(
                                    {"type": "qa_stream", "data": update.model_dump()},
                                    client_id
                                )
                            # Stream finished successfully (saving handled by service wrapper)
                            final_update = QAProgressUpdate(
                                status="completed",
                                message="Answer generated successfully.",
                                partial_answer=full_answer_for_final_update # Send full answer in final update
                            )
                            await connection_manager.send_personal_message(
                                {"type": "qa_complete", "data": final_update.model_dump()},
                                client_id
                            )
                            logger.info(f"Stream completed for client {client_id}, question: '{request.question[:50]}...'")

                        except Exception as stream_err:
                            logger.error(f"Error processing stream for client {client_id}: {stream_err}", exc_info=True)
                            error_update = QAProgressUpdate(
                                status="failed",
                                error=f"An error occurred during streaming: {stream_err}",
                                message="Stream processing failed."
                            )
                            await connection_manager.send_personal_message(
                                {"type": "qa_error", "data": error_update.model_dump()},
                                client_id
                            )
                    else:
                        # Stream generator failed to initialize
                        logger.error(f"Failed to start stream for client {client_id}, question: '{request.question[:50]}...'")
                        error_update = QAProgressUpdate(
                            status="failed",
                            error="Failed to initiate the question answering stream.",
                            message="Stream initialization failed."
                        )
                        await connection_manager.send_personal_message(
                            {"type": "qa_error", "data": error_update.model_dump()},
                            client_id
                        )

                elif command == "get_qa_history":
                    limit = payload.get("limit", 50)
                    offset = payload.get("offset", 0)
                    logger.info(f"Client {client_id} requesting QA history (limit={limit}, offset={offset})")
                    history_data = await qa_service.get_qa_history(limit=limit, offset=offset)
                    # Ensure data matches the QAHistory schema before sending
                    validated_history = [QAHistory.model_validate(item).model_dump() for item in history_data]
                    await connection_manager.send_personal_message(
                        {"type": "qa_history", "data": validated_history},
                        client_id
                    )

                else:
                    logger.warning(f"Client {client_id} sent unknown command: {command}")
                    await connection_manager.send_personal_message(
                        {"type": "error", "message": f"Unknown command: {command}"},
                        client_id
                    )

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from client {client_id}: {data}")
                await connection_manager.send_personal_message(
                    {"type": "error", "message": "Invalid JSON format received."},
                    client_id
                )
            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}", exc_info=True)
                await connection_manager.send_personal_message(
                    {"type": "error", "message": f"An internal server error occurred: {e}"},
                    client_id
                )

    except WebSocketDisconnect:
        logger.info(f"QA WebSocket client {client_id} disconnected.")
    except Exception as e:
        # Catch errors during initial connect or message loop setup
        logger.error(f"Critical error in QA WebSocket connection for client {client_id}: {e}", exc_info=True)
        # Attempt to inform client if websocket is still available (might fail)
        try:
             await websocket.send_json({"type": "error", "message": "WebSocket connection error."})
        except:
             pass # Ignore if send fails
    finally:
        connection_manager.disconnect(client_id)
        logger.info(f"Cleaned up connection for client {client_id}")