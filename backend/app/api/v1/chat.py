"""Chat API — SSE streaming (primary fallback) and a one-shot REST reply.

The WebSocket endpoint at /ws/chat/{conversation_id} is the lowest-latency path.
This module covers platforms that do not support WebSocket upgrades, notably
Vercel serverless functions, by streaming identical events over
Server-Sent Events instead.
"""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.dependencies import get_optional_user
from app.core.security import decrypt_api_key
from app.models.user import User
from app.services.ai_engine import AIError, EnhancedAIEngine
from app.services.chat_pipeline import (
    DEFAULT_SYSTEM_PROMPT,
    load_user_credentials,
    resolve_identity,
    sse_format,
    stream_chat,
)

logger = logging.getLogger(__name__)

router = APIRouter()

engine = EnhancedAIEngine()


class StreamChatRequest(BaseModel):
    conversation_id: str
    message: str = ""
    image: str | None = None


class ChatRequest(BaseModel):
    character_id: str
    message: str
    image_data: str | None = None  # base64


class ChatResponse(BaseModel):
    reply: str


async def _credentials_for(current_user: User | None, token: str | None):
    """Resolve (user_id, api_key, api_model) from either a bearer token or a body token."""
    if token:
        user_id = await resolve_identity(token)
        api_key, api_model = await load_user_credentials(user_id)
        return user_id, api_key, api_model

    if current_user:
        api_key = (
            decrypt_api_key(current_user.api_key_encrypted)
            if current_user.api_key_encrypted
            else None
        )
        return str(current_user.id), api_key, current_user.api_model

    return await resolve_identity(None), None, None


@router.post("/stream")
async def chat_stream_sse(
    data: StreamChatRequest,
    token: str | None = None,
    current_user: User | None = Depends(get_optional_user),
):
    """Stream a chat reply as Server-Sent Events.

    Emits the same event shapes as the WebSocket endpoint:
    `chunk`, `done`, `ai_error`, and `error`.
    """
    user_id, api_key, api_model = await _credentials_for(current_user, token)

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for event in stream_chat(
                conversation_id=data.conversation_id,
                user_message=data.message,
                image_data=data.image,
                user_id=user_id,
                api_key=api_key,
                api_model=api_model,
            ):
                yield sse_format(event)
        except Exception:
            logger.exception("SSE chat stream failed")
            yield sse_format({"type": "error", "message": "Something went wrong. Please try again."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disables response buffering on proxies that would otherwise
            # hold the whole reply until the stream completes.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    current_user: User | None = Depends(get_optional_user),
):
    """Non-streaming chat. Prefer /stream for streamed replies."""
    api_key = (
        decrypt_api_key(current_user.api_key_encrypted)
        if current_user and current_user.api_key_encrypted
        else None
    )
    api_model = current_user.api_model if current_user else None

    try:
        chunks = [
            chunk
            async for chunk in engine.chat_stream(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                history=[],
                user_message=data.message,
                image_data=data.image_data,
                api_key=api_key,
                api_model=api_model,
            )
        ]
    except AIError as e:
        raise HTTPException(status_code=400, detail=e.message) from e

    return ChatResponse(reply="".join(chunks))