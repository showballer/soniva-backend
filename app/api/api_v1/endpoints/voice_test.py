"""
Voice Test Endpoints
"""
import asyncio
import json
import logging
import os
import shutil
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import SessionLocal, get_db
from app.models.user import User
from app.models.voice_test import VoiceTestResult, VoiceTestSong
from app.dependencies import get_current_user
from app.services.voice_service import voice_analysis_service
from app.services.fastgpt_service import fastgpt_service
from app.utils.response import success_response, paginated_response
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Upload directory
UPLOAD_DIR = Path(settings.LOCAL_STORAGE_PATH) / "voice"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Module-level reference set so `asyncio.create_task` results are not
# garbage-collected before they finish. Without this, Python may cancel a
# detached task while it's mid-execution.
_voice_background_tasks: set[asyncio.Task] = set()


def _spawn_detached(coro) -> asyncio.Task:
    """Launch a coroutine in the background, surviving client disconnects."""
    task = asyncio.create_task(coro)
    _voice_background_tasks.add(task)
    task.add_done_callback(_voice_background_tasks.discard)
    return task


# ============ Pydantic Schemas ============

class AnalyzeRequest(BaseModel):
    file_id: str = Field(..., description="Uploaded file ID")
    text_content: str = Field(..., description="Read text content")
    gender: Optional[str] = Field(None, description="Gender: female/male (optional, will use user's gender from database if not provided)")


class VoiceResultResponse(BaseModel):
    result_id: str
    main_voice_type: str
    overall_score: float
    charm_index: float
    tags: List[str]
    created_at: str


# ============ Endpoints ============

