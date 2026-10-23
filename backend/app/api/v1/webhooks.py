"""Clerk webhooks — keeps the database in step with the Clerk instance.

Clerk signs every webhook with the instance's signing secret (Svix format),
so the raw request body is verified before anything is written.

Handled events:

* ``user.created`` / ``user.updated`` — create, link, or refresh the account row
* ``user.deleted`` — deactivate the linked account row
* ``emailAddress.*`` — keep the stored email in step with the instance
"""

import logging
from typing import Any, Mapping

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import (
    ClerkPrincipal,
    invalidate_clerk_user_cache,
    mark_webhook_seen,
    verify_webhook_signature,
)
from app.core.database import get_db
from app.core.identity import link_or_create_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def _principal_from_payload(data: Mapping[str, Any]) -> ClerkPrincipal | None:
    """Build a principal from a Clerk user payload."""
    user_id = data.get("id")
    if not user_id or not isinstance(user_id, str):
        return None

    public_metadata = data.get("public_metadata") or {}
    private_metadata = data.get("private_metadata") or {}

    email = data.get("email")
    if not email:
        addresses = data.get("email_addresses") or []
        primary = next(
            (
                a
                for a in addresses
                if isinstance(a, Mapping) and a.get("id") == data.get("primary_email_address_id")
            ),
            None,
        )
        if primary is None and addresses and isinstance(addresses[0], Mapping):
            primary = addresses[0]
        if primary:
            email = primary.get("email_address")

    full_name = data.get("full_name")
    if not full_name:
        parts = [p for p in (data.get("first_name"), data.get("last_name")) if p]
        full_name = " ".join(parts) if parts else None

    disabled = bool(data.get("disabled")) or bool(data.get("archived")) or bool(data.get("locked"))

    return ClerkPrincipal(
        user_id=user_id,
        email=email,
        username=data.get("username"),
        full_name=full_name,
        image_url=data.get("image_url"),
        external_id=data.get("external_id"),
        is_admin=str(public_metadata.get("role", "")).strip().lower() == "admin",
        disabled=disabled,
        public_metadata=public_metadata,
        private_metadata=private_metadata,
    )


@router.post("/clerk")
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive a Clerk webhook."""
    body = await request.body()

    if not verify_webhook_signature(body, request.headers):
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "invalid signature"})

    svix_id = request.headers.get("svix-id", "")
    if not mark_webhook_seen(svix_id):
        return JSONResponse(status_code=status.HTTP_200_OK, content={"received": True, "duplicate": True})

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Clerk webhook body was not valid JSON")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "invalid payload"})

    event_type = payload.get("event") or payload.get("type") or ""
    data = payload.get("data") or {}
    if not isinstance(data, Mapping):
        data = {}

    try:
        await _handle_event(event_type, data, db)
    except Exception:
        logger.exception("Failed to handle the Clerk webhook %s", event_type)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": "processing failed"})

    return JSONResponse(status_code=status.HTTP_200_OK, content={"received": True})


async def _handle_event(event_type: str, data: Mapping[str, Any], db: AsyncSession) -> None:
    if event_type in ("user.created", "user.updated", "user.created_async"):
        principal = _principal_from_payload(data)
        if principal is None:
            logger.warning("Clerk webhook %s carried no user id", event_type)
            return

        invalidate_clerk_user_cache(principal.user_id)

        user = await link_or_create_user(principal, db, profile=data)
        if user is None:
            return

        # Clerk can disable an account without deleting it.
        if principal.disabled and user.is_active:
            user.is_active = False
            await db.commit()
        elif not principal.disabled and not user.is_active and event_type == "user.updated":
            user.is_active = True
            await db.commit()
        return

    if event_type == "user.deleted":
        user_id = data.get("id")
        if not user_id:
            return
        invalidate_clerk_user_cache(user_id)
        result = await db.execute(select(User).where(User.clerk_user_id == user_id))
        user = result.scalar_one_or_none()
        if user is not None and user.is_active:
            user.is_active = False
            await db.commit()
        return

    if event_type.startswith("emailAddress."):
        await _sync_email(data, db)
        return


async def _sync_email(data: Mapping[str, Any], db: AsyncSession) -> None:
    """Keep the stored email in step with a Clerk email address change."""
    user_id = data.get("user_id")
    email = data.get("email_address")
    if not user_id or not email:
        return

    invalidate_clerk_user_cache(user_id)

    result = await db.execute(select(User).where(User.clerk_user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.email == email:
        return

    clash = await db.execute(select(User.id).where(User.email == email).limit(1))
    if clash.scalars().first() is not None:
        logger.warning("Not applying the email change for Clerk user %s: %s is taken", user_id, email)
        return

    user.email = email
    await db.commit()
