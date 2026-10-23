"""Clerk integration — session-token verification, user lookups, webhook signing.

Clerk owns identity for this app. The browser authenticates against Clerk and
sends the resulting *session token* to the API as a bearer credential. The API
verifies that token against the instance JWKS, then maps the Clerk user id onto
a row in ``users``.

Nothing here raises for untrusted input: verification helpers return ``None``
or ``False`` so callers can decide how to react.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

_JWKS_TTL_SECONDS = 3600.0
_USER_CACHE_TTL_SECONDS = 60.0
_WEBHOOK_TOLERANCE_SECONDS = 300.0
_WEBHOOK_SEEN_TTL_SECONDS = 3600.0
_BACKEND_API_TIMEOUT = 10.0

_jwks_cache: dict[str, Any] = {"keys": [], "fetched_at": 0.0}
_user_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_seen_webhook_ids: dict[str, float] = {}


@dataclass(frozen=True)
class ClerkPrincipal:
    """The identity carried by a verified Clerk session token."""

    user_id: str
    session_id: str | None = None
    email: str | None = None
    username: str | None = None
    full_name: str | None = None
    image_url: str | None = None
    # False when Clerk only has its generated identicon for the user.
    has_image: bool = False
    external_id: str | None = None
    is_admin: bool = False
    disabled: bool = False
    public_metadata: dict[str, Any] = field(default_factory=dict)
    private_metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Instance configuration
# --------------------------------------------------------------------------


def clerk_enabled() -> bool:
    """True when enough Clerk configuration is present to verify tokens."""
    return bool(frontend_api())


def frontend_api() -> str:
    """The instance's frontend API host, e.g. ``example.clerk.accounts.dev``."""
    if settings.clerk_frontend_api:
        return settings.clerk_frontend_api.strip().rstrip("/")
    return _frontend_api_from_publishable_key(settings.clerk_publishable_key)


def issuer() -> str:
    """The expected ``iss`` claim for session tokens."""
    api = frontend_api()
    return f"https://{api}" if api else ""


def jwks_url() -> str:
    api = frontend_api()
    return f"https://{api}/.well-known/jwks.json" if api else ""


def backend_api_url() -> str:
    """The Clerk Backend API host (independent of the instance host)."""
    return "https://api.clerk.com"


def authorized_parties() -> list[str]:
    """Origins allowed to present a session token.

    The instance's own frontend API is always allowed; anything in
    ``CLERK_AUTHORIZED_PARTIES`` is added on top.
    """
    parties: list[str] = []
    api = frontend_api()
    if api:
        parties.append(api)
    for entry in settings.clerk_authorized_parties.split(","):
        cleaned = entry.strip().rstrip("/")
        if cleaned and cleaned not in parties:
            parties.append(cleaned)
    return parties