@router.post("/upload")
async def upload_voice_file(
    file: UploadFile = File(...),
    text_content: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload voice file
    """
    # Validate file type
    allowed_extensions = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Validate file size (max 30MB)
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 30MB"
        )

    # Generate file ID and save
    file_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # Get audio duration using librosa
    try:
        import librosa
        y, sr = librosa.load(str(file_path), sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
    except Exception as e:
        # Clean up file if loading fails
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process audio file: {str(e)}"
        )

    return success_response({
        "file_id": file_id,
        "file_url": f"/uploads/voice/{file_id}{file_ext}",
        "duration": round(duration, 2)
    })


@router.post("/analyze")
async def analyze_voice(
    request: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kick off voice analysis. Returns immediately with a task_status of
    'processing'; the actual librosa + FastGPT work runs in a detached
    background task so that closing/backgrounding the app no longer kills
    the analysis. Clients poll /voice-test/result/{result_id} (or the
    history list) to see when task_status flips to 'completed' / 'failed'.
    """
    # Find the uploaded file
    file_path = None
    for ext in [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"]:
        potential_path = UPLOAD_DIR / f"{request.file_id}{ext}"
        if potential_path.exists():
            file_path = potential_path
            break

    if file_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file not found"
        )

    # Resolve gender + nickname for the worker.
    nickname = current_user.name or "用户"
    gender = request.gender or current_user.gender or "male"

    # Cheap probe so the placeholder row carries a sensible duration; we
    # avoid the expensive feature extraction here — that runs in the worker.
    duration_sec = 0.0
    try:
        import librosa
        y, sr = librosa.load(str(file_path), sr=None)
        duration_sec = float(librosa.get_duration(y=y, sr=sr))
    except Exception:  # noqa: BLE001
        logger.warning("[VoiceTest] Could not probe duration for %s", file_path)

    # Create the placeholder row in 'processing' state. The frontend uses
    # task_status, not main_voice_type, to decide whether to render full
    # data — so we just stash blank placeholders here.
    result_id = str(uuid4())
    placeholder = VoiceTestResult(
        id=result_id,
        user_id=current_user.id,
        audio_url=f"/uploads/voice/{file_path.name}",
        text_content=request.text_content,
        duration=duration_sec,
        gender=gender,
        main_voice_type={"level1": "", "level2": "", "full_name": ""},
        task_status="processing",
    )
    db.add(placeholder)
    db.commit()

    _spawn_detached(_run_voice_analysis(
        result_id=result_id,
        file_path=file_path,
        gender=gender,
        nickname=nickname,
    ))

    return success_response({
        "result_id": result_id,
        "task_status": "processing",
    })


async def _run_voice_analysis(
    *,
    result_id: str,
    file_path: Path,
    gender: str,
    nickname: str,
) -> None:
    """Run librosa + FastGPT, write results back to the placeholder row.

    Runs detached from the request handler so the worker survives client
    disconnects. Uses its own DB session (the request session is closed
    once the handler returns).
    """
    session: Session = SessionLocal()
    try:
        # CPU-bound librosa call — push to a thread so the event loop
        # stays responsive for other requests / FastGPT streams.
        try:
            features = await asyncio.to_thread(
                voice_analysis_service.analyze_audio,
                str(file_path),
            )
            logger.info("[VoiceTest][%s] features extracted", result_id)
        except Exception as exc:
            logger.exception("[VoiceTest][%s] feature extraction failed", result_id)
            _mark_failed(session, result_id, f"声音特征提取失败: {exc}")
            return

        try:
            ai_result = await fastgpt_service.analyze_voice(
                voice_features=features,
                gender=gender,
                nickname=nickname,
            )
            # The *raw* HTTP response body from FastGPT is already logged
            # inside fastgpt_service (`响应原始内容`). This line shows the
            # post-parse dict — useful for verifying what we'll persist.
            logger.info(
                "[VoiceTest][%s] FastGPT parsed dict:\n%s",
                result_id,
                json.dumps(ai_result, ensure_ascii=False, indent=2)
                if ai_result else "(none — FastGPT returned no usable data)",
            )
        except Exception as exc:
            logger.exception("[VoiceTest][%s] FastGPT call crashed", result_id)
            _mark_failed(session, result_id, f"AI 分析失败: {exc}")
            return

        # No silent fallback. If FastGPT didn't produce a usable result
        # (timeout, 5xx, malformed JSON, empty parse) we mark the task as
        # failed so the user knows to retry. The previous rule-based
        # fallback used the same "小幸运/遇见/童话" + "温柔动听/富有感染力"
        # placeholders for every failed call, which silently turned every
        # outage into "every voice gets the same generic profile".
        if not ai_result:
            _mark_failed(
                session,
                result_id,
                "AI 分析未返回有效结果（请稍后重试，或检查后端日志的 FastGPT 接口返回）",
            )
            return

        main_voice_type = ai_result.get("main_voice_type", {})
        auxiliary_tags = ai_result.get("auxiliary_tags", [])
        development_directions = ai_result.get("development_directions", [])
        voice_position = ai_result.get("voice_position", "")
        resonance = ai_result.get("resonance", [])
        voice_attribute = ai_result.get("voice_attribute", "")
        voice_temperature = ai_result.get("voice_temperature", "")
        perceived_food = ai_result.get("perceived_food", "")
        perceived_age = ai_result.get("perceived_age", 0)
        perceived_height = ai_result.get("perceived_height", 0)
        perceived_feedback = ai_result.get("perceived_feedback", [])
        love_score = ai_result.get("love_score", 0)
        recommended_partner = ai_result.get("recommended_partner", [])
        signature = ai_result.get("signature", "")
        improvement_tips = ai_result.get("improvement_tips", [])
        songs = ai_result.get("recommended_songs", [])

        if not main_voice_type or not isinstance(main_voice_type, dict):
            main_voice_type = {
                "level1": "未知",
                "level2": "未知",
                "full_name": "未知",
            }

        # Write back to DB.
        try:
            result = (
                session.query(VoiceTestResult)
                .filter(VoiceTestResult.id == result_id)
                .first()
            )
            if not result:
                logger.error("[VoiceTest][%s] placeholder vanished", result_id)
                return

            result.voice_features = features
            result.duration = features.get("基本信息", {}).get("音频时长_秒", result.duration or 0)
            result.main_voice_type = main_voice_type
            result.auxiliary_tags = auxiliary_tags
            result.development_directions = development_directions
            result.voice_position = voice_position
            result.resonance = resonance
            result.voice_attribute = voice_attribute
            result.voice_temperature = voice_temperature
            result.perceived_food = perceived_food
            result.perceived_age = perceived_age
            result.perceived_height = perceived_height
            result.perceived_feedback = perceived_feedback
            result.love_score = love_score
            result.recommended_partner = recommended_partner
            result.signature = signature
            result.improvement_tips = improvement_tips
            result.task_status = "completed"
            result.error_message = None

            if songs:
                for i, song in enumerate(songs[:3]):
                    if isinstance(song, str):
                        session.add(VoiceTestSong(
                            result_id=result_id,
                            song_name=song,
                            artist="未知",
                            reason="",
                            sort_order=i,
                        ))
                    elif isinstance(song, dict):
                        session.add(VoiceTestSong(
                            result_id=result_id,
                            song_name=song.get("name", song.get("song_name", "")),
                            artist=song.get("artist", ""),
                            reason=song.get("reason", ""),
                            sort_order=i,
                        ))

            # Snapshot of what we're persisting — useful when the AI
            # returned something but a field looks wrong on the client
            # side. Excludes the 50-key voice_features blob since it's
            # already logged by voice_analysis_service.
            try:
                summary = {
                    "result_id": result_id,
                    "main_voice_type": main_voice_type,
                    "auxiliary_tags": auxiliary_tags,
                    "development_directions": development_directions,
                    "voice_position": voice_position,
                    "resonance": resonance,
                    "voice_attribute": voice_attribute,
                    "voice_temperature": voice_temperature,
                    "perceived_food": perceived_food,
                    "perceived_age": perceived_age,
                    "perceived_height": perceived_height,
                    "perceived_feedback": perceived_feedback,
                    "love_score": love_score,
                    "recommended_partner": recommended_partner,
                    "signature": signature,
                    "improvement_tips": improvement_tips,
                    "recommended_songs": songs,
                }
                logger.info(
                    "[VoiceTest][%s] persisting result:\n%s",
                    result_id,
                    json.dumps(summary, ensure_ascii=False, indent=2),
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[VoiceTest][%s] failed to log result summary (non-fatal)",
                    result_id,
                )

            session.commit()
            logger.info("[VoiceTest][%s] completed", result_id)
        except Exception as exc:
            logger.exception("[VoiceTest][%s] persistence failed", result_id)
            session.rollback()
            _mark_failed(session, result_id, f"结果保存失败: {exc}")
    finally:
        session.close()


def _mark_failed(session: Session, result_id: str, message: str) -> None:
    """Best-effort flip a placeholder row to failed state."""
    try:
        result = (
            session.query(VoiceTestResult)
            .filter(VoiceTestResult.id == result_id)
            .first()
        )
        if result:
            result.task_status = "failed"
            result.error_message = (message or "")[:500]
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[VoiceTest][%s] failed to record failure state", result_id)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass


@router.get("/history")
def get_voice_test_history(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get voice test history (includes pending / processing items so the
    frontend can show in-flight rows and poll until they settle).
    """
    query = db.query(VoiceTestResult).filter(
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1,
    ).order_by(VoiceTestResult.created_at.desc())

    total = query.count()
    results = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "result_id": r.id,
        "main_voice_type": r.main_voice_type,
        "auxiliary_tags": r.auxiliary_tags or [],
        "love_score": r.love_score,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "audio_url": r.audio_url,
        "task_status": r.task_status,
        "error_message": r.error_message,
    } for r in results]

    return paginated_response(items, total, page, page_size)


@router.get("/result/{result_id}")
def get_voice_test_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get voice test result detail. Returns task_status so the client can
    distinguish processing rows (where most fields are still empty) from
    completed ones.
    """
    result = db.query(VoiceTestResult).filter(
        VoiceTestResult.id == result_id,
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found"
        )

    # Get recommended songs
    songs = db.query(VoiceTestSong).filter(
        VoiceTestSong.result_id == result_id
    ).order_by(VoiceTestSong.sort_order).all()

    return success_response({
        "result_id": result.id,
        "task_status": result.task_status,
        "error_message": result.error_message,
        "audio_url": result.audio_url,
        "main_voice_type": result.main_voice_type,
        "auxiliary_tags": result.auxiliary_tags or [],
        "development_directions": result.development_directions or [],
        "voice_position": result.voice_position,
        "resonance": result.resonance or [],
        "voice_attribute": result.voice_attribute,
        "voice_temperature": result.voice_temperature,
        "perceived_food": result.perceived_food,
        "perceived_age": result.perceived_age,
        "perceived_height": result.perceived_height,
        "perceived_feedback": result.perceived_feedback or [],
        "love_score": result.love_score,
        "recommended_partner": result.recommended_partner or [],
        "signature": result.signature,
        "improvement_tips": result.improvement_tips or [],
        "recommended_songs": [{
            "name": s.song_name,
            "artist": s.artist,
            "reason": s.reason
        } for s in songs],
        "created_at": result.created_at.isoformat() if result.created_at else None
    })


@router.delete("/result/{result_id}")
def delete_voice_test_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete voice test result
    """
    result = db.query(VoiceTestResult).filter(
        VoiceTestResult.id == result_id,
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found"
        )

    result.status = 0
    db.commit()

    return success_response({
        "message": "Deleted successfully"
    })
