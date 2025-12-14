from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, get_inference_client
from app.models.message import MessageRole
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.conversation_service import ConversationService
from app.services.history_service import get_recent_history
from app.services.inference_client import InferenceClient
from app.repositories import message_repo

router = APIRouter()


async def _build_messages(
    db: AsyncSession, conversation_id: UUID, max_history: int
) -> list[dict]:
    history = await get_recent_history(db, conversation_id, limit=max_history)
    return [{"role": m.role.value, "content": m.content} for m in history]


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
    inference: InferenceClient = Depends(get_inference_client),
    current_user: User = Depends(get_current_user),
):
    conversation_service = ConversationService(db, current_user)

    if payload.conversation_id:
        conversation = await conversation_service.get_conversation(payload.conversation_id)
        conversation_id = conversation.id
    else:
        conversation = await conversation_service.create_conversation()
        conversation_id = conversation.id

    messages = await _build_messages(db, conversation_id, payload.max_history)
    messages.append({"role": "user", "content": payload.message})

    # Persist user message immediately
    await message_repo.create(
        db,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=payload.message,
    )

    async def event_generator() -> AsyncIterator[dict]:
        assistant_parts: list[str] = []
        async for chunk in inference.stream_chat(messages):
            data = chunk.removeprefix("data: ")
            if data.strip() == "[DONE]":
                break
            assistant_parts.append(data)
            yield {"event": "message", "data": data}

        if assistant_parts:
            await message_repo.create(
                db,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content="".join(assistant_parts),
            )

    headers = {"X-Conversation-Id": str(conversation_id)}
    return EventSourceResponse(event_generator(), headers=headers, status_code=status.HTTP_200_OK)
