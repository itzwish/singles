"""Shared chat pipeline.

The same conversation flow powers both transports:
  - WebSocket at /ws/chat/{conversation_id} (primary, lowest latency)
  - SSE at POST /api/v1/chat/stream (fallback for platforms without WS,
    such as Vercel serverless functions)

Both consume the event stream this module yields, so behaviour stays identical.
"""

import asyncio
import json
import logging
import random
import re
import uuid

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.message import Message
from app.models.conversation import Conversation
from app.models.character import Character
from app.models.character_document import CharacterDocument
from app.models.memory import LongTermMemory
from app.models.user import User
from app.core.security import decrypt_api_key
from app.core.identity import resolve_user_id
from app.services.ai_engine import EnhancedAIEngine, remaining_gemini_budget
from app.services.chat_audit import record_reply as audit_record_reply
from app.services.chat_audit import record_turn as audit_record_turn
from app.services.memory_service import consolidate_memories

logger = logging.getLogger(__name__)

engine = EnhancedAIEngine()

# Trigger memory consolidation every N messages
MEMORY_CONSOLIDATE_INTERVAL = 20
# Trigger conversation summarisation every N messages
SUMMARY_INTERVAL = 30

# Local emotion cues. Emotion used to cost one Gemini request per chat turn,
# which doubled the quota burn for a value that is only used as prompt context.
_EMOTION_CUES = {
    "happy": ("happy", "glad", "great", "wonderful", "love", "lovely", "smile", "😊", "😄", "🥰", "❤"),
    "excited": ("excited", "amazing", "awesome", "can't wait", "cant wait", "yay", "🎉", "!!"),
    "sad": ("sad", "unhappy", "lonely", "miss you", "cry", "crying", "hurt", "😢", "😭", "💔"),
    "angry": ("angry", "mad", "annoyed", "furious", "hate", "stupid", "😠", "😡"),
    "anxious": ("anxious", "nervous", "worried", "worry", "scared", "afraid", "stress", "😰", "😨"),
}
_EMOTION_VALENCE = {
    "happy": 0.6,
    "excited": 0.8,
    "sad": -0.6,
    "angry": -0.7,
    "anxious": -0.4,
    "calm": 0.1,
}


def _can_run_maintenance() -> bool:
    """Keep a reserve of requests for actual chat replies.

    Summaries and memory consolidation are useful but not worth spending the
    last few requests of a 20-per-day free tier on.
    """
    remaining = remaining_gemini_budget()
    return remaining is None or remaining > 4


