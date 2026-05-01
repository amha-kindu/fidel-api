<div align="center">
  <h1>Fidel API</h1>
  <p><strong>Real-time FastAPI backend for conversational applications</strong></p>
  <p>
    Authentication, conversation management, SSE chat streaming, Redis-backed caching,
    rate limiting, and an inference proxy layer in a single service.
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/FastAPI-0.124-009688?logo=fastapi&logoColor=white" alt="FastAPI 0.124">
    <img src="https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white" alt="Pydantic v2">
    <img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy 2.0">
    <img src="https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Redis-Cache%20%26%20Rate%20Limits-DC382D?logo=redis&logoColor=white" alt="Redis">
    <img src="https://img.shields.io/badge/OpenAPI-Docs-6BA539?logo=openapiinitiative&logoColor=white" alt="OpenAPI">
    <img src="https://img.shields.io/badge/Coverage-90%25%2B-brightgreen" alt="Coverage 90%+">
  </p>
</div>

## Overview

Fidel API is a production-oriented FastAPI backend for ChatGPT-style experiences. It exposes authenticated APIs for users, conversations, and message history, then proxies streaming chat completions from an inference backend over Server-Sent Events.

The codebase is structured around clear application layers:

- `api` for HTTP routes and dependency wiring
- `services` for orchestration and business logic
- `repositories` for data access
- `models` and `schemas` for persistence and contract boundaries
- `core` for configuration, security, logging, caching, and rate limiting

## Why This Project

- JWT-based authentication with Argon2 password hashing
- Conversation and message persistence with async SQLAlchemy and Postgres
- Streaming chat via `POST /api/v1/chats/stream`
- Optional conversation reuse through the `id` query parameter
- Redis-backed history caching and SlowAPI rate limiting
- Structured JSON logging with `structlog`
- OpenAPI documentation out of the box
- Test suite with coverage enforcement

## Stack At A Glance

| Layer | Technology |
| --- | --- |
| API | FastAPI, ORJSON responses, OpenAPI |
| Validation | Pydantic v2, pydantic-settings |
| Database | PostgreSQL, SQLAlchemy 2.x, Alembic |
| Caching | Redis |
| Auth | JWT, `python-jose`, Argon2 |
| Streaming | SSE via `sse-starlette` |
| HTTP Client | `httpx` |
| Testing | `pytest`, `pytest-asyncio`, coverage |

## API Surface

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create a user account |
| `POST` | `/api/v1/auth/login` | Authenticate and return a bearer token |
| `GET` | `/api/v1/users/me` | Fetch the current authenticated user |
| `POST` | `/api/v1/chats` | Create a conversation |
| `GET` | `/api/v1/chats` | List conversations |
| `GET` | `/api/v1/chats/{id}` | Return conversation message history |
| `DELETE` | `/api/v1/chats/{id}` | Delete a conversation |
| `POST` | `/api/v1/chats/stream?id=<conversation_id>` | Stream an assistant reply and optionally reuse a conversation |
| `GET` | `/health` | Basic healthcheck |

Authentication uses:

```http
Authorization: Bearer <token>
```

Interactive docs are available at:

- `/docs` for Swagger UI
- `/redoc` for ReDoc
- `/openapi.json` for the raw spec

## Quick Start

### Prerequisites

- Python `3.12+`
- Docker and Docker Compose
- PostgreSQL and Redis if running outside Docker

### Environment Setup

Create a local environment file from the example:

```bash
cp .env.example .env
```

Important settings:

- `DATABASE_URL`
- `TEST_DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `INFERENCE_BASE_URL`
- `RATE_LIMIT_STORAGE_URI`

If you want in-memory rate limiting in development or tests, set:

```env
RATE_LIMIT_STORAGE_URI=memory://
```

## Run With Docker

Bring the stack up from the repo root:

```bash
docker-compose up --build
```

Default local endpoints:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Adminer: `http://localhost:8080`

## Local Development

Install dependencies in your preferred Python environment, then run:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

When running locally, make sure Postgres and Redis are reachable from the values in `.env`.

## Project Structure

```text
app/
  api/              # FastAPI routes and dependency wiring
  core/             # config, logging, security, caching, rate limiting
  db/               # session management and Alembic migrations
  models/           # SQLAlchemy ORM models
  repositories/     # persistence helpers
  schemas/          # request/response schemas
  services/         # business logic and orchestration
  main.py           # app creation and lifespan wiring
tests/              # unit and API tests
scripts/            # utility scripts such as OpenAPI export
```

## Testing

Run the full test suite:

```bash
pytest
```

The repository enforces:

- strict pytest markers
- HTML coverage output
- minimum coverage threshold of `90%`

## OpenAPI Export

To export a static OpenAPI document from the repo root, ensure the repo root is on `PYTHONPATH` and run:

```bash
PYTHONPATH=. python scripts/export_openapi.py
```

This writes `openapi.json` at the project root.

## Production Notes

- Run behind a reverse proxy or ingress that terminates TLS
- Use a strong `JWT_SECRET`
- Point `DATABASE_URL` and `REDIS_URL` at production-grade services
- Use Redis for both history caching and distributed rate limiting
- Keep the inference backend reachable and monitored separately from the API

## Development Focus

This codebase is optimized for:

- preserving a stable API surface
- keeping service and repository responsibilities clear
- making streaming chat behavior testable
- supporting iterative backend cleanup without breaking clients
