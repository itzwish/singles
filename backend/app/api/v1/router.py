"""API v1 router aggregation"""

from fastapi import APIRouter

from app.api.v1 import auth, characters, conversations, memories, users, admin, chat, webhooks, companion

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(characters.router, prefix="/characters", tags=["Characters"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(memories.router, prefix="/memories", tags=["Memories"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(companion.router, prefix="/companion", tags=["Companion"])