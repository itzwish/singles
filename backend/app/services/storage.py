"""Filesystem storage helpers for uploaded avatars.

On Vercel (and any read-only filesystem) uploads cannot be persisted. Rather
than crashing, callers get a clear error so the UI can fall back to initials.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BACKEND_ROOT / "static"
AVATAR_DIR = STATIC_DIR / "avatars"


class StorageUnavailableError(RuntimeError):
    """Raised when the deployment filesystem cannot persist an upload."""


def _resolve_extension(original_filename: str | None) -> str:
    if original_filename and "." in original_filename:
        ext = original_filename.rsplit(".", 1)[-1].lower()
        if ext.isalnum() and len(ext) <= 5:
            return ext
    return "png"


def save_avatar(stem: str, original_filename: str | None, content: bytes) -> str:
    """Persist avatar bytes and return the public URL path.

    Raises StorageUnavailableError when the filesystem is read-only.
    """
    ext = _resolve_extension(original_filename)
    filename = f"{stem}.{ext}"
    target = AVATAR_DIR / filename

    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    except OSError as e:
        logger.error(f"Could not write avatar to {target}: {e}")
        raise StorageUnavailableError(
            "Avatar uploads are not supported on this deployment's filesystem."
        ) from e

    return f"/static/avatars/{filename}"


def ensure_writable(path: Path) -> bool:
    """Return True when `path` is (or can be made) writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return os.access(path, os.W_OK)
    except OSError:
        return False