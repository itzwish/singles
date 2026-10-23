"""Admin API — dashboard stats, user management, and chat auditing"""

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_admin_user
from app.core.security import hash_password
from app.core.database import get_db
from app.models.user import User
from app.models.message import Message
from app.models.conversation import Conversation
from app.models.character import Character
from app.models.chat_message import ChatMessage
from app.services.system_config import get_system_config, update_system_config

router = APIRouter()


class UserUpdateData(BaseModel):
    is_active: bool | None = None
    membership_tier: str | None = None


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Dashboard statistics"""
    today = datetime.now(timezone.utc).date()
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    vip_users = (await db.execute(
        select(func.count()).select_from(User).where(User.membership_tier == "vip")
    )).scalar() or 0
    total_chars = (await db.execute(select(func.count()).select_from(Character))).scalar() or 0
    total_convos = (await db.execute(select(func.count()).select_from(Conversation))).scalar() or 0
    total_msgs = (await db.execute(select(func.count()).select_from(Message))).scalar() or 0

    today_msgs = (await db.execute(
        select(func.count()).select_from(Message).where(Message.created_at >= today_start)
    )).scalar() or 0

    today_users = (await db.execute(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    )).scalar() or 0

    active_today = (await db.execute(
        select(func.count(func.distinct(Conversation.user_id))).select_from(Message).join(
            Conversation, Message.conversation_id == Conversation.id
        ).where(Message.created_at >= today_start, Message.role == "user")
    )).scalar() or 0

    return {
        "total_users": total_users,
        "vip_users": vip_users,
        "total_characters": total_chars,
        "total_conversations": total_convos,
        "total_messages": total_msgs,
        "today_messages": today_msgs,
        "today_users": today_users,
        "active_users_today": active_today,
    }


@router.get("/stats/trend")
async def get_trend(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Message counts for the last 7 days"""
    today = datetime.now(timezone.utc).date()
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        cnt = (await db.execute(
            select(func.count()).select_from(Message).where(
                Message.created_at >= day_start, Message.created_at < day_end
            )
        )).scalar() or 0
        days.append({
            "date": d.isoformat(),
            "label": f"{d.month}/{d.day}",
            "count": cnt,
        })
    return {"days": days}


@router.get("/users")
async def list_users(
    search: str = Query("", max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Paginated, searchable user list"""
    base = select(User)
    if search:
        pattern = f"%{search}%"
        base = base.where(
            User.email.ilike(pattern) | User.username.ilike(pattern)
        )
    base = base.order_by(User.created_at.desc())

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(base.offset(offset).limit(page_size))
    users = result.scalars().all()

    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "username": u.username,
                "membership_tier": u.membership_tier,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    data: UserUpdateData,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Update a user (disable/enable, change membership tier)"""
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == _admin.id:
        raise HTTPException(status_code=403, detail="You cannot change your own status or tier")

    if data.is_active is not None:
        user.is_active = data.is_active
    if data.membership_tier is not None:
        if data.membership_tier not in ("free", "premium", "vip"):
            raise HTTPException(status_code=400, detail="Invalid membership tier")
        user.membership_tier = data.membership_tier

    await db.flush()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "membership_tier": user.membership_tier,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
    }


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Reset a user's password and return a temporary one"""
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=403, detail="You cannot reset your own password")

    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    await db.flush()

    return {"temp_password": temp_password, "username": user.username}


class SystemSettingsData(BaseModel):
    ai_provider: str | None = None
    ai_fallback_enabled: bool | None = None
    gemini_fallback_models: str | None = None
    ollama_fallback_models: str | None = None
    vision_enabled: bool | None = None
    vision_model: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    ollama_base_url: str | None = None
    ollama_api_key: str | None = None
    ollama_model: str | None = None
    ollama_vision_model: str | None = None


@router.get("/settings")
async def get_settings(_admin: User = Depends(get_admin_user)):
    """Return the system-wide AI provider configuration."""
    return get_system_config()


@router.put("/settings")
async def update_settings(
    data: SystemSettingsData,
    _admin: User = Depends(get_admin_user),
):
    """Update the system-wide AI provider configuration."""
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="Provide at least one setting")
    if "ai_provider" in payload:
        provider = str(payload["ai_provider"]).strip().lower()
        if provider not in ("gemini", "ollama"):
            raise HTTPException(status_code=400, detail="ai_provider must be 'gemini' or 'ollama'")
        payload["ai_provider"] = provider
    return update_system_config(payload)


# ── Chat auditing ──


@router.get("/chat-logs")
async def list_chat_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str | None = Query(None),
    character_id: str | None = Query(None),
    role: str | None = Query(None, pattern="^(user|assistant)$"),
    search: str | None = Query(None, max_length=200),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Paginated chat audit log across every user and persona.

    Requires an admin JWT — `get_admin_user` rejects signed-out, disabled, and
    non-admin accounts alike.
    """
    filters = []
    if user_id:
        try:
            filters.append(ChatMessage.user_id == uuid.UUID(user_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="user_id must be a valid UUID")
    if character_id:
        filters.append(ChatMessage.character_id == character_id)
    if role:
        filters.append(ChatMessage.role == role)
    if search:
        filters.append(ChatMessage.content.ilike(f"%{search}%"))
    if start_date:
        filters.append(ChatMessage.created_at >= start_date)
    if end_date:
        filters.append(ChatMessage.created_at <= end_date)

    count_q = select(func.count()).select_from(ChatMessage)
    list_q = select(ChatMessage)
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)

    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        list_q.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = result.scalars().all()

    # Resolve persona names in one extra query rather than per row.
    char_ids = {r.character_id for r in rows if r.character_id}
    names: dict[str, str] = {}
    if char_ids:
        try:
            char_uuids = [uuid.UUID(c) for c in char_ids]
        except (ValueError, TypeError):
            char_uuids = []
        if char_uuids:
            char_result = await db.execute(
                select(Character).where(Character.id.in_(char_uuids))
            )
            names = {str(c.id): c.name for c in char_result.scalars().all()}

    return {
        "items": [
            {
                "id": str(row.id),
                "user_id": str(row.user_id),
                "user_email": row.user.email if row.user else None,
                "username": row.user.username if row.user else None,
                "character_id": row.character_id,
                "character_name": names.get(row.character_id),
                "role": row.role,
                "content": row.content,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/chat-logs/stats")
async def chat_log_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Headline audit totals, split by role."""
    rows = (
        await db.execute(
            select(ChatMessage.role, func.count(), func.count(func.distinct(ChatMessage.user_id)))
            .group_by(ChatMessage.role)
        )
    ).all()
    by_role = {role: {"messages": count, "users": users} for role, count, users in rows}
    total_users = (await db.execute(
        select(func.count(func.distinct(ChatMessage.user_id)))
    )).scalar() or 0
    return {
        "total_messages": sum(v["messages"] for v in by_role.values()),
        "distinct_users": total_users,
        "by_role": by_role,
    }