def _frontend_api_from_publishable_key(key: str) -> str:
    """Recover the frontend API host from a Clerk publishable key.

    Publishable keys look like ``pk_test_<base64(host$)>``; the host is what we
    need to build the JWKS and Backend API URLs.
    """
    if not key:
        return ""
    raw = key.strip()
    for prefix in ("pk_test_", "pk_live_"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    raw = raw.split("$", 1)[0]
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return ""
    return decoded.split("$", 1)[0].strip()


# --------------------------------------------------------------------------
# JWKS
# --------------------------------------------------------------------------


async def _fetch_jwks() -> dict[str, Any]:
    url = jwks_url()
    if not url:
        raise RuntimeError("Clerk frontend API is not configured")
    async with httpx.AsyncClient(timeout=_BACKEND_API_TIMEOUT) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def get_jwks(force_refresh: bool = False) -> dict[str, Any]:
    """Return the instance JWKS, cached for an hour.

    Clerk rotates signing keys rarely; the cache keeps the hot path free of
    network calls while still recovering quickly from a rotation.
    """
    now = time.monotonic()
    keys = _jwks_cache.get("keys") or []
    if not force_refresh and keys and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS:
        return {"keys": keys}

    data = await _fetch_jwks()
    keys = data.get("keys") or []
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return {"keys": keys}


async def _decode_session_token(token: str) -> dict[str, Any] | None:
    """Verify signature and standard claims; returns the claims or None."""
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except JWTError:
        algorithm = None

    if algorithm != "RS256":
        # Not a Clerk session token — typically a legacy HS256 app token or a
        # malformed value. Let the caller fall back to the next credential
        # source without logging a misleading rejection.
        logger.debug("Skipping Clerk verification for an %s token", algorithm or "unreadable")
        return None

    options = {
        "verify_aud": False,
        "verify_iss": False,
        # Tolerate a small clock difference between Clerk's servers and this
        # host. Without it a token can arrive a moment before its `nbf` and be
        # rejected even though it is perfectly valid.
        "leeway": max(0, int(settings.clerk_token_leeway_seconds)),
    }

    for attempt in (0, 1):
        try:
            jwks = await get_jwks(force_refresh=attempt == 1)
            return jwt.decode(token, jwks, algorithms=["RS256"], options=options)
        except JWTError as exc:
            if attempt == 0:
                # The signing key may have rotated; refresh the JWKS once.
                continue
            logger.warning("Rejected a Clerk session token: %s", exc)
            return None
        except httpx.HTTPError:
            logger.exception("Failed to fetch the Clerk JWKS")
            return None
        except Exception:
            logger.exception("Unexpected error while verifying a Clerk session token")
            return None
    return None


# --------------------------------------------------------------------------
# Session token verification
# --------------------------------------------------------------------------


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Pull the raw token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def verify_session_token(token: str) -> ClerkPrincipal | None:
    """Verify a Clerk session token and return the identity it carries.

    Returns ``None`` when the token is missing, expired, unsigned by this
    instance, or issued for an origin we do not trust.
    """
    if not token:
        return None
    if not clerk_enabled():
        logger.warning("Clerk is not configured; cannot verify session tokens")
        return None

    claims = await _decode_session_token(token)
    if claims is None:
        return None

    accepted_issuers = {issuer()}
    api = frontend_api()
    if api:
        accepted_issuers.add(f"https://clerk.{api}")
    token_issuer = claims.get("iss")
    if token_issuer not in accepted_issuers:
        logger.warning("Rejected a Clerk session token from an unexpected issuer")
        return None

    parties = authorized_parties()
    if parties:
        token_party = claims.get("azp")
        if not token_party or token_party not in parties:
            logger.warning("Rejected a Clerk session token from an unauthorized party")
            return None

    audience = settings.clerk_api_audience.strip()
    if audience:
        raw_audience = claims.get("aud")
        audiences = raw_audience if isinstance(raw_audience, list) else [raw_audience]
        if audience not in audiences:
            logger.warning("Rejected a Clerk session token with an unexpected audience")
            return None

    subject = claims.get("sub")
    if not subject:
        return None

    profile = await get_clerk_user(subject)
    public_metadata = (profile or {}).get("public_metadata") or {}
    private_metadata = (profile or {}).get("private_metadata") or {}

    return ClerkPrincipal(
        user_id=subject,
        session_id=claims.get("sid"),
        email=(profile or {}).get("email"),
        username=(profile or {}).get("username"),
        full_name=(profile or {}).get("full_name"),
        image_url=(profile or {}).get("image_url"),
        has_image=bool((profile or {}).get("has_image")),
        external_id=(profile or {}).get("external_id"),
        is_admin=str(public_metadata.get("role", "")).strip().lower() == "admin",
        disabled=bool((profile or {}).get("disabled")),
        public_metadata=public_metadata,
        private_metadata=private_metadata,
    )


# --------------------------------------------------------------------------
# Backend API
# --------------------------------------------------------------------------


def _normalize_clerk_user(data: Mapping[str, Any]) -> dict[str, Any]:
    email = data.get("email")
    if not email:
        addresses = data.get("email_addresses") or []
        primary = next(
            (a for a in addresses if isinstance(a, Mapping) and a.get("id") == data.get("primary_email_address_id")),
            None,
        )
        if primary is None and addresses:
            primary = addresses[0] if isinstance(addresses[0], Mapping) else None
        if primary:
            email = primary.get("email_address")

    full_name = data.get("full_name")
    if not full_name:
        parts = [p for p in (data.get("first_name"), data.get("last_name")) if p]
        full_name = " ".join(parts) if parts else None

    return {
        "id": data.get("id"),
        "email": email,
        "username": data.get("username"),
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "full_name": full_name,
        "image_url": data.get("image_url"),
        "has_image": bool(data.get("has_image")),
        "external_id": data.get("external_id"),
        "created_at": data.get("created_at"),
        "public_metadata": data.get("public_metadata") or {},
        "private_metadata": data.get("private_metadata") or {},
        "disabled": bool(data.get("disabled")),
        "archived": bool(data.get("archived")),
        "locked": bool(data.get("locked")),
        "disable_sign_in": bool(data.get("disable_sign_in")),
    }


async def get_clerk_user(user_id: str, *, force_refresh: bool = False) -> dict[str, Any] | None:
    """Fetch a Clerk user through the Backend API, with a short-lived cache.

    Session tokens do not carry metadata or the email address, so the API
    needs the full profile to link an account and to read the admin role.
    """
    now = time.monotonic()
    cached = _user_cache.get(user_id)
    if not force_refresh and cached and cached[0] > now:
        return cached[1]

    secret = settings.clerk_secret_key
    base = backend_api_url()
    if not secret or not base:
        return cached[1] if cached else None

    url = f"{base}/v1/users/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=_BACKEND_API_TIMEOUT) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {secret}"})
            if response.status_code == 404:
                logger.info("Clerk user %s no longer exists", user_id)
                return None
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        logger.exception("Failed to read Clerk user %s from the Backend API", user_id)
        return cached[1] if cached else None

    normalized = _normalize_clerk_user(data)
    _user_cache[user_id] = (now + _USER_CACHE_TTL_SECONDS, normalized)
    return normalized


