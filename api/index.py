"""Vercel serverless entrypoint for the Easy Single FastAPI backend.

Mangum adapts the ASGI app to Vercel's Python (Lambda) runtime. Point
`vercel.json` at this file so every `/api/*` request reaches the backend.
The `functions` block declares this file, so Vercel routes only `/api/*`
to it — everything else (frontend, assets, SPA routes) is served from
`outputDirectory` / `rewrites`.

Notes
-----
* Vercel serverless functions do not support WebSocket upgrades, so streaming
  chat runs over SSE instead (`POST /api/v1/chat/stream`). The frontend
  detects a closed WebSocket and falls back automatically.
* The filesystem is read-only, so the SQLite fallback database is not
  persistent. Set DATABASE_URL to a hosted Postgres for real deployments.
* `lifespan="off"` skips the startup hook. Startup does table creation and
  seeds the guest row, which on Vercel would run per cold start against an
  ephemeral database. Import `app.main:app` and let it run instead if you are
  deploying somewhere with a durable database.
"""

import os
import sys
from pathlib import Path

# Make the `app` package importable from the repo-root `api/` directory.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402

try:  # pragma: no cover - import guarded so `vercel dev` works without it
    from mangum import Mangum

    handler = Mangum(app, lifespan="off", api_gateway_base_path=[])
except ImportError:  # pragma: no cover
    # Local development without Mangum installed still exposes the ASGI app.
    handler = app

# Convenience for `vercel dev` and WSGI-based tooling.
wsgi_app = app
application = app


__all__ = ["app", "handler", "wsgi_app", "application"]
