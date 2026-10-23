<p align="center">
  <h1 align="center">💕 Easy Single</h1>
  <p align="center"><strong>Easy Single — a full-stack AI chat companion</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Vue-3.5-green?logo=vuedotjs" alt="Vue">
  <img src="https://img.shields.io/badge/FastAPI-0.115-teal?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Gemini-8A4FFF?logo=googlegemini" alt="Gemini">
  <img src="https://img.shields.io/badge/Vercel-ready-black?logo=vercel" alt="Vercel">
  <img src="https://img.shields.io/badge/Docker-ready-blue?logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="License">
</p>

---

## ✨ Features

- 💬 **Multi-character AI chat** — streamed responses, custom character personas
- 🖼️ **Multimodal image understanding** — send a photo and the character responds to it
- 🧠 **Long-term memory** — automatic summarisation, importance scoring, and recall
- 🎭 **Emotion detection** — the character's tone adapts to how you're feeling
- 👤 **User accounts** — register/login, JWT auth, per-user Gemini API key
- 📝 **Persistent history** — SQLite or PostgreSQL
- 📊 **Admin dashboard** — user management, system configuration, chat audit log
- ☁️ **One-command Vercel or Fly.io deploy** — serverless-ready

## 🚀 Quick start

### 1. Clone the repo

```bash
git clone https://github.com/314159ctl/virtual-gf.git
cd virtual-gf
```

> The clone URL still points at the original repository name. Rename it in
> GitHub settings if you fork — nothing in the code depends on the URL.

### 2. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini key from https://aistudio.google.com/apikey:

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-1.5-flash
JWT_SECRET=change-me-to-a-random-string
```

The app defaults to a local SQLite database (`sqlite:///./dev.db` when
`DATABASE_URL` is empty), so nothing else is required to get running. Users can
also supply their **own** Gemini API key from the profile screen — the key is
encrypted at rest with Fernet.

> **Environment variables**
>
> | Variable | Purpose |
> |---|---|
> | `GEMINI_API_KEY` | Gemini credentials |
> | `DATABASE_URL` | Connection string; Fly's `postgres://` is auto-rewritten |
> | `JWT_SECRET` | Token signing key |
> | `ALLOWED_ORIGINS` | CORS origins for the frontend |
>
> `SECRET_KEY` and `CORS_ORIGINS` are still accepted as aliases.

### 3. Pick how you want to run it

#### Deploy to Vercel (zero server config)

Push the repo to GitHub, import it into Vercel, and add the environment
variables. That's it — `vercel.json` already routes `/api/*` to the FastAPI
backend and everything else to the Vue SPA.

Set at minimum:

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini key |
| `SECRET_KEY` | a long random string |
| `DATABASE_URL` | a hosted Postgres URL (see below) |
| `CORS_ORIGINS` | your Vercel domain |

<details>
<summary>Database on Vercel</summary>

Vercel's filesystem is read-only, so the SQLite fallback is **not persistent**.
Use any hosted Postgres and paste the URL as-is — the driver is inferred:

```
DATABASE_URL=postgresql://user:password@host:5432/easy_single
```

`app/db/session.py` rewrites `postgres://` and bare `sqlite://` forms into the
correct async SQLAlchemy driver automatically.

> **WebSockets:** Vercel serverless functions do not support WebSocket upgrades.
> The frontend detects this and falls back to Server-Sent Events automatically
> (`POST /api/v1/chat/stream`), so chat still streams token by token. If you
> deploy somewhere that supports WebSockets (Docker, Fly.io, Railway), the
> WebSocket path at `/ws/chat/{id}` is used automatically instead.
</details>

#### Deploy to Fly.io (backend container)

`fly.toml` and `backend/Dockerfile` are ready to go:

```bash
fly launch --no-deploy                  # create the app
fly postgres create                     # creates DATABASE_URL
fly volumes create easy_single_data 1   # only if you stay on SQLite
fly secrets set GEMINI_API_KEY=... SECRET_KEY=... CORS_ORIGINS=https://your-frontend.vercel.app
fly deploy
```

The image is `python:3.12-slim`, exposes `8000`, and runs
`uvicorn app.main:app --host 0.0.0.0 --port 8000`. Fly hands out `postgres://`
URLs; `app/core/database.py` rewrites those to `postgresql://` at startup, so
`fly postgres attach` needs no config on your side.

The frontend is built separately (Vercel, Netlify, …). Set `ALLOWED_ORIGINS` to
that origin, or `ALLOWED_ORIGINS=*` to auto-allow the deployment's own host and any
preview subdomain of it.

<details>
<summary>Backend + frontend on different platforms</summary>

| | Where | What |
|---|---|---|
| Frontend | Vercel | `vercel.json` builds `frontend/` and routes `/api/*` at the backend |
| Backend | Fly.io | `fly.toml` + `backend/Dockerfile` |

