"""
Voice Card Endpoints
"""
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.voice_card import VoiceCard, VoiceCardTemplate
from app.models.voice_test import VoiceTestResult
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response
from app.config import settings

router = APIRouter()


# ============ Pydantic Schemas ============

class GenerateCardRequest(BaseModel):
    result_id: str = Field(..., description="Voice test result ID")
    template_id: str = Field(..., description="Template ID")


class CardResponse(BaseModel):
    card_id: str
    template_id: str
    image_url: str
    created_at: str


# ============ Template Data ============

TEMPLATES = [
    {
        "id": "neon_party",
        "name": "霓虹派对",
        "preview_url": "/templates/neon_party.png",
        "colors": ["#FE2C55", "#7C3AED"],
        "style": "gradient"
    },
    {
        "id": "starry_dream",
        "name": "星空梦境",
        "preview_url": "/templates/starry_dream.png",
        "colors": ["#2DE2E6", "#0B0B0F"],
        "style": "stars"
    },
    {
        "id": "aurora",
        "name": "极光幻影",
        "preview_url": "/templates/aurora.png",
        "colors": ["#2DE2E6", "#00B894"],
        "style": "aurora"
    },
    {
        "id": "deep_sea",
        "name": "深海蔚蓝",
        "preview_url": "/templates/deep_sea.png",
        "colors": ["#1E3A5F", "#2DE2E6"],
        "style": "bubbles"
    },
    {
        "id": "minimal",
        "name": "简约纯色",
        "preview_url": "/templates/minimal.png",
        "colors": ["#0B0B0F", "#FFFFFF"],
        "style": "minimal"
    }
]


# ============ Endpoints ============

@router.get("/templates")
def get_templates():
    """
    Get all available voice card templates
    """
    return success_response({
        "templates": TEMPLATES
    })


@router.post("/generate")
def generate_voice_card(
    request: GenerateCardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a voice card from test result
    """
    # Verify test result exists and belongs to user
    result = db.query(VoiceTestResult).filter(
        VoiceTestResult.id == request.result_id,
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice test result not found"
        )

    # Verify template exists
    template = next((t for t in TEMPLATES if t["id"] == request.template_id), None)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template ID"
        )

    # Generate card image (placeholder for now)
    card_id = str(uuid4())
    image_filename = f"{card_id}.png"
    image_url = f"/uploads/voice_cards/{image_filename}"

    # TODO: Implement actual image generation with template
    # For now, just save the card record

    # Create voice card record
    card = VoiceCard(
        id=card_id,
        user_id=current_user.id,
        result_id=request.result_id,
        template_id=request.template_id,
        image_url=image_url,
        voice_type=result.main_voice_type,
        overall_score=result.overall_score,
        tags=result.tags
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    return success_response({
        "card_id": card.id,
        "template_id": card.template_id,
        "image_url": card.image_url,
        "voice_type": card.voice_type,
        "overall_score": float(card.overall_score) if card.overall_score else 0,
        "tags": card.tags or [],
        "created_at": card.created_at.isoformat() if card.created_at else None
    })


@router.get("/my-cards")
def get_my_cards(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's generated voice cards
    """
    query = db.query(VoiceCard).filter(
        VoiceCard.user_id == current_user.id,
        VoiceCard.status == 1
    ).order_by(VoiceCard.created_at.desc())

    total = query.count()
    cards = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "card_id": c.id,
        "template_id": c.template_id,
        "image_url": c.image_url,
        "voice_type": c.voice_type,
        "overall_score": float(c.overall_score) if c.overall_score else 0,
        "tags": c.tags or [],
        "share_count": c.share_count,
        "created_at": c.created_at.isoformat() if c.created_at else None
    } for c in cards]

    return paginated_response(items, total, page, page_size)


@router.get("/{card_id}")
def get_card_detail(
    card_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get voice card detail
    """
    card = db.query(VoiceCard).filter(
        VoiceCard.id == card_id,
        VoiceCard.status == 1
    ).first()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice card not found"
        )

    # Check access permission (owner or public)
    if card.user_id != current_user.id and not card.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    return success_response({
        "card_id": card.id,
        "template_id": card.template_id,
        "image_url": card.image_url,
        "voice_type": card.voice_type,
        "overall_score": float(card.overall_score) if card.overall_score else 0,
        "tags": card.tags or [],
        "share_count": card.share_count,
        "is_public": card.is_public,
        "created_at": card.created_at.isoformat() if card.created_at else None
    })


@router.post("/{card_id}/share")
def share_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record card share action
    """
    card = db.query(VoiceCard).filter(
        VoiceCard.id == card_id,
        VoiceCard.user_id == current_user.id,
        VoiceCard.status == 1
    ).first()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice card not found"
        )

    card.share_count += 1
    db.commit()

    return success_response({
        "share_count": card.share_count,
        "share_url": f"{settings.APP_BASE_URL}/card/{card_id}"
    })


@router.delete("/{card_id}")
def delete_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete voice card
    """
    card = db.query(VoiceCard).filter(
        VoiceCard.id == card_id,
        VoiceCard.user_id == current_user.id,
        VoiceCard.status == 1
    ).first()

    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice card not found"
        )

    card.status = 0
    db.commit()

    return success_response({
        "message": "Deleted successfully"
    })
