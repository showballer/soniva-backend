"""
User Profile and Settings Endpoints
"""
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import get_db
from app.models.user import User, UserFollow
from app.models.voice_test import VoiceTestResult
from app.models.square import SquarePost, UserFavorite
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response
from app.utils.security import verify_password, get_password_hash
from app.config import settings

router = APIRouter()

# Upload directory
AVATAR_DIR = Path(settings.LOCAL_STORAGE_PATH) / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)


# ============ Pydantic Schemas ============

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    bio: Optional[str] = Field(None, max_length=200)
    gender: Optional[str] = Field(None, description="male/female/other")
    birthday: Optional[str] = Field(None, description="YYYY-MM-DD format")
    location: Optional[str] = Field(None, max_length=100)


class UpdatePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6, max_length=32)


class UpdateAnonymousRequest(BaseModel):
    is_anonymous: bool = Field(..., description="Enable/disable anonymous mode")


# ============ Profile Endpoints ============

@router.get("/profile")
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's profile
    """
    # Get statistics
    test_count = db.query(VoiceTestResult).filter(
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).count()

    post_count = db.query(SquarePost).filter(
        SquarePost.user_id == current_user.id,
        SquarePost.status == 1
    ).count()

    follower_count = db.query(UserFollow).filter(
        UserFollow.following_id == current_user.id
    ).count()

    following_count = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user.id
    ).count()

    # Get latest voice test result
    latest_result = db.query(VoiceTestResult).filter(
        VoiceTestResult.user_id == current_user.id,
        VoiceTestResult.status == 1
    ).order_by(VoiceTestResult.created_at.desc()).first()

    return success_response({
        "user_id": current_user.id,
        "phone": current_user.phone[:3] + "****" + current_user.phone[-4:],
        "name": current_user.name,
        "avatar": current_user.avatar,
        "bio": current_user.bio,
        "gender": current_user.gender,
        "birthday": current_user.birthday.isoformat() if current_user.birthday else None,
        "location": current_user.location,
        "is_anonymous": current_user.is_anonymous,
        "voice_type": latest_result.main_voice_type if latest_result else None,
        "statistics": {
            "test_count": test_count,
            "post_count": post_count,
            "follower_count": follower_count,
            "following_count": following_count
        },
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    })


@router.put("/profile")
def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user profile
    """
    if request.name is not None:
        current_user.name = request.name
    if request.bio is not None:
        current_user.bio = request.bio
    if request.gender is not None:
        if request.gender not in ["male", "female", "other"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid gender value"
            )
        current_user.gender = request.gender
    if request.birthday is not None:
        from datetime import datetime
        try:
            current_user.birthday = datetime.strptime(request.birthday, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid birthday format. Use YYYY-MM-DD"
            )
    if request.location is not None:
        current_user.location = request.location

    db.commit()
    db.refresh(current_user)

    return success_response({
        "message": "Profile updated",
        "name": current_user.name,
        "bio": current_user.bio,
        "gender": current_user.gender,
        "birthday": current_user.birthday.isoformat() if current_user.birthday else None,
        "location": current_user.location
    })


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload user avatar
    """
    # Validate file type
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Validate file size (max 5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB"
        )

    # Save file
    file_id = str(uuid4())
    file_path = AVATAR_DIR / f"{file_id}{file_ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # Update user avatar
    avatar_url = f"/uploads/avatars/{file_id}{file_ext}"
    current_user.avatar = avatar_url
    db.commit()

    return success_response({
        "avatar": avatar_url
    })


@router.put("/password")
def update_password(
    request: UpdatePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user password
    """
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )

    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()

    return success_response({
        "message": "Password updated successfully"
    })


