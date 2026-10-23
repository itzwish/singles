"""Vercel native FastAPI entrypoint for Easy Single.

Vercel auto-detects FastAPI apps at supported entrypoints (app.py, index.py,
main.py, etc.) at the repository root or inside src/ or app/. This file
exposes the backend's `app` instance so Vercel serves it natively — no
Mangum needed.

The backend lives in backend/ (one level down), so we add it to sys.path
here to keep backend/app/main.py importable.
"""

from pathlib import Path
import sys

# Make the `backend` package importable from the repository root.
_BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import app  # noqa: E402

# Convenience aliases for local tooling.
application = app
wsgi_app = app

__all__ = ["app", "application", "wsgi_app"]
