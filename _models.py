"""Quick probe of specific candidate models (streaming)."""

import asyncio
import sys

sys.path.insert(0, "backend")

from google import genai
from google.genai import types

from app.core.config import settings

CANDIDATES = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


def client():
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(base_url=settings.gemini_base_url),
    )


async def probe(name):
    c = client()
    out = ""
    async for chunk in await c.aio.models.generate_content_stream(
        model=name,
        contents="Reply with the single word: ok",
        config=types.GenerateContentConfig(max_output_tokens=20, temperature=0.7),
    ):
        out += chunk.text or ""
    return out.strip()


async def probe_vision(name):
    c = client()
    out = ""
    async for chunk in await c.aio.models.generate_content_stream(
        model=name,
        contents=[
            types.Part.from_text(text="What colour is this image? One word."),
            types.Part.from_bytes(data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(max_output_tokens=20, temperature=0.3),
    ):
        out += chunk.text or ""
    return out.strip()


async def main():
    for name in CANDIDATES:
        try:
            got = await probe(name)
            print(f"  [stream OK]    {name:<24} {got[:35]!r}")
            try:
                v = await probe_vision(name)
                print(f"  [vision OK]    {name:<24} {v[:35]!r}")
            except Exception as e:
                print(f"  [vision FAIL]  {name:<24} {getattr(e, 'code', '?')}")
        except Exception as e:
            print(f"  [stream FAIL]  {name:<24} {getattr(e, 'code', '?')}")


asyncio.run(main())