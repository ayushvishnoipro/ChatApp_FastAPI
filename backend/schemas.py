from typing import List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
from .models import UserStatus, ChannelType, MessageStatus

# User schemas
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class User(UserBase):
    id: int
    role: str
    status: UserStatus
    created_at: datetime
    
    class Config:
        orm_mode = True

class UserInDB(User):
    hashed_password: str

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Channel schemas
class ChannelBase(BaseModel):
    name: str
    type: ChannelType

class ChannelCreate(ChannelBase):
    member_ids: List[int] = []  # Use empty list as default instead of None

class Channel(ChannelBase):
    id: int
    created_at: datetime
    members: List[User]
    
    class Config:
        orm_mode = True

# Message schemas
class MessageBase(BaseModel):
    content: str
    channel_id: int

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: int
    sender_id: int
    status: MessageStatus
    created_at: datetime
    
    class Config:
        orm_mode = True

class MessageRead(BaseModel):
    message_id: int

# WebSocket message schemas
class WebSocketMessage(BaseModel):
    channel_id: int
    content: str
    message_type: str = "message"

class WebSocketResponse(BaseModel):
    message_type: str
    data: Union[Message, List[Message], str, dict]
