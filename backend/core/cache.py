import json
import time
from typing import Optional, Any, Callable, Awaitable
try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("ThothRedisCache")

class RedisCacheManager:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._memory_fallback: dict = {}
        self._memory_expiry: dict = {}
        self._connection_failed: bool = False

    async def get_client(self) -> Optional[Any]:
        if aioredis is None:
            return None
        if self._connection_failed and self._redis is None:
            return None

        if self._redis is None:
            settings = get_settings()
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.5
                )
                await client.ping()
                self._redis = client
                self._connection_failed = False
                logger.info(f"Connected to Redis cache at {settings.REDIS_URL}")
            except Exception as e:
                self._connection_failed = True
                self._redis = None
                logger.warning(f"Redis unreachable ({str(e)}). Running in fail-open in-memory fallback mode.")
        return self._redis

    async def is_connected(self) -> bool:
        client = await self.get_client()
        if client:
            try:
                return await client.ping()
            except Exception:
                return False
        return False

    async def get(self, key: str) -> Optional[Any]:
        client = await self.get_client()
        if client:
            try:
                raw = await client.get(key)
                return json.loads(raw) if raw else None
            except Exception as e:
                logger.warning(f"Redis get failed for '{key}': {e}. Falling back to memory.")

        # Check in-memory fallback
        now = time.time()
        exp = self._memory_expiry.get(key)
        if exp and now > exp:
            self._memory_fallback.pop(key, None)
            self._memory_expiry.pop(key, None)
            return None
        return self._memory_fallback.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        settings = get_settings()
        ttl_sec = ttl if ttl is not None else settings.REDIS_CACHE_TTL
        serialized = json.dumps(value)

        client = await self.get_client()
        if client:
            try:
                await client.set(key, serialized, ex=ttl_sec)
                return
            except Exception as e:
                logger.warning(f"Redis set failed for '{key}': {e}. Storing in memory fallback.")

        # In-memory storage
        self._memory_fallback[key] = value
        if ttl_sec:
            self._memory_expiry[key] = time.time() + ttl_sec

    async def delete(self, key: str) -> None:
        client = await self.get_client()
        if client:
            try:
                await client.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete failed for '{key}': {e}")
        self._memory_fallback.pop(key, None)
        self._memory_expiry.pop(key, None)

    async def get_or_set(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None
    ) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached

        data = await fetcher()
        if data is not None:
            await self.set(key, data, ttl)
        return data

# Global singleton
cache_manager = RedisCacheManager()
