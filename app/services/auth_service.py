from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import user_repo
from app.schemas.auth import Token
from app.schemas.user import UserCreate
from app.core import security
from app.models.user import User


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register_user(self, payload: UserCreate) -> User:
        existing = await user_repo.get_by_email(self.session, payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        hashed = security.get_password_hash(payload.password)
        return await user_repo.create(self.session, email=payload.email, password_hash=hashed)

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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = security.create_access_token({"sub": str(user.id)})
        return Token(access_token=access_token)
