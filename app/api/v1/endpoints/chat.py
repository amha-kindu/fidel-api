import orjson
import structlog
from uuid import UUID
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, get_inference_client
from app.models.message import MessageRole
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.schemas.conversation import ConversationCreate
from app.schemas.message import MessageListResponse, MessageRead
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
    try:
        conversation = await conversation_service.get_conversation(payload.conversation_id)
    except HTTPException:
        conversation = await conversation_service.create_conversation(
            ConversationCreate(title=payload.message[:255])
        )

    # Persist user message immediately
    user_message = await message_repo.create(
        db,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=payload.message,
    )
    await _invalidate_history_cache(conversation.id)

    messages = await _build_messages(db, conversation.id, payload.max_history + 1)      # +1 for the new user message

    async def event_generator() -> AsyncIterator[dict]:
        assistant_parts: list[str] = []
        async for chunk in inference.stream_chat(messages):
            data = chunk.removeprefix("data: ")
            if data.strip() == "[DONE]":
                break

            data = orjson.loads(data)
            data["previous_id"] = str(user_message.id)
            data["chat_info"] = {
                "id": str(conversation.id),
                "title": conversation.title
            }
            content = data["choices"][0]["delta"].get("content", None)
            if content:
                assistant_parts.append(content)
            yield {"event": "message", "data": orjson.dumps(data).decode("utf-8")}

        if assistant_parts:
            await message_repo.create(
                db,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content="".join(assistant_parts),
            )
            logger.info(
                "chat.assistant.saved",
                conversation_id=str(conversation.id),
                user_id=str(current_user.id),
            )

            await conversation_service.update_conversation(
                conversation.id,
                ConversationCreate(
                    title=conversation.title,
                    last_message = "".join(assistant_parts)[:255]
                )
            )
            logger.info(
                "conversation.updated",
                conversation_id=str(conversation.id),
                user_id=str(current_user.id),
            )

        logger.info(
            "chat.stream.end",
            conversation_id=str(conversation.id),
            user_id=str(current_user.id),
        )

    headers = {"X-Conversation-Id": str(conversation.id)}
    logger.info(
        "chat.stream.start",
        conversation_id=str(conversation.id),
        user_id=str(current_user.id),
        has_existing=bool(payload.conversation_id),
    )
    return EventSourceResponse(event_generator(), headers=headers, status_code=status.HTTP_200_OK)

@router.get("/{conversation_id}", response_model=MessageListResponse)
@limiter.limit(settings.chat_rate_limit)
async def get_chat_history(
    request: Request,  # required for rate limit keying
    conversation_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    # Ensure conversation belongs to user by fetching last message; less overhead than loading whole convo
    messages = await message_repo.list_for_conversation(db, conversation_id, limit=limit, offset=offset)
    total = await message_repo.count_for_conversation(db, conversation_id)
    return MessageListResponse(
        items=[MessageRead.model_validate(m) for m in messages],
        total=total,
    )