def _local_emotion(text: str) -> dict:
    """Cheap keyword estimate of the emotion in a message (no API request)."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return {"primary": "calm", "intensity": 2, "valence": 0.0}

    scores = {
        emotion: sum(lowered.count(cue) for cue in cues)
        for emotion, cues in _EMOTION_CUES.items()
    }
    primary, hits = max(scores.items(), key=lambda item: item[1])
    if not hits:
        primary = "calm"
    intensity = min(10, 3 + hits * 2) if hits else 2
    return {
        "primary": primary,
        "intensity": intensity,
        "valence": _EMOTION_VALENCE.get(primary, 0.0),
    }

# Hallucinated [IMAGE:...] tags. We only strip these — image generation is gone.
IMAGE_TAG_RE = re.compile(r'\[[Ii][Mm][Aa][Gg][Ee][：:].*?\]')
# Fake "sent a photo" narration, e.g. [sent a photo] / [sent 3 photos].
# Anchored at the start of the bracket so legitimate text like
# "[look at the image I sent you]" is left alone.
FAKE_SEND_RE = re.compile(r'\[(?:sent|sending|image|photo|picture)s?[^\]]*\]', re.IGNORECASE)

# Action narration the model sometimes emits, stripped before persisting
PAREN_ACTION_RE = re.compile(r'[（(][^）)]*?[）)]')
ASTERISK_ACTION_RE = re.compile(r'\*[^*]+?\*')
BRACKET_EMOTION_RE = re.compile(r'【[^】]+?】')

_WHITESPACE_RE = re.compile(r'[ \t]{2,}')

DEFAULT_SYSTEM_PROMPT = "You are a warm, friendly AI companion. Always reply in English."


def split_messages(text: str) -> list[str]:
    """Split a reply into several messages to mimic how a real person types."""
    if "[NEXT_MSG]" in text:
        return [p.strip() for p in text.split("[NEXT_MSG]") if p.strip()]

    if len(text) <= 80:
        return [text]

    sentences = re.split(r'(?<=[.!?~…\n])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 1:
        return [text]

    if len(sentences) <= 4:
        mid = len(sentences) // 2
        return [''.join(sentences[:mid]), ''.join(sentences[mid:])]

    n = min(3, len(sentences) - 1)
    size = max(1, len(sentences) // n)
    result = []
    for i in range(0, len(sentences), size):
        group = sentences[i : i + size]
        if group:
            result.append(''.join(group))

    # Fold a too-short trailing fragment back into the previous message
    if len(result) >= 2 and len(result[-1]) < 10:
        result[-2] += result[-1]
        result.pop()

    return result[:3]


def strip_narration(text: str) -> str:
    """Remove image tags, fake send-narration, and bracketed action descriptions."""
    text = IMAGE_TAG_RE.sub("", text)
    text = FAKE_SEND_RE.sub("", text)
    text = PAREN_ACTION_RE.sub("", text)
    text = ASTERISK_ACTION_RE.sub("", text)
    text = BRACKET_EMOTION_RE.sub("", text)
    # Removing inline tags leaves gaps behind; collapse them.
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


async def load_user_credentials(user_id: str) -> tuple[str | None, str | None]:
    """Return (api_key, api_model) for a user, or (None, None) if unavailable."""
    try:
        uuid.UUID(user_id)
    except ValueError:
        return None, None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
            user = result.scalar_one_or_none()
            if user:
                api_key = decrypt_api_key(user.api_key_encrypted) if user.api_key_encrypted else None
                return api_key, user.api_model
    except Exception:
        logger.exception("Failed to load the user's API credentials")
    return None, None


async def resolve_identity(token: str | None) -> str:
    """Resolve a credential to a user id, falling back to a throwaway id for guests.

    Accepts a ws ticket, a Clerk session token, or a legacy access token.
    """
    if token and token != "guest":
        user_id = await resolve_user_id(token)
        if user_id:
            return user_id
        logger.warning("Invalid auth token on the chat stream")
    return str(uuid.uuid4())


async def _load_context(db, conversation_id: str, user_id: str):
    """Load everything a reply needs: conversation, character, history, memories, knowledge."""
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        return None

    char_result = await db.execute(
        select(Character).where(Character.id == conv.character_id)
    )
    char = char_result.scalar_one_or_none()

    # Recent history — fake "sent a photo" narration is stripped so the model
    # cannot learn to imitate it.
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == uuid.UUID(conversation_id))
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    history = []
    for m in reversed(msg_result.scalars().all()):
        content = FAKE_SEND_RE.sub("", m.content).strip()
        if not content:
            content = "[photo]"
        history.append({"role": m.role, "content": content})

    mem_result = await db.execute(
        select(LongTermMemory)
        .where(
            LongTermMemory.user_id == uuid.UUID(user_id),
            LongTermMemory.character_id == conv.character_id,
        )
        .order_by(LongTermMemory.importance.desc(), LongTermMemory.created_at.desc())
        .limit(10)
    )
    memories = [
        {"content": m.content, "importance": m.importance, "id": str(m.id)}
        for m in mem_result.scalars().all()
    ]

    doc_result = await db.execute(
        select(CharacterDocument)
        .where(CharacterDocument.character_id == conv.character_id)
        .order_by(CharacterDocument.created_at.desc())
        .limit(5)
    )
    knowledge_docs = [d.content_text for d in doc_result.scalars().all()]

    return {
        "conversation": conv,
        "character": char,
        "history": history,
        "memories": memories,
        "knowledge_docs": knowledge_docs,
        "emotion_state": conv.emotion_state,
        "summary": conv.summary,
    }


async def _detect_and_update_emotion(db, conv, user_message, api_key, api_model):
    """Detect the user's emotion and store it on the conversation."""
    try:
        if settings.gemini_llm_emotion:
            emotion = await engine.detect_emotion(user_message, api_key=api_key, api_model=api_model)
        else:
            emotion = _local_emotion(user_message)
        conv.emotion_state = emotion
        await db.flush()
        return emotion
    except Exception:
        logger.exception("Emotion detection failed")
        return conv.emotion_state


async def _maybe_summarize(db, conv, conversation_id, api_key, api_model):
    """Summarise the conversation once the message count hits the threshold."""
    if conv.message_count > 0 and conv.message_count % SUMMARY_INTERVAL == 0:
        try:
            msg_result = await db.execute(
                select(Message)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .order_by(Message.created_at.desc())
                .limit(30)
            )
            recent = [
                {"role": m.role, "content": m.content}
                for m in reversed(msg_result.scalars().all())
            ]
            summary = await engine.summarize_conversation(recent, api_key=api_key, api_model=api_model)
            if summary:
                conv.summary = summary
                await db.flush()
        except Exception:
            logger.exception("Conversation summarisation failed")


async def _persist_assistant_replies(
    conversation_id: str,
    parts: list[str],
    user_id: str,
    api_key: str | None,
    api_model: str | None,
    character_id: str | None = None,
):
    """Save assistant messages and run the periodic background maintenance."""
    async with AsyncSessionLocal() as db:
        for part in parts:
            db.add(
                Message(
                    conversation_id=uuid.UUID(conversation_id),
                    role="assistant",
                    content=part,
                    content_type="text",
                )
            )

        # Mirror the reply into the admin audit log (background write).
        audit_record_reply(user_id, character_id, parts)

        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.message_count = (conv.message_count or 0) + 1

            if conv.message_count % SUMMARY_INTERVAL == 0 and _can_run_maintenance():
                asyncio.create_task(
                    _maybe_summarize(db, conv, conversation_id, api_key, api_model)
                )

            if conv.message_count % MEMORY_CONSOLIDATE_INTERVAL == 0 and _can_run_maintenance():
                asyncio.create_task(
                    consolidate_memories(
                        str(conv.character_id), user_id, db, api_key, api_model
                    )
                )

        await db.commit()


