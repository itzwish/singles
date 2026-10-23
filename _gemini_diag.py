"""Reproduce the Gemini 400 and surface the server's error message."""

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import STYLE_DIRECTIVE, settings

print("GEMINI_API_KEY set:", bool(settings.gemini_api_key),
      f"(len={len(settings.gemini_api_key)})")
print("model:", settings.gemini_model)
print("max_output_tokens:", settings.gemini_max_token)
print("temperature:", settings.gemini_temperature)
print()

client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(base_url=settings.gemini_base_url),
)

base = "You are Nora, a warm character. Keep replies in English."

cases = [
    ("plain, 300/0.7", base, 300, 0.7),
    ("with STYLE_DIRECTIVE", f"{base}\n\n# Response Style\n\n{STYLE_DIRECTIVE}", 300, 0.7),
    ("2000/0.9 (old defaults)", base, 2000, 0.9),
]

async def probe(label, sysinstr, max_tokens, temp):
    cfg = types.GenerateContentConfig(
        system_instruction=sysinstr, max_output_tokens=max_tokens, temperature=temp
    )
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text="Hi")]),
        types.Content(role="model", parts=[types.Part.from_text(text="Hey! How are you?")]),
        types.Content(role="user", parts=[types.Part.from_text(text="Good, you?")]),
    ]
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(base_url=settings.gemini_base_url),
    )
    try:
        stream = await client.aio.models.generate_content_stream(
            model=settings.gemini_model, contents=contents, config=cfg
        )
        text = ""
        async for chunk in stream:
            text += chunk.text or ""
        print(f"[OK]   {label}: {text[:70]!r}")
    except genai_errors.APIError as e:
        print(f"[ERR]  {label}: code={getattr(e, 'code', '?')}")
        print(f"       {str(e)[:400]}")
    except Exception as e:
        print(f"[EXC]  {label}: {type(e).__name__}: {str(e)[:200]}")
    print()


async def main():
    base = "You are Nora, a warm character. Keep replies in English."
    await probe("plain, 300/0.7", base, 300, 0.7)
    await probe("with STYLE_DIRECTIVE", f"{base}\n\n# Response Style\n\n{STYLE_DIRECTIVE}", 300, 0.7)
    await probe("2000/0.9 (old defaults)", base, 2000, 0.9)


asyncio.run(main())