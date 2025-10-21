import builtins
import logging
import threading
import time
import warnings

from .backends import AsyncCacheBackend, CacheBackend
from .events import CacheEvent, CacheEventType, EventEmitter
from .redis_backends import AsyncRedisCacheBackend, RedisCacheBackend
from .types import CacheValue

logger = logging.getLogger(__name__)

_default_manager = None
_manager_lock = threading.Lock()


class CacheManager:
    """Unified cache manager with dependency tracking using pluggable backend."""

    def __init__(
        self,
        backend: CacheBackend | AsyncCacheBackend | None = None,
        *,
        redis_client=None,
        prefix: str = "cache",
    ):
        # Determine if we should create sync or async backend
        if backend is None:
            if redis_client is not None:
                # Auto-detect based on redis_client type
                import redis.asyncio as async_redis

                if isinstance(redis_client, async_redis.Redis):
                    backend = AsyncRedisCacheBackend(redis_client=redis_client, prefix=prefix)
                else:
                    backend = RedisCacheBackend(redis_client=redis_client, prefix=prefix)
            else:
                # Default to sync backend for backwards compatibility
                backend = RedisCacheBackend(prefix=prefix)

        self.backend = backend
        self._is_async = isinstance(backend, AsyncCacheBackend)
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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'set()' method with async backend. "
                "Use 'await manager.aset()' instead."
            )

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

    async def aset(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: builtins.set[str] | None = None,
    ) -> None:
        """Async version of set - works with async backends, falls back to sync."""
        if self._is_async:
            await self.backend.set(key, value, ttl, dependencies)
        else:
            warnings.warn(
                "Using sync backend with async method 'aset()'. Consider using sync method 'set()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'get()' method with async backend. Use 'await manager.aget()' instead."
            )

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

    async def aget(self, key: str) -> CacheValue | None:
        """Async version of get - works with async backends, falls back to sync."""
        if self._is_async:
            value = await self.backend.get(key)
        else:
            warnings.warn(
                "Using sync backend with async method 'aget()'. Consider using sync method 'get()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'delete()' method with async backend. Use 'await manager.adelete()' instead."
            )

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

    async def adelete(self, *keys: str) -> int:
        """Async version of delete - works with async backends, falls back to sync."""
        if self._is_async:
            count = await self.backend.delete(*keys)
        else:
            warnings.warn(
                "Using sync backend with async method 'adelete()'. Consider using sync method 'delete()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'clear()' method with async backend. Use 'await manager.aclear()' instead."
            )

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

    async def aclear(self, pattern: str = "*") -> int:
        """Async version of clear - works with async backends, falls back to sync."""
        if self._is_async:
            count = await self.backend.clear(pattern)
        else:
            warnings.warn(
                "Using sync backend with async method 'aclear()'. Consider using sync method 'clear()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'invalidate_dependency()' method with async backend. Use 'await manager.ainvalidate_dependency()' instead."
            )

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

    async def ainvalidate_dependency(self, dependency: str) -> int:
        """Async version of invalidate_dependency - works with async backends, falls back to sync."""
        if self._is_async:
            count = await self.backend.invalidate_dependency(dependency)
        else:
            warnings.warn(
                "Using sync backend with async method 'ainvalidate_dependency()'. Consider using sync method 'invalidate_dependency()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            count = self.backend.invalidate_dependency(dependency)

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
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'exists()' method with async backend. Use 'await manager.aexists()' instead."
            )

        return self.backend.exists(key)

    async def aexists(self, key: str) -> bool:
        """Async version of exists - works with async backends, falls back to sync."""
        if self._is_async:
            return await self.backend.exists(key)
        else:
            warnings.warn(
                "Using sync backend with async method 'aexists()'. Consider using sync method 'exists()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            return self.backend.exists(key)

    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        if self._is_async:
            raise RuntimeError(
                "Cannot use sync 'ttl()' method with async backend. Use 'await manager.attl()' instead."
            )

        return self.backend.ttl(key)

    async def attl(self, key: str) -> int:
        """Async version of ttl - works with async backends, falls back to sync."""
        if self._is_async:
            return await self.backend.ttl(key)
        else:
            warnings.warn(
                "Using sync backend with async method 'attl()'. Consider using sync method 'ttl()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            return self.backend.ttl(key)

    async def aclose(self) -> None:
        """Close the backend connection."""
        if self._is_async:
            await self.backend.close()
        else:
            warnings.warn(
                "Using sync backend with async method 'aclose()'. No connection to close for sync backends.",
                UserWarning,
                stacklevel=2,
            )


# Backwards compatibility: Deprecated AsyncCacheManager with old API
class AsyncCacheManager:
    """Deprecated: Use CacheManager with async backend and 'await manager.aset()' instead."""

    def __init__(self, backend=None, *, redis_client=None, prefix="cache"):
        warnings.warn(
            "AsyncCacheManager is deprecated. Use CacheManager with async backend and 'await manager.aset()' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # For AsyncCacheManager, default to async backend if none provided
        if backend is None and redis_client is None:
            backend = AsyncRedisCacheBackend(prefix=prefix)
        # Create the actual unified manager
        self._manager = CacheManager(backend=backend, redis_client=redis_client, prefix=prefix)

    # Delegate all attributes to the internal manager
    def __getattr__(self, name):
        return getattr(self._manager, name)

    # Override async methods to provide old API (without 'a' prefix)
    async def set(self, key, value, ttl=None, dependencies=None):
        """Deprecated: Use CacheManager with await manager.aset() instead."""
        return await self._manager.aset(key, value, ttl, dependencies)

    async def get(self, key):
        """Deprecated: Use CacheManager with await manager.aget() instead."""
        return await self._manager.aget(key)

    async def delete(self, *keys):
        """Deprecated: Use CacheManager with await manager.adelete() instead."""
        return await self._manager.adelete(*keys)

    async def clear(self, pattern="*"):
        """Deprecated: Use CacheManager with await manager.aclear() instead."""
        return await self._manager.aclear(pattern)

    async def invalidate_dependency(self, dependency):
        """Deprecated: Use CacheManager with await manager.ainvalidate_dependency() instead."""
        return await self._manager.ainvalidate_dependency(dependency)

    async def exists(self, key):
        """Deprecated: Use CacheManager with await manager.aexists() instead."""
        return await self._manager.aexists(key)

    async def ttl(self, key):
        """Deprecated: Use CacheManager with await manager.attl() instead."""
        return await self._manager.attl(key)

    async def close(self):
        """Deprecated: Use CacheManager with await manager.aclose() instead."""
        return await self._manager.aclose()


def get_default_cache_manager() -> CacheManager:
    """Get the default cache manager (sync backend)."""
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                _default_manager = CacheManager()
    return _default_manager


def get_default_async_cache_manager() -> CacheManager:
    """Get the default cache manager with async backend."""
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                _default_manager = CacheManager(backend=AsyncRedisCacheBackend())
    return _default_manager
