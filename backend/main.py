from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session
import json
import logging
from typing import List, Optional

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from . import models, schemas, crud, auth, websocket_manager
from .database import engine, get_db
from .redis_client import redis_client
from .websocket_manager import connection_manager
from .models import UserStatus, MessageStatus

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Real-time Chat API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth endpoints
@app.post("/signup", response_model=schemas.User)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Get JWT token for a user"""
    user = crud.get_user_by_username(db, username=form_data.username)
    
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update user status to online
    crud.update_user_status(db, user.id, UserStatus.ONLINE)
    
    # Create access token
    access_token = auth.create_access_token(data={"sub": user.username})
    
    return {"access_token": access_token, "token_type": "bearer"}

# Channel endpoints
@app.get("/channels", response_model=List[schemas.Channel])
def get_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all channels for the current user"""
    return crud.get_channels_for_user(db, user_id=current_user.id)

@app.post("/channels/direct", response_model=schemas.Channel)
def create_direct_channel(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create or get a direct message channel with another user"""
    channel = crud.create_direct_channel(db, current_user.id, user_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Target user not found")
    return channel

@app.post("/channels/group", response_model=schemas.Channel)
def create_group_channel(
    channel: schemas.ChannelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a group channel"""
    try:
        # Ensure member_ids is a list of integers
        if not isinstance(channel.member_ids, list):
            raise HTTPException(status_code=400, detail="member_ids must be a list")
            
        # Filter out any None values
        member_ids = [member_id for member_id in channel.member_ids if member_id is not None]
        
        # Update the member_ids in the channel object
        channel.member_ids = member_ids
        
        return crud.create_group_channel(db, channel, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create group channel: {str(e)}")

# Message endpoints
@app.get("/messages", response_model=List[schemas.Message])
def get_messages(
    channel_id: int,
    limit: Optional[int] = 50,
    skip: Optional[int] = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get messages for a channel"""
    # Check if user is in channel
    channel = crud.get_channel(db, channel_id=channel_id)
    if not channel or current_user not in channel.members:
        raise HTTPException(status_code=403, detail="Not a member of this channel")
    
    return crud.get_messages(db, channel_id=channel_id, limit=limit, skip=skip)

@app.post("/messages/read", response_model=List[schemas.Message])
def mark_messages_as_read(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Mark all messages in a channel as read"""
    # Check if user is in channel
    channel = crud.get_channel(db, channel_id=channel_id)
    if not channel or current_user not in channel.members:
        raise HTTPException(status_code=403, detail="Not a member of this channel")
    
    return crud.mark_messages_as_read(db, channel_id=channel_id, user_id=current_user.id)

# WebSocket endpoint
@app.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    channel_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time chat"""
    # Authenticate user
    user = await websocket_manager.websocket_auth(websocket, token, db)
    if not user:
        return
    
    # Check if user is member of channel
    channel = crud.get_channel(db, channel_id=channel_id)
    if not channel or user not in channel.members:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    try:
        # Connect user to channel WebSocket
        await connection_manager.connect(websocket, user.id, channel_id)
        
        # Send notification to channel that user joined
        join_notification = {
            "message_type": "notification",
            "data": f"{user.username} joined the chat"
        }
        await connection_manager.broadcast_to_channel(channel_id, join_notification)
        
        # Update user status to online
        crud.update_user_status(db, user.id, UserStatus.ONLINE)
        
        # Process messages
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # Create and save the message
                message_create = schemas.MessageCreate(
                    content=message_data["content"],
                    channel_id=channel_id
                )
                
                # Use a new DB session to avoid connection pool issues
                from .database import get_db_context
                with get_db_context() as new_db:
                    db_message = crud.create_message(new_db, message_create, user.id)
                    
                    # Format message for sending
                    message_out = {
                        "message_type": "message",
                        "data": {
                            "id": db_message.id,
                            "content": db_message.content,
                            "sender_id": db_message.sender_id,
                            "channel_id": db_message.channel_id,
                            "status": db_message.status.value,
                            "created_at": db_message.created_at.isoformat()
                        }
                    }
                
                # Publish message to Redis channel for broadcasting
                redis_client.publish(f"chat:{channel_id}", message_out)
                
            except WebSocketDisconnect:
                raise  # Re-raise to be caught by outer try/except
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}")
                # Send error message to client
                try:
                    await websocket.send_json({
                        "message_type": "error",
                        "data": "Error processing your message"
                    })
                except:
                    # If we can't send the error, the connection is probably broken
                    raise WebSocketDisconnect()
                
    except WebSocketDisconnect:
        # Disconnect user and notify channel
        await connection_manager.disconnect(user.id, channel_id)
        leave_notification = {
            "message_type": "notification",
            "data": f"{user.username} left the chat"
        }
        await connection_manager.broadcast_to_channel(channel_id, leave_notification)
        
        # Update user status if no longer connected anywhere
        if not connection_manager.is_user_connected(user.id):
            crud.update_user_status(db, user.id, UserStatus.OFFLINE)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await connection_manager.disconnect(user.id, channel_id)
        except:
            pass

@app.get("/users", response_model=List[schemas.User])
def get_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all users"""
    # Simple implementation - in production you might want pagination
    return db.query(models.User).all()

@app.get("/online-users")
def get_online_users():
    """Get IDs of all online users"""
    return list(redis_client.get_set_members("online_users"))
