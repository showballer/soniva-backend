"""
Message Center Endpoints
"""
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import get_db
from app.models.user import User
from app.models.message import Conversation, ChatMessage, CommentNotification, SystemNotification
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response

router = APIRouter()


# ============ Pydantic Schemas ============

class SendMessageRequest(BaseModel):
    receiver_id: str = Field(..., description="Receiver user ID")
    content: str = Field(..., min_length=1, max_length=1000)
    message_type: str = Field(default="text", description="text/image/voice")


class MarkReadRequest(BaseModel):
    message_ids: List[str] = Field(..., description="Message IDs to mark as read")


# ============ Private Message Endpoints ============

@router.get("/conversations")
def get_conversations(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get conversation list
    """
    query = db.query(Conversation).filter(
        or_(
            Conversation.user1_id == current_user.id,
            Conversation.user2_id == current_user.id
        ),
        Conversation.status == 1
    ).order_by(Conversation.updated_at.desc())

    total = query.count()
    conversations = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for conv in conversations:
        # Get the other user
        other_user_id = conv.user2_id if conv.user1_id == current_user.id else conv.user1_id
        other_user = db.query(User).filter(User.id == other_user_id).first()

        # Get unread count for current user
        unread_count = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.receiver_id == current_user.id,
            ChatMessage.is_read == False
        ).count()

        items.append({
            "conversation_id": conv.id,
            "user": {
                "user_id": other_user.id,
                "name": other_user.name,
                "avatar": other_user.avatar
            } if other_user else None,
            "last_message": conv.last_message,
            "last_message_type": conv.last_message_type,
            "unread_count": unread_count,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None
        })

    return paginated_response(items, total, page, page_size)


@router.get("/conversation/{user_id}")
def get_or_create_conversation(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get or create conversation with a user
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create conversation with yourself"
        )

    # Check if other user exists
    other_user = db.query(User).filter(User.id == user_id, User.status == 1).first()
    if not other_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Find existing conversation
    conv = db.query(Conversation).filter(
        or_(
            and_(Conversation.user1_id == current_user.id, Conversation.user2_id == user_id),
            and_(Conversation.user1_id == user_id, Conversation.user2_id == current_user.id)
        ),
        Conversation.status == 1
    ).first()

    if not conv:
        # Create new conversation
        conv = Conversation(
            id=str(uuid4()),
            user1_id=current_user.id,
            user2_id=user_id
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    return success_response({
        "conversation_id": conv.id,
        "user": {
            "user_id": other_user.id,
            "name": other_user.name,
            "avatar": other_user.avatar
        }
    })


@router.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: str,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get messages in a conversation
    """
    # Verify user is part of conversation
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.user1_id == current_user.id,
            Conversation.user2_id == current_user.id
        )
    ).first()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    query = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.created_at.desc())

    total = query.count()
    messages = query.offset((page - 1) * page_size).limit(page_size).all()

    # Mark messages as read
    db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == False
    ).update({"is_read": True, "read_at": datetime.utcnow()})
    db.commit()

    items = [{
        "message_id": msg.id,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "content": msg.content,
        "message_type": msg.message_type,
        "is_read": msg.is_read,
        "created_at": msg.created_at.isoformat() if msg.created_at else None
    } for msg in messages]

    return paginated_response(items, total, page, page_size)


@router.post("/send")
def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a private message
    """
    if request.receiver_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send message to yourself"
        )

    # Check if receiver exists
    receiver = db.query(User).filter(User.id == request.receiver_id, User.status == 1).first()
    if not receiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receiver not found"
        )

    # Get or create conversation
    conv = db.query(Conversation).filter(
        or_(
            and_(Conversation.user1_id == current_user.id, Conversation.user2_id == request.receiver_id),
            and_(Conversation.user1_id == request.receiver_id, Conversation.user2_id == current_user.id)
        )
    ).first()

    if not conv:
        conv = Conversation(
            id=str(uuid4()),
            user1_id=current_user.id,
            user2_id=request.receiver_id
        )
        db.add(conv)

    # Create message
    message = ChatMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        sender_id=current_user.id,
        receiver_id=request.receiver_id,
        content=request.content,
        message_type=request.message_type
    )
    db.add(message)

    # Update conversation
    conv.last_message = request.content[:100] if len(request.content) > 100 else request.content
    conv.last_message_type = request.message_type
    conv.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(message)

    return success_response({
        "message_id": message.id,
        "conversation_id": conv.id,
        "content": message.content,
        "message_type": message.message_type,
        "created_at": message.created_at.isoformat() if message.created_at else None
    })


# ============ Comment Notification Endpoints ============

@router.get("/comments")
def get_comment_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comment notifications
    """
    query = db.query(CommentNotification).filter(
        CommentNotification.user_id == current_user.id
    ).order_by(CommentNotification.created_at.desc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for notif in notifications:
        from_user = db.query(User).filter(User.id == notif.from_user_id).first()
        items.append({
            "notification_id": notif.id,
            "from_user": {
                "user_id": from_user.id,
                "name": from_user.name,
                "avatar": from_user.avatar
            } if from_user else None,
            "post_id": notif.post_id,
            "comment_id": notif.comment_id,
            "content": notif.content,
            "notification_type": notif.notification_type,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat() if notif.created_at else None
        })

    return paginated_response(items, total, page, page_size)


@router.post("/comments/read")
def mark_comments_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark all comment notifications as read
    """
    db.query(CommentNotification).filter(
        CommentNotification.user_id == current_user.id,
        CommentNotification.is_read == False
    ).update({"is_read": True})
    db.commit()

    return success_response({"message": "All marked as read"})


# ============ System Notification Endpoints ============

@router.get("/notifications")
def get_system_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get system notifications
    """
    query = db.query(SystemNotification).filter(
        SystemNotification.user_id == current_user.id
    ).order_by(SystemNotification.created_at.desc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "notification_id": n.id,
        "title": n.title,
        "content": n.content,
        "notification_type": n.notification_type,
        "action_url": n.action_url,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None
    } for n in notifications]

    return paginated_response(items, total, page, page_size)


@router.post("/notifications/read")
def mark_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark all system notifications as read
    """
    db.query(SystemNotification).filter(
        SystemNotification.user_id == current_user.id,
        SystemNotification.is_read == False
    ).update({"is_read": True})
    db.commit()

    return success_response({"message": "All marked as read"})


# ============ Unread Counts ============

@router.get("/unread-counts")
def get_unread_counts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get unread message counts for all categories
    """
    # Private messages
    private_count = db.query(ChatMessage).filter(
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == False
    ).count()

    # Comment notifications
    comment_count = db.query(CommentNotification).filter(
        CommentNotification.user_id == current_user.id,
        CommentNotification.is_read == False
    ).count()

    # System notifications
    system_count = db.query(SystemNotification).filter(
        SystemNotification.user_id == current_user.id,
        SystemNotification.is_read == False
    ).count()

    return success_response({
        "private_messages": private_count,
        "comments": comment_count,
        "notifications": system_count,
        "total": private_count + comment_count + system_count
    })
