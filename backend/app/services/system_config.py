"""System-wide API configuration — JSON file storage with in-memory sync.

Only values an admin actually changed through the panel are persisted. Values
that come from the environment stay in the environment, so a key set in ``.env``
is never copied into the JSON file.

On read-only filesystems (Vercel serverless, containers) writes fail silently and
the process keeps running with the environment-variable defaults.
"""

import json
import os
from pathlib import Path

from app.core.config import settings

# Fall back to /tmp on read-only deployments so the panel still "works" (in-memory only).
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent
if not os.access(_CONFIG_DIR, os.W_OK):
    _CONFIG_DIR = Path(os.environ.get("TMPDIR", "/tmp"))
CONFIG_PATH = _CONFIG_DIR / "system_config.json"

DEFAULTS = {
    "ai_provider": "gemini",
    "ai_fallback_enabled": True,
    "gemini_fallback_models": "",
    "ollama_fallback_models": "",
    "vision_enabled": True,
    "vision_model": "gemini-3.5-flash",
    "gemini_api_key": "",
    "gemini_model": "gemini-3.5-flash",
    "ollama_base_url": "https://ollama.com/v1",
    "ollama_api_key": "",
    "ollama_model": "gpt-oss:120b",
    "ollama_vision_model": "",
}

# Keys written through the admin panel; only these are persisted.
_overrides: dict = {}


def load_system_config():
    """Load persisted system config at startup, overriding settings defaults."""
    global _overrides
    if not CONFIG_PATH.exists():
        return

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    for key in DEFAULTS:
        if key not in data or not hasattr(settings, key):
            continue
        value = data[key]
        # Blank stored values mean "not configured here" — keep the value from
        # the environment (GEMINI_API_KEY, OLLAMA_API_KEY, etc.) instead of
        # wiping it out with an empty string from the JSON file.
        if value in (None, ""):
            continue
        _overrides[key] = value
        setattr(settings, key, value)


def get_system_config() -> dict:
    """Return the effective system configuration."""
    return _current_state()


def update_system_config(data: dict) -> dict:
    """Partially update the system configuration and return the full new state."""
    for key in DEFAULTS:
        if key in data and hasattr(settings, key):
            val = data[key]
            # Blank values are never persisted: a key set in .env (e.g.
            # GEMINI_API_KEY) must survive an admin clearing its field.
            if val in (None, ""):
                continue
            if isinstance(DEFAULTS[key], bool) and not isinstance(val, bool):
                val = str(val).lower() in ("true", "1", "yes")
            _overrides[key] = val
            setattr(settings, key, val)

    _save()
    return _current_state()


def _current_state() -> dict:
    return {key: getattr(settings, key, DEFAULTS[key]) for key in DEFAULTS}


def _save():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_overrides, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Non-critical path; a failed write must not break the running app.
