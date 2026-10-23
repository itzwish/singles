"""Companion chat pipeline — calls the model with the behavioral engine prompt
and returns the structured bubble payload.

This is a thin layer on top of EnhancedAIEngine._complete_with_fallback().
It does NOT replace the existing stream_chat pipeline; it sits alongside it
and is used only by the /api/v1/companion/* endpoints.
"""

import json
import logging
import re
from datetime import datetime

from app.companion_prompt import (
    DEFAULT_INTERNAL_STATE,
    build_companion_system_prompt,
    format_elapsed_time,
)
from app.services.companion_session import get_session, update_session, touch_last_message
from app.services.ai_engine import EnhancedAIEngine

logger = logging.getLogger(__name__)

engine = EnhancedAIEngine()

# JSON fence stripper
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_companion_json(raw: str) -> dict:
    """Strip markdown fences and parse the model's JSON output.

    Falls back to a safe wrapper so a plain-text reply never crashes the
    endpoint — the user will at least see *something*.
    """
    text = _FENCE_RE.sub("", raw.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try finding the outermost JSON object
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                pass
    # Last resort: wrap the raw text as a single bubble so the frontend
    # always receives a valid payload.
    logger.warning("companion_pipeline: could not parse JSON, wrapping as plain bubble")
    return {
        "internal_state": dict(DEFAULT_INTERNAL_STATE),
        "read_delay_ms": 1200,
        "bubbles": [
            {
                "text": raw[:500],
                "pause_before_ms": 500,
                "ghost_typing_ms": 0,
                "typing_ms": 1800,
            }
        ],
        "next_spontaneous_trigger_minutes": 60,
    }


def _build_user_turn(
    user_message: str,
    is_tick: bool,
    current_time_str: str,
    elapsed_str: str,
) -> str:
    """Prepend the runtime header to the user's message."""
    if is_tick:
        return f"[{current_time_str} | Gap: {elapsed_str}] [SYSTEM_TICK: IDLE_CHECKIN]"
    return f"[{current_time_str} | Gap: {elapsed_str}] User: {user_message}"


async def companion_reply(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    companion_name: str = "Mia",
    companion_gender_role: str = "girlfriend",
    user_name: str = "babe",
    personality_archetype: str = "warm, playful, affectionate, slightly teasing, independent",
    is_tick: bool = False,
    api_key: str | None = None,
    api_model: str | None = None,
) -> dict:
    """Run one companion turn and return the full structured payload.

    Args:
        user_id: caller's user ID (for session keying)
        conversation_id: conversation ID (for session keying)
        user_message: the raw text the user typed (empty string for ticks)
        companion_name: the companion's name rendered into the prompt
        companion_gender_role: e.g. "girlfriend", "boyfriend"
        user_name: how the companion addresses the user
        personality_archetype: short trait description
        is_tick: True when this is an idle SYSTEM_TICK check-in
        api_key: user's personal API key (or None to use the server key)
        api_model: model override (or None for the configured default)

    Returns:
        A dict matching the JSON schema:
        {
          "internal_state": {...},
          "read_delay_ms": int,
          "bubbles": [{"text", "pause_before_ms", "ghost_typing_ms", "typing_ms"}],
          "next_spontaneous_trigger_minutes": int,
        }
    """
    session = get_session(user_id, conversation_id)
    last_message_at: datetime | None = session["last_message_at"]
    previous_state: dict = session["internal_state"]

    now = datetime.now().astimezone()
    current_time_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")
    elapsed_str = format_elapsed_time(last_message_at, now)

    # Build the system prompt with all runtime variables injected
    system_prompt = build_companion_system_prompt(
        companion_name=companion_name,
        companion_gender_role=companion_gender_role,
        user_name=user_name,
        personality_archetype=personality_archetype,
        last_message_at=last_message_at,
        previous_internal_state=previous_state,
    )

    # Build the user-turn string sent as the prompt content
    prompt_content = _build_user_turn(user_message, is_tick, current_time_str, elapsed_str)

    logger.info(
        "[COMPANION] turn user=%s conv=%s tick=%s gap=%s",
        user_id,
        conversation_id,
        is_tick,
        elapsed_str,
    )

    # Call the model — json_mode forces a JSON object response
    raw = await engine._complete_with_fallback(
        prompt=prompt_content,
        system=system_prompt,
        max_tokens=1024,
        temperature=1.0,
        json_mode=True,
        api_key=api_key,
        api_model=api_model,
    )

    payload = _parse_companion_json(raw or "{}")

    # Update session state
    new_state = payload.get("internal_state", previous_state)
    update_session(
        user_id,
        conversation_id,
        internal_state=new_state,
        last_message_at=now if not is_tick else last_message_at,
    )
    if not is_tick:
        touch_last_message(user_id, conversation_id)

    return payload
