"""
API Router Aggregation
"""
from fastapi import APIRouter

from app.api.api_v1.endpoints import (
    auth,
    voice_test,
    voice_card,
    identify,
    chat_room,
    message,
    square,
    user
)

api_router = APIRouter()

# Auth routes
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["认证"]
)

# Voice test routes
api_router.include_router(
    voice_test.router,
    prefix="/voice-test",
    tags=["声音测试"]
)

# Voice card routes
api_router.include_router(
    voice_card.router,
    prefix="/voice-card",
    tags=["声卡"]
)

# Identify routes
api_router.include_router(
    identify.router,
    prefix="/identify",
    tags=["识Ta"]
)

# Chat room routes
api_router.include_router(
    chat_room.router,
    prefix="/chat-room",
    tags=["聊天室"]
)

# Message routes
api_router.include_router(
    message.router,
    prefix="/message",
    tags=["消息中心"]
)

# Square routes
api_router.include_router(
    square.router,
    prefix="/square",
    tags=["广场"]
)

# User routes
api_router.include_router(
    user.router,
    prefix="/user",
    tags=["用户"]
)
