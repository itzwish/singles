"""Shared Upstash Redis client.

Upstash uses a REST/HTTP transport rather than raw TCP, so the standard
``redis.asyncio`` client will not work against it.  We use the official
``upstash-redis`` SDK which speaks the REST protocol natively.

Usage
-----
    from app.core.redis_client import get_redis

    redis = get_redis()          # returns Redis | None
    if redis:
        await redis.set("key", "value", ex=300)
        value = await redis.get("key")

The client is a module-level singleton — it is created once and reused.
``get_redis()`` returns ``None`` when credentials are absent so callers can
fall back gracefully without raising errors.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_initialised = False


def get_redis():
    """Return the Upstash Redis client, or ``None`` when not configured."""
    global _client, _initialised

    if _initialised:
        return _client

    _initialised = True

    from app.core.config import settings

    url = settings.upstash_redis_rest_url
    token = settings.upstash_redis_rest_token

    if not url or not token:
        logger.info("Upstash Redis not configured — running without Redis cache")
        return None

    try:
        from upstash_redis.asyncio import Redis  # type: ignore

        _client = Redis(url=url, token=token)
        logger.info("Upstash Redis client initialised (%s)", url)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to initialise Upstash Redis client: %s", exc)
        _client = None

    return _client