async def stream_chat(
    conversation_id: str,
    user_message: str,
    image_data: str | None,
    user_id: str,
    api_key: str | None,
    api_model: str | None,
):
    """Run one turn of chat, yielding transport-agnostic event dicts.

    Event shapes mirror the historical WebSocket protocol so both clients agree:
      {"type": "chunk",     "content": str}
      {"type": "done",      "full_reply": str, "emotion_state": dict | None}
      {"type": "ai_error",  "code": str, "message": str}
      {"type": "error",     "message": str}
    """
    logger.info(
        f"[CHAT] Message received: {user_message[:80] if user_message else '(empty)'}, "
        f"has_image={bool(image_data)}"
    )

    # When a photo is attached, describe it with the vision model first. If vision
    # is unavailable we forward the raw image to the chat model instead.
    display_content = user_message or "[photo]"  # what the user's bubble renders
    fallback_image = None
    if image_data:
        description = await engine.describe_image(image_data)
        if description:
            user_message = (
                f"[The user sent a photo: {description}] "
                f"They said: {user_message or 'Look at this picture'}"
            )
        else:
            logger.warning("Vision unavailable, forwarding the raw image to the chat model")
            fallback_image = image_data

    async with AsyncSessionLocal() as db:
        # Persist only what the user typed — never the vision context.
        db.add(
            Message(
                conversation_id=uuid.UUID(conversation_id),
                role="user",
                content=display_content,
                content_type="image" if image_data else "text",
                metadata_={"image_base64": image_data} if image_data else None,
            )
        )
        await db.flush()

        ctx = await _load_context(db, conversation_id, user_id)
        if not ctx:
            yield {"type": "error", "message": "Conversation not found"}
            return

        conv = ctx["conversation"]
        char = ctx["character"]
        character_id = str(conv.character_id)

        conv.message_count = (conv.message_count or 0) + 1

        # Mirror the prompt into the admin audit log (background write).
        audit_record_turn(user_id, character_id, "user", display_content)

        # Emotion detection runs in the background and never blocks the reply.
        emotion_task = asyncio.create_task(
            _detect_and_update_emotion(db, conv, user_message, api_key, api_model)
        )

        system_prompt = char.system_prompt if char and char.system_prompt else DEFAULT_SYSTEM_PROMPT
        personality_profile = char.personality_profile if char else None
        character_name = char.name if char else ""

        await db.commit()

    # Stream outside the DB session so the connection is never held open.
    multi = random.random() < 0.35

    raw_full_reply = ""
    async for chunk in engine.chat_stream(
        system_prompt=system_prompt,
        history=ctx["history"],
        user_message=user_message,
        image_data=fallback_image,
        personality_profile=personality_profile,
        emotion_state=conv.emotion_state,
        memories=ctx["memories"],
        summary=conv.summary,
        character_name=character_name,
        knowledge_docs=ctx["knowledge_docs"],
        multi_message=multi,
        api_key=api_key,
        api_model=api_model,
    ):
        raw_full_reply += chunk

    logger.info(f"[CHAT] Stream finished, reply_len={len(raw_full_reply)}")

    err_match = re.search(r'\[AI_ERROR:(\w+)\](.*)', raw_full_reply)
    if err_match:
        yield {
            "type": "ai_error",
            "code": err_match.group(1),
            "message": err_match.group(2).strip(),
        }
        return

    full_reply = strip_narration(raw_full_reply)

    # Let emotion detection finish before we persist state.
    await asyncio.gather(emotion_task, return_exceptions=True)

    msg_parts = split_messages(full_reply) if multi else [full_reply]
    if not msg_parts:
        msg_parts = [full_reply]

    await _persist_assistant_replies(
        conversation_id, msg_parts, user_id, api_key, api_model, character_id
    )

    # Drop empty parts so the UI never renders a blank bubble.
    text_parts = [p for p in msg_parts if p.strip() and p.strip() != "[photo]"]
    logger.info(
        f"[SEND] parts={len(text_parts)} full_reply={repr(full_reply[:100]) if full_reply else 'EMPTY'}"
    )

    if not text_parts:
        yield {
            "type": "ai_error",
            "code": "empty_reply",
            "message": "I lost my train of thought there... could you say that again?",
        }
        return

    for i, part in enumerate(text_parts):
        if i == 0:
            yield {
                "type": "done",
                "full_reply": part,
                "emotion_state": conv.emotion_state,
            }
        else:
            # Type later messages out character by character for realism.
            delay = 1.8 + random.uniform(0, 2.5)
            await asyncio.sleep(delay)
            for j in range(0, len(part), 2):
                yield {"type": "chunk", "content": part[j : j + 2]}
                await asyncio.sleep(0.025)
            yield {
                "type": "done",
                "full_reply": part,
                "emotion_state": conv.emotion_state,
            }


def sse_format(event: dict) -> str:
    """Serialise an event dict as one Server-Sent Event frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"