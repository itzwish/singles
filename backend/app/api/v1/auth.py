"""Auth API — register / login / refresh tokens / captcha

Clerk owns sign-in and sign-up. The legacy password endpoints are kept so
existing sessions keep working while ``AUTH_MODE`` is ``dual``, and are
switched off entirely once ``AUTH_MODE=clerk``.
"""

import logging
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import GUEST_EMAIL, GUEST_USER_ID
from app.core.dependencies import get_current_identity
from app.core.identity import AuthenticatedIdentity, auth_mode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserOut, UserRegister

logger = logging.getLogger(__name__)
from app.services.captcha import generate_captcha, verify_captcha

router = APIRouter()


class WsTicketResponse(BaseModel):
    """A short-lived ticket the browser can put in a WebSocket frame or SSE query."""

    ticket: str
    expires_in: int


def _require_legacy_enabled() -> None:
    """Block the password-based endpoints once Clerk is the only way in."""
    if auth_mode() == "clerk":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password sign-in is disabled; use Clerk",
        )


@router.get("/captcha")
async def get_captcha():
    """Return an image captcha"""
    return await generate_captcha()


@router.post("/guest", response_model=TokenResponse)
async def guest_login(db: AsyncSession = Depends(get_db)):
    """Passwordless guest login — always resolves to the shared system guest user"""
    from uuid import UUID  # noqa: F401  (kept for explicit typing below)

    result = await db.execute(select(User).where(User.id == GUEST_USER_ID))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=GUEST_USER_ID,
            email=GUEST_EMAIL,
            username="Guest",
            password_hash=hash_password("system-guest-no-login"),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    access_token = create_access_token(str(user.id), "free")
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user, seed their starter characters, and return tokens"""
    _require_legacy_enabled()

    if not await verify_captcha(data.captcha_id or "", data.captcha_code or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect or expired captcha")

    # Check whether the email is already registered
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already registered")

    # Check the username
    existing_name = await db.execute(select(User).where(User.username == data.username))
    if existing_name.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is taken")

    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Seed the new user with the default characters
    from app.api.v1.characters import _copy_defaults_for_user
    await _copy_defaults_for_user(db, user.id)

    access_token = create_access_token(str(user.id), user.membership_tier)
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Log in and return a JWT token pair"""
    _require_legacy_enabled()

    if not await verify_captcha(data.captcha_id or "", data.captcha_code or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect or expired captcha")

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    access_token = create_access_token(str(user.id), user.membership_tier)
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access token"""
    try:
        payload = decode_token(refresh_token)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Refresh token decode failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid or expired")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    # `sub` is a string in the JWT; the column is a UUID, so convert before use.
    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(sub) if sub else None
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid or expired")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid or expired")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_access = create_access_token(str(user.id), user.membership_tier)
    new_refresh = create_refresh_token(str(user.id))

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def ws_ticket(identity: AuthenticatedIdentity = Depends(get_current_identity)):
    """Exchange the caller's session for a short-lived streaming ticket.

    WebSocket frames and SSE query parameters cannot carry an Authorization
    header, and a long-lived credential in a URL ends up in logs. The ticket
    carries the resolved user id and expires within a minute.
    """
    from app.core.config import settings

    ticket = create_ws_ticket(str(identity.user.id))
    return WsTicketResponse(ticket=ticket, expires_in=settings.ws_ticket_ttl_seconds)
