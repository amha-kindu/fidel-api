import orjson
import structlog
from uuid import UUID
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request, status
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
from app.core.rate_limit import limiter
from app.core.config import settings
from app.core.cache import get_redis_client
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _build_messages(
    db: AsyncSession, conversation_id: UUID, max_history: int
) -> list[dict]:
    cache = await get_redis_client()
    cache_key = f"history:{conversation_id}:{max_history}"
    if cache:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return orjson.loads(cached)
        except RedisError:
            pass

    history = await get_recent_history(db, conversation_id, limit=max_history)
    messages = [{"role": m.role.value, "content": m.content} for m in history]

    if cache:
        try:
            await cache.set(cache_key, orjson.dumps(messages), ex=settings.history_cache_ttl_s)
        except RedisError:
            pass
    return messages


async def _invalidate_history_cache(conversation_id: UUID) -> None:
    cache = await get_redis_client()
    if not cache:
        return
    try:
        keys = await cache.keys(f"history:{conversation_id}:*")
        if keys:
            await cache.delete(*keys)
    except RedisError:
        pass


@router.post("/stream")
@limiter.limit(settings.chat_rate_limit)
async def chat_stream(
    request: Request,  # required for rate limit keying
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

    # Persist user message immediately
    await message_repo.create(
        db,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=payload.message,
    )
    await _invalidate_history_cache(conversation_id)

    messages = await _build_messages(db, conversation_id, payload.max_history + 1)      # +1 for the new user message

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
            logger.info(
                "chat.assistant.saved",
                conversation_id=str(conversation_id),
                user_id=str(current_user.id),
            )

    headers = {"X-Conversation-Id": str(conversation_id)}
    logger.info(
        "chat.stream.start",
        conversation_id=str(conversation_id),
        user_id=str(current_user.id),
        has_existing=bool(payload.conversation_id),
    )
    return EventSourceResponse(event_generator(), headers=headers, status_code=status.HTTP_200_OK)
