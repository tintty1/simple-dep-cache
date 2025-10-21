"""
Redis-specific cache backend implementations.
"""

import logging
from typing import Any

import redis
import redis.asyncio as async_redis

from .backends import AsyncCacheBackend, CacheBackend
from .config import (
    RedisConfig,
    create_async_redis_client_from_config,
    create_redis_client_from_config,
)
from .types import get_serializer

logger = logging.getLogger(__name__)


class RedisCacheBackend(CacheBackend):
    """Redis-based cache backend for synchronous operations."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_config: RedisConfig | None = None,
        prefix: str = "cache",
    ):
        super().__init__(prefix)
        if redis_client is None:
            from .config import config

            # Use provided redis_config or fall back to global config
            redis_cfg = redis_config or config.redis

            self._redis = None
            if config.cache_enabled:
                logger.info(
                    "Creating Redis client from %s configuration. "
                    "Provide a custom redis_client parameter to override.",
                    "provided redis_config" if redis_config else "environment",
                )
                self._redis = create_redis_client_from_config(redis_cfg)
        else:
            self._redis = redis_client
        self.serializer = get_serializer()

    @property
    def redis(self) -> redis.Redis:
        """Get the Redis client, raising an error if not configured."""
        if self._redis is None:
            raise RuntimeError("Cache is disabled or redis client is not configured.")
        return self._redis

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        dependencies: set[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        cache_key = self._cache_key(key)
        serialized_value = self.serializer.dump(value)

        if ttl:
            self.redis.setex(cache_key, ttl, serialized_value)
        else:
            self.redis.set(cache_key, serialized_value)

        if dependencies:
            for dep in dependencies:
                dep_key = self._deps_key(dep)
                self.redis.sadd(dep_key, cache_key)
                if ttl:
                    current_ttl = self.redis.ttl(dep_key)
                    # Ensure dependency tracking key lives at least as long as cache entries
                    # current_ttl: -1 = no expiration, -2 = doesn't exist, >0 = remaining seconds
                    # Set/extend TTL if: key is persistent OR key has shorter TTL than ours
                    if current_ttl == -1 or (current_ttl != -2 and current_ttl < ttl):
                        self.redis.expire(dep_key, ttl)

    def get(self, key: str) -> Any | None:
        """Get a cache value."""
        cache_key = self._cache_key(key)
        value = self.redis.get(cache_key)

        if value is None:
            return None

        return self.serializer.load(value)

    def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        cache_keys = [self._cache_key(key) for key in keys]
        return self.redis.delete(*cache_keys) if cache_keys else 0

    def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pattern_key = self._cache_key(pattern)
        keys = list(self.redis.scan_iter(match=pattern_key))
        return self.redis.delete(*keys) if keys else 0

    def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        dep_key = self._deps_key(dependency)
        cache_keys = self.redis.smembers(dep_key)

        if not cache_keys:
            count = 0
        else:
            count = self.redis.delete(*cache_keys)
            self.redis.delete(dep_key)

        return count

    def exists(self, key: str) -> bool:
        """Check if a cache key exists."""
        return bool(self.redis.exists(self._cache_key(key)))

    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        return self.redis.ttl(self._cache_key(key))


class AsyncRedisCacheBackend(AsyncCacheBackend):
    """Redis-based cache backend for asynchronous operations."""

    def __init__(
        self,
        redis_client: async_redis.Redis | None = None,
        redis_config: RedisConfig | None = None,
        prefix: str = "cache",
    ):
        super().__init__(prefix)
        if redis_client is None:
            from .config import config

            # Use provided redis_config or fall back to global config
            redis_cfg = redis_config or config.redis

            logger.info(
                "Creating async Redis client from %s configuration. "
                "Provide a custom redis_client parameter to override.",
                "provided redis_config" if redis_config else "environment",
            )
            self.redis = create_async_redis_client_from_config(redis_cfg)
        else:
            self.redis = redis_client
        self.serializer = get_serializer()

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        dependencies: set[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        cache_key = self._cache_key(key)
        serialized_value = self.serializer.dump(value)

        if ttl:
            await self.redis.setex(cache_key, ttl, serialized_value)
        else:
            await self.redis.set(cache_key, serialized_value)

        if dependencies:
            for dep in dependencies:
                dep_key = self._deps_key(dep)
                await self.redis.sadd(dep_key, cache_key)
                if ttl:
                    current_ttl = await self.redis.ttl(dep_key)
                    # Ensure dependency tracking key lives at least as long as cache entries
                    # current_ttl: -1 = no expiration, -2 = doesn't exist, >0 = remaining seconds
                    # Set/extend TTL if: key is persistent OR key has shorter TTL than ours
                    if current_ttl == -1 or (current_ttl != -2 and current_ttl < ttl):
                        await self.redis.expire(dep_key, ttl)

    async def get(self, key: str) -> Any | None:
        """Get a cache value."""
        cache_key = self._cache_key(key)
        value = await self.redis.get(cache_key)

        if value is None:
            return None

        return self.serializer.load(value)

    async def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        cache_keys = [self._cache_key(key) for key in keys]
        return await self.redis.delete(*cache_keys) if cache_keys else 0

    async def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pattern_key = self._cache_key(pattern)
        keys = []
        async for key in self.redis.scan_iter(match=pattern_key):
            keys.append(key)
        return await self.redis.delete(*keys) if keys else 0

    async def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        dep_key = self._deps_key(dependency)
        cache_keys = await self.redis.smembers(dep_key)

        if not cache_keys:
            count = 0
        else:
            count = await self.redis.delete(*cache_keys)
            await self.redis.delete(dep_key)

        return count

    async def exists(self, key: str) -> bool:
        """Check if a cache key exists."""
        return bool(await self.redis.exists(self._cache_key(key)))

    async def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        return await self.redis.ttl(self._cache_key(key))

    async def close(self) -> None:
        """Close the Redis connection."""
        await self.redis.aclose()
