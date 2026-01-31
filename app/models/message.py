"""
Message Center Related Models
"""
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, Text, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.database import Base


class Conversation(Base):
    """Conversation table"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, comment="Conversation ID (UUID)")
    user_a_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User A ID (smaller ID)")
    user_b_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User B ID (larger ID)")
    last_message_id = Column(String(36), comment="Last message ID")
    last_message_at = Column(TIMESTAMP, comment="Last message time")

    # User A status
    user_a_unread = Column(Integer, default=0, comment="User A unread count")
    user_a_deleted = Column(Boolean, default=False, comment="User A deleted")
    user_a_last_read_at = Column(TIMESTAMP, comment="User A last read time")

    # User B status
    user_b_unread = Column(Integer, default=0, comment="User B unread count")
    user_b_deleted = Column(Boolean, default=False, comment="User B deleted")
    user_b_last_read_at = Column(TIMESTAMP, comment="User B last read time")

    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class ChatMessage(Base):
    """Chat message table (private chat)"""
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, comment="Message ID (UUID)")
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True, comment="Conversation ID")
    sender_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Sender ID")
    receiver_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Receiver ID")
    type = Column(String(20), nullable=False, comment="Message type: text/image/voice")
    content = Column(Text, comment="Message content")
    media_url = Column(String(500), comment="Media URL (image/voice)")
    duration = Column(Integer, comment="Voice duration (seconds)")

    # Status
    is_read = Column(Boolean, default=False, comment="Is read")
    read_at = Column(TIMESTAMP, comment="Read time")
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Send time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class CommentNotification(Base):
    """Comment notification table"""
    __tablename__ = "comment_notifications"

    id = Column(String(36), primary_key=True, comment="Notification ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Recipient user ID")
    from_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Source user ID")
    type = Column(String(20), nullable=False, comment="Type: comment/reply/mention")

    # Related content
    target_type = Column(String(20), nullable=False, comment="Target type: post/comment")
    target_id = Column(String(36), nullable=False, comment="Target ID (post ID or comment ID)")
    comment_id = Column(String(36), comment="Comment ID")
    content = Column(String(500), comment="Comment content excerpt")

    # Status
    is_read = Column(Boolean, default=False, comment="Is read")
    read_at = Column(TIMESTAMP, comment="Read time")
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class SystemNotification(Base):
    """System notification table"""
    __tablename__ = "system_notifications"

    id = Column(String(36), primary_key=True, comment="Notification ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="Recipient user ID (NULL for global)")
    type = Column(String(20), nullable=False, index=True, comment="Type: system/activity/achievement")
    title = Column(String(100), nullable=False, comment="Title")
    content = Column(Text, comment="Content")
    image_url = Column(String(500), comment="Image URL")
    action_url = Column(String(500), comment="Action URL")

    # Status
    is_read = Column(Boolean, default=False, comment="Is read")
    read_at = Column(TIMESTAMP, comment="Read time")
    expires_at = Column(TIMESTAMP, index=True, comment="Expiration time")
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
