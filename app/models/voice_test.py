"""
Voice Test Related Models
"""
from sqlalchemy import Column, String, Integer, TIMESTAMP, JSON, Text, ForeignKey, BigInteger, DECIMAL
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class VoiceTestResult(Base):
    """Voice test result table"""
    __tablename__ = "voice_test_results"

    id = Column(String(36), primary_key=True, comment="Result ID (UUID)")
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    audio_url = Column(String(500), nullable=False, comment="Audio file URL")
    text_content = Column(Text, comment="Read text content")
    duration = Column(DECIMAL(5, 2), comment="Audio duration (seconds)")
    gender = Column(String(10), nullable=False, comment="Gender: female/male")

    # Voice feature data (raw data from librosa)
    voice_features = Column(JSON, comment="Raw voice features from librosa analysis")

    # Analysis results
    voice_type_scores = Column(JSON, nullable=False, comment="Voice type scores {type: score}")
    main_voice_type = Column(String(50), nullable=False, index=True, comment="Main voice type")
    tags = Column(JSON, nullable=False, comment="Voice tags array")
    overall_score = Column(DECIMAL(3, 1), comment="Overall score 0-10")
    charm_index = Column(DECIMAL(3, 1), comment="Charm index 0-10")
    hearing_age = Column(Integer, comment="Hearing age")
    hearing_height = Column(Integer, comment="Hearing height")
    voice_attribute = Column(String(20), comment="Voice attribute: attack/receive/both")
    color_temperature = Column(String(20), comment="Color temperature: warm/cold/neutral")
    emotional_summary = Column(Text, comment="Emotional summary")
    advanced_suggestion = Column(Text, comment="Advanced suggestion")

    # Status
    status = Column(Integer, default=1, comment="Status: 1-active 0-deleted")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Updated time")

    # Relationships
    user = relationship("User", back_populates="voice_test_results")
    songs = relationship("VoiceTestSong", back_populates="result", cascade="all, delete-orphan")
    voice_cards = relationship("VoiceCard", back_populates="result")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class VoiceTestSong(Base):
    """Recommended songs table"""
    __tablename__ = "voice_test_songs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Auto increment ID")
    result_id = Column(String(36), ForeignKey("voice_test_results.id", ondelete="CASCADE"), nullable=False, index=True, comment="Voice test result ID")
    song_name = Column(String(100), nullable=False, comment="Song name")
    artist = Column(String(100), nullable=False, comment="Artist")
    reason = Column(Text, comment="Recommendation reason")
    sort_order = Column(Integer, default=0, comment="Sort order")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Created time")

    # Relationships
    result = relationship("VoiceTestResult", back_populates="songs")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
