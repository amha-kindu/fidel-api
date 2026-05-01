import structlog
from typing import Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger(__name__)

_redis_client: Optional[Redis] = None


async def init_redis_client() -> Optional[Redis]:
    """Initialize a shared Redis client; return None if unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
            await _redis_client.ping()
        except RedisError as exc:
            logger.warning("redis.unavailable", error=str(exc))
            _redis_client = None
    return _redis_client


async def get_redis_client() -> Optional[Redis]:
    return await init_redis_client()


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is None:
        return
    try:
        await _redis_client.aclose()
    except RedisError as exc:
        logger.warning("redis.close_failed", error=str(exc))
    finally:
        _redis_client = None