Point the frontend at the Fly hostname, or keep both on Fly and drop
`vercel.json` from the equation. Either way the only cross-origin surface is
`ALLOWED_ORIGINS`.
</details>

<details>
<summary>Docker (recommended for self-hosting)</summary>

```bash
# Full production stack (backend + frontend + Nginx + HTTPS)
docker compose -f docker-compose.prod.yml up -d
```

#### Local development

**Backend (FastAPI):**
```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173` (app) or `http://localhost:8000` (API docs).

## 📁 Project structure

```
easy-single/
├── api/index.py               # Vercel serverless entrypoint (Mangum)
├── vercel.json                # Vercel build + rewrite configuration
├── fly.toml                   # Fly.io deployment configuration
├── backend/
│   ├── Dockerfile             # python:3.12-slim + Uvicorn on :8000
│   ├── app/
│   │   ├── api/v1/            # REST + WebSocket routes
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic validation models
│   │   ├── services/          # business logic (Gemini engine, chat pipeline, audit, memory)
│   │   └── core/              # config, database, security, seed data, dependencies
│   └── alembic/               # database migrations
├── frontend/                  # Vue 3 frontend (TypeScript)
│   └── src/
│       ├── views/             # page components
│       ├── components/        # shared components
│       ├── composables/       # composition helpers
│       └── stores/            # Pinia state
├── characters/                # character definitions (JSON)
├── DESIGN.md                  # UI design specification
└── docker-compose.prod.yml    # production orchestration
```

## 💬 Chat engine

Gemini `gemini-1.5-flash` via the `google-genai` SDK, tuned for cost and latency:

| Setting | Value | Why |
|---|---|---|
| Sliding window | last **8** messages | Bounds input tokens; older turns are covered by the rolling summary |
| `max_output_tokens` | **300** | Chat replies are 1–3 sentences |
| `temperature` | **0.7** | Warm but not repetitive |
| System instruction | ends with *"Keep responses conversational, warm, and dynamic (1 to 3 sentences unless answering a direct query)"* | Stops the model padding replies |

Structured JSON calls (persona generation, chat-log analysis) use a separate
`gemini_max_token_structured = 2000` budget — a 300-token cap truncates their
JSON and breaks the feature.

Photos are passed straight to Gemini as `Part.from_bytes` payloads; the
response is described by a vision call and injected as context.

## 🔐 Chat auditing

Every turn is mirrored into the `chat_messages` table in the background, and
administrators can page through it:

```
GET /api/v1/admin/chat-logs?page=1&page_size=50&role=user&search=hello
GET /api/v1/admin/chat-logs/stats
```

The endpoint requires an admin JWT — `get_admin_user` rejects anonymous (401),
unknown/disabled (401), and non-admin (403) callers. Rows carry `created_at`
(timezone-aware UTC) and are returned joined to `users` and `characters` so you
get `user_email`, `username`, and `character_name`.

`character_id` is a plain string rather than a foreign key, so a record
survives deletion of the character or account that produced it.

> Audit writes are fire-and-forget background tasks. On platforms that reclaim
> containers between requests (Vercel serverless) a row can be lost mid-write —
> deploy to Fly.io or Docker when the trail must be complete.

## 🛠️ Tech stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy (async) |
| **Frontend** | Vue 3, TypeScript, Vite, Pinia |
| **AI** | Google Gemini (`google-genai`) — chat + vision |
| **Database** | PostgreSQL (production) / SQLite (local) |
| **Deployment** | Vercel serverless (frontend/API), Fly.io (backend container), Docker, Nginx |
| **Auth** | JWT + bcrypt |

## 🔌 API overview

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/guest` | Passwordless guest login |
| `POST` | `/api/v1/auth/register` · `/login` · `/refresh` | Account flows |
| `GET` | `/api/v1/characters` | List characters (seeds starters on first call) |
| `POST` | `/api/v1/characters/generate` | AI-generate a personality profile |
| `POST` | `/api/v1/characters/analyze-chat` | Build a profile from a chat transcript |
| `POST` | `/api/v1/chat/stream` | SSE streaming chat (serverless-friendly) |
| `WS` | `/ws/chat/{conversation_id}` | WebSocket streaming chat (primary) |
| `GET` | `/api/v1/memories` · `POST /consolidate` | Long-term memory |
| `POST` | `/api/v1/users/me/test-api` | Verify a user's Gemini key |
| `GET` | `/api/v1/admin/stats` · `/settings` | Admin dashboard |
| `GET` | `/api/v1/admin/chat-logs` | Paginated chat audit log (admin only) |
| `GET` | `/api/v1/admin/chat-logs/stats` | Audit totals by role |

Interactive docs: `http://localhost:8000/docs`

## 🤝 Contributing

Issues and pull requests are welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md).

1. Fork this repository
2. Create your feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a pull request

## 📄 License

MIT License — see the [LICENSE](./LICENSE) file.

---

<p align="center">Made with 💕 by <a href="https://github.com/314159ctl">314159ctl</a></p>