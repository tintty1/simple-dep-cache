import logging
import time

import redis
import redis.asyncio as async_redis

from .config import (
    create_async_redis_client_from_config,
    create_redis_client_from_config,
)
from .events import CacheEvent, CacheEventType, EventEmitter
from .types import CacheValue, get_serializer

logger = logging.getLogger(__name__)


class CacheManager:
    """Synchronous Redis-based cache manager with dependency tracking."""

    def __init__(self, redis_client: redis.Redis | None = None, prefix: str = "cache"):
        if redis_client is None:
            from .config import config

            self._redis = None
            if config.cache_enabled:
                logger.info(
                    "Creating Redis client from environment configuration. "
                    "Provide a custom redis_client parameter to override."
                )
                self._redis = create_redis_client_from_config()
        else:
            self._redis = redis_client
        self.prefix = prefix
        self.events = EventEmitter()
        self.serializer = get_serializer()

    @property
    def redis(self) -> redis.Redis:
        """Get the Redis client, raising an error if not configured."""
        if self._redis is None:
            raise RuntimeError("Cache is disabled or redis client is not configured.")
        return self._redis

    def _cache_key(self, key: str) -> str:
        """Generate prefixed cache key."""
        return f"{self.prefix}:{key}"

    def _deps_key(self, dependency: str) -> str:
        """Generate dependency tracking key."""
        return f"{self.prefix}:deps:{dependency}"

    def set(
        self,
        key: str,
        value: CacheValue,
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

        # Emit set event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.SET,
                key=key,
                timestamp=time.time(),
                value=value,
                dependencies=dependencies,
                ttl=ttl,
            )
        )

    def get(self, key: str) -> CacheValue | None:
        """Get a cache value."""
        cache_key = self._cache_key(key)
        value = self.redis.get(cache_key)

        if value is None:
            # Emit cache miss event
            self.events.emit(
                CacheEvent(event_type=CacheEventType.MISS, key=key, timestamp=time.time())
            )
            return None

        # Emit cache hit event
        deserialized_value = self.serializer.load(value)
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.HIT,
                key=key,
                timestamp=time.time(),
                value=deserialized_value,
            )
        )
        return deserialized_value

    def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        cache_keys = [self._cache_key(key) for key in keys]
        count = self.redis.delete(*cache_keys) if cache_keys else 0

        # Emit delete event for each key
        for key in keys:
            self.events.emit(
                CacheEvent(
                    event_type=CacheEventType.DELETE,
                    key=key,
                    timestamp=time.time(),
                    count=1,
                )
            )

        return count

    def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pattern_key = self._cache_key(pattern)
        keys = list(self.redis.scan_iter(match=pattern_key))
        count = self.redis.delete(*keys) if keys else 0

        # Emit clear event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.CLEAR,
                key=pattern,
                timestamp=time.time(),
                count=count,
            )
        )

        return count

    def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        dep_key = self._deps_key(dependency)
        cache_keys = self.redis.smembers(dep_key)

        if not cache_keys:
            count = 0
        else:
            count = self.redis.delete(*cache_keys)
            self.redis.delete(dep_key)

        # Emit invalidate event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.INVALIDATE,
                key=dependency,
                timestamp=time.time(),
                count=count,
            )
        )

        return count

    def exists(self, key: str) -> bool:
        """Check if a cache key exists."""
        return bool(self.redis.exists(self._cache_key(key)))

    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        return self.redis.ttl(self._cache_key(key))


class AsyncCacheManager:
    """Asynchronous Redis-based cache manager with dependency tracking."""

    def __init__(self, redis_client: async_redis.Redis | None = None, prefix: str = "cache"):
        if redis_client is None:
            logger.info(
                "Creating async Redis client from environment configuration. "
                "Provide a custom redis_client parameter to override."
            )
            self.redis = create_async_redis_client_from_config()
        else:
            self.redis = redis_client
        self.prefix = prefix
        self.events = EventEmitter()
        self.serializer = get_serializer()

    def _cache_key(self, key: str) -> str:
        """Generate prefixed cache key."""
        return f"{self.prefix}:{key}"

    def _deps_key(self, dependency: str) -> str:
        """Generate dependency tracking key."""
        return f"{self.prefix}:deps:{dependency}"

    async def set(
        self,
        key: str,
        value: CacheValue,
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

        # Emit set event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.SET,
                key=key,
                timestamp=time.time(),
                value=value,
                dependencies=dependencies,
                ttl=ttl,
            )
        )

    async def get(self, key: str) -> CacheValue | None:
        """Get a cache value."""
        cache_key = self._cache_key(key)
        value = await self.redis.get(cache_key)

        if value is None:
            # Emit cache miss event
            self.events.emit(
                CacheEvent(event_type=CacheEventType.MISS, key=key, timestamp=time.time())
            )
            return None

        # Emit cache hit event
        deserialized_value = self.serializer.load(value)
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.HIT,
                key=key,
                timestamp=time.time(),
                value=deserialized_value,
            )
        )
        return deserialized_value

    async def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        cache_keys = [self._cache_key(key) for key in keys]
        count = await self.redis.delete(*cache_keys) if cache_keys else 0

        # Emit delete event for each key
        for key in keys:
            self.events.emit(
                CacheEvent(
                    event_type=CacheEventType.DELETE,
                    key=key,
                    timestamp=time.time(),
                    count=1,
                )
            )

        return count

    async def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pattern_key = self._cache_key(pattern)
        keys = []
        async for key in self.redis.scan_iter(match=pattern_key):
            keys.append(key)
        count = await self.redis.delete(*keys) if keys else 0

        # Emit clear event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.CLEAR,
                key=pattern,
                timestamp=time.time(),
                count=count,
            )
        )

        return count

    async def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        dep_key = self._deps_key(dependency)
        cache_keys = await self.redis.smembers(dep_key)

        if not cache_keys:
            count = 0
        else:
            count = await self.redis.delete(*cache_keys)
            await self.redis.delete(dep_key)

        # Emit invalidate event
        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.INVALIDATE,
                key=dependency,
                timestamp=time.time(),
                count=count,
            )
        )

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
