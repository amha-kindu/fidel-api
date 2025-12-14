from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import message_repo


async def get_recent_history(
    session: AsyncSession, conversation_id: UUID, limit: int = 20
):
    """Return last N messages in chronological order for context."""
    return await message_repo.list_for_conversation(session, conversation_id, limit=limit)
