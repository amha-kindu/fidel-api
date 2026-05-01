from types import SimpleNamespace

import pytest

from app.core import cache
from app.db import session as db_session
from app import main as main_module


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_lifecycle_helpers(monkeypatch):
    cache._redis_client = None
    fake_redis = SimpleNamespace(closed=False)

    async def fake_ping():
        return True

    async def fake_aclose():
        fake_redis.closed = True

    fake_redis.ping = fake_ping
    fake_redis.aclose = fake_aclose

    monkeypatch.setattr(cache.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(cache, "get_redis_client", cache.init_redis_client)

    client = await cache.init_redis_client()
    same_client = await cache.get_redis_client()
    await cache.close_redis_client()

    assert client is fake_redis
    assert same_client is fake_redis
    assert fake_redis.closed is True
    assert cache._redis_client is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_db_session_engine_lifecycle(monkeypatch):
    db_session.engine = None
    db_session.AsyncSessionLocal = None
    fake_engine = SimpleNamespace(disposed=False)

    async def fake_dispose():
        fake_engine.disposed = True

    fake_engine.dispose = fake_dispose

    def fake_session_factory(engine, **kwargs):
        return lambda: "session-factory"

    monkeypatch.setattr(db_session, "create_async_engine", lambda *args, **kwargs: fake_engine)
    monkeypatch.setattr(db_session, "async_sessionmaker", fake_session_factory)

    engine = db_session.init_engine()
    same_engine = db_session.get_engine()
    session_factory = db_session.get_session_factory()
    await db_session.close_engine()

    assert engine is fake_engine
    assert same_engine is fake_engine
    assert session_factory() == "session-factory"
    assert fake_engine.disposed is True
    assert db_session.engine is None
    assert db_session.AsyncSessionLocal is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_lifespan_initializes_and_closes_resources(monkeypatch):
    calls: list[str] = []

    class FakeInferenceClient:
        async def aclose(self):
            calls.append("inference.close")

    def fake_init_engine():
        calls.append("engine.init")

    async def fake_init_redis_client():
        calls.append("redis.init")
        return None

    async def fake_close_redis_client():
        calls.append("redis.close")

    async def fake_close_engine():
        calls.append("engine.close")

    monkeypatch.setattr(main_module, "init_engine", fake_init_engine)
    monkeypatch.setattr(main_module, "init_redis_client", fake_init_redis_client)
    monkeypatch.setattr(main_module, "close_redis_client", fake_close_redis_client)
    monkeypatch.setattr(main_module, "close_engine", fake_close_engine)
    monkeypatch.setattr(main_module, "InferenceClient", FakeInferenceClient)

    app = SimpleNamespace(state=SimpleNamespace())

    async with main_module.lifespan(app):
        assert isinstance(app.state.inference_client, FakeInferenceClient)

    assert calls == ["engine.init", "redis.init", "inference.close", "redis.close", "engine.close"]


@pytest.mark.unit
def test_custom_openapi_includes_bearer_auth():
    openapi = main_module.app.openapi()
    assert "BearerAuth" in openapi["components"]["securitySchemes"]
    assert openapi["security"] == [{"BearerAuth": []}]