def invalidate_clerk_user_cache(user_id: str | None = None) -> None:
    """Drop cached Clerk profiles (all of them, or a single user)."""
    if user_id is None:
        _user_cache.clear()
    else:
        _user_cache.pop(user_id, None)


async def clerk_backend_api_request(
    method: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Call the Clerk Backend API with the instance secret key.

    ``path`` is relative to the API version, e.g. ``/users`` or
    ``/users/user_2abc``.
    """
    secret = settings.clerk_secret_key
    base = backend_api_url()
    if not secret or not base:
        raise RuntimeError("CLERK_SECRET_KEY is not configured")

    url = f"{base}/v1{path if path.startswith('/') else '/' + path}"
    async with httpx.AsyncClient(timeout=_BACKEND_API_TIMEOUT) as client:
        response = await client.request(
            method.upper(),
            url,
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            json=dict(payload) if payload is not None else None,
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.error(
                "Clerk Backend API %s %s failed with %s: %s",
                method,
                url,
                response.status_code,
                response.text[:500],
            )
            return None
        if not response.content:
            return {}
        return response.json()


# --------------------------------------------------------------------------
# Webhook signatures
# --------------------------------------------------------------------------


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding)


def verify_webhook_signature(
    body: bytes,
    headers: Mapping[str, str],
    *,
    tolerance_seconds: int = _WEBHOOK_TOLERANCE_SECONDS,
) -> bool:
    """Verify a Clerk/Svix webhook signature over the raw request body.

    Clerk signs ``{svix-id}.{svix-timestamp}.{body}`` with HMAC-SHA256 using
    the instance's webhook signing secret, and sends the result in the
    ``svix-signature`` header as ``v1,<base64>``.
    """
    secret = settings.clerk_webhook_signing_secret
    if not secret:
        logger.warning("CLERK_WEBHOOK_SIGNING_SECRET is not configured; rejecting webhook")
        return False

    def _header(name: str) -> str:
        for key, value in headers.items():
            if key.lower() == name:
                return value or ""
        return ""

    svix_id = _header("svix-id")
    svix_timestamp = _header("svix-timestamp")
    svix_signature = _header("svix-signature")
    if not (svix_id and svix_timestamp and svix_signature):
        return False

    try:
        timestamp = int(svix_timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance_seconds:
        logger.warning("Rejected a Clerk webhook with a stale timestamp")
        return False

    try:
        key = _b64decode(secret.replace("whsec_", "").strip())
    except (binascii.Error, ValueError):
        logger.error("CLERK_WEBHOOK_SIGNING_SECRET is not valid base64")
        return False

    signed_content = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + body
    expected = hmac.new(key, signed_content, hashlib.sha256).digest()

    for part in svix_signature.split(" "):
        if not part.startswith("v1,"):
            continue
        try:
            provided = _b64decode(part[3:])
        except (binascii.Error, ValueError):
            continue
        if hmac.compare_digest(expected, provided):
            return True

    logger.warning("Rejected a Clerk webhook with an invalid signature")
    return False


def mark_webhook_seen(svix_id: str) -> bool:
    """Record a webhook id. Returns False when the id was already handled."""
    if not svix_id:
        return True
    now = time.time()
    for key, seen_at in list(_seen_webhook_ids.items()):
        if now - seen_at > _WEBHOOK_SEEN_TTL_SECONDS:
            _seen_webhook_ids.pop(key, None)
    if svix_id in _seen_webhook_ids:
        return False
    _seen_webhook_ids[svix_id] = now
    return True
