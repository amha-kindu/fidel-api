import pytest

from app.db import session as db_session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_yields_session():
    gen = db_session.get_db()
    db = await anext(gen)
    assert db is not None
    await db.close()
