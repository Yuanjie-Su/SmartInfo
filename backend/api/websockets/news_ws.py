"""
WebSocket handlers for news-related operations.
"""

import logging
import json
import uuid
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from backend.services.news_service import NewsService
from backend.api.dependencies import get_news_service
from backend.api.schemas.news import FetchNewsRequest, NewsProgressUpdate
from backend.api.websockets.connection_manager import connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/news")
async def news_websocket(
    websocket: WebSocket, 
    news_service: NewsService = Depends(get_news_service)
):
    """
    WebSocket endpoint for news operations.
    
    Handles streaming updates for news fetching and analysis operations.
    """
    client_id = str(uuid.uuid4())
    
    try:
        await connection_manager.connect(websocket, client_id, group="news")
        logger.info(f"News WebSocket connection established for client {client_id}")
        
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
                
                if command == "fetch_news":
                    # Parse fetch news request
                    request_data = message.get("data", {})
                    request = FetchNewsRequest(**request_data)
                    
                    # Create progress callback to send updates via WebSocket
                    async def progress_callback(progress_data: Dict[str, Any]):
                        update = NewsProgressUpdate(**progress_data)
                        await connection_manager.send_personal_message(
                            {"type": "news_progress", "data": update.dict()},
                            client_id
                        )
                    
                    # Start news fetching in background task
                    await news_service.fetch_news_from_sources(
                        source_ids=request.source_ids,
                        max_articles_per_source=request.max_articles_per_source,
                        progress_callback=progress_callback
                    )
                
                elif command == "analyze_news":
                    # Similar implementation for news analysis
                    news_ids = message.get("data", {}).get("news_ids", [])
                    analysis_type = message.get("data", {}).get("analysis_type", "summary")
                    
                    # Create progress callback for analysis
                    async def analysis_progress_callback(progress_data: Dict[str, Any]):
                        update = NewsProgressUpdate(**progress_data)
                        await connection_manager.send_personal_message(
                            {"type": "analysis_progress", "data": update.dict()},
                            client_id
                        )
                    
                    # Start analysis in background
                    await news_service.analyze_news(
                        news_ids=news_ids,
                        analysis_type=analysis_type,
                        progress_callback=analysis_progress_callback
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
        logger.info(f"News WebSocket client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Error in news WebSocket connection: {e}")
    
    finally:
        connection_manager.disconnect(client_id) 