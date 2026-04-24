"""
Identify (识Ta) — chat-style relationship analysis endpoints.

Replaces the old voice-based portrait flow. Each conversation maps 1:1 to a
FastGPT chatId so the workflow can maintain its own multi-turn memory.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.identify import IdentifyConversation, IdentifyMessage
from app.models.user import User
from app.services.fastgpt_chat_service import fastgpt_chat_service
from app.services.oss_service import OSSServiceUnavailable, oss_service
from app.utils.response import paginated_response, success_response

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=120)


class ConversationPatchRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class ChatSendRequest(BaseModel):
    text: Optional[str] = Field(None, max_length=2000)
    # Singular image_url kept for backward compatibility with older clients.
    image_url: Optional[str] = Field(None, max_length=500)
    # Preferred multi-image field. When both are supplied, image_urls wins.
    image_urls: Optional[List[str]] = Field(None, max_length=8)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".bmp"}


def _get_owned_conversation(
    db: Session, conversation_id: str, user: User
) -> IdentifyConversation:
    conv = (
        db.query(IdentifyConversation)
        .filter(
            IdentifyConversation.id == conversation_id,
            IdentifyConversation.user_id == user.id,
            IdentifyConversation.status == 1,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def _serialize_conversation(conv: IdentifyConversation) -> Dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "message_count": conv.message_count or 0,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
    }


def _serialize_message(msg: IdentifyMessage) -> Dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "text": msg.text,
        "image_url": msg.image_url,
        # DB currently stores only one URL; expose as a list for frontend
        # parity. (Multi-image persistence is a future schema change.)
        "image_urls": [msg.image_url] if msg.image_url else [],
        "final_content": msg.final_content,
        "workflow_nodes": msg.workflow_nodes or [],
        "tactics": msg.tactics or [],
        "duration_seconds": msg.duration_seconds,
        "status": msg.status,
        "error_message": msg.error_message,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _auto_title(text: Optional[str], has_image: bool) -> str:
    if text:
        cleaned = text.strip().replace("\n", " ")
        if len(cleaned) > 24:
            cleaned = cleaned[:24] + "…"
        if cleaned:
            return cleaned
    return "图片分析" if has_image else "新会话"


# ---------------------------------------------------------------------------
# Endpoints — image upload
# ---------------------------------------------------------------------------
@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    ext = ""
    if file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext and ext not in ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported image type. Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片过大（最大 8MB）")

    try:
        url = oss_service.upload_identify_image(
            user_id=current_user.id,
            file_bytes=content,
            filename=file.filename or f"upload{ext or '.jpg'}",
        )
    except OSSServiceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("OSS upload failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"上传失败: {exc}")

    return success_response({"image_url": url})


# ---------------------------------------------------------------------------
# Endpoints — conversation CRUD
# ---------------------------------------------------------------------------
@router.get("/conversations")
def list_conversations(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = (
        db.query(IdentifyConversation)
        .filter(
            IdentifyConversation.user_id == current_user.id,
            IdentifyConversation.status == 1,
        )
        .order_by(
            sa_func.coalesce(
                IdentifyConversation.last_message_at,
                IdentifyConversation.created_at,
            ).desc()
        )
    )
    total = q.count()
    items = q.offset(max(page - 1, 0) * page_size).limit(page_size).all()
    return paginated_response([_serialize_conversation(c) for c in items], total, page, page_size)


@router.post("/conversations")
def create_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = IdentifyConversation(
        id=str(uuid4()),
        user_id=current_user.id,
        title=(request.title or "新会话").strip() or "新会话",
        message_count=0,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return success_response(_serialize_conversation(conv))


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    request: ConversationPatchRequest,
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    conv.title = request.title.strip()
    db.commit()
    return success_response(_serialize_conversation(conv))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)
    conv.status = 0
    db.commit()
    return success_response({"deleted": True})


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str = Path(...),
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user)

    q = (
        db.query(IdentifyMessage)
        .filter(IdentifyMessage.conversation_id == conv.id)
        .order_by(IdentifyMessage.created_at.asc(), IdentifyMessage.id.asc())
    )
    total = q.count()
    items = q.offset(max(page - 1, 0) * page_size).limit(page_size).all()
    return paginated_response([_serialize_message(m) for m in items], total, page, page_size)


# ---------------------------------------------------------------------------
# Endpoints — SSE chat
# ---------------------------------------------------------------------------
def _sse_line(event: str, payload: Dict) -> bytes:
    return (f"event: {event}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n").encode("utf-8")


@router.post("/conversations/{conversation_id}/chat")
async def chat_stream(
    request: ChatSendRequest,
    conversation_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Normalise input into a single list. image_urls (list) takes precedence;
    # fall back to image_url (string) for older clients.
    img_list: List[str] = [
        u for u in (request.image_urls or []) if u
    ]
    if not img_list and request.image_url:
        img_list = [request.image_url]

    if not (request.text or img_list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "必须提供文本或图片")

    conv = _get_owned_conversation(db, conversation_id, current_user)

    # DB column still stores a single URL; persist the first one for
    # backward-compatible history display. All URLs are forwarded to FastGPT.
    primary_image = img_list[0] if img_list else None

    # Persist the user message immediately.
    # 注意：`user_msg` 的属性在 db.commit() 后会被 expire，之后 async generator
    # 运行时 db session 已关闭，访问 `user_msg.id` 会触发 DetachedInstanceError。
    # 因此先把 id 捕获到纯字符串，避免在 generator 里读 ORM 实例属性。
    user_msg_id = str(uuid4())
    user_msg = IdentifyMessage(
        id=user_msg_id,
        conversation_id=conv.id,
        role="user",
        text=request.text,
        image_url=primary_image,
        status="done",
    )
    now = datetime.utcnow()
    conv.message_count = (conv.message_count or 0) + 1
    conv.last_message_at = now
    if (not conv.title) or conv.title == "新会话":
        conv.title = _auto_title(request.text, bool(img_list))
    db.add(user_msg)
    db.commit()

    # Prepare the assistant-message skeleton (filled as stream progresses).
    assistant_id = str(uuid4())
    assistant_text = request.text
    assistant_images = list(img_list)
    conv_id = conv.id
    user_id = current_user.id

    async def generator() -> AsyncIterator[bytes]:
        answer_parts: List[str] = []
        workflow_nodes: List[Dict] = []
        tactics: List[Dict] = []
        duration_seconds: Optional[int] = None
        errored: Optional[str] = None

        # First frame: tell client the assistant message id so they can locate it later.
        yield _sse_line(
            "start",
            {
                "conversation_id": conv_id,
                "assistant_message_id": assistant_id,
                "user_message": {
                    "id": user_msg_id,
                    "text": assistant_text,
                    "image_url": assistant_images[0] if assistant_images else None,
                    "image_urls": assistant_images,
                },
            },
        )

        try:
            async for evt in fastgpt_chat_service.stream_chat(
                chat_id=conv_id,
                user_id=user_id,
                text=assistant_text,
                image_urls=assistant_images,
            ):
                etype = evt.get("type")

                if etype == "node":
                    name = evt.get("name") or ""
                    stat = evt.get("status") or "running"
                    # Mark previous running node as finished when a new one starts.
                    for n in workflow_nodes:
                        if n.get("status") == "running":
                            n["status"] = "finished"
                    workflow_nodes.append({"name": name, "status": stat})
                    yield _sse_line("node", {"name": name, "status": stat})

                elif etype == "answer":
                    delta = evt.get("delta") or ""
                    if delta:
                        answer_parts.append(delta)
                        yield _sse_line("delta", {"content": delta})

                elif etype == "duration":
                    duration_seconds = int(evt.get("seconds") or 0)
                    yield _sse_line("duration", {"seconds": duration_seconds})

                elif etype == "tactics":
                    data_list = evt.get("data") or []
                    if isinstance(data_list, list) and data_list:
                        tactics = data_list
                        yield _sse_line("tactics", {"tactics": tactics})

                elif etype == "error":
                    errored = evt.get("message") or "AI 分析失败"
                    yield _sse_line("error", {"message": errored})

                elif etype == "done":
                    # No-op — we emit `done` after persistence below.
                    pass
        except Exception as exc:  # noqa: BLE001
            errored = f"流式转发异常: {exc}"
            logger.exception("SSE relay crashed")
            yield _sse_line("error", {"message": errored})

        # Mark final workflow nodes as finished if stream ended cleanly.
        if errored is None:
            for n in workflow_nodes:
                if n.get("status") == "running":
                    n["status"] = "finished"

        # Persist the assistant message in a fresh DB session (the request one
        # may already be closed by the framework once the generator runs).
        final_content = "".join(answer_parts).strip()
        session: Session = SessionLocal()
        try:
            msg = IdentifyMessage(
                id=assistant_id,
                conversation_id=conv_id,
                role="assistant",
                final_content=final_content or None,
                workflow_nodes=workflow_nodes or None,
                tactics=tactics or None,
                duration_seconds=duration_seconds,
                status="failed" if errored else "done",
                error_message=errored,
            )
            session.add(msg)

            refreshed = (
                session.query(IdentifyConversation)
                .filter(IdentifyConversation.id == conv_id)
                .first()
            )
            if refreshed:
                refreshed.message_count = (refreshed.message_count or 0) + 1
                refreshed.last_message_at = datetime.utcnow()
            session.commit()
        except Exception:
            logger.exception("Failed to persist assistant message")
            session.rollback()
        finally:
            session.close()

        yield _sse_line(
            "done",
            {
                "assistant_message_id": assistant_id,
                "status": "failed" if errored else "done",
                "duration_seconds": duration_seconds,
                "error_message": errored,
            },
        )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
