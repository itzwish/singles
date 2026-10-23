"""JWT tokens, password hashing, and API-key encryption"""

import base64
from datetime import datetime, timedelta, timezone

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt silently rejects inputs over 72 bytes, so truncate before hashing
_BCRYPT_MAX_BYTES = 72


# Derive the Fernet key from secret_key (Fernet requires a 32-byte base64 key)
_fernet_key = base64.urlsafe_b64encode(settings.secret_key.encode().ljust(32, b'\0')[:32])
_fernet = Fernet(_fernet_key)


def encrypt_api_key(plain: str) -> str:
    """Encrypt an API key"""
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_api_key(encrypted: str) -> str | None:
    """Decrypt an API key"""
    if not encrypted:
        return None
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()
    ).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, membership_tier: str = "free") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "tier": membership_tier,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode a JWT; raises JWTError on failure"""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def create_ws_ticket(user_id: str) -> str:
    """Mint a short-lived ticket that stands in for a session on streaming transports.

    WebSocket frames and SSE query parameters cannot carry a bearer header, and
    putting a long-lived credential in a URL leaks it into logs. The ticket
    carries the resolved internal user id and expires within a minute.
    """
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.ws_ticket_ttl_seconds)
    payload = {
        "sub": user_id,
        "type": "ws",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def verify_ws_ticket(ticket: str) -> str | None:
    """Return the user id carried by a ws ticket, or None when it is not valid."""
    try:
        payload = decode_token(ticket)
    except JWTError:
        return None
    if payload.get("type") != "ws":
        return None
    user_id = payload.get("sub")
    return user_id or None
