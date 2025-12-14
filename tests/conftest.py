import asyncio
import os
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db_session
from app.core.config import settings
from app.db.base import Base
from app.main import app as fastapi_app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_url() -> str:
    return os.getenv("TEST_DATABASE_URL", settings.database_url)


@pytest.fixture(scope="session")
async def engine(db_url: str) -> AsyncEngine:
    engine = create_async_engine(db_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncSession:
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db
    async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
        yield client
    fastapi_app.dependency_overrides = {}
