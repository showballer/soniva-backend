"""
Square (广场) Endpoints - Social Feed
"""
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from app.database import get_db
from app.models.user import User
from app.models.square import SquarePost, PostComment, PostLike, CommentLike, UserFavorite
from app.models.message import CommentNotification
from app.dependencies import get_current_user
from app.utils.response import success_response, paginated_response
from app.config import settings

router = APIRouter()

# Upload directory
UPLOAD_DIR = Path(settings.LOCAL_STORAGE_PATH) / "posts"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============ Pydantic Schemas ============

class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="Post content")
    voice_url: Optional[str] = Field(None, description="Voice message URL")
    images: Optional[List[str]] = Field(None, description="Image URLs")
    tags: Optional[List[str]] = Field(None, description="Post tags")


class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    parent_id: Optional[str] = Field(None, description="Parent comment ID for reply")


# ============ Post Endpoints ============

@router.get("/feed")
def get_feed(
    page: int = 1,
    page_size: int = 20,
    feed_type: str = "recommend",  # recommend/following/latest
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get social feed
    """
    query = db.query(SquarePost).filter(SquarePost.status == 1)

    if feed_type == "following":
        # Get posts from followed users
        from app.models.user import UserFollow
        following_ids = db.query(UserFollow.following_id).filter(
            UserFollow.follower_id == current_user.id
        ).subquery()
        query = query.filter(SquarePost.user_id.in_(following_ids))
    elif feed_type == "latest":
        query = query.order_by(SquarePost.created_at.desc())
    else:  # recommend
        # Simple recommendation: order by engagement
        query = query.order_by(
            (SquarePost.like_count + SquarePost.comment_count * 2).desc(),
            SquarePost.created_at.desc()
        )

    total = query.count()
    posts = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for post in posts:
        author = db.query(User).filter(User.id == post.user_id).first()

        # Check if current user liked this post
        is_liked = db.query(PostLike).filter(
            PostLike.post_id == post.id,
            PostLike.user_id == current_user.id
        ).first() is not None

        # Check if favorited
        is_favorited = db.query(UserFavorite).filter(
            UserFavorite.user_id == current_user.id,
            UserFavorite.target_type == "post",
            UserFavorite.target_id == post.id
        ).first() is not None

        items.append({
            "post_id": post.id,
            "author": {
                "user_id": author.id,
                "name": author.name,
                "avatar": author.avatar,
                "is_anonymous": author.is_anonymous
            } if author else None,
            "content": post.content,
            "voice_url": post.voice_url,
            "images": post.images or [],
            "tags": post.tags or [],
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "share_count": post.share_count,
            "is_liked": is_liked,
            "is_favorited": is_favorited,
            "created_at": post.created_at.isoformat() if post.created_at else None
        })

    return paginated_response(items, total, page, page_size)


@router.post("/post")
def create_post(
    request: CreatePostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new post
    """
    post = SquarePost(
        id=str(uuid4()),
        user_id=current_user.id,
        content=request.content,
        voice_url=request.voice_url,
        images=request.images,
        tags=request.tags
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    return success_response({
        "post_id": post.id,
        "content": post.content,
        "created_at": post.created_at.isoformat() if post.created_at else None
    })


@router.get("/post/{post_id}")
def get_post_detail(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get post detail
    """
    post = db.query(SquarePost).filter(
        SquarePost.id == post_id,
        SquarePost.status == 1
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    author = db.query(User).filter(User.id == post.user_id).first()

    is_liked = db.query(PostLike).filter(
        PostLike.post_id == post.id,
        PostLike.user_id == current_user.id
    ).first() is not None

    is_favorited = db.query(UserFavorite).filter(
        UserFavorite.user_id == current_user.id,
        UserFavorite.target_type == "post",
        UserFavorite.target_id == post.id
    ).first() is not None

    return success_response({
        "post_id": post.id,
        "author": {
            "user_id": author.id,
            "name": author.name,
            "avatar": author.avatar,
            "is_anonymous": author.is_anonymous
        } if author else None,
        "content": post.content,
        "voice_url": post.voice_url,
        "images": post.images or [],
        "tags": post.tags or [],
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "share_count": post.share_count,
        "is_liked": is_liked,
        "is_favorited": is_favorited,
        "created_at": post.created_at.isoformat() if post.created_at else None
    })


@router.delete("/post/{post_id}")
def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete own post
    """
    post = db.query(SquarePost).filter(
        SquarePost.id == post_id,
        SquarePost.user_id == current_user.id,
        SquarePost.status == 1
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    post.status = 0
    db.commit()

    return success_response({"message": "Deleted successfully"})


# ============ Like Endpoints ============

@router.post("/post/{post_id}/like")
def toggle_like(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle like on a post
    """
    post = db.query(SquarePost).filter(
        SquarePost.id == post_id,
        SquarePost.status == 1
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    existing_like = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id
    ).first()

    if existing_like:
        # Unlike
        db.delete(existing_like)
        post.like_count = max(0, post.like_count - 1)
        is_liked = False
    else:
        # Like
        like = PostLike(
            post_id=post_id,
            user_id=current_user.id
        )
        db.add(like)
        post.like_count += 1
        is_liked = True

        # Create notification if not own post
        if post.user_id != current_user.id:
            notif = CommentNotification(
                id=str(uuid4()),
                user_id=post.user_id,
                from_user_id=current_user.id,
                post_id=post_id,
                content="赞了你的动态",
                notification_type="like"
            )
            db.add(notif)

    db.commit()

    return success_response({
        "is_liked": is_liked,
        "like_count": post.like_count
    })


# ============ Comment Endpoints ============

@router.get("/post/{post_id}/comments")
def get_comments(
    post_id: str,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comments on a post
    """
    query = db.query(PostComment).filter(
        PostComment.post_id == post_id,
        PostComment.status == 1,
        PostComment.parent_id == None  # Top-level comments only
    ).order_by(PostComment.created_at.desc())

    total = query.count()
    comments = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for comment in comments:
        author = db.query(User).filter(User.id == comment.user_id).first()

        # Get replies
        replies = db.query(PostComment).filter(
            PostComment.parent_id == comment.id,
            PostComment.status == 1
        ).order_by(PostComment.created_at.asc()).limit(3).all()

        reply_list = []
        for reply in replies:
            reply_author = db.query(User).filter(User.id == reply.user_id).first()
            reply_list.append({
                "comment_id": reply.id,
                "author": {
                    "user_id": reply_author.id,
                    "name": reply_author.name,
                    "avatar": reply_author.avatar
                } if reply_author else None,
                "content": reply.content,
                "like_count": reply.like_count,
                "created_at": reply.created_at.isoformat() if reply.created_at else None
            })

        # Check if current user liked
        is_liked = db.query(CommentLike).filter(
            CommentLike.comment_id == comment.id,
            CommentLike.user_id == current_user.id
        ).first() is not None

        # Count total replies
        reply_count = db.query(PostComment).filter(
            PostComment.parent_id == comment.id,
            PostComment.status == 1
        ).count()

        items.append({
            "comment_id": comment.id,
            "author": {
                "user_id": author.id,
                "name": author.name,
                "avatar": author.avatar
            } if author else None,
            "content": comment.content,
            "like_count": comment.like_count,
            "reply_count": reply_count,
            "replies": reply_list,
            "is_liked": is_liked,
            "created_at": comment.created_at.isoformat() if comment.created_at else None
        })

    return paginated_response(items, total, page, page_size)


@router.post("/post/{post_id}/comment")
def create_comment(
    post_id: str,
    request: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a comment on a post
    """
    post = db.query(SquarePost).filter(
        SquarePost.id == post_id,
        SquarePost.status == 1
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # If replying to a comment, verify parent exists
    if request.parent_id:
        parent = db.query(PostComment).filter(
            PostComment.id == request.parent_id,
            PostComment.post_id == post_id,
            PostComment.status == 1
        ).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )

    comment = PostComment(
        id=str(uuid4()),
        post_id=post_id,
        user_id=current_user.id,
        parent_id=request.parent_id,
        content=request.content
    )

    db.add(comment)
    post.comment_count += 1

    # Create notification
    notify_user_id = None
    if request.parent_id:
        # Reply notification to parent comment author
        parent = db.query(PostComment).filter(PostComment.id == request.parent_id).first()
        if parent and parent.user_id != current_user.id:
            notify_user_id = parent.user_id
            notif_type = "reply"
            notif_content = f"回复了你的评论: {request.content[:50]}"
    else:
        # Comment notification to post author
        if post.user_id != current_user.id:
            notify_user_id = post.user_id
            notif_type = "comment"
            notif_content = f"评论了你的动态: {request.content[:50]}"

    if notify_user_id:
        notif = CommentNotification(
            id=str(uuid4()),
            user_id=notify_user_id,
            from_user_id=current_user.id,
            post_id=post_id,
            comment_id=comment.id,
            content=notif_content,
            notification_type=notif_type
        )
        db.add(notif)

    db.commit()
    db.refresh(comment)

    return success_response({
        "comment_id": comment.id,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None
    })


@router.post("/comment/{comment_id}/like")
def toggle_comment_like(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle like on a comment
    """
    comment = db.query(PostComment).filter(
        PostComment.id == comment_id,
        PostComment.status == 1
    ).first()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    existing_like = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user.id
    ).first()

    if existing_like:
        db.delete(existing_like)
        comment.like_count = max(0, comment.like_count - 1)
        is_liked = False
    else:
        like = CommentLike(
            comment_id=comment_id,
            user_id=current_user.id
        )
        db.add(like)
        comment.like_count += 1
        is_liked = True

    db.commit()

    return success_response({
        "is_liked": is_liked,
        "like_count": comment.like_count
    })


@router.delete("/comment/{comment_id}")
def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete own comment
    """
    comment = db.query(PostComment).filter(
        PostComment.id == comment_id,
        PostComment.user_id == current_user.id,
        PostComment.status == 1
    ).first()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    # Decrease post comment count
    post = db.query(SquarePost).filter(SquarePost.id == comment.post_id).first()
    if post:
        post.comment_count = max(0, post.comment_count - 1)

    comment.status = 0
    db.commit()

    return success_response({"message": "Deleted successfully"})


# ============ Favorite Endpoints ============

@router.post("/post/{post_id}/favorite")
def toggle_favorite(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle favorite on a post
    """
    post = db.query(SquarePost).filter(
        SquarePost.id == post_id,
        SquarePost.status == 1
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    existing = db.query(UserFavorite).filter(
        UserFavorite.user_id == current_user.id,
        UserFavorite.target_type == "post",
        UserFavorite.target_id == post_id
    ).first()

    if existing:
        db.delete(existing)
        is_favorited = False
    else:
        favorite = UserFavorite(
            id=str(uuid4()),
            user_id=current_user.id,
            target_type="post",
            target_id=post_id
        )
        db.add(favorite)
        is_favorited = True

    db.commit()

    return success_response({
        "is_favorited": is_favorited
    })
