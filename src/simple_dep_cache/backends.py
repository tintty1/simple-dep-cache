"""
Cache backend interfaces and implementations for different storage systems.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .config import ConfigBase
from .types import CacheValue


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    def __init__(self, config: ConfigBase):
        self.prefix = config.prefix

    def _cache_key(self, key: str) -> str:
        """Generate prefixed cache key."""
        return f"{self.prefix}:{key}"

    def _deps_key(self, dependency: str) -> str:
        """Generate dependency tracking key."""
        return f"{self.prefix}:deps:{dependency}"

    @abstractmethod
    def set(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: Iterable[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        pass

    @abstractmethod
    def get(self, key: str) -> CacheValue | None:
        """Get a cache value."""
        pass

    @abstractmethod
    def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        pass

    @abstractmethod
    def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pass

    @abstractmethod
    def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a cache key exists."""
        pass

    @abstractmethod
    def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        pass


class AsyncCacheBackend(ABC):
    """Abstract base class for async cache backends."""

    def __init__(self, config: ConfigBase):
        self.prefix = config.prefix

    def _cache_key(self, key: str) -> str:
        """Generate prefixed cache key."""
        return f"{self.prefix}:{key}"

    def _deps_key(self, dependency: str) -> str:
        """Generate dependency tracking key."""
        return f"{self.prefix}:deps:{dependency}"

    @abstractmethod
    async def set(
        self,
        key: str,
        value: CacheValue,
        ttl: int | None = None,
        dependencies: Iterable[str] | None = None,
    ) -> None:
        """Set a cache value with optional TTL and dependencies."""
        pass

    @abstractmethod
    async def get(self, key: str) -> CacheValue | None:
        """Get a cache value."""
        pass

    @abstractmethod
    async def delete(self, *keys: str) -> int:
        """Delete cache entries."""
        pass

    @abstractmethod
    async def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        pass

    @abstractmethod
    async def invalidate_dependency(self, dependency: str) -> int:
        """Invalidate all cache entries that depend on the given dependency."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a cache key exists."""
        pass

    @abstractmethod
    async def ttl(self, key: str) -> int:
        """Get TTL for a cache key."""
        pass

    async def close(self) -> None:
        """Close the backend connection (if applicable)."""
        return
