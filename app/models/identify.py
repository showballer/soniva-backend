"""
Identify (聊天分析) Models

Chat-style conversation analysis inspired by taoxi.xin.
Old UserPortrait / AnalysisRecord tables are deprecated. They are kept in the
database for historical data but no longer referenced by the code.
"""
from sqlalchemy import Column, String, Integer, TIMESTAMP, JSON, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class IdentifyConversation(Base):
    """One chat-analysis conversation (thread)."""
    __tablename__ = "identify_conversations"

    id = Column(String(36), primary_key=True, comment="Conversation ID (UUID, also used as FastGPT chatId)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(120), nullable=False, default="新会话", comment="Auto-generated from first user message")
    message_count = Column(Integer, nullable=False, default=0)
    last_message_at = Column(TIMESTAMP, nullable=True, index=True)
    status = Column(Integer, nullable=False, default=1, comment="1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    messages = relationship(
        "IdentifyMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="IdentifyMessage.created_at",
    )

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class IdentifyMessage(Base):
    """A single message inside an identify conversation."""
    __tablename__ = "identify_messages"

    id = Column(String(36), primary_key=True)
    conversation_id = Column(
        String(36),
        ForeignKey("identify_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(16), nullable=False, comment="user / assistant")

    # User-side fields
    text = Column(Text, nullable=True, comment="User text content")
    image_url = Column(String(500), nullable=True, comment="Uploaded image OSS URL (user messages)")

    # Assistant-side fields
    final_content = Column(Text, nullable=True, comment="Final rendered markdown from FastGPT")
    workflow_nodes = Column(
        JSON,
        nullable=True,
        comment="Array of node progress, e.g. [{name, status, startedAt, finishedAt}]",
    )
    duration_seconds = Column(Integer, nullable=True, comment="Total workflow runtime reported by FastGPT")
    status = Column(
        String(16),
        nullable=False,
        default="done",
        comment="streaming / done / failed",
    )
    error_message = Column(String(500), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now(), index=True)

    conversation = relationship("IdentifyConversation", back_populates="messages")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
