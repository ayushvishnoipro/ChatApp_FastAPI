from sqlalchemy.orm import Session
from typing import List, Optional
from . import models, schemas, auth
from .models import UserStatus, MessageStatus

# User operations
def get_user(db: Session, user_id: int):
    """Get a user by ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    """Get a user by username"""
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    """Create a new user"""
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_status(db: Session, user_id: int, status: UserStatus):
    """Update a user's status"""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.status = status
        db.commit()
        db.refresh(db_user)
    return db_user

# Channel operations
def get_channel(db: Session, channel_id: int):
    """Get a channel by ID"""
    return db.query(models.Channel).filter(models.Channel.id == channel_id).first()

def get_channels_for_user(db: Session, user_id: int):
    """Get all channels for a user"""
    db_user = get_user(db, user_id)
    return db_user.channels if db_user else []

def create_direct_channel(db: Session, user1_id: int, user2_id: int, name: Optional[str] = None):
    """Create a direct message channel between two users"""
    # Check if a direct channel already exists between these users
    user1 = get_user(db, user1_id)
    user2 = get_user(db, user2_id)
    
    if not user1 or not user2:
        return None
        
    for channel in user1.channels:
        if channel.type == models.ChannelType.DIRECT and user2 in channel.members:
            return channel
            
    # Create a new direct channel
    channel_name = name or f"DM: {user1.username} & {user2.username}"
    db_channel = models.Channel(
        name=channel_name,
        type=models.ChannelType.DIRECT
    )
    
    db_channel.members.append(user1)
    db_channel.members.append(user2)
    
    db.add(db_channel)
    db.commit()
    db.refresh(db_channel)
    return db_channel

def create_group_channel(db: Session, channel: schemas.ChannelCreate, creator_id: int):
    """Create a group channel"""
    db_channel = models.Channel(
        name=channel.name,
        type=models.ChannelType.GROUP
    )
    
    # Add the creator and all members
    creator = get_user(db, creator_id)
    if creator:
        db_channel.members.append(creator)
        
    # Make a set of member IDs to avoid duplicates
    member_ids = set(channel.member_ids)
    member_ids.add(creator_id)  # Make sure creator is included
    
    for member_id in member_ids:
        if member_id != creator_id:  # Avoid adding creator twice
            member = get_user(db, member_id)
            if member:
                db_channel.members.append(member)
    
    db.add(db_channel)
    db.commit()
    db.refresh(db_channel)
    return db_channel

# Message operations
def create_message(db: Session, message: schemas.MessageCreate, user_id: int):
    """Create a new message"""
    db_message = models.Message(
        content=message.content,
        sender_id=user_id,
        channel_id=message.channel_id,
        status=models.MessageStatus.SENT
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_messages(db: Session, channel_id: int, limit: int = 50, skip: int = 0):
    """Get messages for a channel with pagination"""
    return (
        db.query(models.Message)
        .filter(models.Message.channel_id == channel_id)
        .order_by(models.Message.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_message_status(db: Session, message_id: int, status: MessageStatus):
    """Update a message's status"""
    db_message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if db_message:
        db_message.status = status
        db.commit()
        db.refresh(db_message)
    return db_message

def mark_messages_as_read(db: Session, channel_id: int, user_id: int):
    """Mark all messages in a channel as read for a user"""
    # Only mark messages from other users
    messages = (
        db.query(models.Message)
        .filter(
            models.Message.channel_id == channel_id,
            models.Message.sender_id != user_id,
            models.Message.status != models.MessageStatus.READ
        )
        .all()
    )
    
    for message in messages:
        message.status = models.MessageStatus.READ
    
    db.commit()
    return messages
