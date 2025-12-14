from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.api.v1.router import router as api_router
from app.core.config import settings

app = FastAPI(
    title="Fidel API",
    default_response_class=ORJSONResponse,
)


@app.get("/health", tags=["health"])
async def healthcheck():
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)
