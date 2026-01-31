"""
Identify (识Ta) Endpoints - AI Voice Analysis for User Portrait
"""
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import get_db
from app.models.user import User
from app.models.identify import UserPortrait, AnalysisRecord
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response
from app.services.voice_service import voice_analysis_service
from app.config import settings

router = APIRouter()

# Upload directory
UPLOAD_DIR = Path(settings.LOCAL_STORAGE_PATH) / "voice"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============ Pydantic Schemas ============

class AnalyzePortraitRequest(BaseModel):
    file_id: str = Field(..., description="Uploaded voice file ID")
    target_nickname: str = Field(..., description="Target user nickname")
    relationship: str = Field(..., description="Relationship type: friend/partner/colleague/stranger")


class PortraitResponse(BaseModel):
    portrait_id: str
    nickname: str
    mbti: str
    personality_tags: List[str]
    compatibility_score: float


# ============ Mock AI Analysis ============

def analyze_personality_from_voice(features: dict) -> dict:
    """
    Mock AI analysis for generating personality portrait from voice features
    In production, this would call FastGPT or other AI service
    """
    f0_data = features.get("f0_hz", {})
    pitch_stability = f0_data.get("pitch_stability", 0.5)
    f0_mean = f0_data.get("mean", 200)
    harmonic = features.get("harmonic_ratio", {}).get("value", 0.7)
    centroid = features.get("spectral_centroid", {}).get("mean_hz", 2500)

    # Mock MBTI analysis based on voice features
    # E/I: Higher pitch stability = more introverted
    ei = "I" if pitch_stability > 0.6 else "E"
    # S/N: Higher spectral centroid = more intuitive
    sn = "N" if centroid > 2500 else "S"
    # T/F: Higher harmonic ratio = more feeling
    tf = "F" if harmonic > 0.75 else "T"
    # J/P: More stable pitch = more judging
    jp = "J" if pitch_stability > 0.5 else "P"

    mbti = ei + sn + tf + jp

    # Generate personality tags based on voice features
    tags = []
    if pitch_stability > 0.7:
        tags.append("稳重")
    if harmonic > 0.8:
        tags.append("温和")
    if centroid > 3000:
        tags.append("活泼")
    if f0_mean > 250:
        tags.append("开朗")
    elif f0_mean < 150:
        tags.append("沉稳")

    if len(tags) < 3:
        tags.extend(["真诚", "细腻", "理性"][:3 - len(tags)])

    # Generate personality description
    descriptions = {
        "INFJ": "富有洞察力和同理心，追求深层次的人际连接",
        "INFP": "理想主义者，内心丰富，追求真诚的表达",
        "ENFJ": "天生的领导者，善于激励他人，关注群体和谐",
        "ENFP": "热情洋溢，富有创造力，喜欢探索新可能",
        "INTJ": "独立思考者，有远见，追求效率和完美",
        "INTP": "逻辑思维者，好奇心强，喜欢分析和探索",
        "ENTJ": "果断的领导者，善于规划，追求成就",
        "ENTP": "创新者，善于辩论，喜欢挑战传统观念",
        "ISFJ": "可靠的守护者，细心周到，重视传统",
        "ISFP": "艺术家气质，注重当下体验，追求和谐",
        "ESFJ": "热心的助人者，注重关系，善于照顾他人",
        "ESFP": "表演者，热爱生活，善于活跃气氛",
        "ISTJ": "可靠的执行者，注重细节，遵守规则",
        "ISTP": "问题解决者，动手能力强，冷静理性",
        "ESTJ": "组织者，注重效率，善于管理",
        "ESTP": "行动派，适应力强，喜欢冒险"
    }

    description = descriptions.get(mbti, "独特的个性，值得深入了解")

    return {
        "mbti": mbti,
        "personality_tags": tags,
        "description": description,
        "compatibility_base": 0.6 + harmonic * 0.3  # Base compatibility score
    }


# ============ Endpoints ============

