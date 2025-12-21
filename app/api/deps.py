from uuid import UUID
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security
from app.db.session import get_db
from app.models.user import User
from app.repositories import user_repo
from app.schemas.auth import TokenPayload
from app.services.inference_client import InferenceClient, inference_client

bearer = HTTPBearer(auto_error=True)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer), db: AsyncSession = Depends(get_db_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = security.decode_token(creds.credentials)
        token_data = TokenPayload(**payload)
        user_id = UUID(token_data.sub)
    except Exception as exc:  # includes ValueError, ValidationError
        raise credentials_exception from exc

    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise credentials_exception
    return user


def get_inference_client() -> InferenceClient:
    return inference_client
