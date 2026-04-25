"""
Identify (识Ta) — chat-style relationship analysis endpoints.

Replaces the old voice-based portrait flow. Each conversation maps 1:1 to a
FastGPT chatId so the workflow can maintain its own multi-turn memory.
"""
from __future__ import annotations

import asyncio
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


# Module-level reference set so detached `asyncio.create_task` results
# survive request cancellation. Without holding a strong ref the task
# may be garbage-collected mid-flight.
_identify_background_tasks: set[asyncio.Task] = set()


def _spawn_detached(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _identify_background_tasks.add(task)
    task.add_done_callback(_identify_background_tasks.discard)
    return task


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
    # Forwarded to FastGPT as variables.isDeepAnalysis — switches the workflow
    # between simple-mode and the full-depth tactics branch.
    is_deep_analysis: Optional[bool] = Field(False)


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
    """Open an SSE stream for a new assistant reply.

    The FastGPT call runs in a *detached* background task (see
    `_spawn_detached`) so client disconnects mid-stream no longer
    abandon the analysis. The HTTP stream is just a live view of events
    the worker emits — the worker is responsible for flipping the
    pre-persisted assistant placeholder from `streaming` to `done` /
    `failed` regardless of whether anyone is still reading the SSE.

    Resume flow on the client: when reopening the chat after a
    disconnect, the client sees `status='streaming'` on the placeholder,
    shows a spinner, and polls `GET /messages` until status changes.
    """
    logger.info(
        "[识Ta][chat] conv=%s user=%s text_len=%d image_urls=%s image_url=%s is_deep_analysis=%s",
        conversation_id,
        current_user.id,
        len(request.text or ""),
        request.image_urls,
        request.image_url,
        request.is_deep_analysis,
    )

    # Normalise input. image_urls (list) wins; fall back to image_url for older clients.
    img_list: List[str] = [u for u in (request.image_urls or []) if u]
    if not img_list and request.image_url:
        img_list = [request.image_url]

    if not (request.text or img_list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "必须提供文本或图片")

    conv = _get_owned_conversation(db, conversation_id, current_user)
    primary_image = img_list[0] if img_list else None

    # Persist BOTH the user message and an assistant placeholder upfront.
    # Committing the placeholder before kicking off the worker means:
    #   • the worker can locate it via id even from a fresh session
    #   • a client that reopens the chat mid-flight sees the
    #     placeholder in `streaming` state and knows to poll
    user_msg_id = str(uuid4())
    assistant_id = str(uuid4())
    now = datetime.utcnow()

    user_msg = IdentifyMessage(
        id=user_msg_id,
        conversation_id=conv.id,
        role="user",
        text=request.text,
        image_url=primary_image,
        status="done",
    )
    assistant_placeholder = IdentifyMessage(
        id=assistant_id,
        conversation_id=conv.id,
        role="assistant",
        status="streaming",
    )
    conv.message_count = (conv.message_count or 0) + 2
    conv.last_message_at = now
    if (not conv.title) or conv.title == "新会话":
        conv.title = _auto_title(request.text, bool(img_list))
    db.add_all([user_msg, assistant_placeholder])
    db.commit()

    # Snapshot inputs into plain values — the worker uses its own DB
    # session and may run after the request handler has returned.
    conv_id = conv.id
    user_id = current_user.id
    text = request.text
    images = list(img_list)
    is_deep = bool(request.is_deep_analysis)

    # Bridges live FastGPT events from the worker to the HTTP stream.
    # If the client disconnects, the queue is simply abandoned (it gets
    # GC'd along with the http_stream coroutine); the worker keeps
    # running and pushing events here until it finishes — those extra
    # puts are harmless on an unbounded queue with no consumer.
    events_queue: asyncio.Queue = asyncio.Queue()

    _spawn_detached(_process_identify_chat(
        assistant_id=assistant_id,
        conv_id=conv_id,
        user_id=user_id,
        text=text,
        images=images,
        is_deep=is_deep,
        events_queue=events_queue,
    ))

    async def http_stream() -> AsyncIterator[bytes]:
        # First frame: tell client the assistant message id so they can
        # locate it later in /messages history.
        yield _sse_line(
            "start",
            {
                "conversation_id": conv_id,
                "assistant_message_id": assistant_id,
                "user_message": {
                    "id": user_msg_id,
                    "text": text,
                    "image_url": images[0] if images else None,
                    "image_urls": images,
                },
            },
        )

        while True:
            evt = await events_queue.get()
            etype = evt.get("type")

            if etype == "_end":
                yield _sse_line("done", {
                    "assistant_message_id": assistant_id,
                    "status": evt.get("status"),
                    "duration_seconds": evt.get("duration_seconds"),
                    "error_message": evt.get("error_message"),
                })
                return

            if etype == "node":
                yield _sse_line("node", {
                    "name": evt.get("name") or "",
                    "status": evt.get("status") or "running",
                })
            elif etype == "answer":
                delta = evt.get("delta") or ""
                if delta:
                    yield _sse_line("delta", {"content": delta})
            elif etype == "duration":
                yield _sse_line("duration", {"seconds": int(evt.get("seconds") or 0)})
            elif etype == "tactics":
                data_list = evt.get("data") or []
                if isinstance(data_list, list) and data_list:
                    yield _sse_line("tactics", {"tactics": data_list})
            elif etype == "error":
                yield _sse_line("error", {"message": evt.get("message") or "AI 分析失败"})
            # `done` events from FastGPT are absorbed by the worker; we
            # only emit our own once persistence is complete.

    return StreamingResponse(
        http_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _process_identify_chat(
    *,
    assistant_id: str,
    conv_id: str,
    user_id: str,
    text: Optional[str],
    images: List[str],
    is_deep: bool,
    events_queue: asyncio.Queue,
) -> None:
    """Run FastGPT, persist the result, signal the live stream when done.

    Detached from the request handler so a client disconnect does not
    cancel us — the analysis must always reach a terminal state in the
    DB so that resume / history fetches see a definitive status.
    """
    answer_parts: List[str] = []
    workflow_nodes: List[Dict] = []
    tactics: List[Dict] = []
    duration_seconds: Optional[int] = None
    errored: Optional[str] = None

    try:
        async for evt in fastgpt_chat_service.stream_chat(
            chat_id=conv_id,
            user_id=user_id,
            text=text,
            image_urls=images,
            is_deep_analysis=is_deep,
        ):
            etype = evt.get("type")

            if etype == "node":
                name = evt.get("name") or ""
                stat = evt.get("status") or "running"
                for n in workflow_nodes:
                    if n.get("status") == "running":
                        n["status"] = "finished"
                workflow_nodes.append({"name": name, "status": stat})
            elif etype == "answer":
                delta = evt.get("delta") or ""
                if delta:
                    answer_parts.append(delta)
            elif etype == "duration":
                duration_seconds = int(evt.get("seconds") or 0)
            elif etype == "tactics":
                data_list = evt.get("data") or []
                if isinstance(data_list, list) and data_list:
                    tactics = data_list
            elif etype == "error":
                errored = evt.get("message") or "AI 分析失败"
            elif etype == "done":
                # No-op — we emit our own _end after DB persistence.
                continue

            # Forward to the live HTTP stream. put_nowait is safe — the
            # queue is unbounded; an absent consumer just leaks events
            # that get GC'd when this coroutine returns.
            try:
                events_queue.put_nowait(evt)
            except Exception:  # noqa: BLE001
                logger.warning("[识Ta][%s] events_queue.put_nowait dropped", assistant_id)
    except Exception as exc:  # noqa: BLE001
        errored = f"流式转发异常: {exc}"
        logger.exception("[识Ta][%s] FastGPT processing crashed", assistant_id)
        try:
            events_queue.put_nowait({"type": "error", "message": errored})
        except Exception:  # noqa: BLE001
            pass

    if errored is None:
        for n in workflow_nodes:
            if n.get("status") == "running":
                n["status"] = "finished"

    final_content = "".join(answer_parts).strip() or None
    final_status = "failed" if errored else "done"

    session: Session = SessionLocal()
    try:
        msg = (
            session.query(IdentifyMessage)
            .filter(IdentifyMessage.id == assistant_id)
            .first()
        )
        if msg is None:
            logger.error("[识Ta][%s] assistant placeholder vanished", assistant_id)
        else:
            msg.final_content = final_content
            msg.workflow_nodes = workflow_nodes or None
            msg.tactics = tactics or None
            msg.duration_seconds = duration_seconds
            msg.status = final_status
            msg.error_message = errored

            conv_row = (
                session.query(IdentifyConversation)
                .filter(IdentifyConversation.id == conv_id)
                .first()
            )
            if conv_row:
                conv_row.last_message_at = datetime.utcnow()

            session.commit()
            logger.info(
                "[识Ta][%s] persisted status=%s len=%d",
                assistant_id,
                final_status,
                len(final_content or ""),
            )
    except Exception:  # noqa: BLE001
        logger.exception("[识Ta][%s] failed to persist assistant message", assistant_id)
        session.rollback()
    finally:
        session.close()

    # Sentinel: signal the HTTP stream we're done. If no one is listening
    # the queue is just GC'd alongside this coroutine.
    try:
        events_queue.put_nowait({
            "type": "_end",
            "status": final_status,
            "duration_seconds": duration_seconds,
            "error_message": errored,
        })
    except Exception:  # noqa: BLE001
        pass
