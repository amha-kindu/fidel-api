from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.db.registry import *  # noqa: F403
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.router import router as api_router
from app.core.errors import register_exception_handlers

setup_logging()
app = FastAPI(
    title="Fidel API",
    default_response_class=ORJSONResponse,
)
register_exception_handlers(app)


@app.get("/health", tags=["health"])
async def healthcheck():
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)
