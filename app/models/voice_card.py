"""
Voice Card Related Models
"""
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, JSON, Text, ForeignKey, DECIMAL
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class VoiceCard(Base):
    """Voice card table"""
    __tablename__ = "voice_cards"

    id = Column(String(36), primary_key=True, comment="Card ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    result_id = Column(String(36), ForeignKey("voice_test_results.id", ondelete="CASCADE"), nullable=False, index=True, comment="Voice test result ID")
    template_id = Column(String(50), nullable=False, index=True, comment="Template ID")
    card_url = Column(String(500), nullable=False, comment="Card image URL")

    # Voice info snapshot
    main_voice_type = Column(String(50), nullable=False, comment="Main voice type")
    overall_score = Column(DECIMAL(3, 1), comment="Overall score")
    charm_index = Column(DECIMAL(3, 1), comment="Charm index")
    tags = Column(JSON, comment="Voice tags")

    # Share statistics
    share_count = Column(Integer, default=0, comment="Share count")
    view_count = Column(Integer, default=0, comment="View count")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    user = relationship("User", back_populates="voice_cards")
    result = relationship("VoiceTestResult", back_populates="voice_cards")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class VoiceCardTemplate(Base):
    """Voice card template table"""
    __tablename__ = "voice_card_templates"

    id = Column(String(50), primary_key=True, comment="Template ID")
    name = Column(String(50), nullable=False, comment="Template name")
    description = Column(String(200), comment="Template description")
    preview_url = Column(String(500), comment="Preview image URL")

    # Color configuration
    primary_color = Column(String(20), comment="Primary color")
    secondary_color = Column(String(20), comment="Secondary color")
    background_style = Column(String(200), comment="Background style")

    # Status
    sort_order = Column(Integer, default=0, index=True, comment="Sort order")
    is_active = Column(Boolean, default=True, comment="Is active")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
