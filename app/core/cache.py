import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger(__name__)

_redis_client: Redis | None = None


async def get_redis_client() -> Redis | None:
    """Lazily return a Redis client; return None if unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
            await _redis_client.ping()
        except RedisError as exc:
            logger.warning("redis.unavailable", error=str(exc))
            _redis_client = None
    return _redis_client
