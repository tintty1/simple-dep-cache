import builtins
import threading
import time
import warnings
from collections.abc import Callable
from typing import Optional

from .backends import AsyncCacheBackend, CacheBackend
from .config import ConfigBase, RedisConfig
from .events import CacheEvent, CacheEventType, EventEmitter
from .types import CacheValue

_manager_lock = threading.Lock()

_managers: dict[str, "CacheManager"] = {}


# for backward compatability
def get_default_cache_manager():
    return get_or_create_cache_manager()


def get_default_async_cache_manager():
    return get_or_create_cache_manager(create_async_backend=True)


def get_or_create_cache_manager(
    name: str | None = None,
    config: ConfigBase | None = None,
    backend: CacheBackend | None = None,
    async_backend: AsyncCacheBackend | None = None,
    create_async_backend: bool = False,
) -> Optional["CacheManager"]:
    """Get or create a CacheManager for the given configuration."""
    global _managers

    manager = None

    with _manager_lock:
        if config is None:
            config = RedisConfig()
        if name is None:
            name = config.prefix
        if name in _managers:
            # manager already exists, ignore other params
            manager = _managers[name]
            config = manager.config
        if not config.cache_enabled:
            import warnings

            warnings.warn("Caching is disabled in the configuration.", UserWarning, stacklevel=2)
            return None
        if name is None:
            name = config.prefix
        if manager is None:
            from .factories import create_cache_manager

            manager = create_cache_manager(
                name=name,
                config=config,
                backend=backend,
                async_backend=async_backend,
                create_async_backend=create_async_backend,
            )
            _managers[name] = manager
    return manager


# this class should not be used directly, use get_or_create_cache_manager() instead
class CacheManager:
    """Unified cache manager with dependency tracking using pluggable backend."""

    def __init__(
        self,
        config: ConfigBase,
        name: str | None = None,
        backend: CacheBackend | None = None,
        async_backend: AsyncCacheBackend | None = None,
    ):
        # if `name` was provided,
        # `config.prefix` should be set to non-default value to avoid conflict
        # if it's not provided, use `config.prefix` as name
        self._name = name
        self.config = config
        # At least one backend must be provided
        if backend is None and async_backend is None:
            raise ValueError("Must specify either 'backend', 'async_backend', or both")

        self.backend = backend
        self.async_backend = async_backend
        self.events = EventEmitter(self.config)

    @property
    def prefix(self) -> str:
        return self.config.prefix

    @property
    def name(self) -> str:
        # use prefix as name
        return self._name or self.prefix

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

    def on_event(self, event_type: CacheEventType, callback: Callable[[CacheEvent], None]) -> None:
        """Register a callback for a specific cache event type.

        Args:
            event_type: The type of event to listen for
            callback: Function to call when the event occurs
        """
        self.events.on(event_type, callback)

    def on_all_events(self, callback: Callable[[CacheEvent], None]) -> None:
        """Register a callback for all cache events.

        Args:
            callback: Function to call when any cache event occurs
        """
        self.events.on_all(callback)

    def remove_event_callback(
        self, event_type: CacheEventType, callback: Callable[[CacheEvent], None]
    ) -> bool:
        """Remove a callback for a specific event type.

        Args:
            event_type: The type of event to stop listening for
            callback: The callback function to remove

        Returns:
            True if the callback was removed, False if it wasn't found
        """
        return self.events.off(event_type, callback)

    def remove_all_events_callback(self, callback: Callable[[CacheEvent], None]) -> bool:
        """Remove a callback from all events.

        Args:
            callback: The callback function to remove

        Returns:
            True if the callback was removed, False if it wasn't found
        """
        return self.events.off_all(callback)

    def clear_all_event_callbacks(self) -> None:
        """Remove all registered event callbacks."""
        self.events.clear_all()

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
