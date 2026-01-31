"""
Chat Room Endpoints with WebSocket Support
"""
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import json

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.chat_room import ChatRoom, RoomMember, MicSeat, RoomMessage, MicRequest
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response
from app.utils.security import decode_token

router = APIRouter()


# ============ WebSocket Connection Manager ============

class ConnectionManager:
    """Manage WebSocket connections for chat rooms"""

    def __init__(self):
        # room_id -> {user_id: websocket}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
        self.active_connections[room_id][user_id] = websocket

    def disconnect(self, room_id: str, user_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].pop(user_id, None)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast_to_room(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            for websocket in self.active_connections[room_id].values():
                try:
                    await websocket.send_json(message)
                except Exception:
                    pass

    async def send_personal(self, room_id: str, user_id: str, message: dict):
        if room_id in self.active_connections and user_id in self.active_connections[room_id]:
            await self.active_connections[room_id][user_id].send_json(message)


manager = ConnectionManager()


# ============ Pydantic Schemas ============

class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Room name")
    room_type: str = Field(default="eight_mic", description="Room type: eight_mic/one_on_one")
    is_private: bool = Field(default=False, description="Is private room")
    password: Optional[str] = Field(None, description="Room password if private")


class UpdateRoomRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    notice: Optional[str] = Field(None, max_length=500)
    background_url: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    message_type: str = Field(default="text", description="Message type: text/gift/system")


# ============ Endpoints ============

@router.post("/create")
def create_room(
    request: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new chat room
    """
    # Generate room code
    room_code = str(uuid4())[:8].upper()

    room = ChatRoom(
        id=str(uuid4()),
        host_id=current_user.id,
        name=request.name,
        room_code=room_code,
        room_type=request.room_type,
        is_private=request.is_private,
        password=request.password if request.is_private else None,
        max_members=2 if request.room_type == "one_on_one" else 100,
        current_members=1
    )

    db.add(room)

    # Add host as first member
    member = RoomMember(
        room_id=room.id,
        user_id=current_user.id,
        role="host"
    )
    db.add(member)

    # Create mic seats (8 for eight_mic, 2 for one_on_one)
    seat_count = 2 if request.room_type == "one_on_one" else 8
    for i in range(seat_count):
        seat = MicSeat(
            id=str(uuid4()),
            room_id=room.id,
            seat_index=i,
            user_id=current_user.id if i == 0 else None,  # Host on first seat
            is_muted=False,
            is_locked=False
        )
        db.add(seat)

    db.commit()
    db.refresh(room)

    return success_response({
        "room_id": room.id,
        "room_code": room.room_code,
        "name": room.name,
        "room_type": room.room_type,
        "is_private": room.is_private,
        "created_at": room.created_at.isoformat() if room.created_at else None
    })


@router.get("/list")
def list_rooms(
    page: int = 1,
    page_size: int = 20,
    room_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List public rooms
    """
    query = db.query(ChatRoom).filter(
        ChatRoom.status == 1,
        ChatRoom.is_private == False
    )

    if room_type:
        query = query.filter(ChatRoom.room_type == room_type)

    query = query.order_by(ChatRoom.current_members.desc(), ChatRoom.created_at.desc())

    total = query.count()
    rooms = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for room in rooms:
        # Get host info
        host = db.query(User).filter(User.id == room.host_id).first()
        items.append({
            "room_id": room.id,
            "room_code": room.room_code,
            "name": room.name,
            "room_type": room.room_type,
            "cover_url": room.cover_url,
            "current_members": room.current_members,
            "max_members": room.max_members,
            "host": {
                "user_id": host.id,
                "name": host.name,
                "avatar": host.avatar
            } if host else None
        })

    return paginated_response(items, total, page, page_size)


@router.get("/{room_id}")
def get_room_detail(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get room detail
    """
    room = db.query(ChatRoom).filter(
        ChatRoom.id == room_id,
        ChatRoom.status == 1
    ).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    # Get host info
    host = db.query(User).filter(User.id == room.host_id).first()

    # Get mic seats
    seats = db.query(MicSeat).filter(
        MicSeat.room_id == room_id
    ).order_by(MicSeat.seat_index).all()

    seat_list = []
    for seat in seats:
        seat_user = None
        if seat.user_id:
            user = db.query(User).filter(User.id == seat.user_id).first()
            if user:
                seat_user = {
                    "user_id": user.id,
                    "name": user.name,
                    "avatar": user.avatar
                }
        seat_list.append({
            "seat_index": seat.seat_index,
            "user": seat_user,
            "is_muted": seat.is_muted,
            "is_locked": seat.is_locked
        })

    return success_response({
        "room_id": room.id,
        "room_code": room.room_code,
        "name": room.name,
        "notice": room.notice,
        "room_type": room.room_type,
        "cover_url": room.cover_url,
        "background_url": room.background_url,
        "current_members": room.current_members,
        "max_members": room.max_members,
        "is_private": room.is_private,
        "host": {
            "user_id": host.id,
            "name": host.name,
            "avatar": host.avatar
        } if host else None,
        "mic_seats": seat_list,
        "created_at": room.created_at.isoformat() if room.created_at else None
    })


@router.post("/{room_id}/join")
def join_room(
    room_id: str,
    password: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Join a chat room
    """
    room = db.query(ChatRoom).filter(
        ChatRoom.id == room_id,
        ChatRoom.status == 1
    ).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    # Check password for private room
    if room.is_private and room.password != password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid password"
        )

    # Check if already a member
    existing = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == current_user.id
    ).first()

    if existing:
        return success_response({"message": "Already in room"})

    # Check room capacity
    if room.current_members >= room.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room is full"
        )

    # Add as member
    member = RoomMember(
        room_id=room_id,
        user_id=current_user.id,
        role="member"
    )
    db.add(member)

    room.current_members += 1
    db.commit()

    return success_response({
        "room_id": room.id,
        "message": "Joined successfully"
    })


