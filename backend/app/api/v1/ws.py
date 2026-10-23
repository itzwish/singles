"""WebSocket streaming chat — the primary transport."""

import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.chat_pipeline import load_user_credentials, resolve_identity, stream_chat

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str, conversation_id: str):
        await websocket.accept()
        key = f"{user_id}:{conversation_id}"
        self.active[key] = websocket

    def disconnect(self, user_id: str, conversation_id: str):
        key = f"{user_id}:{conversation_id}"
        self.active.pop(key, None)


manager = ConnectionManager()


@router.websocket("/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: str):
    user_id = str(uuid.uuid4())
    user_api_key: str | None = None
    user_api_model: str | None = None

    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15)
        msg = json.loads(raw)

        if msg.get("type") == "auth" and msg.get("token"):
            user_id = await resolve_identity(msg["token"])
            user_api_key, user_api_model = await load_user_credentials(user_id)

        manager.active[f"{user_id}:{conversation_id}"] = websocket

        # If the first frame was auth, wait for a real chat frame; otherwise handle it now.
        first_message = msg if msg.get("type") != "auth" else None

        while True:
            if first_message:
                msg = first_message
                first_message = None
            else:
                raw = await websocket.receive_text()
                msg = json.loads(raw)

            if msg.get("type") != "chat":
                continue

            async for event in stream_chat(
                conversation_id=conversation_id,
                user_message=msg.get("message", ""),
                image_data=msg.get("image"),
                user_id=user_id,
                api_key=user_api_key,
                api_model=user_api_model,
            ):
                await websocket.send_json(event)

    except asyncio.TimeoutError:
        pass  # Auth handshake timed out — close silently.
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket chat error")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        manager.disconnect(user_id, conversation_id)