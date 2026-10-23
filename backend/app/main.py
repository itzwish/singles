"""Easy Single — FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import GUEST_EMAIL, GUEST_USER_ID, settings
from app.services.storage import STATIC_DIR
from app.services.system_config import load_system_config

logger = logging.getLogger(__name__)

# Load persisted system configuration
load_system_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — runs on startup and shutdown."""
    from app.core.database import engine, AsyncSessionLocal
    from app.db.base import Base
    from app.models.__init__ import (
        User, Character, Conversation, Message, ChatMessage,
        LongTermMemory, CharacterDocument, Payment, UsageLog,
    )
    from app.core.security import hash_password

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables are ready")

        # Make sure the system guest user exists so foreign keys resolve.
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            existing = await db.execute(select(User).where(User.id == GUEST_USER_ID))
            if not existing.scalar_one_or_none():
                db.add(User(
                    id=GUEST_USER_ID,
                    email=GUEST_EMAIL,
                    username="Guest",
                    password_hash=hash_password("system-guest-no-login"),
                ))
                await db.commit()
                logger.info("System guest user created")
    except Exception as e:
        logger.warning(f"Database is not ready: {e}")
        logger.warning("  Start docker compose or set DATABASE_URL before retrying")

    # SQLite development convenience: ensure the dev local database file exists
    # as a fallback when no DATABASE_URL is set. This intentionally does not
    # seed or otherwise touch this file; it only guarantees a path so startup
    # does not raise FileNotFoundError in local sqlite-only runs.
    try:
        from app.core.config import settings as _settings
        from urllib.parse import urlparse
        _url = _settings.database_url
        if _url and urlparse(_url).scheme == "sqlite" and _url != "sqlite:///:memory:":
            from pathlib import Path
            _db_path = Path(urlparse(_url).netloc or "./dev.db")
            if _db_path.name:
                _db_path.parent.mkdir(parents=True, exist_ok=True)
                if not _db_path.exists():
                    _db_path.touch()
                    logger.info(f"Created local sqlite database file at {_db_path}")
    except Exception:
        pass

    yield

    # Flush any in-process chat audit rows before the process exits so an
    # admin restart does not silently lose the last few messages.
    try:
        from app.services.chat_audit import drain as _drain_audit

        await _drain_audit(timeout=5.0)
    except Exception:
        pass

    await engine.dispose()


def _parse_cors_origins(raw: str) -> list[str]:
    """Parse CORS_ORIGINS into a list, expanding a single `*` wildcard.

    Starlette's CORSMiddleware does not understand `https://*.vercel.app`, so
    pattern entries are expanded against the deployment's own hostname. That
    covers preview deploys, which get a unique subdomain per push.
    """
    entries = [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]
    if "*" in entries:
        entries = [e for e in entries if e != "*"]

        suffix_candidates = []
        # Derive the deployment's own hostname from VERCEL_URL / FLY_APP_NAME.
        vercel_url = os.environ.get("VERCEL_URL")
        if vercel_url:
            suffix_candidates.append(f"https://{vercel_url.split('://')[-1]}")

        fly_app = os.environ.get("FLY_APP_NAME")
        if fly_app:
            suffix_candidates.append(f"https://{fly_app}.fly.dev")

        if not suffix_candidates:
            # Local development convenience: allow any localhost port.
            logger.warning(
                "CORS_ORIGINS contains '*' but no VERCEL_URL/FLY_APP_NAME is set; "
                "allowing any http://localhost:* origin"
            )
            entries.append("http://localhost:*")
        else:
            for base in suffix_candidates:
                host = base.split("://", 1)[1]
                entries.append(base)
                entries.append(f"https://*.{host}")

    return entries


def create_app() -> FastAPI:
    app = FastAPI(
        title="Easy Single API",
        description="Easy Single — a full-stack AI chat companion backend.",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — the frontend is typically deployed separately (Vercel) from the
    # API (Fly.io), so origins are configured via CORS_ORIGINS.
    origins = _parse_cors_origins(settings.cors_origins)
    logger.info(f"CORS allowed origins: {origins or '(none)'}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Wildcard entries are handled by the middleware's own regex matching,
        # so keep credentials enabled for concrete origins only.
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Type"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api")
    def api_root():
        return {"name": "Easy Single API", "version": "2.0.0", "docs": "/docs", "health": "/health"}

    @app.exception_handler(Exception)
    async def global_exception_handler(_request: Request, exc: Exception):
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "The service is temporarily unavailable. Please try again shortly."},
        )

    # REST routes
    from app.api.v1.router import api_router

    app.include_router(api_router, prefix="/api/v1")

    # WebSocket routes
    from app.api.v1.ws import router as ws_router

    app.include_router(ws_router, prefix="/ws/chat")

    # Static files (avatars, etc.) — skipped when the directory is unavailable,
    # which is the case on read-only serverless filesystems.
    if STATIC_DIR.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        logger.warning(f"Static directory not found at {STATIC_DIR}; /static is disabled")

    # Frontend — Vercel promotes frontend/dist/ to the CDN and serves it at /.
    # SPA routes automatically fall back to index.html. Local-only: skipped when
    # the directory doesn't exist yet (before `npm run build` runs).
    try:
        from pathlib import Path
        _frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
        if _frontend_dist.is_dir():
            app.frontend("/", directory=str(_frontend_dist))
    except AttributeError:
        pass

    return app


app = create_app()