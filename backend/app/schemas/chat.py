"""Chat-related schemas"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    character_id: str
    message: str
    image_data: str | None = None  # base64


class ChatResponse(BaseModel):
    reply: str
