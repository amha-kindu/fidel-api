from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationBase(BaseModel):
    title: str | None = None


class ConversationCreate(ConversationBase):
    pass


class ConversationRead(ConversationBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
