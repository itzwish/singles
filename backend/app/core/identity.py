"""Identity resolution â€” turns a bearer credential into an application user.

Three credential shapes are understood, in this order:

1. a **Clerk session token** â€” verified against the instance JWKS;
2. a **legacy access token** â€” the app's own HS256 JWT;
3. a **ws ticket** â€” a short-lived, internally signed ticket that carries the
   resolved user id so streaming transports never carry a long-lived token.

``AUTH_MODE`` decides which of them are accepted:

``dual``   â€” everything (default while the migration is in flight)
``clerk``  â€” Clerk session tokens and ws tickets only
``legacy`` â€” the pre-Clerk behaviour
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import (
    ClerkPrincipal,
    clerk_enabled,
    get_clerk_user,
    verify_session_token,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token, hash_password, verify_ws_ticket
from app.models.user import User

logger = logging.getLogger(__name__)

_USERNAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_USERNAME = 100


@dataclass
class AuthenticatedIdentity:
    """A resolved credential: the database user plus how it was authenticated."""

    user: User
    principal: ClerkPrincipal | None = None
    token_type: str = "legacy"

    @property
    def is_clerk(self) -> bool:
        return self.principal is not None

    @property
    def is_admin(self) -> bool:
        return bool(self.user.is_admin) or bool(self.principal and self.principal.is_admin)


def auth_mode() -> str:
    """The configured authentication mode, normalised."""
    mode = (settings.auth_mode or "dual").strip().lower()
    return mode if mode in ("dual", "clerk", "legacy") else "dual"


def _clerk_path_enabled() -> bool:
    return auth_mode() in ("dual", "clerk") and clerk_enabled()


def _legacy_path_enabled() -> bool:
    return auth_mode() in ("dual", "legacy")


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


async def resolve_identity(token: str | None, db: AsyncSession) -> AuthenticatedIdentity | None:
    """Resolve a bearer credential into an :class:`AuthenticatedIdentity`."""
    if not token:
        return None

    # A ws ticket is an internally signed, short-lived stand-in for a
    # session. It is accepted in every auth mode, so streaming transports
    # keep working once the legacy path is switched off.
    ticket_identity = await _resolve_with_ws_ticket(token, db)
    if ticket_identity is not None:
        return ticket_identity

    if _clerk_path_enabled():
        identity = await _resolve_with_clerk(token, db)
        if identity is not None:
            return identity
        if auth_mode() == "clerk":
            return None

    if _legacy_path_enabled():
        identity = await _resolve_with_legacy(token, db)
        if identity is not None:
            return identity

    return None


async def _resolve_with_ws_ticket(token: str, db: AsyncSession) -> AuthenticatedIdentity | None:
    """Resolve a short-lived streaming ticket into an identity."""
    user_id = verify_ws_ticket(token)
    if not user_id:
        return None
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        return None

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    return AuthenticatedIdentity(user=user, principal=None, token_type="ws")


async def _resolve_with_clerk(token: str, db: AsyncSession) -> AuthenticatedIdentity | None:
    principal = await verify_session_token(token)
    if principal is None:
        return None
    if principal.disabled:
        logger.warning("Rejected a disabled Clerk user: %s", principal.user_id)
        return None

    user = await link_or_create_user(principal, db)
    if user is None:
        return None
    if not user.is_active:
        logger.warning("Rejected a disabled account for Clerk user %s", principal.user_id)
        return None

    return AuthenticatedIdentity(user=user, principal=principal, token_type="clerk")


async def _resolve_with_legacy(token: str, db: AsyncSession) -> AuthenticatedIdentity | None:
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") not in ("access", "ws"):
        return None

    subject = payload.get("sub")
    if not subject:
        return None
    try:
        user_uuid = uuid.UUID(subject)
    except (ValueError, TypeError, AttributeError):
        return None

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    return AuthenticatedIdentity(user=user, principal=None, token_type="legacy")


async def link_or_create_user(
    principal: ClerkPrincipal,
    db: AsyncSession,
    profile: Mapping[str, Any] | None = None,
) -> User | None:
    """Find the database row for a Clerk user, linking or creating it if needed.

    ``profile`` lets a caller (the webhook handler) pass data it already has,
    so the Backend API is not queried again.
    """
    result = await db.execute(select(User).where(User.clerk_user_id == principal.user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        if await _sync_profile(user, principal):
            await db.commit()
            await db.refresh(user)
        return user

    if profile is None:
        profile = await get_clerk_user(principal.user_id)
    email = (profile or {}).get("email") or principal.email
    if not email:
        logger.warning("Clerk user %s has no email address; cannot provision an account", principal.user_id)
        return None

    existing = await _find_by_email(db, email)
    if existing is not None:
        if existing.clerk_user_id and existing.clerk_user_id != principal.user_id:
            logger.warning(
                "Account %s is already linked to a different Clerk user; refusing to relink",
                existing.email,
            )
            return None
        existing.clerk_user_id = principal.user_id
        existing.must_change_password = False
        await _sync_profile(existing, principal)
        await db.commit()
        await db.refresh(existing)
        return existing

    username = await _unique_username(db, (profile or {}).get("username") or email.split("@")[0])
    user = User(
        email=email,
        username=username,
        # Clerk owns the password, so this row cannot be logged into through the
        # legacy endpoint. A random secret keeps the hash unpredictable.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        clerk_user_id=principal.user_id,
        # Clerk serves a generated identicon for users without a picture; the
        # app draws initials in the brand tint instead of showing it.
        avatar_url=((profile or {}).get("image_url") if (profile or {}).get("has_image") else None),
        is_admin=principal.is_admin,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to provision a database row for Clerk user %s", principal.user_id)
        await db.rollback()
        return None
    await db.refresh(user)

    try:
        from app.api.v1.characters import _copy_defaults_for_user

        await _copy_defaults_for_user(db, user.id)
        await db.commit()
    except Exception:
        logger.exception("Failed to seed starter characters for Clerk user %s", principal.user_id)
        await db.rollback()

    return user


async def _sync_profile(user: User, principal: ClerkPrincipal) -> bool:
    """Copy profile fields from Clerk onto the database row.

    Returns True when the row was modified and still needs to be committed.
    """
    changed = False
    stored_is_clerk = (user.avatar_url or "").startswith("https://img.clerk.com/")
    if principal.has_image and principal.image_url and not user.avatar_url:
        # Fill an empty avatar from a real Clerk picture; never replace the
        # picture the user uploaded here.
        user.avatar_url = principal.image_url
        changed = True
    elif not principal.has_image and stored_is_clerk:
        # Left behind by an earlier sync of Clerk's generated identicon.
        user.avatar_url = None
        changed = True
    if principal.is_admin and not user.is_admin:
        user.is_admin = True
        changed = True
    return changed


async def _find_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    result = await db.execute(select(User).where(func.lower(User.email) == email.lower()).limit(1))
    return result.scalars().first()


async def _unique_username(db: AsyncSession, desired: str) -> str:
    """Return a free username derived from ``desired``."""
    base = _USERNAME_SAFE_RE.sub("", (desired or "").strip())[:_MAX_USERNAME] or "user"
    candidate = base
    counter = 1
    while True:
        result = await db.execute(select(User.id).where(User.username == candidate).limit(1))
        if result.scalars().first() is None:
            return candidate
        counter += 1
        suffix = str(counter)
        candidate = f"{base[: _MAX_USERNAME - len(suffix)]}{suffix}"


# --------------------------------------------------------------------------
# Transport helper
# --------------------------------------------------------------------------


async def resolve_user_id(token: str | None) -> str | None:
    """Resolve a credential to an internal user id, for transports without
    dependency injection (WebSocket frames, SSE query parameters).

    Returns ``None`` when the credential cannot be trusted.
    """
    if not token or token == "guest":
        return None

    # Internally signed tokens: ws tickets and legacy access tokens.
    try:
        payload = decode_token(token)
    except JWTError:
        payload = None
    except Exception:
        payload = None

    if payload and payload.get("type") in ("ws", "access"):
        subject = payload.get("sub")
        if not subject:
            return None
        try:
            uuid.UUID(subject)
        except (ValueError, TypeError, AttributeError):
            return None
        return subject

    async with AsyncSessionLocal() as db:
        identity = await resolve_identity(token, db)
        if identity is None:
            return None
        return str(identity.user.id)
