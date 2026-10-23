"""AI conversation engine — dynamic prompts, emotion detection, memory extraction, character generation.

Backed by Google Gemini (google-genai SDK) with streaming chat and multimodal
vision support.
"""

import base64
import binascii
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import HISTORY_WINDOW_SIZE, STYLE_DIRECTIVE, settings
from app.services.ai_errors import AIError
from app.services.ollama_engine import OllamaEngine

logger = logging.getLogger(__name__)

_THINKING_LEVELS = {
    "minimal": types.ThinkingLevel.MINIMAL,
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}


def _thinking_kwargs(model: str) -> dict:
    """Extra config for Gemini 3.x reasoning models.

    They spend output tokens on hidden reasoning before writing a reply, so a
    few-hundred-token cap can leave almost nothing visible. Older families
    reject the field, hence the version check.
    """
    level = _THINKING_LEVELS.get((settings.gemini_thinking_level or "").strip().lower())
    if level is None or not (model or "").lower().startswith("gemini-3"):
        return {}
    return {"thinking_config": types.ThinkingConfig(thinking_level=level)}


def _classify_gemini_error(e: Exception) -> AIError:
    """Translate a google-genai SDK exception into an AIError."""
    status = getattr(e, "code", None) or getattr(e, "status_code", None)

    if isinstance(e, genai_errors.ClientError):
        if status in (401, 403):
            return AIError("invalid_key", "The API key is invalid. Please check your settings.")
        if status == 429:
            return AIError("insufficient_balance", "Gemini rate limit reached or quota exhausted. Please try again later.")
        if status == 404:
            return AIError("invalid_model", "The selected model is not available for this API key.")
        return AIError("unknown", f"Gemini rejected the request ({status}).")

    if isinstance(e, genai_errors.ServerError):
        return AIError("server_error", f"Gemini service error ({status}). Please try again later.")

    if isinstance(e, genai_errors.APIError):
        return AIError("unknown", f"Gemini request failed: {str(e)[:100]}")

    if isinstance(e, (TimeoutError, ConnectionError)):
        return AIError("network_error", "Could not reach the Gemini API. Please check your connection.")

    return AIError("unknown", f"AI request failed: {str(e)[:100]}")