@router.put("/anonymous")
def update_anonymous_setting(
    request: UpdateAnonymousRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update anonymous mode setting
    """
    current_user.is_anonymous = request.is_anonymous
    db.commit()

    return success_response({
        "is_anonymous": current_user.is_anonymous
    })


# ============ Other User Profile ============

@router.get("/{user_id}")
def get_user_profile(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get another user's public profile
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.status == 1
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get statistics
    post_count = db.query(SquarePost).filter(
        SquarePost.user_id == user.id,
        SquarePost.status == 1
    ).count()

    follower_count = db.query(UserFollow).filter(
        UserFollow.following_id == user.id
    ).count()

    following_count = db.query(UserFollow).filter(
        UserFollow.follower_id == user.id
    ).count()

    # Check if current user is following
    is_following = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user.id,
        UserFollow.following_id == user.id
    ).first() is not None

    # Get voice type if user is not anonymous or is current user
    voice_type = None
    if not user.is_anonymous or user.id == current_user.id:
        latest_result = db.query(VoiceTestResult).filter(
            VoiceTestResult.user_id == user.id,
            VoiceTestResult.status == 1
        ).order_by(VoiceTestResult.created_at.desc()).first()
        voice_type = latest_result.main_voice_type if latest_result else None

    return success_response({
        "user_id": user.id,
        "name": user.name,
        "avatar": user.avatar,
        "bio": user.bio,
        "is_anonymous": user.is_anonymous,
        "voice_type": voice_type,
        "statistics": {
            "post_count": post_count,
            "follower_count": follower_count,
            "following_count": following_count
        },
        "is_following": is_following
    })


# ============ Follow Endpoints ============

@router.post("/{user_id}/follow")
def toggle_follow(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle follow a user
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself"
        )

    target_user = db.query(User).filter(
        User.id == user_id,
        User.status == 1
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    existing_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user.id,
        UserFollow.following_id == user_id
    ).first()

    if existing_follow:
        db.delete(existing_follow)
        is_following = False
    else:
        follow = UserFollow(
            follower_id=current_user.id,
            following_id=user_id
        )
        db.add(follow)
        is_following = True

    db.commit()

    return success_response({
        "is_following": is_following
    })


@router.get("/{user_id}/followers")
def get_followers(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's followers
    """
    query = db.query(UserFollow).filter(
        UserFollow.following_id == user_id
    ).order_by(UserFollow.created_at.desc())

    total = query.count()
    follows = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for follow in follows:
        follower = db.query(User).filter(User.id == follow.follower_id).first()
        if follower:
            # Check if current user is following this person
            is_following = db.query(UserFollow).filter(
                UserFollow.follower_id == current_user.id,
                UserFollow.following_id == follower.id
            ).first() is not None

            items.append({
                "user_id": follower.id,
                "name": follower.name,
                "avatar": follower.avatar,
                "bio": follower.bio,
                "is_following": is_following
            })

    return paginated_response(items, total, page, page_size)


@router.get("/{user_id}/following")
def get_following(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get users that this user is following
    """
    query = db.query(UserFollow).filter(
        UserFollow.follower_id == user_id
    ).order_by(UserFollow.created_at.desc())

    total = query.count()
    follows = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for follow in follows:
        following_user = db.query(User).filter(User.id == follow.following_id).first()
        if following_user:
            is_following = db.query(UserFollow).filter(
                UserFollow.follower_id == current_user.id,
                UserFollow.following_id == following_user.id
            ).first() is not None

            items.append({
                "user_id": following_user.id,
                "name": following_user.name,
                "avatar": following_user.avatar,
                "bio": following_user.bio,
                "is_following": is_following
            })

    return paginated_response(items, total, page, page_size)


# ============ Favorites ============

@router.get("/me/favorites")
def get_my_favorites(
    page: int = 1,
    page_size: int = 20,
    target_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's favorites
    """
    query = db.query(UserFavorite).filter(
        UserFavorite.user_id == current_user.id
    )

    if target_type:
        query = query.filter(UserFavorite.target_type == target_type)

    query = query.order_by(UserFavorite.created_at.desc())

    total = query.count()
    favorites = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for fav in favorites:
        item = {
            "favorite_id": fav.id,
            "target_type": fav.target_type,
            "target_id": fav.target_id,
            "created_at": fav.created_at.isoformat() if fav.created_at else None
        }

        # Get target details
        if fav.target_type == "post":
            post = db.query(SquarePost).filter(SquarePost.id == fav.target_id).first()
            if post:
                author = db.query(User).filter(User.id == post.user_id).first()
                item["target"] = {
                    "post_id": post.id,
                    "content": post.content[:100],
                    "author": {
                        "user_id": author.id,
                        "name": author.name,
                        "avatar": author.avatar
                    } if author else None
                }
        elif fav.target_type == "user":
            user = db.query(User).filter(User.id == fav.target_id).first()
            if user:
                item["target"] = {
                    "user_id": user.id,
                    "name": user.name,
                    "avatar": user.avatar
                }

        items.append(item)

    return paginated_response(items, total, page, page_size)


# ============ User Posts ============

@router.get("/{user_id}/posts")
def get_user_posts(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get posts by a specific user
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    query = db.query(SquarePost).filter(
        SquarePost.user_id == user_id,
        SquarePost.status == 1
    ).order_by(SquarePost.created_at.desc())

    total = query.count()
    posts = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for post in posts:
        from app.models.square import PostLike

        is_liked = db.query(PostLike).filter(
            PostLike.post_id == post.id,
            PostLike.user_id == current_user.id
        ).first() is not None

        items.append({
            "post_id": post.id,
            "content": post.content,
            "voice_url": post.voice_url,
            "images": post.images or [],
            "tags": post.tags or [],
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "is_liked": is_liked,
            "created_at": post.created_at.isoformat() if post.created_at else None
        })

    return paginated_response(items, total, page, page_size)
