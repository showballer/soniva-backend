"""
Identify (Ta Analysis) Related Models
"""
from sqlalchemy import Column, String, Integer, TIMESTAMP, JSON, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class UserPortrait(Base):
    """User portrait table"""
    __tablename__ = "user_portraits"

    id = Column(String(36), primary_key=True, comment="Portrait ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="Creator ID")
    nickname = Column(String(50), comment="Target user nickname")
    tags = Column(JSON, comment="Tags array")

    # Portrait details
    basic_info = Column(JSON, comment="Basic info {age, gender, location, occupation}")
    economic_info = Column(JSON, comment="Economic info {level, attitude, range}")
    personality_info = Column(JSON, comment="Personality info {likes, dislikes, traits}")
    social_preference = Column(JSON, comment="Social preference {interaction_style, preferences}")

    strategy = Column(Text, comment="Coping strategy")
    notes = Column(Text, comment="Notes")

    # Statistics
    analysis_count = Column(Integer, default=0, comment="Analysis count")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    user = relationship("User", back_populates="portraits")
    analysis_records = relationship("AnalysisRecord", back_populates="portrait")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class AnalysisRecord(Base):
    """Analysis record table"""
    __tablename__ = "analysis_records"

    id = Column(String(36), primary_key=True, comment="Analysis ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    portrait_id = Column(String(36), ForeignKey("user_portraits.id", ondelete="SET NULL"), index=True, comment="Related portrait ID (optional)")
    type = Column(String(20), nullable=False, index=True, comment="Analysis type: chat/moments/avatar")
    image_url = Column(String(500), nullable=False, comment="Analysis image URL")

    # Analysis result (varies by type)
    result = Column(JSON, nullable=False, comment="Analysis result JSON")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), index=True, comment="Created time")

    # Relationships
    portrait = relationship("UserPortrait", back_populates="analysis_records")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
