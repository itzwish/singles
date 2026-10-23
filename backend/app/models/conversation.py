"""Conversation model"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONType, UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200))
    emotion_state: Mapped[dict | None] = mapped_column(JSONType)  # {primary, intensity, valence}
    summary: Mapped[str | None] = mapped_column(Text)  # AI-generated conversation summary
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    user = relationship("User", back_populates="conversations")
    character = relationship("Character", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", lazy="dynamic",
                            order_by="Message.created_at", cascade="all, delete-orphan",
                            passive_deletes=True)
