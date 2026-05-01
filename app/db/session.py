from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


engine: Optional[AsyncEngine] = None
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine() -> AsyncEngine:
    global engine, AsyncSessionLocal
    if engine is None:
        engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine


def get_engine() -> AsyncEngine:
    return init_engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    init_engine()
    if AsyncSessionLocal is None:
        raise RuntimeError("Session factory is not initialized")
    return AsyncSessionLocal


async def close_engine() -> None:
    global engine, AsyncSessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
