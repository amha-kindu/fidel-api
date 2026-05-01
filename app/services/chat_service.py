from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import orjson
import structlog
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis_client
from app.core.config import settings
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User
from app.repositories import conversation_repo, message_repo
from app.schemas.chat import ChatRequest
from app.services.history_service import get_recent_history
from app.services.inference_client import InferenceClient


logger = structlog.get_logger(__name__)
_DONE_SENTINEL = object()


@dataclass(slots=True)
class ChatStreamContext:
    conversation: Conversation
    headers: dict[str, str]
    events: AsyncIterator[dict[str, str]]


class ChatService:
    def __init__(self, session: AsyncSession, user: User, inference: InferenceClient):
        self.session = session
        self.user = user
        self.inference = inference

    async def start_chat_stream(
        self,
        payload: ChatRequest,
        conversation_id: UUID | None,
    ) -> ChatStreamContext:
        conversation, has_existing = await self._get_or_create_conversation(
            conversation_id, payload.message[:255]
        )
        user_message = await self._persist_user_message(conversation.id, payload.message)
        messages = await self._build_messages(conversation.id, payload.max_history + 1)

        logger.info(
            "chat.stream.start",
            conversation_id=str(conversation.id),
            user_id=str(self.user.id),
            has_existing=has_existing,
        )
        return ChatStreamContext(
            conversation=conversation,
            headers={"X-Conversation-Id": str(conversation.id)},
            events=self._event_generator(conversation, user_message, messages),
        )

    async def persist_assistant_response(
        self,
        conversation: Conversation,
        assistant_content: str,
    ) -> Message:
        try:
            assistant_message = await message_repo.create(
                self.session,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
            )
            conversation.last_message = assistant_content[:255]
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception(
                "chat.assistant.persist_failed",
                conversation_id=str(conversation.id),
                user_id=str(self.user.id),
            )
            raise

        await self.session.refresh(assistant_message)
        await self.session.refresh(conversation)
        await self._bump_history_version(conversation.id)
        logger.info(
            "chat.assistant.saved",
            conversation_id=str(conversation.id),
            user_id=str(self.user.id),
        )
        logger.info(
            "conversation.updated",
            conversation_id=str(conversation.id),
            user_id=str(self.user.id),
        )
        return assistant_message

    async def _get_or_create_conversation(
        self,
        conversation_id: UUID | None,
        title: str,
    ) -> tuple[Conversation, bool]:
        if conversation_id is not None:
            conversation = await conversation_repo.get_for_user(
                self.session,
                conversation_id=conversation_id,
                user_id=self.user.id,
            )
            if conversation is not None:
                return conversation, True

        conversation = await conversation_repo.create(
            self.session,
            user_id=self.user.id,
            title=title,
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(conversation)
        logger.info(
            "conversation.created",
            conversation_id=str(conversation.id),
            user_id=str(self.user.id),
        )
        return conversation, False

    async def _persist_user_message(self, conversation_id: UUID, content: str) -> Message:
        try:
            user_message = await message_repo.create(
                self.session,
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=content,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        await self.session.refresh(user_message)
        await self._bump_history_version(conversation_id)
        return user_message

    async def _build_messages(self, conversation_id: UUID, max_history: int) -> list[dict[str, str]]:
        cache = await get_redis_client()
        version = await self._get_history_version(conversation_id, cache)
        cache_key = self._build_history_cache_key(conversation_id, max_history, version)

        if cache:
            try:
                cached = await cache.get(cache_key)
                if cached:
                    return orjson.loads(cached)
            except RedisError as exc:
                logger.warning(
                    "chat.history_cache.get_failed",
                    conversation_id=str(conversation_id),
                    error=str(exc),
                )

        history = await get_recent_history(self.session, conversation_id, limit=max_history)
        messages = [{"role": message.role.value, "content": message.content} for message in history]

        if cache:
            try:
                await cache.set(cache_key, orjson.dumps(messages), ex=settings.history_cache_ttl_s)
            except RedisError as exc:
                logger.warning(
                    "chat.history_cache.set_failed",
                    conversation_id=str(conversation_id),
                    error=str(exc),
                )
        return messages

    async def _get_history_version(self, conversation_id: UUID, cache) -> int:
        if not cache:
            return 0
        try:
            version = await cache.get(self._history_version_key(conversation_id))
        except RedisError as exc:
            logger.warning(
                "chat.history_cache.version_read_failed",
                conversation_id=str(conversation_id),
                error=str(exc),
            )
            return 0
        if version is None:
            return 0
        try:
            return int(version)
        except (TypeError, ValueError):
            return 0

    async def _bump_history_version(self, conversation_id: UUID) -> None:
        cache = await get_redis_client()
        if not cache:
            return
        try:
            await cache.incr(self._history_version_key(conversation_id))
        except RedisError as exc:
            logger.warning(
                "chat.history_cache.version_bump_failed",
                conversation_id=str(conversation_id),
                error=str(exc),
            )

    def _build_history_cache_key(self, conversation_id: UUID, max_history: int, version: int) -> str:
        return f"history:{conversation_id}:{max_history}:v{version}"

    def _history_version_key(self, conversation_id: UUID) -> str:
        return f"history-version:{conversation_id}"

    async def _event_generator(
        self,
        conversation: Conversation,
        user_message: Message,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, str]]:
        assistant_parts: list[str] = []
        async for chunk in self.inference.stream_chat(messages):
            parsed = self._parse_stream_chunk(chunk, conversation.id)
            if parsed is _DONE_SENTINEL:
                break
            if parsed is None:
                continue

            parsed["previous_id"] = str(user_message.id)
            parsed["chat_info"] = {
                "id": str(conversation.id),
                "title": conversation.title,
            }
            content = self._extract_delta_content(parsed)
            if content:
                assistant_parts.append(content)
            yield {"event": "message", "data": orjson.dumps(parsed).decode("utf-8")}

        if assistant_parts:
            await self.persist_assistant_response(conversation, "".join(assistant_parts))

        logger.info(
            "chat.stream.end",
            conversation_id=str(conversation.id),
            user_id=str(self.user.id),
        )

    def _parse_stream_chunk(self, chunk: str, conversation_id: UUID):
        data = chunk.removeprefix("data: ")
        if data.strip() == "[DONE]":
            return _DONE_SENTINEL
        if not chunk.startswith("data: "):
            logger.warning(
                "chat.stream.chunk_ignored",
                conversation_id=str(conversation_id),
                chunk=chunk,
            )
            return None
        try:
            payload = orjson.loads(data)
        except orjson.JSONDecodeError:
            logger.warning(
                "chat.stream.chunk_invalid_json",
                conversation_id=str(conversation_id),
                chunk=data,
            )
            return None
        if not isinstance(payload, dict):
            logger.warning(
                "chat.stream.chunk_invalid_payload",
                conversation_id=str(conversation_id),
            )
            return None
        return payload

    def _extract_delta_content(self, payload: dict) -> str | None:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if not isinstance(choice, dict):
            return None
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        if isinstance(content, str):
            return content
        return None