@router.post("/{room_id}/leave")
def leave_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Leave a chat room
    """
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    # Can't leave if host
    if room.host_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Host cannot leave. Please close the room instead."
        )

    # Remove from members
    db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == current_user.id
    ).delete()

    # Remove from mic seat if on one
    db.query(MicSeat).filter(
        MicSeat.room_id == room_id,
        MicSeat.user_id == current_user.id
    ).update({"user_id": None})

    room.current_members = max(0, room.current_members - 1)
    db.commit()

    return success_response({"message": "Left room"})


@router.post("/{room_id}/mic/request")
def request_mic(
    room_id: str,
    seat_index: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request to get on mic
    """
    room = db.query(ChatRoom).filter(
        ChatRoom.id == room_id,
        ChatRoom.status == 1
    ).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    # Check if seat is available
    seat = db.query(MicSeat).filter(
        MicSeat.room_id == room_id,
        MicSeat.seat_index == seat_index
    ).first()

    if not seat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid seat"
        )

    if seat.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seat is occupied"
        )

    if seat.is_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seat is locked"
        )

    # Create mic request
    request = MicRequest(
        id=str(uuid4()),
        room_id=room_id,
        user_id=current_user.id,
        seat_index=seat_index
    )
    db.add(request)
    db.commit()

    return success_response({
        "request_id": request.id,
        "message": "Mic request sent"
    })


@router.post("/{room_id}/mic/approve/{request_id}")
def approve_mic_request(
    room_id: str,
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Approve mic request (host only)
    """
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room or room.host_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only host can approve requests"
        )

    request = db.query(MicRequest).filter(
        MicRequest.id == request_id,
        MicRequest.status == "pending"
    ).first()

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )

    # Update seat
    seat = db.query(MicSeat).filter(
        MicSeat.room_id == room_id,
        MicSeat.seat_index == request.seat_index
    ).first()

    if seat and not seat.user_id:
        seat.user_id = request.user_id
        request.status = "approved"
        db.commit()
        return success_response({"message": "Request approved"})

    request.status = "rejected"
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Seat no longer available"
    )


@router.post("/{room_id}/mic/leave")
def leave_mic(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Leave mic seat
    """
    seat = db.query(MicSeat).filter(
        MicSeat.room_id == room_id,
        MicSeat.user_id == current_user.id
    ).first()

    if not seat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not on mic"
        )

    # Can't leave if host and on seat 0
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if room and room.host_id == current_user.id and seat.seat_index == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Host cannot leave main seat"
        )

    seat.user_id = None
    db.commit()

    return success_response({"message": "Left mic"})


@router.post("/{room_id}/mic/mute/{seat_index}")
def toggle_mute(
    room_id: str,
    seat_index: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle mute on mic seat
    """
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    seat = db.query(MicSeat).filter(
        MicSeat.room_id == room_id,
        MicSeat.seat_index == seat_index
    ).first()

    if not seat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found"
        )

    # Only host or seat owner can mute
    if room.host_id != current_user.id and seat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )

    seat.is_muted = not seat.is_muted
    db.commit()

    return success_response({
        "seat_index": seat_index,
        "is_muted": seat.is_muted
    })


@router.post("/{room_id}/close")
def close_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Close room (host only)
    """
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    if room.host_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only host can close the room"
        )

    room.status = 0
    db.commit()

    return success_response({"message": "Room closed"})


@router.get("/{room_id}/messages")
def get_room_messages(
    room_id: str,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get room message history
    """
    query = db.query(RoomMessage).filter(
        RoomMessage.room_id == room_id
    ).order_by(RoomMessage.created_at.desc())

    total = query.count()
    messages = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for msg in messages:
        user = db.query(User).filter(User.id == msg.user_id).first()
        items.append({
            "message_id": msg.id,
            "user": {
                "user_id": user.id,
                "name": user.name,
                "avatar": user.avatar
            } if user else None,
            "content": msg.content,
            "message_type": msg.message_type,
            "created_at": msg.created_at.isoformat() if msg.created_at else None
        })

    return paginated_response(items, total, page, page_size)


# ============ WebSocket Endpoint ============

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str
):
    """
    WebSocket connection for real-time chat room communication
    """
    # Get token from query params
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return

    # Verify token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")

    # Verify room exists
    db = SessionLocal()
    try:
        room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.status == 1
        ).first()

        if not room:
            await websocket.close(code=4004)
            return

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close(code=4001)
            return

        await manager.connect(websocket, room_id, user_id)

        # Broadcast join message
        await manager.broadcast_to_room(room_id, {
            "type": "user_joined",
            "user": {
                "user_id": user.id,
                "name": user.name,
                "avatar": user.avatar
            },
            "timestamp": datetime.utcnow().isoformat()
        })

        try:
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type", "message")

                if message_type == "message":
                    # Save message to database
                    msg = RoomMessage(
                        id=str(uuid4()),
                        room_id=room_id,
                        user_id=user_id,
                        content=data.get("content", ""),
                        message_type="text"
                    )
                    db.add(msg)
                    db.commit()

                    # Broadcast message
                    await manager.broadcast_to_room(room_id, {
                        "type": "message",
                        "message_id": msg.id,
                        "user": {
                            "user_id": user.id,
                            "name": user.name,
                            "avatar": user.avatar
                        },
                        "content": msg.content,
                        "timestamp": msg.created_at.isoformat() if msg.created_at else None
                    })

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            manager.disconnect(room_id, user_id)
            await manager.broadcast_to_room(room_id, {
                "type": "user_left",
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            })
    finally:
        db.close()
