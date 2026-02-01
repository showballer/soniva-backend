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
from app.services.fastgpt_service import fastgpt_service
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
    Analyze voice (AI function with FastGPT integration)
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

    # Extract voice features using librosa
    try:
        features = voice_analysis_service.analyze_audio(str(file_path))
        print(f"[VoiceTest] Extracted features: {features.get('AI预判断', {})}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice analysis failed: {str(e)}"
        )

    # Call FastGPT for AI analysis
    # Pass user nickname and gender to FastGPT
    nickname = current_user.name or "用户"
    ai_result = await fastgpt_service.analyze_voice(
        voice_features=features,
        gender=request.gender,
        nickname=nickname
    )
    print(f"[VoiceTest] FastGPT result: {ai_result}")

    # Use FastGPT results if available, otherwise fall back to rule-based
    if ai_result:
        # Use AI results (新字段结构)
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

        # 确保 main_voice_type 有完整结构
        if not main_voice_type or not isinstance(main_voice_type, dict):
            main_voice_type = {
                "level1": "未知",
                "level2": "未知",
                "full_name": "未知"
            }
    else:
        # Fall back to rule-based analysis (生成默认数据)
        ai_hints = features.get("AI预判断", {})
        f0_data = features.get("基频F0_Hz", {})

        # 使用规则生成主音色
        voice_type_hint = ai_hints.get("⭐音色大类预判", "少御音")
        main_voice_type = {
            "level1": voice_type_hint.replace("【", "").replace("】", "").split("音")[0] + "音" if "音" in voice_type_hint else "未知",
            "level2": "",
            "full_name": voice_type_hint.replace("【", "").replace("】", "")
        }

        # Generate tags based on AI hints
        auxiliary_tags = []
        if "清澈" in ai_hints.get("清澈度预判", ""):
            auxiliary_tags.append("清澈")
        if "明亮" in ai_hints.get("亮度预判", ""):
            auxiliary_tags.append("明亮")
        if "轻柔" in ai_hints.get("能量预判", ""):
            auxiliary_tags.append("温柔")
        if "气息感" in ai_hints.get("气息感预判", ""):
            auxiliary_tags.append("气息感")

        development_directions = []
        voice_position = "发声于中央喉位"
        resonance = ["胸腔", "鼻腔"]

        # Voice attribute based on pitch stability
        pitch_stability = f0_data.get("音高稳定性", 0.5)
        if pitch_stability > 0.8:
            voice_attribute = "攻"
        elif pitch_stability < 0.5:
            voice_attribute = "受"
        else:
            voice_attribute = "可攻可受"

        # Voice temperature based on spectral centroid
        centroid = features.get("频谱质心_声音亮度", {}).get("平均值_Hz", 2500)
        if centroid > 3000:
            voice_temperature = "冷"
        elif centroid < 2000:
            voice_temperature = "暖"
        else:
            voice_temperature = "中性"

        perceived_food = "温柔蜂蜜配清茶"

        # Perceived age/height based on F0
        f0_mean = f0_data.get("平均值", 200)
        if request.gender == "female":
            perceived_age = max(16, min(35, int(40 - f0_mean / 15)))
            perceived_height = max(155, min(175, int(140 + f0_mean / 10)))
        else:
            perceived_age = max(18, min(45, int(50 - f0_mean / 5)))
            perceived_height = max(165, min(190, int(180 - f0_mean / 20)))

        perceived_feedback = ["温柔动听", "富有感染力"]
        love_score = 75
        recommended_partner = ["温柔型", "知性型"]
        signature = ai_hints.get("推荐修饰词", "声音温柔动听，富有感染力。")
        improvement_tips = ["可尝试增加一些气息变化", "注意发音的清晰度"]
        songs = ["小幸运", "遇见", "童话"]

    # Create result record (新字段结构)
    result = VoiceTestResult(
        id=str(uuid4()),
        user_id=current_user.id,
        audio_url=f"/uploads/voice/{file_path.name}",
        text_content=request.text_content,
        duration=features.get("基本信息", {}).get("音频时长_秒", 0),
        gender=request.gender,
        voice_features=features,
        main_voice_type=main_voice_type,
        auxiliary_tags=auxiliary_tags,
        development_directions=development_directions,
        voice_position=voice_position,
        resonance=resonance,
        voice_attribute=voice_attribute,
        voice_temperature=voice_temperature,
        perceived_food=perceived_food,
        perceived_age=perceived_age,
        perceived_height=perceived_height,
        perceived_feedback=perceived_feedback,
        love_score=love_score,
        recommended_partner=recommended_partner,
        signature=signature,
        improvement_tips=improvement_tips
    )

    db.add(result)

    # Add recommended songs (支持字符串数组或对象数组)
    song_list = []
    if songs:
        for i, song in enumerate(songs[:3]):  # Max 3 songs
            if isinstance(song, str):
                # 字符串格式
                song_list.append(VoiceTestSong(
                    result_id=result.id,
                    song_name=song,
                    artist="未知",
                    reason="",
                    sort_order=i
                ))
            elif isinstance(song, dict):
                # 对象格式
                song_list.append(VoiceTestSong(
                    result_id=result.id,
                    song_name=song.get("name", song.get("song_name", "")),
                    artist=song.get("artist", ""),
                    reason=song.get("reason", ""),
                    sort_order=i
                ))

    for song_record in song_list:
        db.add(song_record)

    db.commit()
    db.refresh(result)

    # 获取AI检测到的性别（如果有）
    detected_gender = ai_result.get("gender", "") if ai_result else ""
    # 将gender转换为中文
    detected_gender_cn = "女" if detected_gender == "female" or detected_gender == "女" else ("男" if detected_gender == "male" or detected_gender == "男" else "")
    user_gender_cn = "女" if request.gender == "female" else "男"

    # 返回新格式的数据
    return success_response({
        "result_id": result.id,
        "detected_gender": detected_gender_cn,  # AI检测到的性别
        "user_gender": user_gender_cn,  # 用户选择的性别
        "main_voice_type": result.main_voice_type,
        "auxiliary_tags": result.auxiliary_tags,
        "development_directions": result.development_directions,
        "voice_position": result.voice_position,
        "resonance": result.resonance,
        "voice_attribute": result.voice_attribute,
        "voice_temperature": result.voice_temperature,
        "perceived_food": result.perceived_food,
        "perceived_age": result.perceived_age,
        "perceived_height": result.perceived_height,
        "perceived_feedback": result.perceived_feedback,
        "love_score": result.love_score,
        "recommended_partner": result.recommended_partner,
        "signature": result.signature,
        "improvement_tips": result.improvement_tips,
        "recommended_songs": [{
            "name": s.song_name,
            "artist": s.artist,
            "reason": s.reason
        } for s in song_list],
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
        "auxiliary_tags": r.auxiliary_tags or [],
        "love_score": r.love_score,
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
