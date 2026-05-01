from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User
from app.repositories import conversation_repo, message_repo, user_repo


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, scalars=None, scalar=None, scalar_one=None):
        self._scalars = scalars or []
        self._scalar = scalar
        self._scalar_one = scalar_one if scalar_one is not None else scalar

    def scalars(self):
        return FakeScalars(self._scalars)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar_one


class FakeSession:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.add_all_items = None
        self.commit_called = 0
        self.flush_called = 0
        self.refresh_called = []
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if self.results:
            return self.results.pop(0)
        return FakeResult()

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, items):
        self.add_all_items = list(items)

    async def flush(self):
        self.flush_called += 1

    async def commit(self):
        self.commit_called += 1

    async def refresh(self, obj):
        self.refresh_called.append(obj)


@pytest.mark.repo_unit
@pytest.mark.asyncio
async def test_user_repo_get_and_create():
    user = User(id=uuid4(), email="a@example.com", password_hash="x", created_at=datetime.now(timezone.utc))
    session = FakeSession(results=[FakeResult(scalar=user), FakeResult(scalar=None)])

    fetched = await user_repo.get_by_email(session, "a@example.com")
    assert fetched is user

    missing = await user_repo.get_by_id(session, uuid4())
    assert missing is None

    created = await user_repo.create(session, email="b@example.com", password_hash="secret")
    assert isinstance(created, User)
    assert created.email == "b@example.com"
    assert session.added
    assert session.flush_called == 1


@pytest.mark.repo_unit
@pytest.mark.asyncio
async def test_conversation_repo_crud_and_count(monkeypatch):
    now = datetime.now(timezone.utc)
    conv = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        title="Old",
        last_message=None,
        created_at=now,
        updated_at=now,
    )
    session = FakeSession(
        results=[
            FakeResult(scalars=[conv]),
            FakeResult(scalar=conv),
            FakeResult(scalars=[uuid4(), uuid4()]),
            FakeResult(scalar_one=3),
        ]
    )

    created = await conversation_repo.create(session, user_id=uuid4(), title="New")
    assert isinstance(created, Conversation)
    assert created.title == "New"

    listed = await conversation_repo.list_for_user(session, user_id=conv.user_id, limit=10, offset=0)
    assert listed == [conv]

    fetched = await conversation_repo.get_for_user(session, conversation_id=conv.id, user_id=conv.user_id)
    assert fetched is conv

    deleted = await conversation_repo.delete_for_user(session, conversation_id=uuid4(), user_id=conv.user_id)
    assert deleted == 2

    count = await conversation_repo.count_for_user(session, user_id=conv.user_id)
    assert count == 3

    async def fake_get_for_user(session, conversation_id, user_id):
        return None

    monkeypatch.setattr(conversation_repo, "get_for_user", fake_get_for_user)
    missing = await conversation_repo.update(session, conversation_id=uuid4(), user_id=uuid4(), title="x")
    assert missing is None


@pytest.mark.repo_unit
@pytest.mark.asyncio
async def test_conversation_repo_update_success(monkeypatch):
    now = datetime.now(timezone.utc)
    conv = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        title="Old",
        last_message=None,
        created_at=now,
        updated_at=now,
    )
    session = FakeSession()

    async def fake_get_for_user(session, conversation_id, user_id):
        return conv

    monkeypatch.setattr(conversation_repo, "get_for_user", fake_get_for_user)
    updated = await conversation_repo.update(
        session, conversation_id=conv.id, user_id=conv.user_id, title="New", last_message="Hi"
    )
    assert updated.title == "New"
    assert updated.last_message == "Hi"


@pytest.mark.repo_unit
@pytest.mark.asyncio
async def test_message_repo_helpers():
    msg1 = Message(
        id=uuid4(),
        conversation_id=uuid4(),
        role=MessageRole.USER,
        content="first",
        created_at=datetime.now(timezone.utc),
    )
    msg2 = Message(
        id=uuid4(),
        conversation_id=msg1.conversation_id,
        role=MessageRole.ASSISTANT,
        content="second",
        created_at=datetime.now(timezone.utc),
    )
    session = FakeSession(
        results=[
            FakeResult(scalars=[msg2, msg1]),
            FakeResult(scalar=msg2),
            FakeResult(scalar_one=2),
        ]
    )

    created = await message_repo.create(
        session,
        conversation_id=msg1.conversation_id,
        role=MessageRole.USER,
        content="hello",
    )
    assert isinstance(created, Message)
    assert created.content == "hello"
    assert session.flush_called == 1

    await message_repo.bulk_create(session, [msg1, msg2])
    assert session.add_all_items == [msg1, msg2]
    assert session.flush_called == 2

    listed = await message_repo.list_for_conversation(session, msg1.conversation_id, limit=5, offset=0)
    assert listed == [msg1, msg2]

    last = await message_repo.get_last_message(session, msg1.conversation_id, role=MessageRole.ASSISTANT)
    assert last is msg2

    count = await message_repo.count_for_conversation(session, msg1.conversation_id)
    assert count == 2
