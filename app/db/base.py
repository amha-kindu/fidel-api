from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# IMPORTANT: import models so Alembic sees them
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
