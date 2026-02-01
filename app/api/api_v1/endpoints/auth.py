"""
Authentication Endpoints
"""
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.user import User, VerificationCode
from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_verification_code
)
from app.utils.response import success_response

router = APIRouter()


# ============ Pydantic Schemas ============

class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="Phone number")
    type: str = Field(..., description="Type: register/login/reset_password")


class RegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="Phone number")
    verification_code: str = Field(..., min_length=6, max_length=6, description="Verification code")
    password: str = Field(..., min_length=6, max_length=32, description="Password")
    name: str = Field(default=None, max_length=50, description="Username (optional)")
    is_anonymous: bool = Field(default=True, description="Is anonymous")


class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="Phone number")
    password: str = Field(..., min_length=6, max_length=32, description="Password")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")


# ============ Endpoints ============

@router.post("/send-code")
def send_verification_code(
    request: SendCodeRequest,
    db: Session = Depends(get_db)
):
    """
    Send verification code
    """
    if request.type not in ["register", "login", "reset_password"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code type"
        )

    # Check if user exists for register
    if request.type == "register":
        existing_user = db.query(User).filter(User.phone == request.phone).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists"
            )

    # Generate verification code
    code = generate_verification_code()

    # Save to database
    verification = VerificationCode(
        phone=request.phone,
        code=code,
        type=request.type,
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(verification)
    db.commit()

    # TODO: Send SMS via Aliyun or other service
    # For development, print the code
    print(f"[DEV] Verification code for {request.phone}: {code}")

    return success_response({
        "message": "Verification code sent",
        "expires_in": 300,
        # For development only, remove in production
        "code": code if True else None
    })


@router.post("/register")
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    User registration
    """
    # Check if user exists
    existing_user = db.query(User).filter(User.phone == request.phone).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists"
        )

    # Verify code
    verification = db.query(VerificationCode).filter(
        VerificationCode.phone == request.phone,
        VerificationCode.type == "register",
        VerificationCode.code == request.verification_code,
        VerificationCode.is_used == False,
        VerificationCode.expires_at > datetime.utcnow()
    ).order_by(VerificationCode.created_at.desc()).first()

    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )

    # Mark code as used
    verification.is_used = True

    # Create user with default name if not provided
    default_name = f"用户{request.phone[-4:]}"
    user = User(
        id=str(uuid4()),
        phone=request.phone,
        password_hash=get_password_hash(request.password),
        name=request.name if request.name else default_name,
        is_anonymous=request.is_anonymous
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return success_response({
        "user_id": user.id,
        "name": user.name,
        "avatar": user.avatar,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 7200
    })


@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    User login
    """
    # Find user
    user = db.query(User).filter(User.phone == request.phone).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password"
        )

    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password"
        )

    # Check user status
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled"
        )

    # Update last login time
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Generate tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return success_response({
        "user_id": user.id,
        "name": user.name,
        "avatar": user.avatar,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 7200
    })


@router.post("/refresh")
def refresh_token(
    request: RefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token
    """
    payload = decode_token(request.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.status == 1).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled"
        )

    # Generate new tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    return success_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 7200
    })


@router.post("/logout")
def logout():
    """
    User logout (client should delete tokens)
    """
    return success_response({
        "message": "Logged out successfully"
    })
