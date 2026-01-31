"""
Database Models
"""
from app.models.user import User, UserFollow, VerificationCode
from app.models.voice_test import VoiceTestResult, VoiceTestSong
from app.models.voice_card import VoiceCard, VoiceCardTemplate
from app.models.identify import UserPortrait, AnalysisRecord
from app.models.chat_room import ChatRoom, RoomMember, MicSeat, RoomMessage, MicRequest
from app.models.message import Conversation, ChatMessage, CommentNotification, SystemNotification
from app.models.square import SquarePost, PostComment, PostLike, CommentLike, UserFavorite

__all__ = [
    # User
    "User", "UserFollow", "VerificationCode",
    # Voice Test
    "VoiceTestResult", "VoiceTestSong",
    # Voice Card
    "VoiceCard", "VoiceCardTemplate",
    # Identify
    "UserPortrait", "AnalysisRecord",
    # Chat Room
    "ChatRoom", "RoomMember", "MicSeat", "RoomMessage", "MicRequest",
    # Message
    "Conversation", "ChatMessage", "CommentNotification", "SystemNotification",
    # Square
    "SquarePost", "PostComment", "PostLike", "CommentLike", "UserFavorite",
]
