# Fidel API

FastAPI backend for a ChatGPT-like Next.js frontend. It provides user auth with JWT, conversation/message management, chat streaming proxy to an inference backend, Redis-backed caching, and rate limiting. Project uses async SQLAlchemy, Postgres, Alembic migrations, and Pydantic v2.

## Features
- FastAPI + ORJSON responses
- JWT auth (password hashing via passlib)
- Conversations/messages models with async SQLAlchemy & Postgres
- Streaming chat proxy endpoint (`/api/v1/chat/stream`) with history windowing
- Redis caching for message history and SlowAPI rate limiting
- Structured logging (structlog)
- OpenAPI docs: Swagger UI at `/docs`, ReDoc at `/redoc`, OpenAPI JSON at `/openapi.json`
- Test suite with pytest/pytest-asyncio and httpx

## Getting Started
### Prerequisites
- Docker and docker-compose
- Python 3.12+ (for local dev without Docker)

### Environment
Copy `.env.example` to `.env` and adjust as needed:
```bash
cp .env.example .env
```
Key variables:
- `DATABASE_URL` / `TEST_DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `INFERENCE_BASE_URL`
- `RATE_LIMIT_STORAGE_URI` (set to `memory://` to disable Redis in dev/tests)

### Run with Docker Compose
```bash
docker-compose up --build
```
Services:
- API: http://localhost:8000
- Postgres: localhost:5432
- Redis: localhost:6379
- Adminer: http://localhost:8080 (server: `db`, user/password from env)

API docs:
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

### Local Dev (without Docker)
1) Create venv & install deps:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt  # or `pip install .` if using pyproject extras
```
2) Start Postgres & Redis locally; ensure `DATABASE_URL`/`REDIS_URL` point to them.
3) Run migrations:
```bash
alembic upgrade head
```
4) Run server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Project Structure
```
app/
  api/              # FastAPI routers/endpoints
  core/             # config, logging, security, rate limiting, errors
  db/               # engine/session, migrations
  models/           # SQLAlchemy models
  repositories/     # data access helpers
  schemas/          # Pydantic schemas
  services/         # business logic, inference client, history
  main.py           # FastAPI app factory & wiring
tests/              # pytest suite (unit + integration)
scripts/export_openapi.py  # generate static OpenAPI json
```

## Key Endpoints (API v1)
- `POST /api/v1/auth/register` — create user
- `POST /api/v1/auth/login` — JWT bearer token
- `GET /api/v1/users/me` — current user
- `POST /api/v1/conversations` — create conversation
- `GET /api/v1/conversations` — list conversations
- `GET /api/v1/conversations/{id}` — fetch conversation
- `DELETE /api/v1/conversations/{id}` — delete conversation
- `POST /api/v1/chat/stream` — stream assistant reply (SSE proxy to inference backend)
- `GET /health` — healthcheck

Auth: Bearer token in `Authorization: Bearer <token>`. Swagger UI is preconfigured for HTTP bearer.

Rate limiting: SlowAPI with defaults from env (`RATE_LIMIT_STORAGE_URI`, per-route limits). Redis recommended for production.

## Running Tests
Use test database/Redis URLs (or `memory://` for limiter):
```bash
pytest
```
Coverage target is configured at 90% in `pytest.ini`.

## OpenAPI Export
Generate a static spec for frontend/CI:
```bash
python scripts/export_openapi.py
```
Outputs `openapi.json` at repo root.

## Production Notes
- Run behind a reverse proxy/ingress that terminates TLS.
- Set a strong `JWT_SECRET` and production DB/Redis credentials.
- Use Redis for rate limiting and history caching; set `RATE_LIMIT_STORAGE_URI` accordingly.
- Scale with multiple API replicas; keep DB pool and Redis accessible.
