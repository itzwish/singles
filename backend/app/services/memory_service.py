"""Memory service — automatic summarisation, AI importance scoring, and capacity eviction."""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import LongTermMemory
from app.models.message import Message
from app.models.conversation import Conversation
from app.models.character import Character
from app.services.ai_engine import AIError, EnhancedAIEngine

logger = logging.getLogger(__name__)

engine = EnhancedAIEngine()

# ── Memory capacity ──
MAX_MEMORIES_PER_CHARACTER = 30
CONSOLIDATE_MIN_MESSAGES = 12


def _parse_importance(text: str, default: int = 3) -> int:
    """Pull a 1-5 score out of a model response."""
    match = re.search(r"[1-5]", text or "")
    return int(match.group()) if match else default


async def _get_unlinked_messages(
    character_id: str, user_id: str, db: AsyncSession, limit: int = 100
) -> list[Message]:
    """Fetch messages not yet folded into a long-term memory (across up to 3 conversations)."""
    from uuid import UUID

    conv_stmt = (
        select(Conversation)
        .where(
            Conversation.character_id == UUID(character_id),
            Conversation.user_id == UUID(user_id),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(3)
    )
    conv_result = await db.execute(conv_stmt)
    conversations = conv_result.scalars().all()

    if not conversations:
        return []

    conv_ids = [c.id for c in conversations]

    msg_stmt = (
        select(Message)
        .where(
            Message.conversation_id.in_(conv_ids),
            Message.role.in_(["user", "assistant"]),
            ~Message.id.in_(
                select(LongTermMemory.source_message_id).where(
                    LongTermMemory.source_message_id.isnot(None)
                )
            ),
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    msg_result = await db.execute(msg_stmt)
    return list(msg_result.scalars().all())


async def consolidate_memories(
    character_id: str,
    user_id: str,
    db: AsyncSession,
    api_key: str | None = None,
    api_model: str | None = None,
) -> dict:
    """Fold recent short-term messages into a durable long-term memory."""
    from uuid import UUID

    messages = await _get_unlinked_messages(character_id, user_id, db)
    if len(messages) < CONSOLIDATE_MIN_MESSAGES:
        return {
            "consolidated": False,
            "reason": f"Not enough messages ({len(messages)}/{CONSOLIDATE_MIN_MESSAGES})",
        }

    char_result = await db.execute(
        select(Character).where(Character.id == UUID(character_id))
    )
    character = char_result.scalar_one_or_none()
    char_name = character.name if character else "the character"

    log_lines = [
        f"[{char_name if m.role == 'assistant' else 'User'}] {m.content}" for m in messages
    ]
    full_log = "\n".join(log_lines)

    # Step 1: summarise from the character's point of view
    summary_prompt = (
        f"You are playing as {char_name}. Summarise the conversation below from {char_name}'s "
        "first-person perspective, pulling out the details worth remembering. Reply with the "
        "summary alone — no labels or prefixes.\n\n" + full_log
    )
    try:
        summary = (await engine.generate_text(
            summary_prompt, api_key=api_key, api_model=api_model, max_output_tokens=400, temperature=0.5
        )).strip()
    except AIError:
        raise
    except Exception as e:
        logger.error(f"Memory summarisation failed: {e}")
        return {"consolidated": False, "reason": "AI summarisation failed"}

    if not summary:
        return {"consolidated": False, "reason": "The AI returned an empty summary"}

    # Step 2: AI importance score (1-5)
    try:
        importance_text = await engine.generate_text(
            f"Rate how important this memory is (1 = trivial, 5 = very important). "
            f"Reply with the single digit only:\n\n{summary}",
            api_key=api_key,
            api_model=api_model,
            max_output_tokens=10,
            temperature=0.1,
        )
        importance = _parse_importance(importance_text)
    except Exception:
        importance = 3

    last_msg = messages[-1]
    memory = LongTermMemory(
        user_id=UUID(user_id),
        character_id=UUID(character_id),
        content=summary,
        importance=importance,
        source_message_id=last_msg.id,
    )
    db.add(memory)
    await db.flush()

    await manage_memory_capacity(character_id, user_id, db)

    logger.info(
        f"Memory consolidated: character={char_name}, importance={importance}, "
        f"messages={len(messages)}, summary_len={len(summary)}"
    )
    return {
        "consolidated": True,
        "importance": importance,
        "summary": summary[:200],
        "message_count": len(messages),
    }


async def manage_memory_capacity(character_id: str, user_id: str, db: AsyncSession):
    """Evict low-scoring memories once the per-character cap is exceeded."""
    from uuid import UUID

    stmt = (
        select(LongTermMemory)
        .where(
            LongTermMemory.character_id == UUID(character_id),
            LongTermMemory.user_id == UUID(user_id),
        )
        .order_by(LongTermMemory.created_at.desc())
    )
    result = await db.execute(stmt)
    memories = list(result.scalars().all())

    if len(memories) <= MAX_MEMORIES_PER_CHARACTER:
        return

    now = datetime.now(timezone.utc)

    scored = []
    for m in memories:
        age_hours = (now - m.created_at).total_seconds() / 3600
        score = 0.6 * m.importance - 0.4 * age_hours
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    keep_ids = {s[1].id for s in scored[:MAX_MEMORIES_PER_CHARACTER]}

    to_delete = [m for m in memories if m.id not in keep_ids]
    for m in to_delete:
        await db.delete(m)

    if to_delete:
        logger.info(f"Memory eviction: removed {len(to_delete)} low-scoring memories")