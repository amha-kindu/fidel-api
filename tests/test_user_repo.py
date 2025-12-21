import uuid

import pytest

from app.core import security
from app.models.user import User
from app.repositories import user_repo


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.integration
async def test_user_repo_crud(db_session):
    email = f"user-{uuid.uuid4()}@example.com"
    hashed = security.get_password_hash("secret123")

    user = await user_repo.create(db_session, email=email, password_hash=hashed)
    assert isinstance(user, User)

    fetched = await user_repo.get_by_email(db_session, email)
    assert fetched is not None
    assert fetched.id == user.id

    fetched_by_id = await user_repo.get_by_id(db_session, user.id)
    assert fetched_by_id is not None
    assert fetched_by_id.email == email
