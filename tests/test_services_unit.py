import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api import deps
from app.core.config import settings
from app.core import security
from app.models.conversation import Conversation
from app.models.message import MessageRole
from app.services.auth_service import AuthService
from app.services.inference_client import InferenceClient
from app.services.chat_service import ChatService
from app.repositories import user_repo, conversation_repo
from app.services.conversation_service import ConversationService


class DummySession:
    """Lightweight stand-in for AsyncSession."""

    def __init__(self) -> None:
        self.rollback_calls = 0

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None

    async def rollback(self):
        self.rollback_calls += 1
        return None


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(monkeypatch):
    def fake_decode(token):
        raise ValueError("bad token")

    monkeypatch.setattr(security, "decode_token", fake_decode)

    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(
            creds=HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid"),
            db=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_success(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com")

    def fake_decode(token):
        return {"sub": str(user.id)}

    async def fake_get_by_id(db, user_id):
        return user

    monkeypatch.setattr(security, "decode_token", fake_decode)
    monkeypatch.setattr(user_repo, "get_by_id", fake_get_by_id)

    fetched = await deps.get_current_user(
        creds=HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        db=None,  # type: ignore[arg-type]
    )
    assert fetched.email == user.email


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_session_generator(monkeypatch):
    async def fake_get_db():
        yield "session"

    monkeypatch.setattr(deps, "get_db", fake_get_db)
    gen = deps.get_db_session()
    assert await anext(gen) == "session"


def test_get_inference_client_singleton():
    inference = InferenceClient(base_url="http://test")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inference_client=inference)))
    assert deps.get_inference_client(request) is inference


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_service_register_conflict(monkeypatch):
    dummy_user = SimpleNamespace(id=uuid.uuid4(), email="exists@example.com")

    async def fake_get_by_email(session, email):
        return dummy_user

    monkeypatch.setattr(user_repo, "get_by_email", fake_get_by_email)
    service = AuthService(DummySession())

    with pytest.raises(HTTPException) as exc:
        await service.register_user(SimpleNamespace(email=dummy_user.email, password="x"))
    assert exc.value.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_service_register_success(monkeypatch):
    created_user = SimpleNamespace(id=uuid.uuid4(), email="new@example.com")

    async def fake_get_by_email(session, email):
        return None

    async def fake_create(session, email, password_hash):
        return created_user

    monkeypatch.setattr(user_repo, "get_by_email", fake_get_by_email)
    monkeypatch.setattr(user_repo, "create", fake_create)

    service = AuthService(DummySession())
    user = await service.register_user(SimpleNamespace(email=created_user.email, password="secret"))
    assert user is created_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_service_login_flow(monkeypatch):
    password = "secret123"
    hashed = security.get_password_hash(password)
    dummy_user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", password_hash=hashed)

    async def fake_get_by_email(session, email):
        return dummy_user

    monkeypatch.setattr(user_repo, "get_by_email", fake_get_by_email)
    service = AuthService(DummySession())

    token = await service.login(dummy_user.email, password)
    assert token.access_token

    with pytest.raises(HTTPException):
        await service.login(dummy_user.email, "wrong")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_service_not_found(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())

    async def fake_get_for_user(session, conversation_id, user_id):
        return None

    async def fake_delete_for_user(session, conversation_id, user_id):
        return 0

    monkeypatch.setattr(conversation_repo, "get_for_user", fake_get_for_user)
    monkeypatch.setattr(conversation_repo, "delete_for_user", fake_delete_for_user)

    service = ConversationService(DummySession(), user)

    with pytest.raises(HTTPException) as exc:
        await service.get_conversation(uuid.uuid4())
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await service.delete_conversation(uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_service_create_list_delete(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    created = SimpleNamespace(id=uuid.uuid4())

    async def fake_create(session, user_id, title):
        return created

    async def fake_list_for_user(session, user_id, limit, offset):
        return [created]

    async def fake_delete_for_user(session, conversation_id, user_id):
        return 1

    monkeypatch.setattr(conversation_repo, "create", fake_create)
    monkeypatch.setattr(conversation_repo, "list_for_user", fake_list_for_user)
    monkeypatch.setattr(conversation_repo, "delete_for_user", fake_delete_for_user)

    service = ConversationService(DummySession(), user)
    conv = await service.create_conversation()
    assert conv is created

    listed = await service.list_conversations()
    assert listed == [created]

    await service.delete_conversation(created.id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inference_client_stream_chat_mocked(monkeypatch):
    class DummyResponse:
        def __init__(self, lines):
            self._lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            for line in self._lines:
                yield line

        def raise_for_status(self):
            return None

    def fake_stream(method, url, json):
        assert method == "POST"
        assert url == "/v1/chat/completions"
        assert json["model"] == settings.inference_model
        assert json["messages"] == [{"role": "user", "content": "hi"}]
        assert json["stream"] is True
        return DummyResponse(["data: hello", "data: [DONE]"])

    client = InferenceClient(base_url="http://test")
    client._client.stream = fake_stream  # type: ignore[assignment]

    chunks = []
    async for chunk in client.stream_chat([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert chunks == ["data: hello", "data: [DONE]"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_service_rolls_back_on_assistant_persist_failure(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    conversation = Conversation(user_id=user.id, title="chat")
    conversation.id = uuid.uuid4()

    async def fake_get_redis_client():
        return None

    async def fake_create_message(session, **kwargs):
        if kwargs["role"] == MessageRole.ASSISTANT:
            raise RuntimeError("db failed")
        return SimpleNamespace(id=uuid.uuid4(), **kwargs)

    monkeypatch.setattr("app.services.chat_service.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("app.services.chat_service.message_repo.create", fake_create_message)

    service = ChatService(DummySession(), user, InferenceClient(base_url="http://test"))

    with pytest.raises(RuntimeError):
        await service.persist_assistant_response(conversation, "hello")

    assert service.session.rollback_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_service_cache_versioning_refreshes_history(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    session = DummySession()
    conversation = Conversation(user_id=user.id, title="chat")
    conversation.id = uuid.uuid4()

    class FakeRedis:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ex=None):
            self.data[key] = value

        async def incr(self, key):
            current = int(self.data.get(key, b"0"))
            current += 1
            self.data[key] = str(current).encode("utf-8")
            return current

    fake_redis = FakeRedis()
    history_batches = [
        [SimpleNamespace(role=MessageRole.USER, content="Hello")],
        [
            SimpleNamespace(role=MessageRole.USER, content="Hello"),
            SimpleNamespace(role=MessageRole.ASSISTANT, content="Hi"),
        ],
    ]

    async def fake_get_redis_client():
        return fake_redis

    async def fake_history(*args, **kwargs):
        return history_batches.pop(0)

    monkeypatch.setattr("app.services.chat_service.get_redis_client", fake_get_redis_client)
    monkeypatch.setattr("app.services.chat_service.get_recent_history", fake_history)

    service = ChatService(session, user, InferenceClient(base_url="http://test"))

    first_messages = await service._build_messages(conversation.id, 20)
    await service._bump_history_version(conversation.id)
    second_messages = await service._build_messages(conversation.id, 20)

    assert first_messages == [{"role": "user", "content": "Hello"}]
    assert second_messages == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]
