'''Core Redis integration for FastAPI.

Provides a singleton async connection pool and a FastAPI dependency
`get_redis` that yields an instance of ``redis.asyncio.Redis``.

The connection parameters are taken from ``app.core.config.settings``.
'''

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import redis.asyncio as redis
from redis.asyncio import Redis, ConnectionPool

from app.core.config import settings

class RedisManager:
    """Manage a global Redis connection pool.

    The pool is created once at startup and closed on application shutdown.
    """

    def __init__(self) -> None:
        self.pool: ConnectionPool | None = None
        self.client: Redis | None = None

    async def connect(self) -> None:
        """Initialize the connection pool and client.

        This should be called during the FastAPI lifespan ``startup`` phase.
        """
        if self.pool is None:
            self.pool = redis.ConnectionPool.from_url(
                str(settings.REDIS_URL), max_connections=20, decode_responses=True
            )
            self.client = redis.Redis(connection_pool=self.pool)

    async def disconnect(self) -> None:
        """Close the client and pool.

        Called during the FastAPI ``shutdown`` phase.
        """
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        if self.pool is not None:
            await self.pool.disconnect()
            self.pool = None

    def get_client(self) -> Redis:
        """Return the Redis client instance.

        Raises:
            RuntimeError: If the pool has not been initialised.
        """
        if self.client is None:
            raise RuntimeError("Redis client not initialised. Call 'connect' first.")
        return self.client

# Global manager instance
redis_manager = RedisManager()

@asynccontextmanager
async def lifespan(app: object) -> AsyncIterator[None]:
    """FastAPI lifespan hook to manage Redis resources.

    Usage::
        app = FastAPI(lifespan=lifespan)
    """
    await redis_manager.connect()
    yield
    await redis_manager.disconnect()

async def get_redis() -> Redis:
    """FastAPI dependency that provides a Redis client.

    The returned client shares the same underlying connection pool.
    """
    return redis_manager.get_client()

__all__ = ["lifespan", "get_redis", "redis_manager"]
