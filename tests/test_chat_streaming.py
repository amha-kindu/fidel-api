from http import HTTPStatus
import json
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.core import cache
from app.services import chat_service as chat_service_module
from app.repositories import message_repo
from app.models.message import MessageRole
from tests.conftest import FakeInferenceClient


async def register_and_login(client: AsyncClient):
    email = f"user-{uuid4()}@example.com"
    password = "secret123"
    register_resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register_resp.status_code == HTTPStatus.CREATED
    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == HTTPStatus.OK
    token = login_resp.json()["access_token"]
    return email, token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def stream_path(conversation_id: UUID | str | None = None) -> str:
    if conversation_id is None:
        return "/api/v1/chats/stream"
    return f"/api/v1/chats/stream?id={conversation_id}"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_creates_conversation_and_persists_messages(
    client: AsyncClient, db_session
):
    _, token = await register_and_login(client)
    new_conv_id = uuid4()

    async with client.stream(
        "POST",
        stream_path(new_conv_id),
        json={"message": "Hello"},
        headers=auth_header(token),
    ) as resp:
        assert resp.status_code == HTTPStatus.OK
        lines = [line async for line in resp.aiter_lines() if line]

    assert resp.headers.get("x-conversation-id")
    conv_id = UUID(resp.headers["x-conversation-id"])
    assert any('"content":"hi"' in line for line in lines)

    messages = await message_repo.list_for_conversation(db_session, conv_id, limit=10)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "Hello"
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[1].content == "hi"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_reuses_conversation(client: AsyncClient, db_session):
    _, token = await register_and_login(client)
    new_conv_id = uuid4()
    async with client.stream(
        "POST",
        stream_path(new_conv_id),
        json={"message": "First"},
        headers=auth_header(token),
    ) as resp1:
        await resp1.aread()
    conv_id = resp1.headers["x-conversation-id"]

    async with client.stream(
        "POST",
        stream_path(conv_id),
        json={"message": "Second"},
        headers=auth_header(token),
    ) as resp2:
        await resp2.aread()

    messages = await message_repo.list_for_conversation(db_session, UUID(conv_id), limit=10)
    user_messages = [m for m in messages if m.role == MessageRole.USER]
    assert len(user_messages) == 2


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_requires_auth(client: AsyncClient):
    resp = await client.post(stream_path(uuid4()), json={"message": "Hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_aggregates_chunks(client: AsyncClient, db_session, fake_inference_client: FakeInferenceClient):
    fake_inference_client.chunks = [
        'data: {"choices":[{"delta":{"content":"hello "}}]}',
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        "[DONE]",
    ]
    _, token = await register_and_login(client)
    new_conv_id = uuid4()

    async with client.stream(
        "POST",
        stream_path(new_conv_id),
        json={"message": "Hi there"},
        headers=auth_header(token),
    ) as resp:
        await resp.aread()

    conv_id = UUID(resp.headers["x-conversation-id"])
    messages = await message_repo.list_for_conversation(db_session, conv_id, limit=10)
    assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
    assert assistant_msgs
    assert assistant_msgs[-1].content == "hello world"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_respects_history_limit(client: AsyncClient, db_session, fake_inference_client: FakeInferenceClient):
    fake_inference_client.chunks = [
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "[DONE]",
    ]
    _, token = await register_and_login(client)

    # create conversation and seed messages
    create_resp = await client.post(
        "/api/v1/chats",
        json={"title": "History test"},
        headers=auth_header(token),
    )
    conv_id = create_resp.json()["id"]

    await message_repo.create(
        db_session, conversation_id=UUID(conv_id), role=MessageRole.USER, content="Old 1"
    )
    await message_repo.create(
        db_session, conversation_id=UUID(conv_id), role=MessageRole.ASSISTANT, content="Old 2"
    )

    async with client.stream(
        "POST",
        stream_path(conv_id),
        json={"message": "New message", "max_history": 1},
        headers=auth_header(token),
    ) as resp:
        await resp.aread()

    # Only last assistant message plus new user message should be sent to backend
    assert fake_inference_client.last_messages is not None
    roles = [m["role"] for m in fake_inference_client.last_messages]
    contents = [m["content"] for m in fake_inference_client.last_messages]
    assert roles == ["assistant", "user"]
    assert contents == ["Old 2", "New message"]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_creates_conversation_for_unknown_id(client: AsyncClient):
    _, token = await register_and_login(client)
    bad_id = str(uuid4())
    async with client.stream(
        "POST",
        stream_path(bad_id),
        json={"message": "Hi"},
        headers=auth_header(token),
    ) as resp:
        await resp.aread()
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers.get("x-conversation-id")
    assert resp.headers["x-conversation-id"] != bad_id


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_preserves_response_shape(client: AsyncClient):
    _, token = await register_and_login(client)

    async with client.stream(
        "POST",
        stream_path(),
        json={"message": "Shape check"},
        headers=auth_header(token),
    ) as resp:
        assert resp.status_code == HTTPStatus.OK
        lines = [line async for line in resp.aiter_lines() if line]

    assert resp.headers.get("x-conversation-id")
    data_lines = [line for line in lines if line.startswith("data: ")]
    assert data_lines
    payload = json.loads(data_lines[0].removeprefix("data: "))
    assert payload["previous_id"]
    assert payload["chat_info"]["id"] == resp.headers["x-conversation-id"]
    assert "title" in payload["chat_info"]
    assert payload["choices"][0]["delta"]["content"] == "hi"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_ignores_malformed_chunks(
    client: AsyncClient,
    db_session,
    fake_inference_client: FakeInferenceClient,
):
    fake_inference_client.chunks = [
        "event: message",
        'data: {"choices":[{"delta":{"content":"hello "}}]}',
        "data: {not-json}",
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        "[DONE]",
    ]
    _, token = await register_and_login(client)

    async with client.stream(
        "POST",
        stream_path(uuid4()),
        json={"message": "Hi there"},
        headers=auth_header(token),
    ) as resp:
        lines = [line async for line in resp.aiter_lines() if line]

    conv_id = UUID(resp.headers["x-conversation-id"])
    messages = await message_repo.list_for_conversation(db_session, conv_id, limit=10)
    assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
    assert assistant_msgs[-1].content == "hello world"
    assert any(line.startswith("data: ") for line in lines)


class InMemoryRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: bytes, ex: int | None = None):
        self.data[key] = value

    async def incr(self, key: str):
        current = int(self.data.get(key, b"0"))
        current += 1
        self.data[key] = str(current).encode("utf-8")
        return current


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_chat_stream_cache_versioning_includes_latest_assistant_message(
    client: AsyncClient,
    fake_inference_client: FakeInferenceClient,
    monkeypatch,
):
    fake_redis = InMemoryRedis()

    async def fake_get_redis_client():
        return fake_redis

    monkeypatch.setattr(cache, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(chat_service_module, "get_redis_client", fake_get_redis_client)

    _, token = await register_and_login(client)
    fake_inference_client.chunks = [
        'data: {"choices":[{"delta":{"content":"first reply"}}]}',
        "[DONE]",
    ]
    async with client.stream(
        "POST",
        stream_path(uuid4()),
        json={"message": "First"},
        headers=auth_header(token),
    ) as resp1:
        await resp1.aread()

    conv_id = resp1.headers["x-conversation-id"]
    fake_inference_client.chunks = [
        'data: {"choices":[{"delta":{"content":"second reply"}}]}',
        "[DONE]",
    ]
    async with client.stream(
        "POST",
        stream_path(conv_id),
        json={"message": "Second"},
        headers=auth_header(token),
    ) as resp2:
        await resp2.aread()

    assert resp2.status_code == HTTPStatus.OK
    assert fake_inference_client.last_messages is not None
    roles = [message["role"] for message in fake_inference_client.last_messages]
    contents = [message["content"] for message in fake_inference_client.last_messages]
    assert roles == ["user", "assistant", "user"]
    assert contents == ["First", "first reply", "Second"]
