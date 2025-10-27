"""Fake cache backends for testing.

This module provides fake implementations of cache backends and configuration
that can be used in tests to avoid dependencies on external services like Redis.
"""

from .backends import AsyncCacheBackend, CacheBackend
from .config import ConfigBase
from .types import JSONSerializer


class FakeConfig(ConfigBase):
    """Fake configuration for testing.

    This configuration class provides sensible defaults for testing
    without requiring any Redis-specific configuration.
    """

    def __init__(self, **kwargs):
        cache_backend_class = "simple_dep_cache.fakes.FakeCacheBackend"
        async_cache_backend_class = "simple_dep_cache.fakes.FakeAsyncCacheBackend"
        super().__init__(
            cache_backend_class=cache_backend_class,
            async_cache_backend_class=async_cache_backend_class,
            **kwargs,
        )


class FakeCacheBackend(CacheBackend):
    """Fake cache backend for testing.

    This backend stores cached data in memory and provides basic functionality
    for testing cache operations without requiring external services.
    """

    def __init__(self, config):
        super().__init__(config)
        self.config = config
        self._cache = {}
        self._dependencies = {}
        self.serializer = JSONSerializer()

    def get(self, key: str):
        cache_key = self._cache_key(key)
        return self._cache.get(cache_key)

    def set(self, key: str, value, ttl=None, dependencies=None):
        cache_key = self._cache_key(key)
        self._cache[cache_key] = value

        # Track dependencies
        if dependencies:
            for dep in dependencies:
                deps_key = self._deps_key(dep)
                if deps_key not in self._dependencies:
                    self._dependencies[deps_key] = set()
                self._dependencies[deps_key].add(cache_key)

    def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            cache_key = self._cache_key(key)
            if cache_key in self._cache:
                del self._cache[cache_key]
                count += 1
        return count

    def clear(self, pattern: str = "*") -> int:
        if pattern == "*":
            count = len(self._cache)
            self._cache.clear()
            return count
        return 0

    def invalidate_dependency(self, dependency: str) -> int:
        deps_key = self._deps_key(dependency)
        if deps_key not in self._dependencies:
            return 0

        keys_to_delete = self._dependencies[deps_key]
        count = 0
        for cache_key in keys_to_delete:
            if cache_key in self._cache:
                del self._cache[cache_key]
                count += 1

        del self._dependencies[deps_key]
        return count

    def exists(self, key: str) -> bool:
        cache_key = self._cache_key(key)
        return cache_key in self._cache

    def ttl(self, key: str) -> int:
        return -1 if self.exists(key) else -2


class FakeAsyncCacheBackend(AsyncCacheBackend):
    """Fake async cache backend for testing.

    This async backend wraps the FakeCacheBackend to provide async methods
    while maintaining the same in-memory storage behavior.
    """

    def __init__(self, config):
        self._sync_backend = FakeCacheBackend(config)

    async def get(self, key: str):
        return self._sync_backend.get(key)

    async def set(self, key: str, value, ttl=None, dependencies=None):
        self._sync_backend.set(key, value, ttl, dependencies)

    async def delete(self, *keys: str) -> int:
        return self._sync_backend.delete(*keys)

    async def clear(self, pattern: str = "*") -> int:
        return self._sync_backend.clear(pattern)

    async def invalidate_dependency(self, dependency: str) -> int:
        return self._sync_backend.invalidate_dependency(dependency)

    async def exists(self, key: str) -> bool:
        return self._sync_backend.exists(key)

    async def ttl(self, key: str) -> int:
        return self._sync_backend.ttl(key)

    async def close(self):
        pass


__all__ = ["FakeConfig", "FakeCacheBackend", "FakeAsyncCacheBackend"]
