import builtins
import logging
import threading
import time
import warnings

from .backends import AsyncCacheBackend, CacheBackend
from .config import ConfigBase
from .events import CacheEvent, CacheEventType, EventEmitter
from .types import CacheValue

logger = logging.getLogger(__name__)

_default_manager = None
_manager_lock = threading.Lock()


class CacheManager:
    """Unified cache manager with dependency tracking using pluggable backend."""

    def __init__(
        self,
        config: ConfigBase,
        backend: CacheBackend | None = None,
        async_backend: AsyncCacheBackend | None = None,
    ):
        self.config = config
        # At least one backend must be provided
        if backend is None and async_backend is None:
            raise ValueError("Must specify either 'backend', 'async_backend', or both")

        self.backend = backend
        self.async_backend = async_backend
        self.events = EventEmitter()

    @property
    def prefix(self) -> str:
        return self.config.prefix

    @property
    def name(self) -> str:
        # use prefix as name
        return self.prefix

    def _cache_key(self, key: str) -> str:
        if self.backend is not None:
            return self.backend._cache_key(key)
        elif self.async_backend is not None:
            return self.async_backend._cache_key(key)
        else:
            raise RuntimeError("No backend available.")

    def _deps_key(self, dependency: str) -> str:
        if self.backend is not None:
            return self.backend._deps_key(dependency)
        elif self.async_backend is not None:
            return self.async_backend._deps_key(dependency)
        else:
            raise RuntimeError("No backend available.")

    def set(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: set[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.aset()' instead.")

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
        """Async version of set - uses async backend, falls back to sync backend."""
        if self.async_backend is not None:
            await self.async_backend.set(key, value, ttl, dependencies)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'aset()'. "
                "Consider using sync method 'set()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            self.backend.set(key, value, ttl, dependencies)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

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
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.aget()' instead.")

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
        """Async version of get - uses async backend, falls back to sync backend."""
        if self.async_backend is not None:
            value = await self.async_backend.get(key)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'aget()'. "
                "Consider using sync method 'get()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            value = self.backend.get(key)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

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
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.adelete()' instead.")

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
        """Async version of delete - uses async backend, falls back to sync backend."""
        if self.async_backend is not None:
            count = await self.async_backend.delete(*keys)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'adelete()'. "
                "Consider using sync method 'delete()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            count = self.backend.delete(*keys)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

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
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.aclear()' instead.")

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
        if self.async_backend is not None:
            count = await self.async_backend.clear(pattern)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'aclear()'. "
                "Consider using sync method 'clear()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            count = self.backend.clear(pattern)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

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
        if self.backend is None:
            raise RuntimeError(
                "No sync backend available. Use 'await manager.ainvalidate_dependency()' instead."
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
        """Async version of invalidate_dependency - uses async backend, falls back to sync
        backend."""
        if self.async_backend is not None:
            count = await self.async_backend.invalidate_dependency(dependency)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'ainvalidate_dependency()'. "
                "Consider using sync method 'invalidate_dependency()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            count = self.backend.invalidate_dependency(dependency)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

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
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.aexists()' instead.")

        return self.backend.exists(key)

    async def aexists(self, key: str) -> bool:
        """Async version of exists - uses async backend, falls back to sync backend."""
        if self.async_backend is not None:
            return await self.async_backend.exists(key)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'aexists()'. "
                "Consider using sync method 'exists()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            return self.backend.exists(key)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        if self.backend is None:
            raise RuntimeError("No sync backend available. Use 'await manager.attl()' instead.")

        return self.backend.ttl(key)

    async def attl(self, key: str) -> int:
        """Async version of ttl - uses async backend, falls back to sync backend."""
        if self.async_backend is not None:
            return await self.async_backend.ttl(key)
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'attl()'. "
                "Consider using sync method 'ttl()' for better performance.",
                UserWarning,
                stacklevel=2,
            )
            return self.backend.ttl(key)
        else:
            raise RuntimeError("No backend available. Provide either 'backend' or 'async_backend'.")

    async def aclose(self) -> None:
        """Close the backend connection."""
        if self.async_backend is not None:
            await self.async_backend.close()
        elif self.backend is not None:
            warnings.warn(
                "Using sync backend with async method 'aclose()'. "
                "No connection to close for sync backends.",
                UserWarning,
                stacklevel=2,
            )
        # No error needed for aclose - it's fine if there's no backend to close
