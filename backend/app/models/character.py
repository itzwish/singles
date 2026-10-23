"""Character model"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONType, UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class Character(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "characters"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str | None] = mapped_column(String(500))  # comma-separated tags
    personality_profile: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    owner = relationship("User", back_populates="characters")
    conversations = relationship("Conversation", back_populates="character", lazy="dynamic")
