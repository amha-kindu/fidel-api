from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.models.message import MessageRole
from app.repositories import message_repo
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


@pytest.mark.asyncio(loop_scope="session")
async def test_chat_stream_creates_conversation_and_persists_messages(
    client: AsyncClient, db_session
):
    _, token = await register_and_login(client)

    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "Hello"},
        headers=auth_header(token),
    ) as resp:
        assert resp.status_code == HTTPStatus.OK
        lines = [line async for line in resp.aiter_lines() if line]

    assert resp.headers.get("x-conversation-id")
    conv_id = UUID(resp.headers["x-conversation-id"])
    assert any("data: hi" in line for line in lines)

    messages = await message_repo.list_for_conversation(db_session, conv_id, limit=10)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "Hello"
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[1].content == "hi"


@pytest.mark.asyncio(loop_scope="session")
async def test_chat_stream_reuses_conversation(client: AsyncClient, db_session):
    _, token = await register_and_login(client)
    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "First"},
        headers=auth_header(token),
    ) as resp1:
        await resp1.aread()
    conv_id = resp1.headers["x-conversation-id"]

    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "Second", "conversation_id": conv_id},
        headers=auth_header(token),
    ) as resp2:
        await resp2.aread()

    messages = await message_repo.list_for_conversation(db_session, UUID(conv_id), limit=10)
    user_messages = [m for m in messages if m.role == MessageRole.USER]
    assert len(user_messages) == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_chat_stream_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/chat/stream", json={"message": "Hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio(loop_scope="session")
async def test_chat_stream_aggregates_chunks(client: AsyncClient, db_session, fake_inference_client: FakeInferenceClient):
    fake_inference_client.chunks = ["data: hello ", "data: world", "[DONE]"]
    _, token = await register_and_login(client)

    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
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
async def test_chat_stream_respects_history_limit(client: AsyncClient, db_session, fake_inference_client: FakeInferenceClient):
    fake_inference_client.chunks = ["data: ok", "[DONE]"]
    _, token = await register_and_login(client)

    # create conversation and seed messages
    create_resp = await client.post(
        "/api/v1/conversations",
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
        "/api/v1/chat/stream",
        json={"message": "New message", "conversation_id": conv_id, "max_history": 1},
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
async def test_chat_stream_rejects_unknown_conversation(client: AsyncClient):
    _, token = await register_and_login(client)
    bad_id = str(uuid4())
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Hi", "conversation_id": bad_id},
        headers=auth_header(token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
