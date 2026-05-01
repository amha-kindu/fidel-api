from uuid import UUID
from typing import Optional

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.user import User
from app.repositories import conversation_repo
from app.schemas.conversation import ConversationCreate


logger = structlog.get_logger(__name__)


class ConversationService:
    def __init__(self, session: AsyncSession, user: User):
        self.session = session
        self.user = user

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _commit_and_refresh(self, *entities: object) -> None:
        await self._commit()
        for entity in entities:
            await self.session.refresh(entity)

    async def create_conversation(self, payload: Optional[ConversationCreate] = None) -> Conversation:
        title = payload.title if payload else None
        conversation = await conversation_repo.create(
            self.session, user_id=self.user.id, title=title
        )
        await self._commit_and_refresh(conversation)
        logger.info(
            "conversation.created", conversation_id=str(conversation.id), user_id=str(self.user.id)
        )
        return conversation

    async def list_conversations(self, limit: int = 20, offset: int = 0) -> list[Conversation]:
        return await conversation_repo.list_for_user(
            self.session, user_id=self.user.id, limit=limit, offset=offset
        )

    async def count_for_user(self) -> int:
        return await conversation_repo.count_for_user(
            self.session,
            user_id=self.user.id
        )

    async def get_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = await conversation_repo.get_for_user(
            self.session, conversation_id=conversation_id, user_id=self.user.id
        )
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return conversation

    async def delete_conversation(self, conversation_id: UUID) -> None:
        deleted = await conversation_repo.delete_for_user(
            self.session, conversation_id=conversation_id, user_id=self.user.id
        )
        if deleted == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        await self._commit()
        logger.info(
            "conversation.deleted", conversation_id=str(conversation_id), user_id=str(self.user.id)
        )

    async def update_conversation(self, conversation_id: UUID, payload: ConversationCreate) -> Conversation:
        title = payload.title if payload else None
        last_message = payload.last_message if payload else None
        conversation = await conversation_repo.update(
            self.session, conversation_id=conversation_id, user_id=self.user.id, title=title, last_message=last_message
        )
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        await self._commit_and_refresh(conversation)
        logger.info(
            "conversation.updated", conversation_id=str(conversation.id), user_id=str(self.user.id)
        )
        return conversation
