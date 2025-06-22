from typing import Dict, List, Set, Optional, Union, Any
from fastapi import WebSocket, WebSocketDisconnect, Depends, status
import json
import asyncio
import logging
from sqlalchemy.orm import Session
import time

from . import models, schemas, auth, crud
from .database import get_db, get_db_context
from .redis_client import redis_client

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # All active connections: user_id -> {channel_id -> WebSocket}
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}
        # Channel subscribers: channel_id -> set(user_id)
        self.channel_subscribers: Dict[int, Set[int]] = {}
        # Lock for async operations
        self.lock = asyncio.Lock()
        # Track connection status
        self.connection_status: Dict[int, Dict[int, bool]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: int, channel_id: int):
        """Connect a user to a channel via WebSocket"""
        try:
            await websocket.accept()
            
            async with self.lock:
                # Initialize user's connections dict if needed
                if user_id not in self.active_connections:
                    self.active_connections[user_id] = {}
                    self.connection_status[user_id] = {}
                
                # Add this connection to user's connections
                self.active_connections[user_id][channel_id] = websocket
                self.connection_status[user_id][channel_id] = True
                
                # Initialize channel's subscribers set if needed
                if channel_id not in self.channel_subscribers:
                    self.channel_subscribers[channel_id] = set()
                    
                # Add user to channel subscribers
                self.channel_subscribers[channel_id].add(user_id)
            
            # Send a confirmation message to the user
            await websocket.send_json({
                "message_type": "connection_status",
                "data": {
                    "status": "connected",
                    "channel_id": channel_id,
                    "timestamp": time.time()
                }
            })
                
            # Set up Redis subscription if first subscriber to this channel
            if len(self.channel_subscribers[channel_id]) == 1:
                # Subscribe to Redis channel
                redis_channel = f"chat:{channel_id}"
                
                def redis_callback(data: Dict[str, Any]):
                    # Use create_task to run the async function in the event loop
                    asyncio.create_task(self.broadcast_to_channel(channel_id, data))
                    
                redis_client.subscribe(redis_channel, redis_callback)
                
            # Track user as online
            redis_client.add_to_set("online_users", str(user_id))
            
            logger.info(f"User {user_id} connected to channel {channel_id}")
            
        except Exception as e:
            logger.error(f"Error connecting user {user_id} to channel {channel_id}: {str(e)}")
            try:
                if not websocket.client_state.DISCONNECTED:
                    await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            except:
                pass
        
    async def disconnect(self, user_id: int, channel_id: int):
        """Disconnect a user from a channel"""
        try:
            async with self.lock:
                # Update connection status
                if user_id in self.connection_status and channel_id in self.connection_status[user_id]:
                    self.connection_status[user_id][channel_id] = False
                
                # Remove the connection
                if user_id in self.active_connections and channel_id in self.active_connections[user_id]:
                    del self.active_connections[user_id][channel_id]
                    
                    # Clean up if user has no more connections
                    if not self.active_connections[user_id]:
                        del self.active_connections[user_id]
                        del self.connection_status[user_id]
                        redis_client.remove_from_set("online_users", str(user_id))
                    
                    # Remove from channel subscribers
                    if channel_id in self.channel_subscribers:
                        self.channel_subscribers[channel_id].remove(user_id)
                        
                        # If no more subscribers, unsubscribe from Redis
                        if not self.channel_subscribers[channel_id]:
                            redis_client.unsubscribe(f"chat:{channel_id}")
                            del self.channel_subscribers[channel_id]
                            
                    logger.info(f"User {user_id} disconnected from channel {channel_id}")
        except Exception as e:
            logger.error(f"Error disconnecting user {user_id} from channel {channel_id}: {str(e)}")
    
    async def send_personal_message(self, message: Dict, user_id: int, channel_id: int):
        """Send a message to a specific user in a specific channel"""
        try:
            if (user_id in self.active_connections and 
                channel_id in self.active_connections[user_id]):
                websocket = self.active_connections[user_id][channel_id]
                if not websocket.client_state.DISCONNECTED:
                    await websocket.send_json(message)
                    return True
                else:
                    # WebSocket is disconnected but still in our map
                    await self.disconnect(user_id, channel_id)
        except Exception as e:
            logger.error(f"Error sending message to user {user_id} in channel {channel_id}: {str(e)}")
            try:
                await self.disconnect(user_id, channel_id)
            except:
                pass
        return False
                
    async def broadcast_to_channel(self, channel_id: int, message: Dict):
        """Broadcast a message to all subscribers of a channel"""
        if channel_id in self.channel_subscribers:
            # Make a copy of the subscriber set to avoid mutation during iteration
            subscribers = list(self.channel_subscribers[channel_id])
            for user_id in subscribers:
                success = await self.send_personal_message(message, user_id, channel_id)
                if not success and user_id in self.channel_subscribers.get(channel_id, set()):
                    # If sending failed and user is still subscribed, disconnect them
                    await self.disconnect(user_id, channel_id)
                    
    def is_user_connected(self, user_id: int) -> bool:
        """Check if a user is connected via any WebSocket"""
        if user_id not in self.connection_status:
            return False
        return any(self.connection_status[user_id].values())
    
    def is_user_in_channel(self, user_id: int, channel_id: int) -> bool:
        """Check if a user is connected to a specific channel"""
        if user_id not in self.connection_status:
            return False
        return self.connection_status[user_id].get(channel_id, False)

# Create a singleton instance
connection_manager = ConnectionManager()

async def websocket_auth(websocket: WebSocket, token: str, db: Session):
    """Authenticate a WebSocket connection using JWT token"""
    try:
        user = auth.get_user_from_token(token, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        return user
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return None
