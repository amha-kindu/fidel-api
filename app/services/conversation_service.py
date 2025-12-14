from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import conversation_repo
from app.schemas.conversation import ConversationCreate


class ConversationService:
    def __init__(self, session: AsyncSession, user: User):
        self.session = session
        self.user = user

    async def create_conversation(self, payload: ConversationCreate | None = None):
        title = payload.title if payload else None
        return await conversation_repo.create(self.session, user_id=self.user.id, title=title)

    async def list_conversations(self, limit: int = 20, offset: int = 0):
        return await conversation_repo.list_for_user(
            self.session, user_id=self.user.id, limit=limit, offset=offset
        )

    async def get_conversation(self, conversation_id: UUID):
        conversation = await conversation_repo.get_for_user(
            self.session, conversation_id=conversation_id, user_id=self.user.id
        )
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return conversation

    async def delete_conversation(self, conversation_id: UUID):
        deleted = await conversation_repo.delete_for_user(
            self.session, conversation_id=conversation_id, user_id=self.user.id
        )
        if deleted == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
