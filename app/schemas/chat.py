from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[UUID] = None
    message: str
    max_history: int = Field(default=20, ge=0, le=100)


class ChatStreamChunk(BaseModel):
    data: str
