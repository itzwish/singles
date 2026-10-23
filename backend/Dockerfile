# ============================================================
# Easy Single — backend image (FastAPI + Uvicorn)
# Build context is the repository root:
#   docker build -f backend/Dockerfile -t easy-single-backend .
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so the layer caches across code changes.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Application code
COPY backend /app/backend

# Run from backend/ so alembic.ini and ../.env resolve the way they do locally.
WORKDIR /app/backend

# Avatars are written here; mount a volume if you want them to survive deploys.
RUN mkdir -p /app/backend/static/avatars

EXPOSE 8000

# Bound to 0.0.0.0 so the Fly proxy can reach the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]