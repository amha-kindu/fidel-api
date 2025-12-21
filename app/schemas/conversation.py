from uuid import UUID
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationBase(BaseModel):
    title: Optional[str] = None
    last_message: Optional[str] = None


class ConversationCreate(ConversationBase):
    pass


class ConversationRead(ConversationBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ConversationListResponse(BaseModel):
    items: list[ConversationRead]
    total: int
