"""Chat audit logging.

Every turn is mirrored into `chat_messages` so administrators can review what
was said across all users and personas.

Writes are dispatched as background tasks so they never sit on the critical
path of a streamed reply. Each task owns its own session and swallows its own
errors — losing an audit row must never take down a live conversation.

Durability caveat: these tasks are in-process and fire-and-forget. On platforms
that freeze or discard the container between requests (Vercel serverless), a
row can be lost if the process is reclaimed mid-write. Deploy to a long-lived
backend (Fly.io, Docker, Railway) when the audit trail must be complete.
"""

import asyncio
import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.chat_message import ChatMessage

logger = logging.getLogger(__name__)

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# Strong references to in-flight writes so the event loop does not garbage
# collect a task mid-await.
_PENDING: set[asyncio.Task] = set()


def _coerce_user_id(user_id: str | None) -> uuid.UUID | None:
    """Return a valid UUID, or None when the caller has no persisted user."""
    if not user_id:
        return None
    try:
        return uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        logger.debug("Skipping audit row: user_id=%r is not a UUID", user_id)
        return None


def _spawn(rows: list[dict]) -> None:
    """Schedule an audit write, retaining a reference until it completes."""
    try:
        task = asyncio.create_task(_run_write(rows))
    except RuntimeError:
        # No running loop (e.g. called from sync code) — drop the row.
        logger.warning("No event loop; dropping %d chat audit row(s)", len(rows))
        return
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


async def _run_write(rows: list[tuple[str, str]]) -> None:
    """Insert audit rows in their own session. Never raises."""
    try:
        async with AsyncSessionLocal() as db:
            for row in rows:
                db.add(ChatMessage(**row))
            await db.commit()
    except SQLAlchemyError:
        logger.exception("Chat audit write failed")
    except Exception:
        logger.exception("Unexpected error writing a chat audit row")


def record_turn(
    user_id: str | None,
    character_id: str | None,
    role: str,
    content: str,
) -> None:
    """Queue one audit row for a single turn."""
    if not user_id or not character_id:
        return
    _spawn([_build_row(user_id, character_id, role, content)])


def record_reply(
    user_id: str | None,
    character_id: str | None,
    contents: list[str],
) -> None:
    """Queue one audit row per assistant message."""
    if not user_id or not character_id:
        return
    rows = [r for r in (_build_row(user_id, character_id, ROLE_ASSISTANT, c) for c in contents) if r]
    if rows:
        _spawn(rows)


def _build_row(user_id: str, character_id: str, role: str, content: str) -> dict | None:
    uid = _coerce_user_id(user_id)
    if uid is None:
        return None
    return {
        "user_id": uid,
        "character_id": str(character_id),
        "role": role,
        "content": content or "",
    }


async def drain(timeout: float = 5.0) -> None:
    """Wait for outstanding audit writes. Useful in tests and on shutdown."""
    if not _PENDING:
        return
    await asyncio.wait(set(_PENDING), timeout=timeout)