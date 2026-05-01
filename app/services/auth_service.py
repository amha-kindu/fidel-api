from typing import Optional

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models.user import User
from app.schemas.auth import Token
from app.repositories import user_repo
from app.schemas.user import UserCreate


logger = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _commit_and_refresh(self, *entities: object) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        for entity in entities:
            await self.session.refresh(entity)

    async def register_user(self, payload: UserCreate) -> User:
        existing = await user_repo.get_by_email(self.session, payload.email)
        if existing:
            logger.info("auth.register.email_conflict", email=payload.email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        hashed = security.get_password_hash(payload.password)
        user = await user_repo.create(self.session, email=payload.email, password_hash=hashed)
        await self._commit_and_refresh(user)
        logger.info("auth.register.success", user_id=str(user.id), email=user.email)
        return user

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = await user_repo.get_by_email(self.session, email)
        if not user:
            return None
        if not security.verify_password(password, user.password_hash):
            return None
        return user

    async def login(self, email: str, password: str) -> Token:
        user = await self.authenticate_user(email, password)
        if not user:
            logger.info("auth.login.failed", email=email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = security.create_access_token({"sub": str(user.id)})
        logger.info("auth.login.success", user_id=str(user.id), email=user.email)
        return Token(access_token=access_token)
