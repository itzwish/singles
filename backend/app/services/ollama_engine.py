"""Ollama adapter (Ollama Cloud or a local daemon) over the OpenAI-compatible API.

Ollama exposes ``/v1/chat/completions`` at ``OLLAMA_BASE_URL`` (``https://ollama.com/v1``
for Ollama Cloud, ``http://localhost:11434/v1`` for a local install). Streaming uses the
same server-sent-event shape as OpenAI, so no SDK is needed beyond httpx.

Two Ollama quirks are handled here:

* reasoning models (gpt-oss, deepseek, minimax) spend the output budget on hidden
  reasoning, so ``max_tokens`` gets headroom and ``reasoning_effort`` is lowered;
* a model can be missing or outside the account's plan (404/402), so callers pass an
  ordered model list and the next one is tried.
"""

import json
import logging
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.services.ai_errors import AIError

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0)
_MAX_TOKEN_CEILING = 4096


def _normalise_base(base_url: str) -> str:
    base = (base_url or "https://ollama.com/v1").strip().rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _classify(status: int, body: str) -> AIError:
    detail = (body or "").strip()[:200]
    try:
        message = json.loads(body).get("error", {}).get("message") or detail
    except (json.JSONDecodeError, AttributeError, TypeError):
        message = detail
    if status in (401, 403):
        return AIError("invalid_key", f"Ollama rejected the API key. {message}".strip())
    if status == 402:
        return AIError("invalid_model", f"Ollama: {message or 'this model is not in your plan.'}")
    if status == 404:
        return AIError("invalid_model", f"Ollama model not found. {message}".strip())
    if status == 429:
        return AIError("insufficient_balance", "Ollama rate limit reached. Please try again later.")
    if status >= 500:
        return AIError("server_error", f"Ollama service error ({status}). Please try again later.")
    return AIError("unknown", f"Ollama rejected the request ({status}){': ' + message if message else ''}")


class OllamaEngine:
    """Minimal chat client: text, streaming, vision, and JSON-mode completions."""

    def __init__(self, base_url: str, api_key: str, model: str, vision_model: str = ""):
        self.base_url = _normalise_base(base_url)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.vision_model = (vision_model or "").strip() or self.model

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(
        self,
        *,
        messages: list[dict],
        model: str,
        max_tokens: int | None,
        temperature: float | None,
        stream: bool,
        json_mode: bool,
    ) -> dict:
        payload: dict = {"model": model, "messages": messages, "stream": stream}
        if max_tokens:
            headroom = max(0, settings.ollama_token_headroom)
            payload["max_tokens"] = min(max_tokens + headroom, _MAX_TOKEN_CEILING)
        if temperature is not None:
            payload["temperature"] = temperature
        effort = (settings.ollama_reasoning_effort or "").strip().lower()
        if effort:
            payload["reasoning_effort"] = effort
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        model: str | None = None,
    ) -> str:
        """One non-streaming completion; returns the assistant text."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        target = model or self.model
        if not target:
            raise AIError("invalid_model", "No Ollama model configured. Set OLLAMA_MODEL.")

        payload = self._payload(
            messages=messages,
            model=target,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
            json_mode=json_mode,
        )
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await self._post(client, payload)
            text, finish = _read_message(response)
            if not text and finish == "length":
                # Reasoning ate the whole budget; give it room for an answer.
                payload["max_tokens"] = min(
                    (payload.get("max_tokens") or 0) * 3 or 1024, _MAX_TOKEN_CEILING
                )
                response = await self._post(client, payload)
                text, _ = _read_message(response)
            return text

    async def stream(
        self,
        *,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield assistant text deltas."""
        target = model or self.model
        if not target:
            raise AIError("invalid_model", "No Ollama model configured. Set OLLAMA_MODEL.")

        full: list[dict] = []
        if system:
            full.append({"role": "system", "content": system})
        full.extend(messages)

        payload = self._payload(
            messages=full,
            model=target,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            json_mode=False,
        )
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")
                        raise _classify(response.status_code, body)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk or chunk == "[DONE]":
                            continue
                        try:
                            event = json.loads(chunk)
                            delta = event["choices"][0].get("delta") or {}
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        text = delta.get("content")
                        if text:
                            yield text
            except httpx.TimeoutException as e:
                raise AIError("network_error", "The Ollama request timed out. Please try again.") from e
            except httpx.HTTPError as e:
                raise AIError("network_error", "Could not reach the Ollama server. Check OLLAMA_BASE_URL.") from e

    async def describe_image(
        self,
        *,
        prompt: str,
        image_data_url: str,
        max_tokens: int = 512,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        """Vision completion for an OpenAI-style data URL."""
        payload = {
            "model": model or self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            "stream": False,
            "max_tokens": min(max_tokens + max(0, settings.ollama_token_headroom), _MAX_TOKEN_CEILING),
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await self._post(client, payload)
        text, _ = _read_message(response)
        return text

    async def list_models(self) -> list[str]:
        """Model ids the server exposes (used for diagnostics)."""
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url, headers=self._headers())
        if response.status_code >= 400:
            raise _classify(response.status_code, response.text)
        try:
            return [row["id"] for row in response.json().get("data", [])]
        except (KeyError, TypeError, ValueError):
            return []

    async def _post(self, client: httpx.AsyncClient, payload: dict) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"
        try:
            response = await client.post(url, headers=self._headers(), json=payload)
            if response.status_code == 400 and (
                "response_format" in payload or "reasoning_effort" in payload
            ):
                # Older builds reject these optional fields; retry without them.
                logger.info("Ollama rejected optional fields; retrying without them")
                trimmed = {k: v for k, v in payload.items() if k not in ("response_format", "reasoning_effort")}
                response = await client.post(url, headers=self._headers(), json=trimmed)
        except httpx.TimeoutException as e:
            raise AIError("network_error", "The Ollama request timed out. Please try again.") from e
        except httpx.HTTPError as e:
            raise AIError("network_error", "Could not reach the Ollama server. Check OLLAMA_BASE_URL.") from e

        if response.status_code >= 400:
            raise _classify(response.status_code, response.text)
        return response


def _read_message(response: httpx.Response) -> tuple[str, str]:
    """Pull the assistant text and finish reason out of a completion response."""
    try:
        choice = response.json()["choices"][0]
        message = choice.get("message") or {}
        return (message.get("content") or "").strip(), choice.get("finish_reason") or ""
    except (KeyError, IndexError, TypeError, ValueError):
        logger.warning("Unexpected Ollama response shape: %s", response.text[:300])
        return "", ""
