"""Database engine, session factory, and connection-string normalisation.

Single source of truth for the SQLAlchemy async engine. Every module imports
from here rather than managing its own engine.

Connection handling
-------------------
`DATABASE_URL` arrives in whatever shape the host hands us:

  postgres://user:pw@host:5432/db   Fly Postgres  -> rewritten to postgresql://
  postgresql://…                    already fine   -> left alone
  sqlite:///./dev.db                local default  -> aiosqlite driver
  /data/dev.db                      bare path      -> treated as SQLite

`create_async_engine` resolves the plain `postgresql://` scheme to a psycopg3
driver on its own, so no explicit `+psycopg` suffix is needed. An explicit
`postgresql+asyncpg://` is still honoured for anyone carrying an old URL.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# Used when DATABASE_URL is unset (local development).
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./dev.db"


def normalize_database_url(url: str | None) -> str:
    """Coerce a user-supplied DATABASE_URL into a URL SQLAlchemy can open."""
    url = (url or "").strip()
    if not url:
        logger.info(f"DATABASE_URL not set, falling back to {DEFAULT_DATABASE_URL}")
        return DEFAULT_DATABASE_URL

    # Fly Postgres (and most hosting dashboards) hand out the legacy scheme.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]

    if url.startswith(("postgresql://", "postgresql+asyncpg://")):
        return url

    if url.startswith("sqlite+aiosqlite:"):
        return url

    if url.startswith("sqlite:"):
        # sqlite:///relative.db, sqlite:////absolute.db, sqlite://relative.db
        _, _, remainder = url.partition(":")
        if remainder.startswith("///"):
            return "sqlite+aiosqlite:" + remainder
        if remainder.startswith("//"):
            return "sqlite+aiosqlite:///" + remainder[2:]
        return "sqlite+aiosqlite:///" + remainder

    if "://" in url:
        logger.warning("Unrecognised DATABASE_URL scheme, passing it through unchanged")
        return url

    # Bare filesystem path, e.g. "/data/dev.db"
    return "sqlite+aiosqlite:///" + url


def _engine_kwargs(url: str) -> dict:
    """Connection-pool options only apply to networked drivers."""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_size": 5, "max_overflow": 5, "pool_pre_ping": True}


DATABASE_URL = normalize_database_url(settings.database_url)

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    **_engine_kwargs(DATABASE_URL),
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency yielding a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise