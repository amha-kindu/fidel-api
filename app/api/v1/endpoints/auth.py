from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService
from app.core.rate_limit import limiter
from app.core.config import settings

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.auth_rate_limit)
async def register_user(
    request: Request,  # required for rate limit keying
    payload: UserCreate,
    db: AsyncSession = Depends(get_db_session),
) -> UserRead:
    service = AuthService(db)
    user = await service.register_user(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
@limiter.limit(settings.auth_rate_limit)
async def login(
    request: Request,  # required for rate limit keying
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Token:
    service = AuthService(db)
    token = await service.login(payload.email, payload.password)
    return token
