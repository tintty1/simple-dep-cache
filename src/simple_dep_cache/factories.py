"""
Factory functions for creating cache backends and managers.
"""

import redis
import redis.asyncio as async_redis

from .backends import AsyncCacheBackend, CacheBackend
from .manager import CacheManager
from .redis_backends import AsyncRedisCacheBackend, RedisCacheBackend


def create_redis_backend(
    redis_client: redis.Redis | None = None, prefix: str = "cache"
) -> RedisCacheBackend:
    """
    Create a Redis cache backend.

    Args:
        redis_client: Custom Redis client (optional)
        prefix: Cache key prefix (default: "cache")

    Returns:
        RedisCacheBackend instance
    """
    return RedisCacheBackend(redis_client=redis_client, prefix=prefix)


def create_async_redis_backend(
    redis_client: async_redis.Redis | None = None, prefix: str = "cache"
) -> AsyncRedisCacheBackend:
    """
    Create an async Redis cache backend.

    Args:
        redis_client: Custom async Redis client (optional)
        prefix: Cache key prefix (default: "cache")

    Returns:
        AsyncRedisCacheBackend instance
    """
    return AsyncRedisCacheBackend(redis_client=redis_client, prefix=prefix)


def create_cache_manager(
    backend: CacheBackend | None = None,
    redis_client: redis.Redis | None = None,
    prefix: str = "cache",
) -> CacheManager:
    """
    Create a cache manager with Redis backend.

    Args:
        backend: Custom cache backend (takes precedence over redis_client)
        redis_client: Custom Redis client (used if backend not provided)
        prefix: Cache key prefix (default: "cache")

    Returns:
        CacheManager instance
    """
    if backend is None:
        backend = create_redis_backend(redis_client=redis_client, prefix=prefix)

    return CacheManager(backend=backend)


def create_async_cache_manager(
    backend: AsyncCacheBackend | None = None,
    redis_client: async_redis.Redis | None = None,
    prefix: str = "cache",
) -> CacheManager:
    """
    Create a cache manager with async Redis backend.

    Args:
        backend: Custom async cache backend (takes precedence over redis_client)
        redis_client: Custom async Redis client (used if backend not provided)
        prefix: Cache key prefix (default: "cache")

    Returns:
        CacheManager instance with async backend
    """
    if backend is None:
        backend = create_async_redis_backend(redis_client=redis_client, prefix=prefix)

    return CacheManager(backend=backend)


def create_unified_cache_manager(
    backend: CacheBackend | AsyncCacheBackend | None = None,
    redis_client: redis.Redis | async_redis.Redis | None = None,
    prefix: str = "cache",
) -> CacheManager:
    """
    Create a unified cache manager that works with both sync and async backends.

    Args:
        backend: Custom cache backend (sync or async, takes precedence over redis_client)
        redis_client: Custom Redis client (sync or async, used if backend not provided)
        prefix: Cache key prefix (default: "cache")

    Returns:
        Unified CacheManager instance
    """
    return CacheManager(backend=backend, redis_client=redis_client, prefix=prefix)
