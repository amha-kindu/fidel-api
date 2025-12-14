from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncIterator

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.repositories import user_repo
from app.schemas.auth import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = security.decode_token(token)
        token_data = TokenPayload(**payload)
        user_id = UUID(token_data.sub)
    except Exception as exc:  # includes ValueError, ValidationError
        raise credentials_exception from exc

    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    return user
