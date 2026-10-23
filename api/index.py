"""Vercel serverless entrypoint for the Easy Single FastAPI backend.

Mangum adapts the ASGI app to Vercel's Python (Lambda) runtime. The
`functions` block in vercel.json declares this file, so Vercel routes
/api/* requests to it. Static files and SPA rewrites are handled by
Vercel's outputDirectory + rewrites configuration.
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

    handler = Mangum(app, lifespan="off", api_gateway_base_path="/api")
except ImportError:  # pragma: no cover
    handler = app

# Convenience for `vercel dev` and WSGI-based tooling.
wsgi_app = app
application = app

__all__ = ["app", "handler", "wsgi_app", "application"]