@router.post("/upload")
async def upload_target_voice(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload target user's voice for analysis
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

    # Get audio duration
    try:
        import librosa
        y, sr = librosa.load(str(file_path), sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
    except Exception as e:
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
def analyze_portrait(
    request: AnalyzePortraitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analyze voice to generate user portrait
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

    # Analyze personality from voice
    personality = analyze_personality_from_voice(features)

    # Calculate compatibility score based on relationship type
    relationship_modifiers = {
        "friend": 0.1,
        "partner": 0.15,
        "colleague": 0.05,
        "stranger": 0
    }
    modifier = relationship_modifiers.get(request.relationship, 0)
    compatibility_score = min(0.99, personality["compatibility_base"] + modifier)

    # Create portrait record
    portrait = UserPortrait(
        id=str(uuid4()),
        user_id=current_user.id,
        nickname=request.target_nickname,
        relationship=request.relationship,
        audio_url=f"/uploads/voice/{file_path.name}",
        voice_features=features,
        mbti=personality["mbti"],
        personality_tags=personality["personality_tags"],
        personality_description=personality["description"],
        compatibility_score=round(compatibility_score * 100, 1)
    )

    db.add(portrait)

    # Create analysis record
    record = AnalysisRecord(
        id=str(uuid4()),
        user_id=current_user.id,
        portrait_id=portrait.id,
        analysis_type="voice",
        raw_features=features,
        ai_analysis={
            "mbti": personality["mbti"],
            "tags": personality["personality_tags"],
            "description": personality["description"]
        }
    )

    db.add(record)
    db.commit()
    db.refresh(portrait)

    return success_response({
        "portrait_id": portrait.id,
        "nickname": portrait.nickname,
        "mbti": portrait.mbti,
        "personality_tags": portrait.personality_tags,
        "personality_description": portrait.personality_description,
        "compatibility_score": float(portrait.compatibility_score),
        "relationship": portrait.relationship,
        "created_at": portrait.created_at.isoformat() if portrait.created_at else None
    })


@router.get("/portraits")
def get_portraits(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's analyzed portraits
    """
    query = db.query(UserPortrait).filter(
        UserPortrait.user_id == current_user.id,
        UserPortrait.status == 1
    ).order_by(UserPortrait.created_at.desc())

    total = query.count()
    portraits = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "portrait_id": p.id,
        "nickname": p.nickname,
        "avatar": p.avatar,
        "mbti": p.mbti,
        "personality_tags": p.personality_tags or [],
        "compatibility_score": float(p.compatibility_score) if p.compatibility_score else 0,
        "relationship": p.relationship,
        "is_favorite": p.is_favorite,
        "created_at": p.created_at.isoformat() if p.created_at else None
    } for p in portraits]

    return paginated_response(items, total, page, page_size)


@router.get("/portrait/{portrait_id}")
def get_portrait_detail(
    portrait_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get portrait detail
    """
    portrait = db.query(UserPortrait).filter(
        UserPortrait.id == portrait_id,
        UserPortrait.user_id == current_user.id,
        UserPortrait.status == 1
    ).first()

    if not portrait:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait not found"
        )

    return success_response({
        "portrait_id": portrait.id,
        "nickname": portrait.nickname,
        "avatar": portrait.avatar,
        "mbti": portrait.mbti,
        "personality_tags": portrait.personality_tags or [],
        "personality_description": portrait.personality_description,
        "compatibility_score": float(portrait.compatibility_score) if portrait.compatibility_score else 0,
        "relationship": portrait.relationship,
        "audio_url": portrait.audio_url,
        "is_favorite": portrait.is_favorite,
        "created_at": portrait.created_at.isoformat() if portrait.created_at else None
    })


@router.post("/portrait/{portrait_id}/favorite")
def toggle_favorite(
    portrait_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle portrait favorite status
    """
    portrait = db.query(UserPortrait).filter(
        UserPortrait.id == portrait_id,
        UserPortrait.user_id == current_user.id,
        UserPortrait.status == 1
    ).first()

    if not portrait:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait not found"
        )

    portrait.is_favorite = not portrait.is_favorite
    db.commit()

    return success_response({
        "is_favorite": portrait.is_favorite
    })


@router.delete("/portrait/{portrait_id}")
def delete_portrait(
    portrait_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete portrait
    """
    portrait = db.query(UserPortrait).filter(
        UserPortrait.id == portrait_id,
        UserPortrait.user_id == current_user.id,
        UserPortrait.status == 1
    ).first()

    if not portrait:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait not found"
        )

    portrait.status = 0
    db.commit()

    return success_response({
        "message": "Deleted successfully"
    })
