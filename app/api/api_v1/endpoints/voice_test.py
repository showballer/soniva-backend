"""
Voice Test Endpoints
"""
import os
import shutil
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import get_db
from app.models.user import User
from app.models.voice_test import VoiceTestResult, VoiceTestSong
from app.dependencies import get_current_user
from app.services.voice_service import voice_analysis_service
from app.utils.response import success_response, paginated_response
from app.config import settings

router = APIRouter()

# Upload directory
UPLOAD_DIR = Path(settings.LOCAL_STORAGE_PATH) / "voice"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============ Pydantic Schemas ============

class AnalyzeRequest(BaseModel):
    file_id: str = Field(..., description="Uploaded file ID")
    text_content: str = Field(..., description="Read text content")
    gender: str = Field(..., description="Gender: female/male")


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
    Analyze voice (AI function)
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

    # Extract voice features
    try:
        features = voice_analysis_service.analyze_audio(str(file_path))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice analysis failed: {str(e)}"
        )

    # Calculate voice type scores
    voice_type_scores = voice_analysis_service.get_voice_type_scores(features, request.gender)

    # Get main voice type (highest score)
    main_voice_type = max(voice_type_scores, key=voice_type_scores.get)

    # Generate tags based on AI hints
    ai_hints = features.get("ai_hints", {})
    tags = []
    if "clear" in ai_hints.get("clarity_hint", "").lower():
        tags.append("清澈")
    if "bright" in ai_hints.get("brightness_hint", "").lower():
        tags.append("明亮")
    if "gentle" in ai_hints.get("energy_hint", "").lower() or "soft" in ai_hints.get("energy_hint", "").lower():
        tags.append("温柔")
    if "breath" in ai_hints.get("breath_hint", "").lower():
        tags.append("气息感")
    if "stable" in ai_hints.get("stability_hint", "").lower():
        tags.append("稳定")

    # Calculate scores (simplified algorithm)
    f0_data = features.get("f0_hz", {})
    harmonic = features.get("harmonic_ratio", {}).get("value", 0.7)

    overall_score = min(10, max(5, 7 + harmonic * 3 + f0_data.get("pitch_stability", 0.5) * 2))
    charm_index = min(10, max(5, 6.5 + harmonic * 2 + (1 - features.get("spectral_flatness", {}).get("mean", 0.5)) * 2))

    # Estimate hearing age and height based on F0
    f0_mean = f0_data.get("mean", 200)
    if request.gender == "female":
        hearing_age = max(16, min(35, int(40 - f0_mean / 15)))
        hearing_height = max(155, min(175, int(140 + f0_mean / 10)))
    else:
        hearing_age = max(18, min(45, int(50 - f0_mean / 5)))
        hearing_height = max(165, min(190, int(180 - f0_mean / 20)))

    # Voice attribute
    pitch_stability = f0_data.get("pitch_stability", 0.5)
    if pitch_stability > 0.8:
        voice_attribute = "攻"
    elif pitch_stability < 0.5:
        voice_attribute = "受"
    else:
        voice_attribute = "可攻可受"

    # Color temperature
    centroid = features.get("spectral_centroid", {}).get("mean_hz", 2500)
    if centroid > 3000:
        color_temperature = "冷"
    elif centroid < 2000:
        color_temperature = "暖"
    else:
        color_temperature = "中性"

    # Create result record
    result = VoiceTestResult(
        id=str(uuid4()),
        user_id=current_user.id,
        audio_url=f"/uploads/voice/{file_path.name}",
        text_content=request.text_content,
        duration=features.get("basic_info", {}).get("duration_seconds", 0),
        gender=request.gender,
        voice_features=features,
        voice_type_scores=voice_type_scores,
        main_voice_type=main_voice_type,
        tags=tags,
        overall_score=round(overall_score, 1),
        charm_index=round(charm_index, 1),
        hearing_age=hearing_age,
        hearing_height=hearing_height,
        voice_attribute=voice_attribute,
        color_temperature=color_temperature,
        emotional_summary=ai_hints.get("voice_type_hint", ""),
        advanced_suggestion=ai_hints.get("modifier_hint", "")
    )

    db.add(result)

    # Add recommended songs (mock data for now)
    songs = [
        {"name": "小幸运", "artist": "田馥甄", "reason": "音域契合，适合展现声音特质"},
        {"name": "遇见", "artist": "孙燕姿", "reason": "节奏适中，适合练习气息控制"},
        {"name": "童话", "artist": "光良", "reason": "旋律优美，适合展现声音魅力"}
    ]

    for i, song in enumerate(songs):
        db.add(VoiceTestSong(
            result_id=result.id,
            song_name=song["name"],
            artist=song["artist"],
            reason=song["reason"],
            sort_order=i
        ))

    db.commit()
    db.refresh(result)

    return success_response({
        "result_id": result.id,
        "voice_type_scores": voice_type_scores,
        "main_voice_type": main_voice_type,
        "tags": tags,
        "overall_score": result.overall_score,
        "charm_index": result.charm_index,
        "hearing_age": result.hearing_age,
        "hearing_height": result.hearing_height,
        "voice_attribute": result.voice_attribute,
        "color_temperature": result.color_temperature,
        "emotional_summary": result.emotional_summary,
        "advanced_suggestion": result.advanced_suggestion,
        "recommended_songs": songs,
        "created_at": result.created_at.isoformat() if result.created_at else None
    })


@router.get("/history")
def get_voice_test_history(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get voice test history
    """
    query = db.query(VoiceTestResult).filter(
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).order_by(VoiceTestResult.created_at.desc())

    total = query.count()
    results = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "result_id": r.id,
        "main_voice_type": r.main_voice_type,
        "overall_score": float(r.overall_score) if r.overall_score else 0,
        "tags": r.tags or [],
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "audio_url": r.audio_url
    } for r in results]

    return paginated_response(items, total, page, page_size)


@router.get("/result/{result_id}")
def get_voice_test_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get voice test result detail
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
        "voice_type_scores": result.voice_type_scores,
        "main_voice_type": result.main_voice_type,
        "tags": result.tags,
        "overall_score": float(result.overall_score) if result.overall_score else 0,
        "charm_index": float(result.charm_index) if result.charm_index else 0,
        "hearing_age": result.hearing_age,
        "hearing_height": result.hearing_height,
        "voice_attribute": result.voice_attribute,
        "color_temperature": result.color_temperature,
        "emotional_summary": result.emotional_summary,
        "advanced_suggestion": result.advanced_suggestion,
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
