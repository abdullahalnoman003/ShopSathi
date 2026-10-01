from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DENYLIST_PREFIX, get_current_user, get_token_payload
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    hash_password,
    hash_reset_token,
    new_reset_token,
    verify_password,
)
from app.models import PasswordResetToken, Shop, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
)
from app.services.email import EmailService, get_email_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_response(user: User) -> AuthResponse:
    token = create_access_token(user_id=user.id, role=user.role, shop_id=user.shop_id)
    return AuthResponse.model_validate(
        {"access_token": token, "user": user, "shop": user.shop}, from_attributes=True
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    # Shop and owner are created in one transaction. Prompt 3 adds the plan to this step.
    shop = Shop(name=body.shop_name)
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.owner_name,
        role="owner",
        shop=shop,
    )
    db.add_all([shop, user])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    s = get_settings()
    email = body.email.lower()
    check_rate_limit("login-ip", _client_ip(request), s.login_rate_limit, s.login_rate_window_seconds)
    check_rate_limit("login-email", email, s.login_rate_limit, s.login_rate_window_seconds)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.shop is not None and user.shop.status == "suspended":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Shop suspended")
    return _auth_response(user)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: dict[str, Any] = Depends(get_token_payload)) -> MessageResponse:
    """Revoke the current token by denylisting its id until it would have expired."""
    ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
    if ttl > 0:
        get_redis().set(DENYLIST_PREFIX + payload["jti"], 1, ex=ttl)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse.model_validate({"user": user, "shop": user.shop}, from_attributes=True)


@router.post("/password-reset/request", response_model=MessageResponse)
def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    emailer: EmailService = Depends(get_email_service),
) -> MessageResponse:
    s = get_settings()
    email = body.email.lower()
    check_rate_limit("reset-ip", _client_ip(request), s.reset_rate_limit, s.reset_rate_window_seconds)
    check_rate_limit("reset-email", email, s.reset_rate_limit, s.reset_rate_window_seconds)
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is not None:
        raw, hashed = new_reset_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hashed,
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=s.password_reset_expire_minutes),
            )
        )
        db.commit()
        link = f"{s.frontend_origin.rstrip('/')}/reset-password?token={raw}"
        background.add_task(emailer.send_password_reset, user.email, link)
    # Same response whether or not the email exists.
    return MessageResponse(message="If that email is registered, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=MessageResponse)
def password_reset_confirm(body: PasswordResetConfirm, db: Session = Depends(get_db)) -> MessageResponse:
    now = datetime.now(timezone.utc)
    token = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_reset_token(body.token))
        .with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link")
    user.password_hash = hash_password(body.new_password)
    token.used_at = now
    db.commit()
    return MessageResponse(message="Password updated. You can now log in.")
