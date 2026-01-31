"""
Square (Social) Related Models
"""
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, JSON, Text, ForeignKey, BigInteger, DECIMAL
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SquarePost(Base):
    """Square post table"""
    __tablename__ = "square_posts"

    id = Column(String(36), primary_key=True, comment="Post ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Author ID")
    type = Column(String(20), nullable=False, index=True, comment="Post type: experience/voice_card/question")
    content = Column(Text, nullable=False, comment="Post content")
    images = Column(JSON, comment="Image URLs array")

    # Type-specific fields
    voice_card_id = Column(String(36), ForeignKey("voice_cards.id", ondelete="SET NULL"), index=True, comment="Voice card ID (for voice_card type)")
    reward_amount = Column(DECIMAL(10, 2), comment="Reward amount (for question type)")
    is_solved = Column(Boolean, default=False, comment="Is solved (for question type)")

    # Statistics
    likes_count = Column(Integer, default=0, index=True, comment="Likes count")
    comments_count = Column(Integer, default=0, comment="Comments count")
    shares_count = Column(Integer, default=0, comment="Shares count")
    views_count = Column(Integer, default=0, comment="Views count")

    # Settings
    is_anonymous = Column(Boolean, default=False, comment="Is anonymous")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    author = relationship("User", back_populates="posts")
    comments = relationship("PostComment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PostComment(Base):
    """Post comment table"""
    __tablename__ = "post_comments"

    id = Column(String(36), primary_key=True, comment="Comment ID (UUID)")
    post_id = Column(String(36), ForeignKey("square_posts.id", ondelete="CASCADE"), nullable=False, index=True, comment="Post ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Commenter ID")
    content = Column(Text, nullable=False, comment="Comment content")
    parent_id = Column(String(36), ForeignKey("post_comments.id", ondelete="CASCADE"), index=True, comment="Parent comment ID (for replies)")
    reply_to_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), comment="@User ID")

    # Statistics
    likes_count = Column(Integer, default=0, comment="Likes count")
    replies_count = Column(Integer, default=0, comment="Replies count")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    post = relationship("SquarePost", back_populates="comments")
    replies = relationship("PostComment", remote_side=[id], backref="parent")
    likes = relationship("CommentLike", back_populates="comment", cascade="all, delete-orphan")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PostLike(Base):
    """Post like table"""
    __tablename__ = "post_likes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    post_id = Column(String(36), ForeignKey("square_posts.id", ondelete="CASCADE"), nullable=False, index=True, comment="Post ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Like time")

    # Relationships
    post = relationship("SquarePost", back_populates="likes")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class CommentLike(Base):
    """Comment like table"""
    __tablename__ = "comment_likes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    comment_id = Column(String(36), ForeignKey("post_comments.id", ondelete="CASCADE"), nullable=False, index=True, comment="Comment ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Like time")

    # Relationships
    comment = relationship("PostComment", back_populates="likes")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class UserFavorite(Base):
    """User favorite table"""
    __tablename__ = "user_favorites"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    post_id = Column(String(36), ForeignKey("square_posts.id", ondelete="CASCADE"), nullable=False, index=True, comment="Post ID")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Favorite time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
