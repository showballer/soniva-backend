"""
Chat Room Related Models
"""
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, Text, ForeignKey, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ChatRoom(Base):
    """Chat room table"""
    __tablename__ = "chat_rooms"

    id = Column(String(36), primary_key=True, comment="Room ID (UUID)")
    host_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Host ID")
    name = Column(String(100), nullable=False, comment="Room name")
    description = Column(String(500), comment="Room description")
    type = Column(String(20), nullable=False, index=True, comment="Room type: group (8-mic) | private (1-on-1)")
    cover_image = Column(String(500), comment="Cover image URL")

    # Room settings
    is_private = Column(Boolean, default=False, comment="Is private room")
    password_hash = Column(String(255), comment="Room password hash")
    max_seats = Column(Integer, default=8, comment="Max mic seats")

    # Statistics
    online_count = Column(Integer, default=0, comment="Online count")
    total_visitors = Column(Integer, default=0, comment="Total visitors")

    # Status
    status = Column(Integer, default=1, index=True, comment="Status: 1-open 0-closed")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")
    closed_at = Column(TIMESTAMP, comment="Closed time")

    # Relationships
    members = relationship("RoomMember", back_populates="room", cascade="all, delete-orphan")
    mic_seats = relationship("MicSeat", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("RoomMessage", back_populates="room", cascade="all, delete-orphan")
    mic_requests = relationship("MicRequest", back_populates="room", cascade="all, delete-orphan")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class RoomMember(Base):
    """Room member table"""
    __tablename__ = "room_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    room_id = Column(String(36), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True, comment="Room ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    role = Column(String(20), default="member", comment="Role: host/admin/member")
    joined_at = Column(TIMESTAMP, server_default=func.now(), comment="Join time")
    left_at = Column(TIMESTAMP, comment="Leave time")

    # Relationships
    room = relationship("ChatRoom", back_populates="members")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class MicSeat(Base):
    """Mic seat table"""
    __tablename__ = "mic_seats"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    room_id = Column(String(36), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True, comment="Room ID")
    seat_index = Column(Integer, nullable=False, comment="Seat index (0-7)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, comment="Occupant user ID")
    status = Column(String(20), default="empty", comment="Status: empty/occupied/locked")
    is_muted = Column(Boolean, default=False, comment="Is muted")
    is_admin = Column(Boolean, default=False, comment="Is admin")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    room = relationship("ChatRoom", back_populates="mic_seats")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class RoomMessage(Base):
    """Room message table"""
    __tablename__ = "room_messages"

    id = Column(String(36), primary_key=True, comment="Message ID (UUID)")
    room_id = Column(String(36), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True, comment="Room ID")
    sender_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Sender ID")
    type = Column(String(20), nullable=False, comment="Message type: text/emoji/gift/system/enter/leave")
    content = Column(Text, comment="Message content")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Send time")

    # Relationships
    room = relationship("ChatRoom", back_populates="messages")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class MicRequest(Base):
    """Mic request table"""
    __tablename__ = "mic_requests"

    id = Column(String(36), primary_key=True, comment="Request ID (UUID)")
    room_id = Column(String(36), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True, comment="Room ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Applicant user ID")
    seat_index = Column(Integer, comment="Requested seat index")
    status = Column(String(20), default="pending", index=True, comment="Status: pending/approved/rejected/expired")
    handler_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), comment="Handler ID")
    handled_at = Column(TIMESTAMP, comment="Handle time")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")

    # Relationships
    room = relationship("ChatRoom", back_populates="mic_requests")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
