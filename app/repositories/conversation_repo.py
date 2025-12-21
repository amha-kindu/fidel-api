from uuid import UUID
from typing import Optional, cast

from fastapi import HTTPException, status
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


async def create(
    session: AsyncSession,
    user_id: UUID,
    title: Optional[str] = None
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation

async def update(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    title: Optional[str] = None,
    last_message: Optional[str] = None
) -> Conversation:
    conversation = await get_for_user(session, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    conversation.title = title
    conversation.last_message = last_message
    await session.commit()
    await session.refresh(conversation)
    return conversation

async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return cast(list[Conversation], result.scalars().all())


async def get_for_user(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID
) -> Optional[Conversation]:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def delete_for_user(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID
) -> int:
    result = await session.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        .returning(Conversation.id)
    )
    deleted_ids = result.scalars().all()
    await session.commit()
    return len(deleted_ids)


async def count_for_user(
    session: AsyncSession,
    user_id: UUID
):
    result = await session.execute(
        select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
    )
    return int(result.scalar_one() or 0)
