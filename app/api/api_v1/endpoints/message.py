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
            Conversation.user_a_id == current_user.id,
            Conversation.user_b_id == current_user.id
        )
    ).order_by(Conversation.updated_at.desc())

    total = query.count()
    conversations = query.offset((page - 1) * page_size).limit(page_size).all()

    # Batch-load all "other" users and last messages — 2 queries instead of 2*N
    other_user_ids = {
        (conv.user_b_id if conv.user_a_id == current_user.id else conv.user_a_id)
        for conv in conversations
    }
    last_message_ids = {
        conv.last_message_id for conv in conversations if conv.last_message_id
    }

    users_by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(other_user_ids)).all()
    } if other_user_ids else {}

    last_messages_by_id = {
        m.id: m
        for m in db.query(ChatMessage).filter(
            ChatMessage.id.in_(last_message_ids)
        ).all()
    } if last_message_ids else {}

    items = []
    for conv in conversations:
        other_user_id = conv.user_b_id if conv.user_a_id == current_user.id else conv.user_a_id
        other_user = users_by_id.get(other_user_id)

        is_user_a = conv.user_a_id == current_user.id
        unread_count = conv.user_a_unread if is_user_a else conv.user_b_unread

        last_msg = None
        last_msg_type = None
        if conv.last_message_id:
            last_message_obj = last_messages_by_id.get(conv.last_message_id)
            if last_message_obj:
                last_msg = last_message_obj.content[:100] if last_message_obj.content else None
                last_msg_type = last_message_obj.type

        items.append({
            "conversation_id": conv.id,
            "user": {
                "user_id": other_user.id,
                "name": other_user.name,
                "avatar": other_user.avatar
            } if other_user else None,
            "last_message": last_msg,
            "last_message_type": last_msg_type,
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

    # Find existing conversation (user_a_id is always the smaller ID)
    user_ids = sorted([current_user.id, user_id])
    conv = db.query(Conversation).filter(
        Conversation.user_a_id == user_ids[0],
        Conversation.user_b_id == user_ids[1]
    ).first()

    if not conv:
        # Create new conversation
        conv = Conversation(
            id=str(uuid4()),
            user_a_id=user_ids[0],
            user_b_id=user_ids[1]
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
            Conversation.user_a_id == current_user.id,
            Conversation.user_b_id == current_user.id
        )
    ).first()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    query = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.status == 1
    ).order_by(ChatMessage.created_at.desc())

    total = query.count()
    messages = query.offset((page - 1) * page_size).limit(page_size).all()

    # Bulk-mark unread messages as read — single UPDATE instead of per-row loop
    now = datetime.utcnow()
    updated = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.receiver_id == current_user.id,
        ChatMessage.is_read == False
    ).update(
        {"is_read": True, "read_at": now},
        synchronize_session=False
    )

    if updated:
        # Update conversation unread count
        is_user_a = conv.user_a_id == current_user.id
        if is_user_a:
            conv.user_a_unread = 0
        else:
            conv.user_b_unread = 0

        db.commit()

    items = [{
        "message_id": msg.id,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "content": msg.content,
        "message_type": msg.type,
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

    # Get or create conversation (user_a_id is always the smaller ID)
    user_ids = sorted([current_user.id, request.receiver_id])
    conv = db.query(Conversation).filter(
        Conversation.user_a_id == user_ids[0],
        Conversation.user_b_id == user_ids[1]
    ).first()

    if not conv:
        conv = Conversation(
            id=str(uuid4()),
            user_a_id=user_ids[0],
            user_b_id=user_ids[1]
        )
        db.add(conv)
        db.flush()  # Get the ID

    # Create message
    message = ChatMessage(
        id=str(uuid4()),
        conversation_id=conv.id,
        sender_id=current_user.id,
        receiver_id=request.receiver_id,
        type=request.message_type,
        content=request.content
    )
    db.add(message)
    db.flush()

    # Update conversation
    conv.last_message_id = message.id
    conv.last_message_at = datetime.utcnow()
    conv.updated_at = datetime.utcnow()

    # Update receiver's unread count
    is_receiver_user_a = conv.user_a_id == request.receiver_id
    if is_receiver_user_a:
        conv.user_a_unread = (conv.user_a_unread or 0) + 1
    else:
        conv.user_b_unread = (conv.user_b_unread or 0) + 1

    db.commit()
    db.refresh(message)

    return success_response({
        "message_id": message.id,
        "conversation_id": conv.id,
        "content": message.content,
        "message_type": message.type,
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
        CommentNotification.user_id == current_user.id,
        CommentNotification.status == 1
    ).order_by(CommentNotification.created_at.desc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    # Batch-load all sender users in one query
    from_user_ids = {n.from_user_id for n in notifications if n.from_user_id}
    users_by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(from_user_ids)).all()
    } if from_user_ids else {}

    items = []
    for notif in notifications:
        from_user = users_by_id.get(notif.from_user_id)
        # Get post_id from target_id if target_type is post
        post_id = notif.target_id if notif.target_type == 'post' else None

        items.append({
            "notification_id": notif.id,
            "from_user": {
                "user_id": from_user.id,
                "name": from_user.name,
                "avatar": from_user.avatar
            } if from_user else None,
            "post_id": post_id,
            "comment_id": notif.comment_id,
            "content": notif.content,
            "notification_type": notif.type,
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
    ).update({"is_read": True, "read_at": datetime.utcnow()})
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
        or_(
            SystemNotification.user_id == current_user.id,
            SystemNotification.user_id == None  # Global notifications
        ),
        SystemNotification.status == 1
    ).order_by(SystemNotification.created_at.desc())

    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "notification_id": n.id,
        "title": n.title,
        "content": n.content,
        "notification_type": n.type,
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
    ).update({"is_read": True, "read_at": datetime.utcnow()})
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
        ChatMessage.is_read == False,
        ChatMessage.status == 1
    ).count()

    # Comment notifications
    comment_count = db.query(CommentNotification).filter(
        CommentNotification.user_id == current_user.id,
        CommentNotification.is_read == False,
        CommentNotification.status == 1
    ).count()

    # System notifications
    system_count = db.query(SystemNotification).filter(
        SystemNotification.user_id == current_user.id,
        SystemNotification.is_read == False,
        SystemNotification.status == 1
    ).count()

    return success_response({
        "private_messages": private_count,
        "comments": comment_count,
        "notifications": system_count,
        "total": private_count + comment_count + system_count
    })
