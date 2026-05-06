FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.3.4 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps (psycopg2-binary doesn't need build tools, but keep curl for health/debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Copy only dependency files first (better caching)
COPY pyproject.toml poetry.lock* /app/

# Install dependencies
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Copy application code
COPY . /app

# Optional: create non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# Start: run migrations, then run server
# NOTE: keep this simple; in k8s you'd run migrations as a separate job
CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
