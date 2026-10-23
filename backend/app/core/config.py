"""Application configuration — loaded from environment variables via Pydantic Settings."""

import uuid

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

# Shared system guest account backing passwordless login. The ID is a fixed
# all-zero UUID so the row can be created up front and satisfy FK constraints.
GUEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
GUEST_EMAIL = "guest@easy-single.local"

# How many recent messages are replayed to the model each turn. Keeping this
# small bounds input tokens; older context is covered by the rolling summary.
HISTORY_WINDOW_SIZE = 8

# Appended to every chat system instruction. Caps output without making the
# character terse when the user actually asks a question.
STYLE_DIRECTIVE = (
    "Keep responses conversational, warm, and dynamic "
    "(1 to 3 sentences unless answering a direct query)"
)


class Settings(BaseSettings):
    # Which backend answers chat and background AI work. "gemini" uses the
    # Google SDK; "ollama" talks to any OpenAI-compatible Ollama endpoint
    # (Ollama Cloud or a local daemon). Users who supply their own key in the
    # profile are always served by Gemini with that key.
    ai_provider: str = "gemini"
    # When the primary provider fails (quota, bad key, outage) or a model is
    # unavailable, retry on the other provider and the next model in the list.
    ai_fallback_enabled: bool = True
    # Comma-separated extra models tried in order when the configured one is
    # missing or outside the account's plan.
    gemini_fallback_models: str = ""
    ollama_fallback_models: str = ""

    # Ollama (Ollama Cloud: https://ollama.com/v1, local: http://localhost:11434/v1)
    ollama_base_url: str = "https://ollama.com/v1"
    ollama_api_key: str = ""
    ollama_model: str = "gpt-oss:120b"
    # Separate vision model (must support images, e.g. qwen3-vl or gemma3).
    # Empty falls back to ollama_model.
    ollama_vision_model: str = ""
    # Reasoning models burn the output budget on hidden thinking, so the cap is
    # padded and the effort lowered. Empty disables the field.
    ollama_reasoning_effort: str = "low"
    ollama_token_headroom: int = 160

    # Google Gemini API
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    # Gemini 1.5 and 2.5 are retired for new keys; 3.x flash is the current
    # general-purpose model.
    gemini_model: str = "gemini-3.5-flash"
    # Reasoning models spend output tokens on hidden "thinking" before writing
    # a reply. The conversational calls below are capped at a few hundred
    # tokens, so the level is kept minimal there or the reply comes back empty.
    # One of: minimal, low, medium, high (empty = model default).
    gemini_thinking_level: str = "minimal"

    # Conversational calls are budgeted tightly.
    gemini_max_token: int = 300
    gemini_temperature: float = 0.7

    # Structured JSON generation (persona profiles, chat-log analysis) needs far
    # more room than a chat reply — a 300-token cap truncates the JSON.
    gemini_max_token_structured: int = 2000

    # Vision (image understanding) — same Gemini key, separate model toggle
    vision_enabled: bool = True
    vision_model: str = "gemini-3.5-flash"

    # Request pacing. The free tier allows 20 requests per day per model and
    # only a few per minute; unpaced, one chat turn could spend two requests and
    # the next turns came straight back as 429. Set the budget to the limit of
    # your own key (0 disables the guard).
    gemini_min_interval_seconds: float = 4.0
    gemini_daily_budget: int = 20
    # Emotion is inferred locally by default. Turning this on spends one extra
    # Gemini request on every chat turn.
    gemini_llm_emotion: bool = False

    # Database. Fly Postgres hands out `postgres://…`; both that and a bare
    # path are accepted. See app.core.database.normalize_database_url.
    database_url: str = ""

    redis_url: str = ""

    # Upstash Redis — REST-based, works on Vercel/serverless runtimes
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # JWT — JWT_SECRET is the documented name; SECRET_KEY stays supported.
    secret_key: str = Field(
        default="dev-secret-change-in-production",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Clerk. The browser authenticates against Clerk and sends the Clerk
    # session token to the API, which verifies it against the instance JWKS.
    # The frontend API host can be derived from the publishable key, so it is
    # only read from the environment when the key is not available.
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    clerk_frontend_api: str = ""
    # Comma separated list of origins allowed to request tokens. Mirrors the
    # instance's "Authorized parties" setting.
    clerk_authorized_parties: str = ""
    # Optional API audience. When the instance issues tokens with an `aud`
    # claim, it must contain this value.
    clerk_api_audience: str = ""
    # Clock-skew tolerance, in seconds, when validating the `nbf` and `exp`
    # claims of a Clerk session token. Clerk's servers and the API host drift
    # apart by a few seconds, and a token that is "not yet valid" by a couple
    # of seconds must not be rejected.
    clerk_token_leeway_seconds: int = 60
    # Signing secret from the Clerk dashboard (webhooks -> signing secret).
    clerk_webhook_signing_secret: str = ""
    # How the API accepts credentials:
    #   dual   — Clerk session tokens and legacy JWTs are both accepted
    #   clerk  — Clerk session tokens only
    #   legacy — legacy JWTs only (the pre-Clerk behaviour)
    auth_mode: str = "dual"
    # Lifetime of the short-lived ticket the browser exchanges for a WS/SSE
    # connection, in seconds.
    ws_ticket_ttl_seconds: int = 60

    # App
    app_port: int = 8000
    debug: bool = False
    # ALLOWED_ORIGINS is the documented name; CORS_ORIGINS stays supported.
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )

    # Quotas
    free_daily_messages: int = 50
    premium_daily_messages: int = 500

    # CAPTCHA storage: "redis" or "memory" (memory is the default fallback when
    # no Redis instance is reachable, which keeps serverless deploys working).
    captcha_backend: str = "memory"

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


settings = Settings()