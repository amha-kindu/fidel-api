
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db_session, get_inference_client
from app.core.config import settings
from app.db.base import Base
from app.main import app as fastapi_app


class FakeInferenceClient:
    def __init__(self, chunks: list[str] | None = None):
        self.chunks = chunks or ["data: hi", "[DONE]"]
        self.last_messages = None

    async def stream_chat(self, messages):
        self.last_messages = list(messages)
        for chunk in self.chunks:
            yield chunk


@pytest.fixture(scope="session")
def db_url() -> str:
    return settings.test_database_url


@pytest.fixture
def fake_inference_client() -> FakeInferenceClient:
    return FakeInferenceClient()


@pytest_asyncio.fixture(scope="session")
async def engine(db_url: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        db_url,
        future=True,
        pool_pre_ping=True,
    )

    # Create schema once
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop schema once (after all tests)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    # One connection per test
    async with engine.connect() as connection:
        # Begin outer transaction
        trans = await connection.begin()

        SessionLocal = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        async with SessionLocal() as session:
            yield session

        # Rollback changes after test
        await trans.rollback()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, fake_inference_client: FakeInferenceClient
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db
    fastapi_app.dependency_overrides[get_inference_client] = lambda: fake_inference_client

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()
