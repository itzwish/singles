"""User model"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONType, UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Set once the account is linked to a Clerk user. Rows created before the
    # Clerk migration keep this NULL until the user signs in with Clerk.
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    membership_tier: Mapped[str] = mapped_column(String(20), default="free")  # free / premium / vip
    membership_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    api_key_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)

    # Relationships
    characters = relationship("Character", back_populates="owner", lazy="dynamic")
    conversations = relationship("Conversation", back_populates="user", lazy="dynamic")
