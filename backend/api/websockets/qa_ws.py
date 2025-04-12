"""
WebSocket handlers for QA-related operations.
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from backend.api.services.qa_service import QAService
from backend.api.dependencies import get_qa_service
from backend.api.schemas.qa import QARequest, QAProgressUpdate
from backend.api.websockets.connection_manager import connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/qa")
async def qa_websocket(
    websocket: WebSocket, 
    qa_service: QAService = Depends(get_qa_service)
):
    """
    WebSocket endpoint for QA operations.
    
    Handles streaming responses for Q&A interactions with the LLM.
    """
    client_id = str(uuid.uuid4())
    
    try:
        await connection_manager.connect(websocket, client_id, group="qa")
        logger.info(f"QA WebSocket connection established for client {client_id}")
        
        # Send initial connection confirmation
        await connection_manager.send_personal_message(
            {"type": "connection_established", "client_id": client_id}, 
            client_id
        )
        
        # Listen for messages from the client
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                command = message.get("command")
                
                if command == "ask_question":
                    # Parse QA request
                    request_data = message.get("data", {})
                    request = QARequest(**request_data)
                    
                    # Create streaming callback to send partial answers via WebSocket
                    async def stream_callback(partial_text: str, metadata: Optional[Dict[str, Any]] = None):
                        update = QAProgressUpdate(
                            status="in_progress",
                            partial_answer=partial_text,
                            message="Generating answer"
                        )
                        await connection_manager.send_personal_message(
                            {"type": "qa_stream", "data": update.dict()},
                            client_id
                        )
                    
                    # Start streaming QA response
                    # Preserve the core LLM implementation
                    result = await qa_service.ask_question(
                        question=request.question,
                        context_ids=request.context_ids,
                        use_history=request.use_history,
                        stream_callback=stream_callback
                    )
                    
                    # Send completed response
                    update = QAProgressUpdate(
                        status="completed",
                        message="Answer generated",
                        partial_answer=result.get("answer")
                    )
                    await connection_manager.send_personal_message(
                        {"type": "qa_complete", "data": update.dict()},
                        client_id
                    )
                
                elif command == "get_qa_history":
                    # Fetch QA history
                    history = await qa_service.get_history(
                        limit=message.get("data", {}).get("limit", 10),
                        offset=message.get("data", {}).get("offset", 0)
                    )
                    
                    # Send history response
                    await connection_manager.send_personal_message(
                        {"type": "qa_history", "data": history},
                        client_id
                    )
                
                else:
                    logger.warning(f"Unknown command received: {command}")
                    await connection_manager.send_personal_message(
                        {"type": "error", "message": f"Unknown command: {command}"},
                        client_id
                    )
            
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from client {client_id}")
                await connection_manager.send_personal_message(
                    {"type": "error", "message": "Invalid JSON"},
                    client_id
                )
            
            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}")
                await connection_manager.send_personal_message(
                    {"type": "error", "message": str(e)},
                    client_id
                )
    
    except WebSocketDisconnect:
        logger.info(f"QA WebSocket client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Error in QA WebSocket connection: {e}")
    
    finally:
        connection_manager.disconnect(client_id) 