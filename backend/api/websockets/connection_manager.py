"""
WebSocket connection manager for the SmartInfo application.
"""

from typing import Dict, List, Optional, Set
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.
    """
    
    def __init__(self):
        # active_connections: client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # client_groups: group_name -> set of client_ids
        self.client_groups: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, group: Optional[str] = None) -> None:
        """
        Accept a new WebSocket connection and register it.
        
        Args:
            websocket: The WebSocket connection to register
            client_id: Unique identifier for the client
            group: Optional group to assign the client to
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
        
        if group:
            self.add_to_group(client_id, group)
    
    def disconnect(self, client_id: str) -> None:
        """
        Remove a connection when it's closed.
        
        Args:
            client_id: ID of the client to disconnect
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
            
            # Remove from all groups
            for group_name, clients in list(self.client_groups.items()):
                if client_id in clients:
                    clients.remove(client_id)
                if not clients:
                    del self.client_groups[group_name]
    
    def add_to_group(self, client_id: str, group: str) -> None:
        """
        Add a client to a group for targeted messaging.
        
        Args:
            client_id: ID of the client to add
            group: Group name to add the client to
        """
        if group not in self.client_groups:
            self.client_groups[group] = set()
        self.client_groups[group].add(client_id)
        logger.debug(f"Added client {client_id} to group {group}")
    
    def remove_from_group(self, client_id: str, group: str) -> None:
        """
        Remove a client from a group.
        
        Args:
            client_id: ID of the client to remove
            group: Group name to remove the client from
        """
        if group in self.client_groups and client_id in self.client_groups[group]:
            self.client_groups[group].remove(client_id)
            if not self.client_groups[group]:
                del self.client_groups[group]
            logger.debug(f"Removed client {client_id} from group {group}")
    
    async def send_personal_message(self, message: dict, client_id: str) -> bool:
        """
        Send a message to a specific client.
        
        Args:
            message: Dictionary to send as JSON
            client_id: ID of the client to send to
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if client_id not in self.active_connections:
            logger.warning(f"Attempted to send message to non-existent client {client_id}")
            return False
        
        try:
            websocket = self.active_connections[client_id]
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending message to client {client_id}: {e}")
            return False
    
    async def send_personal_text(self, message: str, client_id: str) -> bool:
        """
        Send a text message to a specific client.
        
        Args:
            message: Text message to send
            client_id: ID of the client to send to
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if client_id not in self.active_connections:
            logger.warning(f"Attempted to send text to non-existent client {client_id}")
            return False
        
        try:
            websocket = self.active_connections[client_id]
            await websocket.send_text(message)
            return True
        except Exception as e:
            logger.error(f"Error sending text to client {client_id}: {e}")
            return False
    
    async def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Dictionary to send as JSON
        """
        disconnected_clients = []
        
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)
    
    async def broadcast_to_group(self, message: dict, group: str) -> None:
        """
        Broadcast a message to all clients in a specific group.
        
        Args:
            message: Dictionary to send as JSON
            group: Group name to broadcast to
        """
        if group not in self.client_groups:
            logger.warning(f"Attempted to broadcast to non-existent group {group}")
            return
        
        disconnected_clients = []
        
        for client_id in self.client_groups[group]:
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id} in group {group}: {e}")
                    disconnected_clients.append(client_id)
            else:
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)


# Global connection manager instance
connection_manager = ConnectionManager() 