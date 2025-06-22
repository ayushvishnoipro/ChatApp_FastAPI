from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, Table, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from .database import Base

# Many-to-many relationship table between users and channels
channel_members = Table(
    "channel_members",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("channel_id", Integer, ForeignKey("channels.id"), primary_key=True),
)

class UserStatus(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"

class ChannelType(enum.Enum):
    DIRECT = "direct"
    GROUP = "group"

class MessageStatus(enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")
    status = Column(Enum(UserStatus), default=UserStatus.OFFLINE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sent_messages = relationship("Message", back_populates="sender")
    channels = relationship("Channel", secondary=channel_members, back_populates="members")

class Channel(Base):
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(Enum(ChannelType))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="channel", cascade="all, delete-orphan")
    members = relationship("User", secondary=channel_members, back_populates="channels")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    status = Column(Enum(MessageStatus), default=MessageStatus.SENT)
    sender_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(Integer, ForeignKey("channels.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sender = relationship("User", back_populates="sent_messages")
    channel = relationship("Channel", back_populates="messages")
