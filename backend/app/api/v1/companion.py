"""Companion chat API — structured bubble-based responses.

Endpoints:
  POST /api/v1/companion/chat   — user sends a message, gets bubble payload
  POST /api/v1/companion/tick   — idle timer fires, gets spontaneous check-in

Both return the same CompanionResponse schema consumed by the frontend
playback queue.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_optional_user
from app.core.security import decrypt_api_key
from app.models.user import User
from app.models.character import Character
from app.services.companion_pipeline import companion_reply
from app.core.database import AsyncSessionLocal
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CompanionChatRequest(BaseModel):
    conversation_id: str
    message: str = ""


class CompanionTickRequest(BaseModel):
    conversation_id: str


class BubbleOut(BaseModel):
    text: str
    pause_before_ms: int
    ghost_typing_ms: int
    typing_ms: int


class InternalStateOut(BaseModel):
    current_mood: str
    valence: float
    energy: float
    busyness_level: float
    effective_wpm: int
    current_activity: str
    unfiltered_thought: str


class CompanionResponse(BaseModel):
    internal_state: InternalStateOut
    read_delay_ms: int
    bubbles: list[BubbleOut]
    next_spontaneous_trigger_minutes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_character_for_conversation(conversation_id: str) -> Character | None:
    """Load the Character linked to a conversation, if available."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return None
    try:
        from app.models.conversation import Conversation
        async with AsyncSessionLocal() as db:
            conv_res = await db.execute(
                select(Conversation).where(Conversation.id == conv_uuid)
            )
            conv = conv_res.scalar_one_or_none()
            if not conv:
                return None
            char_res = await db.execute(
                select(Character).where(Character.id == conv.character_id)
            )
            return char_res.scalar_one_or_none()
    except Exception:
        logger.exception("_load_character_for_conversation failed")
        return None


def _companion_kwargs_from_character(char: Character | None) -> dict:
    """Extract companion persona fields from a Character's personality_profile."""
    if not char:
        return {}
    profile: dict = char.personality_profile or {}
    kwargs: dict = {}
    # Map personality_profile keys to companion prompt variables
    if char.name:
        kwargs["companion_name"] = char.name
    if profile.get("companion_gender_role"):
        kwargs["companion_gender_role"] = profile["companion_gender_role"]
    if profile.get("user_name"):
        kwargs["user_name"] = profile["user_name"]
    if profile.get("personality_archetype") or profile.get("personality"):
        kwargs["personality_archetype"] = (
            profile.get("personality_archetype") or profile.get("personality", "")
        )
    return kwargs


def _coerce_payload(raw: dict) -> dict:
    """Ensure the payload has sensible defaults for every field so Pydantic never rejects it."""
    raw.setdefault("read_delay_ms", 1200)
    raw.setdefault("next_spontaneous_trigger_minutes", 60)
    raw.setdefault("bubbles", [])

    state = raw.setdefault("internal_state", {})
    state.setdefault("current_mood", "neutral")
    state.setdefault("valence", 0.5)
    state.setdefault("energy", 0.5)
    state.setdefault("busyness_level", 0.3)
    state.setdefault("effective_wpm", 48)
    state.setdefault("current_activity", "on my phone")
    state.setdefault("unfiltered_thought", "")

    coerced_bubbles = []
    for b in raw["bubbles"]:
        if not isinstance(b, dict) or not b.get("text"):
            continue
        coerced_bubbles.append(
            {
                "text": str(b.get("text", "")),
                "pause_before_ms": int(b.get("pause_before_ms", 600)),
                "ghost_typing_ms": int(b.get("ghost_typing_ms", 0)),
                "typing_ms": max(850, int(b.get("typing_ms", 1200))),
            }
        )
    raw["bubbles"] = coerced_bubbles
    return raw


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=CompanionResponse)
async def companion_chat(
    data: CompanionChatRequest,
    current_user: User | None = Depends(get_optional_user),
):
    """User sends a message; returns the companion's structured bubble reply."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    api_key = (
        decrypt_api_key(current_user.api_key_encrypted)
        if current_user.api_key_encrypted
        else None
    )
    api_model = current_user.api_model

    char = await _load_character_for_conversation(data.conversation_id)
    persona_kwargs = _companion_kwargs_from_character(char)

    try:
        payload = await companion_reply(
            user_id=str(current_user.id),
            conversation_id=data.conversation_id,
            user_message=data.message,
            is_tick=False,
            api_key=api_key,
            api_model=api_model,
            **persona_kwargs,
        )
    except Exception as exc:
        logger.exception("companion_chat failed")
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc

    return _coerce_payload(payload)


@router.post("/tick", response_model=CompanionResponse)
async def companion_tick(
    data: CompanionTickRequest,
    current_user: User | None = Depends(get_optional_user),
):
    """Idle timer fires; returns a spontaneous check-in (may be empty bubbles)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    api_key = (
        decrypt_api_key(current_user.api_key_encrypted)
        if current_user.api_key_encrypted
        else None
    )
    api_model = current_user.api_model

    char = await _load_character_for_conversation(data.conversation_id)
    persona_kwargs = _companion_kwargs_from_character(char)

    try:
        payload = await companion_reply(
            user_id=str(current_user.id),
            conversation_id=data.conversation_id,
            user_message="",
            is_tick=True,
            api_key=api_key,
            api_model=api_model,
            **persona_kwargs,
        )
    except Exception as exc:
        logger.exception("companion_tick failed")
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc

    return _coerce_payload(payload)
