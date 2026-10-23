"""User account API"""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import encrypt_api_key, decrypt_api_key, verify_password, hash_password
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.storage import StorageUnavailableError, save_avatar

logger = logging.getLogger(__name__)
from app.schemas.user import UserOut, UserUpdate


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

router = APIRouter()

AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5MB


def _user_to_out(user: User) -> dict:
    """Flatten an ORM user into a UserOut dict, adding computed fields.

    has_api_key is True when *either* the user stored their own key *or* the
    server is configured with a shared Gemini key — i.e. AI features are available.
    """
    from app.core.config import settings as _settings
    server_key_available = bool(_settings.gemini_api_key)
    return {
        **{c.name: getattr(user, c.name) for c in user.__table__.columns},
        "has_api_key": bool(user.api_key_encrypted) or server_key_available,
    }


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the current user's profile"""
    return _user_to_out(current_user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's profile"""
    if data.username is not None:
        current_user.username = data.username
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
    if data.api_key is not None:
        current_user.api_key_encrypted = encrypt_api_key(data.api_key)
    if data.api_base_url is not None:
        current_user.api_base_url = data.api_base_url
    if data.api_model is not None:
        current_user.api_model = data.api_model
    await db.flush()
    await db.refresh(current_user)
    return _user_to_out(current_user)


@router.post("/me/avatar", response_model=UserOut)
async def upload_user_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload the user's avatar"""

    if file.content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image format. Use JPEG, PNG, WebP, or GIF")

    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image is too large (max 5MB)")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "png"
    try:
        avatar_url = save_avatar(f"user_{current_user.id}", f"{current_user.id}.{ext}", content)
    except StorageUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    current_user.avatar_url = avatar_url
    await db.flush()
    await db.refresh(current_user)
    return _user_to_out(current_user)


@router.post("/me/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the account password"""
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    current_user.password_hash = hash_password(data.new_password)
    current_user.must_change_password = False
    await db.flush()
    return {"message": "Password updated"}


@router.post("/me/test-api")
async def test_api_connection(current_user: User = Depends(get_current_user)):
    """Verify connectivity by sending a one-token Gemini request with the user's key/model."""
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types

    api_key = decrypt_api_key(current_user.api_key_encrypted) if current_user.api_key_encrypted else None
    if not api_key:
        raise HTTPException(status_code=400, detail="Set your API key first")

    base_url = current_user.api_base_url or settings.gemini_base_url
    model = current_user.api_model or settings.gemini_model

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(base_url=base_url, timeout=15000),
    )
    try:
        await client.aio.models.generate_content(
            model=model,
            contents="hi",
            config=types.GenerateContentConfig(max_output_tokens=1, temperature=0),
        )
        return {"status": "ok", "model": model, "base_url": base_url}
    except genai_errors.ClientError as e:
        status = getattr(e, "code", None)
        if status in (401, 403):
            raise HTTPException(status_code=401, detail="That API key is invalid. Check it and try again.")
        if status == 429:
            raise HTTPException(status_code=429, detail="Rate limit reached or quota exhausted. Try again shortly.")
        if status == 404:
            raise HTTPException(status_code=404, detail="That model is not available for this API key.")
        raise HTTPException(status_code=502, detail=f"Gemini rejected the request ({status}). Try again shortly.")
    except genai_errors.ServerError as e:
        raise HTTPException(status_code=502, detail=f"Gemini service error ({getattr(e, 'code', '?')}). Try again shortly.")
    except genai_errors.APIError as e:
        logger.exception("Gemini connection test failed")
        raise HTTPException(status_code=502, detail=f"Connection failed: {str(e)[:120]}")
    except Exception as e:
        logger.exception("Gemini connection test failed")
        raise HTTPException(status_code=502, detail=f"Connection failed: {str(e)[:120]}")
