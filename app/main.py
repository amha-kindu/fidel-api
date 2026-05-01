from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from slowapi.errors import RateLimitExceeded
from fastapi.openapi.utils import get_openapi
from slowapi.middleware import SlowAPIMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse

from app.db.registry import *  # noqa: F403
from app.core.config import settings
from app.core.cache import close_redis_client, init_redis_client
from app.core.rate_limit import limiter
from app.core.logging import setup_logging
from app.db.session import close_engine, init_engine
from app.api.v1.router import router as api_router
from app.core.errors import register_exception_handlers
from app.services.inference_client import InferenceClient

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engine()
    await init_redis_client()
    app.state.inference_client = InferenceClient()
    try:
        yield
    finally:
        await app.state.inference_client.aclose()
        await close_redis_client()
        await close_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fidel API",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "auth", "description": "Registration and login via JWT bearer tokens."},
            {"name": "users", "description": "User profile operations for the current user."},
            {"name": "conversations", "description": "Create, list, fetch, and delete chat conversations."},
            {"name": "chat", "description": "Send chat messages and stream assistant responses."},
            {"name": "health", "description": "Liveness checks."},
        ],
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        # Configure bearer auth scheme for Swagger/ReDoc
        openapi_schema["components"] = openapi_schema.get("components", {})
        security_schemes = openapi_schema["components"].get("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        openapi_schema["components"]["securitySchemes"] = security_schemes
        openapi_schema["security"] = [{"BearerAuth": []}]
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[assignment]
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        {"detail": "Rate limit exceeded"},
        status_code=429,
    )


@app.get("/health", tags=["health"])
async def healthcheck():
    return {"status": "ok"}
