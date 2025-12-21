from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.models.user import User
from app.schemas.conversation import ConversationCreate, ConversationListResponse, ConversationRead
from app.services.conversation_service import ConversationService

router = APIRouter()


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationRead:
    service = ConversationService(db, current_user)
    conv = await service.create_conversation(payload)
    return ConversationRead.model_validate(conv)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
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


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationRead:
    service = ConversationService(db, current_user)
    conv = await service.get_conversation(conversation_id)
    return ConversationRead.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    service = ConversationService(db, current_user)
    await service.delete_conversation(conversation_id)
