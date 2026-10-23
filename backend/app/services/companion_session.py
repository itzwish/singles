"""In-memory session store for companion internal state.

Keyed by (user_id, conversation_id) so each conversation thread maintains
its own emotional trajectory. Data lives only as long as the process; a
restart resets to DEFAULT_INTERNAL_STATE which is fine - the companion
simply starts fresh (as if waking up after sleeping).
"""

from datetime import datetime
from typing import Optional

from app.companion_prompt import DEFAULT_INTERNAL_STATE

# { (user_id, conversation_id) -> {"last_message_at": datetime | None, "internal_state": dict} }
_sessions: dict[tuple[str, str], dict] = {}


def get_session(user_id: str, conversation_id: str) -> dict:
    """Return the live session dict, creating a fresh one if absent."""
    key = (user_id, conversation_id)
    if key not in _sessions:
        _sessions[key] = {
            "last_message_at": None,
            "internal_state": dict(DEFAULT_INTERNAL_STATE),
        }
    return _sessions[key]


def update_session(
    user_id: str,
    conversation_id: str,
    internal_state: dict,
    last_message_at: Optional[datetime] = None,
) -> None:
    """Persist a new internal_state (and optionally update last_message_at)."""
    key = (user_id, conversation_id)
    session = _sessions.setdefault(
        key,
        {"last_message_at": None, "internal_state": dict(DEFAULT_INTERNAL_STATE)},
    )
    session["internal_state"] = internal_state
    if last_message_at is not None:
        session["last_message_at"] = last_message_at


def touch_last_message(user_id: str, conversation_id: str) -> None:
    """Record that the user just sent a message (now)."""
    session = get_session(user_id, conversation_id)
    session["last_message_at"] = datetime.now().astimezone()
