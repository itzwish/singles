"""Long-term memory model — supports pgvector semantic search"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JSONType, UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class LongTermMemory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "long_term_memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    # The embedding column is created by the migration using the pgvector extension