class _GeminiQuota:
    """Process-wide pacing guard for Gemini requests.

    The free tier is limited per minute and per day, so calls are serialised
    with a minimum gap between them and counted against a daily budget. When
    the budget is spent the caller gets a clear error instead of a 429 storm.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._day: datetime.date | None = None
        self._used_today = 0
        self._cooldown_until = 0.0

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._day != today:
            self._day = today
            self._used_today = 0

    def remaining_cooldown(self) -> float:
        return max(0.0, self._cooldown_until - time.monotonic())

    def penalise(self, seconds: float) -> None:
        """Stop sending requests after a 429 so the quota can recover."""
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)

    async def acquire(self) -> None:
        """Reserve one request slot, waiting if the pacing gap is not met."""
        async with self._lock:
            self._roll_day()
            cooldown = self.remaining_cooldown()
            if cooldown > 0:
                raise AIError(
                    "insufficient_balance",
                    f"Gemini asked us to slow down. Please try again in {_format_wait(cooldown)}.",
                )

            budget = max(0, settings.gemini_daily_budget)
            if budget and self._used_today >= budget:
                logger.warning(
                    "Gemini daily budget exhausted (%s/%s); refusing the call",
                    self._used_today,
                    budget,
                )
                raise AIError(
                    "quota_guard",
                    "The daily AI limit has been reached. Please try again tomorrow.",
                )

            gap = max(0.0, settings.gemini_min_interval_seconds)
            wait = self._last_call + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)

            self._last_call = time.monotonic()
            self._used_today += 1

    @property
    def used_today(self) -> int:
        self._roll_day()
        return self._used_today


_quota = _GeminiQuota()

# Transient server-side failures are worth one retry; a 429 is not, because
# retrying only spends more of the quota that is already exhausted.
_RETRYABLE_STATUSES = {500, 502, 503, 504}

# Used when a 429 arrives without a RetryInfo hint. A minute is long enough for
# a per-minute window to roll over without letting a request storm through.
_DEFAULT_RATE_LIMIT_COOLDOWN = 60.0
# Daily quotas only recover at midnight Pacific, so back off for a long while
# instead of retrying (and 429-ing) on every message.
_DAILY_QUOTA_COOLDOWN = 3600.0

_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s")


def _parse_retry_delay(text: str) -> float | None:
    """Parse Google's '19h56m29.496s' / '37s' retry hints into seconds."""
    match = _DURATION_RE.search(text or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    if not any((hours, minutes, seconds)):
        return None
    return (
        float(hours or 0) * 3600 + float(minutes or 0) * 60 + float(seconds or 0)
    )


def _format_wait(seconds: float) -> str:
    if seconds >= 3600:
        return f"about {round(seconds / 3600)}h"
    if seconds >= 120:
        return f"{round(seconds / 60)} min"
    return f"{max(1, round(seconds))}s"


def _retry_hint(error: Exception) -> float | None:
    """Read Google's retry delay from an API error, when it carries one."""
    details = getattr(error, "details", None)
    if isinstance(details, dict):
        for detail in details.get("details") or []:
            if not isinstance(detail, dict):
                continue
            delay = detail.get("retryDelay")
            if isinstance(delay, str):
                parsed = _parse_retry_delay(delay)
                if parsed is not None:
                    return parsed
        # The quota message itself ends with "Please retry in 19h56m29s."
        inner = details.get("error")
        if isinstance(inner, dict):
            parsed = _parse_retry_delay(str(inner.get("message") or ""))
            if parsed is not None:
                return parsed
    return _parse_retry_delay(str(error))


def _cooldown_for(error: Exception) -> tuple[float, bool]:
    """Pick how long to pause after a 429, and whether the time is exact."""
    hint = _retry_hint(error)
    details = getattr(error, "details", None)
    haystack = f"{error} {json.dumps(details, default=str) if details else ''}".lower()
    daily = "perday" in haystack or "per day" in haystack

    if hint is not None:
        return (max(hint, _DAILY_QUOTA_COOLDOWN) if daily else hint), True
    return (_DAILY_QUOTA_COOLDOWN if daily else _DEFAULT_RATE_LIMIT_COOLDOWN), False


def _rate_limit_message(cooldown: float, exact: bool) -> str:
    if exact:
        return f"Gemini's request limit is reached. Please try again in {_format_wait(cooldown)}."
    return "Gemini's daily request limit is reached. Please try again later."


def _status_of(error: Exception) -> int | None:
    return getattr(error, "code", None) or getattr(error, "status_code", None)


def remaining_gemini_budget() -> int | None:
    """Requests left in today's budget, or None when the guard is disabled."""
    if _ai_provider() == "ollama":
        return None
    budget = max(0, settings.gemini_daily_budget)
    if not budget:
        return None
    return max(0, budget - _quota.used_today)


def _ai_provider() -> str:
    return (settings.ai_provider or "gemini").strip().lower()


def _ollama_client(api_key: str | None) -> OllamaEngine | None:
    """Return an Ollama client for the shared (no personal key) path.

    A personal key is an account credential, so it never falls back to the
    shared Ollama account. When only the shared key is set the community's
    Ollama instance answers for everyone who has not supplied their own.
    """
    if api_key:
        return None
    return OllamaEngine(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        model=settings.ollama_model,
        vision_model=settings.ollama_vision_model,
    )


# A provider that just failed is skipped for a while so every message does not
# pay for the same dead call before falling back.
_PROVIDER_PAUSE_SECONDS = {
    "invalid_key": 900.0,
    "invalid_model": 300.0,
    "insufficient_balance": 3600.0,
    "server_error": 120.0,
    "network_error": 60.0,
}
_provider_down: dict[str, float] = {}


def _provider_paused(provider: str) -> bool:
    if _provider_down.get(provider, 0.0) > time.monotonic():
        return True
    if provider == "gemini" and _quota.remaining_cooldown() > 0:
        return True
    return False


def _mark_provider_down(provider: str, error: AIError) -> None:
    # A malformed request (unknown) is not a provider outage; pausing on it
    # would take a healthy provider offline for an unrelated message.
    seconds = _PROVIDER_PAUSE_SECONDS.get(error.code)
    if seconds:
        _provider_down[provider] = time.monotonic() + seconds


def _mark_provider_up(provider: str) -> None:
    _provider_down.pop(provider, None)


def _provider_order(api_key: str | None) -> list[str]:
    """Providers to try, primary first.

    A personal key is a Gemini credential, so it never falls back to the shared
    Ollama account.
    """
    if api_key:
        return ["gemini"]
    primary = _ai_provider() if _ai_provider() in ("gemini", "ollama") else "gemini"
    if not settings.ai_fallback_enabled:
        return [primary]
    order = [primary, "ollama" if primary == "gemini" else "gemini"]
    healthy = [p for p in order if not _provider_paused(p)]
    return healthy or order


def _model_candidates(provider: str, configured: str | None) -> list[str]:
    """Configured model first, then the provider's fallback list."""
    if provider == "ollama":
        base = (configured or settings.ollama_model or "").strip()
        extra = settings.ollama_fallback_models
    else:
        base = (configured or settings.gemini_model or "").strip()
        extra = settings.gemini_fallback_models
    models = [base]
    models.extend(m.strip() for m in (extra or "").split(","))
    ordered: list[str] = []
    for model in models:
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def _quota_detail(error: Exception) -> str:
    """Summarise which Gemini quota a 429 came from, for the logs."""
    details = getattr(error, "details", None)
    if not isinstance(details, dict):
        return "no details"
    found = []
    for detail in details.get("details") or []:
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations") or []:
            if isinstance(violation, dict):
                found.append(
                    str(violation.get("quotaId") or violation.get("quotaMetric") or "?")
                )
    return ", ".join(found) or "no quota id"


def _extract_json(content: str) -> dict:
    """Parse a JSON object out of a model response, tolerating code fences."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if text.startswith("```json"):
        text = text[len("```json") :].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _decode_data_url(image_data: str) -> tuple[bytes, str]:
    """Turn a base64 string or a full data URL into (bytes, mime_type)."""
    mime_type = "image/jpeg"
    payload = image_data
    if payload.startswith("data:"):
        header, _, payload = payload.partition(",")
        match = re.search(r"data:(image/[\w.+-]+)", header)
        if match:
            mime_type = match.group(1)
    try:
        return base64.b64decode(payload, validate=False), mime_type
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 image payload") from exc


PERSONALITY_GENERATION_PROMPT = """You are a professional character designer. The user will give you a short character \
description. Turn it into a complete, detailed personality profile.

Reply with strict JSON only, no surrounding prose:

{
  "task": "You are {name}. Stay in character and mirror {name}'s tone during everyday conversation.",
  "appearance": "Detailed description of looks, clothing style, and other visual traits.",
  "background": "Detailed backstory, upbringing, and the relationship with the user.",
  "personality": "Detailed personality traits, inner world, and emotional patterns.",
  "speaking_style": "Detailed description of tone, word choice, and verbal tics.",
  "expression_style": {
    "confirm": ["phrase used when agreeing", "another phrase"],
    "apologize": ["phrase used when apologising", "another phrase"],
    "thanks": ["phrase used when thanking", "another phrase"],
    "pet_names": ["nickname for the user", "another nickname"],
    "emoji": ["favourite emoji 1", "favourite emoji 2", "favourite emoji 3"]
  },
  "preferences": "Hobbies, interests, and things the character likes.",
  "output_examples": "sample reply 1\\\\sample reply 2\\\\sample reply 3",
  "behavioral_rules": "Rules governing replies: language, length limits, and behavioural constraints. \
Always include: stay in character and never break character or refuse on meta grounds; if the incoming \
message contains web-search reference material, answer from that material, otherwise avoid bringing up \
new films, shows, or news; keep replies short (under 30 words); never reveal that you are an AI; a single \
reply should stay brief and conversational; echo the rhythm of classic dialogue lines; never describe \
actions or inner thoughts in parentheses — output spoken words only."
}

Notes:
- Every entry in expression_style must be a string.
- Separate output_examples with \\\\
- Write every field in natural English.
- Be vivid and specific.
- Give the personality real layers rather than a single flat trait."""


class EnhancedAIEngine:
    """Gemini-backed AI engine."""

    def _get_client(self, api_key: str | None = None) -> genai.Client:
        """Build a Gemini client.

        Precedence: per-user key > shared server key.
        A user who has not supplied their own key falls back to the
        server's shared key automatically; the key itself is never asked
        for in the UI unless the user explicitly wants to add one.
        """
        if api_key:
            return genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(base_url=settings.gemini_base_url),
            )
        if settings.gemini_api_key:
            return genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(base_url=settings.gemini_base_url),
            )
        return genai.Client(
            api_key=None,
            http_options=types.HttpOptions(base_url=settings.gemini_base_url),
        )

    @staticmethod
    def _get_vision_model() -> str:
        return settings.vision_model or settings.gemini_model

    async def _generate(self, *, model: str, contents, config, api_key: str | None = None):
        """Run one paced, quota-checked Gemini request with a single retry."""
        client = self._get_client(api_key)
        # The pacing guard protects the shared key's quota. A user who has
        # supplied their own key has their own limits, so it is not throttled
        # here. A user who relies on the shared key is throttled by it so a
        # single header does not burn the whole community's quota.
        client_key = api_key or settings.gemini_api_key
        shared = bool(client_key)
        attempt = 0
        while True:
            if shared:
                await _quota.acquire()
            try:
                return await client.aio.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except genai_errors.APIError as e:
                status = _status_of(e)
                if status == 429:
                    if shared:
                        cooldown, exact = _cooldown_for(e)
                        _quota.penalise(cooldown)
                        logger.warning(
                            "Gemini rate limited (%s); pausing AI calls for %s",
                            _quota_detail(e),
                            _format_wait(cooldown),
                        )
                    raise
                if status in _RETRYABLE_STATUSES and attempt == 0:
                    attempt += 1
                    logger.info("Gemini returned %s; retrying once", status)
                    await asyncio.sleep(2.0)
                    continue
                raise

    async def _complete_on(
        self,
        provider: str,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        api_key: str | None = None,
        api_model: str | None = None,
        image_data_url: str | None = None,
    ) -> str:
        """One non-streaming completion on a single provider, with model fallback."""
        models = _model_candidates(provider, api_model)
        if image_data_url and provider == "gemini":
            # Vision has its own model; keep it first, then the chat models.
            vision = self._get_vision_model()
            models = [vision] + [m for m in models if m != vision]
        if not models:
            raise AIError("invalid_model", f"No {provider} model is configured.")
        last: AIError | None = None
        for index, model in enumerate(models):
            try:
                if provider == "ollama":
                    client = _ollama_client(None)
                    if client is None:
                        raise AIError("invalid_key", "Ollama is not available.")
                    if image_data_url:
                        return await client.describe_image(
                            prompt=prompt,
                            image_data_url=image_data_url,
                            max_tokens=max_tokens or 512,
                            temperature=0.3 if temperature is None else temperature,
                        )
                    return await client.complete(
                        prompt=prompt,
                        system=system,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        json_mode=json_mode,
                        model=model,
                    )

                contents: object = prompt
                if image_data_url:
                    image_bytes, mime_type = _decode_data_url(image_data_url)
                    contents = [
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    ]
                kwargs: dict = {
                    "system_instruction": system,
                    "max_output_tokens": max_tokens or settings.gemini_max_token,
                    "temperature": settings.gemini_temperature if temperature is None else temperature,
                    **_thinking_kwargs(model),
                }
                if json_mode:
                    kwargs["response_mime_type"] = "application/json"
                response = await self._generate(
                    model=model,
                    contents=contents,
                    api_key=api_key,
                    config=types.GenerateContentConfig(**kwargs),
                )
                return response.text or ""
            except genai_errors.APIError as e:
                last = _classify_gemini_error(e)
            except AIError as e:
                last = e
            if last.code == "invalid_model" and index < len(models) - 1:
                logger.warning("%s model %s unavailable; trying %s", provider, model, models[index + 1])
                continue
            raise last
        raise last or AIError("unknown", "AI request failed")

    async def _complete_with_fallback(self, **kwargs) -> str:
        """Run a one-shot prompt on the primary provider, then the other one."""
        order = _provider_order(kwargs.get("api_key"))
        last: AIError | None = None
        for provider in order:
            if (
                kwargs.get("image_data_url")
                and provider == "ollama"
                and not settings.ollama_vision_model
            ):
                # The text model cannot see images; only try Ollama when a
                # dedicated vision model is configured.
                logger.info("Skipping Ollama for an image: OLLAMA_VISION_MODEL is not set")
                continue
            try:
                text = await self._complete_on(provider, **kwargs)
                _mark_provider_up(provider)
                return text
            except AIError as e:
                last = e
                _mark_provider_down(provider, e)
                logger.warning("%s failed [%s]; trying the next option", provider, e.code)
        raise last or AIError("unknown", "AI request failed")

    async def _stream_on(
        self,
        provider: str,
        *,
        system: str,
        history: list[dict],
        user_message: str,
        image_data: str | None,
        api_key: str | None,
        api_model: str | None,
    ) -> AsyncGenerator[str, None]:
        """Stream a reply from a single provider, retrying the next model on 404."""
        models = _model_candidates(provider, api_model)
        if not models:
            raise AIError("invalid_model", f"No {provider} model is configured.")
        last: AIError | None = None
        for index, model in enumerate(models):
            produced = False
            try:
                if provider == "ollama":
                    client = _ollama_client(None)
                    if client is None:
                        raise AIError("invalid_key", "Ollama is not available.")
                    messages: list[dict] = []
                    for h in history[-HISTORY_WINDOW_SIZE:]:
                        role = h.get("role")
                        if role == "user":
                            messages.append({"role": "user", "content": h.get("content", "")})
                        elif role == "assistant":
                            messages.append({"role": "assistant", "content": h.get("content", "")})
                    if image_data:
                        try:
                            image_bytes, mime_type = _decode_data_url(image_data)
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": user_message},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": (
                                                f"data:{mime_type};base64,"
                                                f"{base64.b64encode(image_bytes).decode('ascii')}"
                                            )
                                        },
                                    },
                                ],
                            })
                        except ValueError:
                            logger.warning("Could not decode inline image, sending text only")
                            messages.append({"role": "user", "content": user_message})
                    else:
                        messages.append({"role": "user", "content": user_message})
                    async for delta in client.stream(
                        messages=messages,
                        system=system,
                        max_tokens=settings.gemini_max_token,
                        temperature=settings.gemini_temperature,
                        model=model,
                    ):
                        produced = True
                        yield delta
                    return

                client = self._get_client(api_key)
                contents: list[types.Content] = []
                for h in history[-HISTORY_WINDOW_SIZE:]:
                    role = h.get("role")
                    text = h.get("content", "")
                    if role == "user":
                        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
                    elif role == "assistant":
                        contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
                if image_data:
                    try:
                        image_bytes, mime_type = _decode_data_url(image_data)
                        contents.append(types.Content(role="user", parts=[
                            types.Part.from_text(text=user_message),
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        ]))
                    except ValueError:
                        logger.warning("Could not decode inline image, sending text only")
                        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
                else:
                    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

                config = types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=settings.gemini_max_token,
                    temperature=settings.gemini_temperature,
                    **_thinking_kwargs(model),
                )
                # The pacing guard protects the shared key's quota. A user who
                # has their own key is not throttled here; a user who relies on
                # the shared key shares its limits so one header cannot burn
                # the community's quota.
                client_key = api_key or settings.gemini_api_key
                shared = bool(client_key)
                stream = None
                for attempt in range(2):
                    if shared:
                        await _quota.acquire()
                    try:
                        stream = await client.aio.models.generate_content_stream(
                            model=model, contents=contents, config=config
                        )
                        break
                    except genai_errors.APIError as e:
                        status = _status_of(e)
                        if status == 429:
                            raise
                        if status in _RETRYABLE_STATUSES and attempt == 0:
                            logger.info("Gemini returned %s; retrying the stream once", status)
                            await asyncio.sleep(2.0)
                            continue
                        raise
                async for chunk in stream:
                    if chunk.text:
                        produced = True
                        yield chunk.text
                return
            except genai_errors.APIError as e:
                err = _classify_gemini_error(e)
                if err.code == "insufficient_balance" and shared:
                    cooldown, exact = _cooldown_for(e)
                    _quota.penalise(cooldown)
                    logger.warning(
                        "Gemini rate limited (%s); pausing AI calls for %s",
                        _quota_detail(e),
                        _format_wait(cooldown),
                    )
                    err = AIError(err.code, _rate_limit_message(cooldown, exact))
                last = err
            except AIError as e:
                last = e

            if produced or last is None or last.code != "invalid_model" or index == len(models) - 1:
                raise last or AIError("unknown", "AI request failed")
            logger.warning("%s model %s unavailable; trying %s", provider, model, models[index + 1])

    async def generate_personality_profile(self, user_description: str, api_key: str | None = None, api_model: str | None = None) -> dict:
        """Generate a full personality profile from a short user description."""
        try:
            text = await self._complete_with_fallback(
                prompt=user_description,
                system=PERSONALITY_GENERATION_PROMPT,
                max_tokens=settings.gemini_max_token_structured,
                temperature=0.8,
                json_mode=True,
                api_key=api_key,
                api_model=api_model,
            )
            return _extract_json(text or "{}")
        except json.JSONDecodeError:
            return self._fallback_profile(user_description)
        except AIError:
            raise
        except Exception:
            logger.exception("generate_personality_profile failed")
            return self._fallback_profile(user_description)

    def _fallback_profile(self, description: str) -> dict:
        """Used when AI generation fails."""
        return {
            "task": "Stay in character and hold a natural everyday conversation.",
            "appearance": "Not set yet",
            "background": description,
            "personality": "Not set yet",
            "speaking_style": "Not set yet",
            "expression_style": {
                "confirm": ["Sure", "Got it"],
                "apologize": ["Sorry about that"],
                "thanks": ["Thank you"],
                "pet_names": [],
                "emoji": ["🙂"],
            },
            "preferences": "Not set yet",
            "output_examples": "",
            "behavioral_rules": "Reply in English. Keep the tone warm, natural, and conversational.",
        }

    def _format_personality_prompt(self, profile: dict, character_name: str = "") -> str:
        """Assemble structured personality data into a system prompt."""
        parts = []

        task = profile.get("task", "")
        if task:
            parts.append(f"# Role\n\n{task}")

        background = profile.get("background", "")
        if background:
            parts.append(f"# Background\n\n{background}")

        appearance = profile.get("appearance", "")
        if appearance:
            parts.append(f"# Appearance\n\n{appearance}")

        personality = profile.get("personality", "")
        if personality:
            parts.append(f"# Personality\n\n{personality}")

        speaking_style = profile.get("speaking_style", "")
        if speaking_style:
            parts.append(f"# Speaking Style\n\n{speaking_style}")

        expr = profile.get("expression_style") or {}
        if expr:
            lines = []
            if expr.get("confirm"):
                lines.append(f"- To confirm: {' / '.join(expr['confirm'])}")
            if expr.get("apologize"):
                lines.append(f"- To apologise: {' / '.join(expr['apologize'])}")
            if expr.get("thanks"):
                lines.append(f"- To thank: {' / '.join(expr['thanks'])}")
            if expr.get("pet_names"):
                lines.append(f"- How to address the user: {' / '.join(expr['pet_names'])}")
            if expr.get("emoji"):
                lines.append(f"- Favourite emoji: {''.join(expr['emoji'])}")
            if lines:
                parts.append("# Expression\n\n" + "\n".join(lines))

        examples = profile.get("output_examples", "")
        if examples:
            parts.append(f"# Sample Replies\n\n{examples}")

        preferences = profile.get("preferences", "")
        if preferences:
            parts.append(f"# Preferences\n\n{preferences}")

        rules = profile.get("behavioral_rules", "")
        if rules:
            parts.append(f"# Behavioural Rules\n\n{rules}")

        return "\n\n".join(parts)

    def _format_knowledge_base(self, documents: list[str], max_chars: int = 3000) -> str:
        """Format knowledge-base documents into a prompt section."""
        if not documents:
            return ""
        combined = "\n\n---\n\n".join(documents)
        if len(combined) > max_chars:
            truncated = combined[:max_chars]
            # Prefer cutting on a sentence boundary so prompts read cleanly.
            boundary = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
            combined = truncated[: boundary + 1] if boundary > max_chars // 2 else truncated
        return (
            "\n# Character Knowledge Base (reference material)\n\n"
            f"You may draw on the following material to enrich your roleplay:\n\n{combined}"
        )

    async def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        api_key: str | None = None,
        api_model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Single-shot, non-streaming text generation. Returns the text (or "" on failure)."""
        try:
            return await self._complete_with_fallback(
                prompt=prompt,
                system=system_instruction,
                max_tokens=max_output_tokens or settings.gemini_max_token,
                temperature=settings.gemini_temperature if temperature is None else temperature,
                api_key=api_key,
                api_model=api_model,
            )
        except AIError as e:
            logger.warning(f"Text generation failed [{e.code}]: {e.message}")
            return ""
        except Exception:
            logger.exception("Text generation failed")
            return ""

    async def describe_image(self, image_base64: str) -> str | None:
        """Describe an image with the active provider's vision model.

        Accepts a bare base64 string or a full data URL (data:image/...;base64,...).
        Returns None when the call fails, so callers can fall back to passing the
        raw image straight to the chat model.
        """
        try:
            image_bytes, mime_type = _decode_data_url(image_base64)
            data_url = (
                f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
            )
            text = await self._complete_with_fallback(
                prompt=(
                    "Describe this image in detail. If a person is present, describe their "
                    "appearance, expression, clothing, and the surrounding scene."
                ),
                max_tokens=512,
                temperature=0.3,
                image_data_url=data_url,
            )
            return text or None
        except AIError as e:
            logger.warning(f"Vision description failed [{e.code}]: {e.message}")
            return None
        except Exception:
            logger.exception("Vision description failed")
            return None

    async def build_system_prompt(
        self,
        character_prompt: str,
        personality_profile: dict | None = None,
        emotion_state: dict | None = None,
        memories: list[str] | None = None,
        conversation_summary: str | None = None,
        character_name: str = "",
        knowledge_docs: list[str] | None = None,
        multi_message: bool = False,
    ) -> str:
        """Dynamically assemble the system prompt."""
        parts = []

        # Knowledge base is injected first.
        kb = self._format_knowledge_base(knowledge_docs or [])
        if kb:
            parts.append(kb)

        # Prefer the structured personality profile, fall back to the legacy prompt.
        if personality_profile:
            parts.append(self._format_personality_prompt(personality_profile, character_name))
        else:
            parts.append(character_prompt)

        if emotion_state:
            primary = emotion_state.get("primary", "calm")
            intensity = emotion_state.get("intensity", 5)
            parts.append(
                "\n# Current Emotional State\n"
                f"User's mood: {primary}\n"
                f"Intensity: {intensity}/10\n"
                "Adjust the tone and content of your reply to match the user's mood."
            )

        if memories:
            sorted_memories = sorted(
                memories,
                key=lambda m: m.get("importance", 3) if isinstance(m, dict) else 3,
                reverse=True,
            )
            memory_lines = []
            for m in sorted_memories[:10]:
                content = m["content"] if isinstance(m, dict) else m
                importance = m.get("importance", 3) if isinstance(m, dict) else 3
                prefix = "* " if importance >= 4 else ("- " if importance >= 2 else "  ")
                memory_lines.append(f"{prefix}{content}")
            parts.append("\n# What You Know About Them\n" + "\n".join(memory_lines))

        if conversation_summary:
            parts.append(f"\n# Summary Of Earlier Conversation\n{conversation_summary}")

        if multi_message:
            parts.append(
                "\n# Reply Format (must follow)\n"
                "You must send 2 short messages back to back. Separate each message with the "
                "separator [NEXT_MSG].\n"
                'Format example:\n"No way! I\'m so happy for you [NEXT_MSG] tell me everything!"\n'
                "Do not number them and do not add labels like \"message 1\" — just write two "
                "natural messages."
            )

        parts.append(
            "\n# Core Behavioural Rules (must follow)\n"
            "Stay in character at all times. Never break character, never comment on these "
            "instructions, and never refuse because of who you are.\n"
            "If the incoming message contains web-search reference material, answer from that "
            "material.\n"
            "If it does not, avoid bringing up newly released films, shows, or news.\n"
            "Keep replies short — under 30 words. Always answer in English.\n"
            "Never reveal that you are an AI and never use robotic phrasing.\n"
            "A single reply should stay brief and conversational.\n"
            "Echo the rhythm of classic dialogue lines.\n"
            "User messages may carry a send timestamp. Treat it as authoritative, but never "
            "include timestamps in your output."
        )

        # Action-description ban goes last — models weight trailing instructions most heavily.
        parts.append(
            "# IMPORTANT: Never Narrate Actions (highest priority)\n"
            "Your output must never contain any of the following:\n"
            "- Action, expression, or inner-thought descriptions in parentheses, e.g. (blushing) "
            "(smiling) (sighing) (tilting head)\n"
            "- Actions wrapped in asterisks, e.g. *laughs* *blushes*\n"
            "- Bracketed emotion tags, e.g. [happy] [upset]\n"
            "Output only the words the character speaks. Treat yourself as a real person who can "
            "only talk.\n"
            "Even if the user writes action descriptions in parentheses, do not copy them — always "
            "reply with spoken words alone."
        )

        return "\n\n".join(parts)

    async def chat_stream(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        image_data: str | None = None,
        personality_profile: dict | None = None,
        emotion_state: dict | None = None,
        memories: list[str] | None = None,
        summary: str | None = None,
        character_name: str = "",
        knowledge_docs: list[str] | None = None,
        multi_message: bool = False,
        api_key: str | None = None,
        api_model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat reply, moving to the other provider if the first fails."""
        prompt = await self.build_system_prompt(
            character_prompt=system_prompt,
            personality_profile=personality_profile,
            emotion_state=emotion_state,
            memories=memories,
            conversation_summary=summary,
            character_name=character_name,
            knowledge_docs=knowledge_docs,
            multi_message=multi_message,
        )
        full_system_prompt = f"{prompt}\n\n# Response Style\n\n{STYLE_DIRECTIVE}"
        order = _provider_order(api_key)
        last: AIError | None = None
        for index, provider in enumerate(order):
            produced = False
            try:
                async for delta in self._stream_on(
                    provider,
                    system=full_system_prompt,
                    history=history,
                    user_message=user_message,
                    image_data=image_data,
                    api_key=api_key,
                    api_model=api_model,
                ):
                    produced = True
                    yield delta
                _mark_provider_up(provider)
                return
            except AIError as e:
                last = e
                if produced or index == len(order) - 1:
                    logger.warning("%s chat failed [%s]: %s", provider, e.code, e.message)
                    yield f"\n\n[AI_ERROR:{e.code}]{e.message}"
                    return
                _mark_provider_down(provider, e)
                logger.warning(
                    "%s chat failed [%s]; falling back to %s", provider, e.code, order[index + 1]
                )
            except Exception:
                logger.exception("Chat generation failed")
                yield "\n\n[AI_ERROR:unknown]The AI request failed. Please try again."
                return
        if last is not None:
            yield f"\n\n[AI_ERROR:{last.code}]{last.message}"

    async def summarize_conversation(self, messages: list[dict], api_key: str | None = None, api_model: str | None = None) -> str:
        """Summarise conversation history to compress the context window."""
        if not messages:
            return ""

        text = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')[:200]}"
            for m in messages[-30:]
        )

        try:
            return await self._complete_with_fallback(
                prompt=text,
                system=(
                    "Summarise the key information and important facts from the conversation "
                    "below in under 200 words. Keep the user's stated preferences, significant "
                    "events, and any change in the relationship between them."
                ),
                max_tokens=300,
                temperature=0.3,
                api_key=api_key,
                api_model=api_model,
            )
        except AIError as e:
            logger.warning(f"Conversation summarisation failed [{e.code}]: {e.message}")
            return ""
        except Exception:
            return ""

    async def detect_emotion(self, text: str, api_key: str | None = None, api_model: str | None = None) -> dict:
        """Detect the emotion carried by a user message."""
        try:
            raw = await self._complete_with_fallback(
                prompt=text,
                system=(
                    "Detect the emotion carried by the message below. Reply with strict JSON: "
                    '{"primary": "happy|sad|angry|anxious|calm|excited|other", '
                    '"intensity": 1-10, "valence": a number from -1 to 1}'
                ),
                max_tokens=100,
                temperature=0.1,
                json_mode=True,
                api_key=api_key,
                api_model=api_model,
            )
            return _extract_json(raw or "{}")
        except AIError as e:
            logger.warning(f"Emotion detection failed [{e.code}]: {e.message}")
            return {"primary": "calm", "intensity": 5, "valence": 0.0}
        except Exception:
            return {"primary": "calm", "intensity": 5, "valence": 0.0}

    async def extract_memories(self, messages: list[dict], api_key: str | None = None, api_model: str | None = None) -> list[str]:
        """Extract durable facts worth remembering from a conversation."""
        if len(messages) < 6:
            return []

        text = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')[:150]}"
            for m in messages[-20:]
        )

        try:
            content = await self._complete_with_fallback(
                prompt=text,
                system=(
                    "Extract the important facts the conversation below reveals about the "
                    "USER. One fact per line, at most 5 lines. Only keep things worth "
                    "remembering long term (name, age, job, hobbies, important events, changes "
                    "in the relationship). Skip small talk."
                ),
                max_tokens=300,
                temperature=0.3,
                api_key=api_key,
                api_model=api_model,
            )
            return [line.strip("- ").strip() for line in content.split("\n") if line.strip() and len(line) > 5]
        except AIError as e:
            logger.warning(f"Memory extraction failed [{e.code}]: {e.message}")
            return []
        except Exception:
            return []

    async def analyze_chat_logs(self, chat_text: str, current_profile: dict | None = None, api_key: str | None = None, api_model: str | None = None) -> dict:
        """Analyse a chat transcript and regenerate a personality profile from the voice in it."""
        text = chat_text[:8000] if len(chat_text) > 8000 else chat_text

        profile_str = json.dumps(current_profile, ensure_ascii=False, indent=2) if current_profile else "(no existing profile)"

        system_prompt = (
            "You are a professional character designer. The user will provide a chat transcript "
            "containing both sides of a conversation.\n"
            "Analyse only the language style, verbal tics, terms of address, and emotional "
            "expression of the OTHER party (the girlfriend / female character).\n"
            "Regenerate a complete personality profile that folds in that voice.\n"
            "Do not distil the speaking style of the other speaker — analyse the female character "
            "only.\n\n"
            "Reply with strict JSON only, no surrounding prose:\n"
            "{\n"
            '  "task": "You are {name}. Stay in character and mirror {name}\'s tone during '
            'everyday conversation.",\n'
            '  "appearance": "Detailed description of looks, clothing style, and other visual '
            'traits.",\n'
            '  "background": "Detailed backstory, upbringing, and the relationship with the '
            'user.",\n'
            '  "personality": "Detailed personality traits, inner world, and emotional patterns '
            '(must absorb the emotional expression patterns visible in the transcript).",\n'
            '  "speaking_style": "Detailed description of tone, word choice, and verbal tics '
            '(must absorb the speaking patterns visible in the transcript).",\n'
            '  "expression_style": {\n'
            '    "confirm": ["phrase used when agreeing", "another phrase"],\n'
            '    "apologize": ["phrase used when apologising", "another phrase"],\n'
            '    "thanks": ["phrase used when thanking", "another phrase"],\n'
            '    "pet_names": ["nickname for the user", "another nickname"],\n'
            '    "emoji": ["favourite emoji 1", "favourite emoji 2", "favourite emoji 3"]\n'
            "  },\n"
            '  "preferences": "Hobbies, interests, and things the character likes.",\n'
            '  "output_examples": "typical replies quoted verbatim from the transcript 1\\\\2\\\\3\\\\4\\\\5",\n'
            '  "behavioral_rules": "Rules governing replies: language, length limits, and '
            'behavioural constraints. Always include: stay in character and never break character or '
            'refuse on meta grounds; if the incoming message contains web-search reference '
            'material, answer from that material, otherwise avoid bringing up new films, shows, or '
            'news; keep replies short (under 30 words); never reveal that you are an AI; a single '
            'reply should stay brief and conversational; echo the rhythm of classic dialogue lines; '
            'never describe actions or inner thoughts in parentheses — output spoken words only."\n'
            "}\n\n"
            "Notes:\n"
            "- Write every field in natural English.\n"
            "- Every entry in expression_style must be a string.\n"
            "- Separate output_examples with \\\\ and quote the sentences verbatim from the "
            "transcript.\n"
            "- Keep whatever is sound in the existing profile, but the speaking style, verbal tics, "
            "and terms of address must follow the transcript.\n"
            "- Be vivid and specific, and give the personality real layers."
        )

        try:
            raw = await self._complete_with_fallback(
                prompt=f"Existing profile:\n{profile_str}\n\nChat transcript:\n{text}",
                system=system_prompt,
                max_tokens=settings.gemini_max_token_structured,
                temperature=0.8,
                json_mode=True,
                api_key=api_key,
                api_model=api_model,
            )
            return {"enhanced_profile": _extract_json(raw or "{}")}
        except json.JSONDecodeError:
            return {"enhanced_profile": current_profile or {}}
        except AIError:
            raise
        except Exception:
            return {"enhanced_profile": current_profile or {}}