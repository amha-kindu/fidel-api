import uuid

import pytest

from app.models.message import Message, MessageRole
from app.repositories import user_repo
from app.repositories import conversation_repo, message_repo


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_conversation_repo_crud(db_session):
    user = await user_repo.create(
        db_session, email=f"user-{uuid.uuid4()}@example.com", password_hash="x"
    )
    user_id = user.id
    conv = await conversation_repo.create(db_session, user_id=user_id, title="Repo test")
    assert conv.user_id == user_id

    listed = await conversation_repo.list_for_user(db_session, user_id=user_id, limit=10, offset=0)
    assert listed and listed[0].id == conv.id

    fetched = await conversation_repo.get_for_user(db_session, conversation_id=conv.id, user_id=user_id)
    assert fetched is not None

    deleted = await conversation_repo.delete_for_user(db_session, conversation_id=conv.id, user_id=user_id)
    assert deleted == 1

    missing = await conversation_repo.delete_for_user(
        db_session, conversation_id=uuid.uuid4(), user_id=user_id
    )
    assert missing == 0


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_message_repo_helpers(db_session):
    user = await user_repo.create(
        db_session, email=f"user-{uuid.uuid4()}@example.com", password_hash="x"
    )
    conv = await conversation_repo.create(db_session, user_id=user.id, title="Msg test")

    # bulk create
    bulk_messages = [
        Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content="Bulk 1",
        ),
        Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content="Bulk 2",
        ),
    ]
    await message_repo.bulk_create(db_session, bulk_messages)

    await message_repo.create(
        db_session, conversation_id=conv.id, role=MessageRole.USER, content="First"
    )
    await message_repo.create(
        db_session, conversation_id=conv.id, role=MessageRole.ASSISTANT, content="Second"
    )

    history = await message_repo.list_for_conversation(db_session, conv.id, limit=5)
    # history ordered ascending by created_at/id
    assert [m.content for m in history][:2] == ["Bulk 1", "Bulk 2"]

    last_user = await message_repo.get_last_message(db_session, conv.id, role=MessageRole.USER)
    assert last_user is not None and last_user.content == "First"

    last_any = await message_repo.get_last_message(db_session, conv.id)
    assert last_any is not None and last_any.content == "Second"
