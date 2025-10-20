import logging
import threading
import time

from .backends import AsyncCacheBackend, CacheBackend
from .events import CacheEvent, CacheEventType, EventEmitter
from .redis_backends import AsyncRedisCacheBackend, RedisCacheBackend
from .types import CacheValue

logger = logging.getLogger(__name__)

_default_sync_manager = None
_default_async_manager = None
_manager_lock = threading.Lock()


class CacheManager:
    """Cache manager with dependency tracking using pluggable backend."""

    def __init__(
        self, backend: CacheBackend | None = None, *, redis_client=None, prefix: str = "cache"
    ):
        # Backwards compatibility: if redis_client is provided, create backend
        if backend is None and redis_client is not None:
            backend = RedisCacheBackend(redis_client=redis_client, prefix=prefix)
        elif backend is None:
            backend = RedisCacheBackend(prefix=prefix)

        self.backend = backend
        self.prefix = prefix
        self.events = EventEmitter()

    @property
    def redis(self):
        """Backwards compatibility property to access redis client."""
        return self.backend.redis

    def _cache_key(self, key: str) -> str:
        """Backwards compatibility method."""
        return self.backend._cache_key(key)

    def _deps_key(self, dependency: str) -> str:
        """Backwards compatibility method."""
        return self.backend._deps_key(dependency)

    def set(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: set[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        self.backend.set(key, value, ttl, dependencies)

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
        value = self.backend.get(key)

        if value is None:
            self.events.emit(
                CacheEvent(event_type=CacheEventType.MISS, key=key, timestamp=time.time())
            )
            return None

        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.HIT,
                key=key,
                timestamp=time.time(),
                value=value,
            )
        )
        return value

    def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        count = self.backend.delete(*keys)

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
        count = self.backend.clear(pattern)

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
        count = self.backend.invalidate_dependency(dependency)

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
        return self.backend.exists(key)

    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        return self.backend.ttl(key)


class AsyncCacheManager:
    """Asynchronous cache manager with dependency tracking using pluggable backend."""

    def __init__(
        self, backend: AsyncCacheBackend | None = None, *, redis_client=None, prefix: str = "cache"
    ):
        # Backwards compatibility: if redis_client is provided, create backend
        if backend is None and redis_client is not None:
            backend = AsyncRedisCacheBackend(redis_client=redis_client, prefix=prefix)
        elif backend is None:
            backend = AsyncRedisCacheBackend(prefix=prefix)

        self.backend = backend
        self.prefix = prefix
        self.events = EventEmitter()

    @property
    def redis(self):
        """Backwards compatibility property to access redis client."""
        return self.backend.redis

    def _cache_key(self, key: str) -> str:
        """Backwards compatibility method."""
        return self.backend._cache_key(key)

    def _deps_key(self, dependency: str) -> str:
        """Backwards compatibility method."""
        return self.backend._deps_key(dependency)

    async def set(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: set[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        await self.backend.set(key, value, ttl, dependencies)

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
        value = await self.backend.get(key)

        if value is None:
            self.events.emit(
                CacheEvent(event_type=CacheEventType.MISS, key=key, timestamp=time.time())
            )
            return None

        self.events.emit(
            CacheEvent(
                event_type=CacheEventType.HIT,
                key=key,
                timestamp=time.time(),
                value=value,
            )
        )
        return value

    async def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        count = await self.backend.delete(*keys)

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
        count = await self.backend.clear(pattern)

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
        count = await self.backend.invalidate_dependency(dependency)

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
        return await self.backend.exists(key)

    async def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        return await self.backend.ttl(key)

    async def close(self) -> None:
        """Close the backend connection."""
        await self.backend.close()


def get_default_cache_manager() -> CacheManager:
    global _default_sync_manager
    if _default_sync_manager is None:
        with _manager_lock:
            if _default_sync_manager is None:
                _default_sync_manager = CacheManager()
    return _default_sync_manager


def get_default_async_cache_manager() -> AsyncCacheManager:
    global _default_async_manager
    if _default_async_manager is None:
        with _manager_lock:
            if _default_async_manager is None:
                _default_async_manager = AsyncCacheManager()
    return _default_async_manager
