from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole


async def create(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    role: MessageRole,
    content: str,
    token_count: int | None = None,
    metadata: dict | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        token_count=token_count,
        metadata=metadata,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def bulk_create(session: AsyncSession, messages: Iterable[Message]) -> None:
    session.add_all(list(messages))
    await session.commit()


async def list_for_conversation(
    session: AsyncSession, conversation_id: UUID, limit: int = 20, offset: int = 0
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def get_last_message(
    session: AsyncSession, conversation_id: UUID, role: MessageRole | None = None
) -> Optional[Message]:
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if role:
        stmt = stmt.where(Message.role == role)
    stmt = stmt.order_by(Message.created_at.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_for_conversation(session: AsyncSession, conversation_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    )
    return int(result.scalar_one() or 0)
