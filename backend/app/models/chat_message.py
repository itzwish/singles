"""Chat audit log model.

Denormalised on purpose: `character_id` is a plain string rather than a foreign
key, so a record survives deletion of the character or account that produced it.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin
from app.db.types import UUID


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    Stands in for `datetime.utcnow`, which is deprecated in Python 3.12+ and
    returns a *naive* datetime. A naive value written into a TIMESTAMPTZ column
    is rejected by the psycopg driver on Postgres, so the aware form is used
    instead — the stored instant is identical.
    """
    return datetime.now(timezone.utc)


class ChatMessage(Base, UUIDMixin):
    """One turn of a conversation, recorded for administrative review."""

    __tablename__ = "chat_messages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Deliberately not a foreign key: the log must outlive the character.
    character_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    user = relationship("User", lazy="joined")

    __table_args__ = (
        # Admin listing is almost always "newest first, optionally filtered".
        Index("ix_chat_messages_user_created_at", "user_id", "created_at"),
    )