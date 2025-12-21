from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.message import MessageRole


class MessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    items: list[MessageRead]
    total: int
