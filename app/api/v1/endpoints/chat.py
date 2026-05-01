from uuid import UUID
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, Depends, Request, status, Query

from app.models.user import User
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.chat import ChatRequest
from app.repositories import message_repo
from app.services.inference_client import InferenceClient
from app.schemas.message import MessageListResponse, MessageRead
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.api.deps import get_current_user, get_db_session, get_inference_client
from app.schemas.conversation import ConversationCreate, ConversationListResponse, ConversationRead

router = APIRouter()


@router.post("/stream")
@limiter.limit(settings.chat_rate_limit)
async def chat_stream(
    request: Request,  # required for rate limit keying
    payload: ChatRequest,
    id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    inference: InferenceClient = Depends(get_inference_client),
    current_user: User = Depends(get_current_user),
) -> EventSourceResponse:
    chat_service = ChatService(db, current_user, inference)
    stream_context = await chat_service.start_chat_stream(payload, id)
    return EventSourceResponse(
        stream_context.events,
        headers=stream_context.headers,
        status_code=status.HTTP_200_OK,
    )

@router.get("", response_model=ConversationListResponse)
@limiter.limit(settings.rate_limit_default)
async def get_conversations(
    request: Request,  # required for rate limit keying
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    service = ConversationService(db, current_user)
    conversations = await service.list_conversations(limit=limit, offset=offset)
    total = await service.count_for_user()
    return ConversationListResponse(
        items=[ConversationRead.model_validate(c) for c in conversations],
        total = total
    )

@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_default)
async def create_conversation(
    request: Request,  # required for rate limit keying
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationRead:
    service = ConversationService(db, current_user)
    conv = await service.create_conversation(payload)
    return ConversationRead.model_validate(conv)


@router.get("/{conversation_id}", response_model=MessageListResponse)
@limiter.limit(settings.rate_limit_default)
async def get_chat_history(
    request: Request,  # required for rate limit keying
    conversation_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    service = ConversationService(db, current_user)
    await service.get_conversation(conversation_id)
    messages = await message_repo.list_for_conversation(db, conversation_id, limit=limit, offset=offset)
    total = await message_repo.count_for_conversation(db, conversation_id)
    return MessageListResponse(
        items=[MessageRead.model_validate(m) for m in messages],
        total=total,
    )

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.rate_limit_default)
async def delete_conversation(
    request: Request,  # required for rate limit keying
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    service = ConversationService(db, current_user)
    await service.delete_conversation(conversation_id)
