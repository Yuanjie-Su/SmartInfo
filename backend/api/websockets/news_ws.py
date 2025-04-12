# backend/api/websockets/news_ws.py
"""
WebSocket handler for receiving news fetch progress updates.
"""

import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

# Use the globally managed instance
from backend.api.websockets.connection_manager import connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Define the group name used by the news_router's fetch callbacks
NEWS_FETCH_PROGRESS_GROUP = "news_fetch_progress"

@router.websocket("/ws/news_progress")
async def news_progress_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for clients to connect and receive news fetch progress.

    Clients connect here, join the 'news_fetch_progress' group, and listen
    for messages broadcasted by the news fetching process triggered via the
    HTTP POST /api/news/fetch endpoint.

    Sends:
    - {"type": "connection_established", "client_id": "..."}
    - Messages broadcasted to NEWS_FETCH_PROGRESS_GROUP (types: "news_progress", "stream_chunk")
    - {"type": "error", "message": "..."} (e.g., connection issues)

    Receives:
    - Optional client messages (e.g., ping, though none handled currently).
    """
    client_id = str(uuid.uuid4())

    try:
        # Accept connection and add to the progress group
        await connection_manager.connect(websocket, client_id, group=NEWS_FETCH_PROGRESS_GROUP)
        logger.info(f"News Progress WebSocket client {client_id} connected and added to group '{NEWS_FETCH_PROGRESS_GROUP}'.")

        # Send connection confirmation
        await connection_manager.send_personal_message(
            {"type": "connection_established", "client_id": client_id},
            client_id
        )

        # Keep the connection alive and listen for potential client messages (optional)
        # This loop primarily keeps the connection open to receive broadcasts.
        while True:
            # We aren't expecting specific commands here, just listening for broadcasts.
            # receive_text() will raise WebSocketDisconnect if the client closes.
            # You could add a timeout or periodic ping/pong if needed.
            data = await websocket.receive_text()
            logger.debug(f"Received text from news progress client {client_id}: {data} (ignoring)")
            # Optional: Handle ping or other client messages if defined
            # if data == "ping": await websocket.send_text("pong")


    except WebSocketDisconnect:
        logger.info(f"News Progress WebSocket client {client_id} disconnected.")
    except Exception as e:
        # Catch errors during connect or the listen loop
        logger.error(f"Error in News Progress WebSocket for client {client_id}: {e}", exc_info=True)
        # Attempt to inform client if websocket is still available
        try:
             await websocket.send_json({"type": "error", "message": "WebSocket connection error."})
        except:
             pass
    finally:
        # Ensure the client is removed from the manager and group on disconnect/error
        connection_manager.disconnect(client_id)
        logger.info(f"Cleaned up News Progress WebSocket connection for client {client_id}")