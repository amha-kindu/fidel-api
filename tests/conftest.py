
from typing import Optional
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session, get_inference_client
from app.core import cache
from app.core.rate_limit import limiter
from app.db import session as db_session_module
from app.main import app as fastapi_app
from app.repositories import conversation_repo, message_repo, user_repo
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message


class FakeInferenceClient:
    def __init__(self, chunks: Optional[list[str]] = None):
        self.chunks = chunks or [
            'data: {"choices":[{"delta":{"content":"hi"}}]}',
            "[DONE]",
        ]
        self.last_messages = None

    async def stream_chat(self, messages):
        self.last_messages = list(messages)
        for chunk in self.chunks:
            yield chunk


limiter.enabled = False


class DummySession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self):
        self.commit_calls += 1
        return None

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollback_calls += 1
        return None

    async def close(self):
        return None


class InMemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.users_by_id: dict[UUID, SimpleNamespace] = {}
        self.users_by_email: dict[str, SimpleNamespace] = {}
        self.conversations_by_id: dict[UUID, SimpleNamespace] = {}
        self.messages: list[SimpleNamespace] = []
        self._clock = datetime.now(timezone.utc)
        self._tick = 0

    def now(self) -> datetime:
        self._tick += 1
        return self._clock + timedelta(microseconds=self._tick)


STORE = InMemoryStore()


@pytest.fixture
def fake_inference_client() -> FakeInferenceClient:
    return FakeInferenceClient()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[DummySession, None]:
    yield DummySession()


@pytest_asyncio.fixture
async def client(
    db_session: DummySession, fake_inference_client: FakeInferenceClient
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[DummySession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db
    fastapi_app.dependency_overrides[get_inference_client] = lambda: fake_inference_client

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def fake_data_layer(monkeypatch, request):
    STORE.reset()

    async def fake_get_redis_client():
        return None

    async def fake_get_db():
        yield DummySession()

    async def fake_get_by_email(session, email):
        return STORE.users_by_email.get(email)

    async def fake_get_by_id(session, user_id):
        return STORE.users_by_id.get(user_id)

    async def fake_create_user(session, email, password_hash):
        user = User(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            created_at=STORE.now(),
        )
        STORE.users_by_id[user.id] = user
        STORE.users_by_email[email] = user
        return user

    async def fake_create_conversation(session, user_id, title=None):
        now = STORE.now()
        conv = Conversation(
            id=uuid4(),
            user_id=user_id,
            title=title,
            last_message=None,
            created_at=now,
            updated_at=now,
        )
        STORE.conversations_by_id[conv.id] = conv
        return conv

    async def fake_update_conversation(session, conversation_id, user_id, title=None, last_message=None):
        conv = STORE.conversations_by_id.get(conversation_id)
        if not conv or conv.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        conv.title = title
        conv.last_message = last_message
        conv.updated_at = STORE.now()
        return conv

    async def fake_list_conversations(session, user_id, limit=20, offset=0):
        items = [c for c in STORE.conversations_by_id.values() if c.user_id == user_id]
        items.sort(key=lambda c: c.created_at, reverse=True)
        return items[offset:offset + limit]

    async def fake_get_conversation(session, conversation_id, user_id):
        conv = STORE.conversations_by_id.get(conversation_id)
        if conv and conv.user_id == user_id:
            return conv
        return None

    async def fake_delete_conversation(session, conversation_id, user_id):
        conv = STORE.conversations_by_id.get(conversation_id)
        if not conv or conv.user_id != user_id:
            return 0
        STORE.conversations_by_id.pop(conversation_id, None)
        STORE.messages = [m for m in STORE.messages if m.conversation_id != conversation_id]
        return 1

    async def fake_count_conversations(session, user_id):
        return len([c for c in STORE.conversations_by_id.values() if c.user_id == user_id])

    async def fake_create_message(session, *, conversation_id, role, content, token_count=None, metadata=None):
        msg = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
            extra=metadata,
            created_at=STORE.now(),
        )
        STORE.messages.append(msg)
        return msg

    async def fake_bulk_create(session, messages):
        for msg in messages:
            if getattr(msg, "id", None) is None:
                msg.id = uuid4()
            if getattr(msg, "created_at", None) is None:
                msg.created_at = STORE.now()
        STORE.messages.extend(list(messages))

    async def fake_list_messages(session, conversation_id, limit=20, offset=0):
        items = [m for m in STORE.messages if m.conversation_id == conversation_id]
        items.sort(key=lambda m: m.created_at, reverse=True)
        items = items[offset:offset + limit]
        return list(reversed(items))

    async def fake_get_last_message(session, conversation_id, role=None):
        items = [m for m in STORE.messages if m.conversation_id == conversation_id]
        if role is not None:
            items = [m for m in items if m.role == role]
        if not items:
            return None
        return max(items, key=lambda m: m.created_at)

    async def fake_count_messages(session, conversation_id):
        return len([m for m in STORE.messages if m.conversation_id == conversation_id])

    monkeypatch.setattr(cache, "get_redis_client", fake_get_redis_client)
    cache._redis_client = None
    monkeypatch.setattr(db_session_module, "get_db", fake_get_db)

    if not request.node.get_closest_marker("repo_unit"):
        monkeypatch.setattr(user_repo, "get_by_email", fake_get_by_email)
        monkeypatch.setattr(user_repo, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(user_repo, "create", fake_create_user)

        monkeypatch.setattr(conversation_repo, "create", fake_create_conversation)
        monkeypatch.setattr(conversation_repo, "update", fake_update_conversation)
        monkeypatch.setattr(conversation_repo, "list_for_user", fake_list_conversations)
        monkeypatch.setattr(conversation_repo, "get_for_user", fake_get_conversation)
        monkeypatch.setattr(conversation_repo, "delete_for_user", fake_delete_conversation)
        monkeypatch.setattr(conversation_repo, "count_for_user", fake_count_conversations)

        monkeypatch.setattr(message_repo, "create", fake_create_message)
        monkeypatch.setattr(message_repo, "bulk_create", fake_bulk_create)
        monkeypatch.setattr(message_repo, "list_for_conversation", fake_list_messages)
        monkeypatch.setattr(message_repo, "get_last_message", fake_get_last_message)
        monkeypatch.setattr(message_repo, "count_for_conversation", fake_count_messages)

    yield
