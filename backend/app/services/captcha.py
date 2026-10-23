"""SVG image captcha — stored in Upstash Redis when available, otherwise in process memory.

Upstash Redis uses a REST/HTTP transport so the standard ``redis.asyncio``
client does not apply here.  When Upstash credentials are absent (e.g. pure
serverless with no Redis) the in-memory fallback keeps the login flow working
(captchas simply do not survive a cold start in that case).
"""

import base64
import random
import time
import uuid

from app.core.redis_client import get_redis

TTL = 300  # 5 minutes

# In-process fallback store: {captcha_id: (code, expires_at)}
_MEMORY_STORE: dict[str, tuple[str, float]] = {}


def _key(captcha_id: str) -> str:
    return f"captcha:{captcha_id}"


def _memory_set(captcha_id: str, code: str) -> None:
    now = time.monotonic()
    for stale_id, (_, expires) in list(_MEMORY_STORE.items()):
        if expires <= now:
            _MEMORY_STORE.pop(stale_id, None)
    _MEMORY_STORE[captcha_id] = (code, now + TTL)


def _memory_pop(captcha_id: str) -> str | None:
    entry = _MEMORY_STORE.pop(captcha_id, None)
    if not entry:
        return None
    code, expires = entry
    return code if expires > time.monotonic() else None


async def generate_captcha() -> dict:
    """Generate an SVG captcha and return {captcha_id, captcha_image}."""
    # 4 random alphanumeric characters, minus the visually ambiguous 0/O/1/I/l
    chars = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    code = "".join(random.choices(chars, k=4))

    svg = _render_svg(code)

    captcha_id = uuid.uuid4().hex[:12]
    client = get_redis()
    if client is not None:
        try:
            # Upstash SDK: set(key, value, ex=seconds)
            await client.set(_key(captcha_id), code, ex=TTL)
        except Exception:
            _memory_set(captcha_id, code)
    else:
        _memory_set(captcha_id, code)

    svg_b64 = base64.b64encode(svg.encode()).decode()
    return {
        "captcha_id": captcha_id,
        "captcha_image": f"data:image/svg+xml;base64,{svg_b64}",
    }


async def verify_captcha(captcha_id: str, captcha_code: str) -> bool:
    """Verify a captcha. Consumes it either way (single use)."""
    if not captcha_id or not captcha_code:
        return False

    stored: str | None = None
    client = get_redis()
    if client is not None:
        try:
            # Upstash getdel returns a str (or None) directly — no .decode() needed
            stored = await client.getdel(_key(captcha_id))
        except Exception:
            stored = _memory_pop(captcha_id)
    else:
        stored = _memory_pop(captcha_id)

    if not stored:
        return False
    return captcha_code.strip().upper() == stored.upper()


def _render_svg(code: str) -> str:
    """Render an SVG captcha with noise lines and dots."""
    w, h = 120, 44
    colors = ["#e87d8a", "#c44d6a", "#d4687c", "#b84560", "#f598a5", "#9b3d54"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="#fef5f7" rx="6"/>',
    ]

    # 3 noise lines
    for _ in range(3):
        x1, y1 = random.randint(0, w // 3), random.randint(4, h - 4)
        x2, y2 = random.randint(w * 2 // 3, w), random.randint(4, h - 4)
        stroke = random.choice(colors)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="1" opacity="0.3"/>'
        )

    # 15 noise dots
    for _ in range(15):
        cx, cy = random.randint(4, w - 4), random.randint(4, h - 4)
        fill = random.choice(colors)
        r = random.uniform(0.5, 1.5)
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" opacity="0.3"/>')

    # Characters, each rotated and offset
    char_w = w // len(code)
    for i, ch in enumerate(code):
        x = char_w * i + random.randint(6, char_w - 20)
        y = random.randint(28, 36)
        angle = random.randint(-30, 30)
        font_size = random.randint(22, 26)
        fill = random.choice(colors)
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{font_size}" fill="{fill}" '
            f'font-family="Arial,Helvetica,sans-serif" font-weight="bold" '
            f'transform="rotate({angle},{x},{y})">{ch}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)