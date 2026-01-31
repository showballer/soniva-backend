"""
User Related Models
"""
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, JSON, Text, ForeignKey, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """User table"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, comment="User ID (UUID)")
    phone = Column(String(20), unique=True, nullable=False, index=True, comment="Phone number")
    password_hash = Column(String(255), nullable=False, comment="Password hash")
    name = Column(String(50), nullable=False, comment="Username")
    avatar = Column(String(500), comment="Avatar URL")
    bio = Column(String(200), comment="Personal bio")
    gender = Column(String(10), comment="Gender: male/female/other")
    birthday = Column(TIMESTAMP, comment="Birthday")
    location = Column(String(100), comment="Location")
    is_anonymous = Column(Boolean, default=True, comment="Is anonymous")
    tags = Column(JSON, comment="User tags array")

    # Statistics
    posts_count = Column(Integer, default=0, comment="Posts count")
    likes_count = Column(Integer, default=0, comment="Likes received count")
    followers_count = Column(Integer, default=0, comment="Followers count")
    following_count = Column(Integer, default=0, comment="Following count")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-disabled")
    last_login_at = Column(TIMESTAMP, comment="Last login time")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    voice_test_results = relationship("VoiceTestResult", back_populates="user")
    voice_cards = relationship("VoiceCard", back_populates="user")
    portraits = relationship("UserPortrait", back_populates="user")
    posts = relationship("SquarePost", back_populates="author")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class UserFollow(Base):
    """User follow relationship table"""
    __tablename__ = "user_follows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    follower_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Follower ID")
    following_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Following ID")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Follow time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class VerificationCode(Base):
    """Verification code table"""
    __tablename__ = "verification_codes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    phone = Column(String(20), nullable=False, index=True, comment="Phone number")
    code = Column(String(6), nullable=False, comment="Verification code")
    type = Column(String(20), nullable=False, comment="Type: register/login/reset_password")
    expires_at = Column(TIMESTAMP, nullable=False, comment="Expiration time")
    is_used = Column(Boolean, default=False, comment="Is used")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
