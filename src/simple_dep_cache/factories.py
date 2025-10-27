"""
Factory functions for creating cache backends and managers.
"""

from typing import TYPE_CHECKING

import redis
import redis.asyncio as async_redis

from .backends import AsyncCacheBackend, CacheBackend
from .config import ConfigBase, RedisConfig
from .manager import CacheManager
from .redis_backends import AsyncRedisCacheBackend, RedisCacheBackend
from .utils import DynamicImporter

if TYPE_CHECKING:
    import redis
    import redis.asyncio


def load_class(class_path: str):
    """Load a class from a string like 'package.module.ClassName'."""
    return DynamicImporter.load_class(class_path)


def create_backend_from_config(config: ConfigBase) -> CacheBackend:
    """
    Create a cache backend from configuration.

    Args:
        config: Configuration object

    Returns:
        CacheBackend instance based on configuration
    """
    if config.cache_backend_class:
        klass = load_class(config.cache_backend_class)
        return klass(config)
    else:
        # Default to Redis backend
        if isinstance(config, RedisConfig):
            return create_redis_backend(config)
        else:
            raise ValueError("Provide a custom cache_backend_class for non-Redis backend.")


def create_async_backend_from_config(config: ConfigBase) -> AsyncCacheBackend:
    """
    Create an async cache backend from configuration.

    Args:
        config: Configuration object

    Returns:
        AsyncCacheBackend instance based on configuration
    """
    if config.async_cache_backend_class:
        klass = load_class(config.async_cache_backend_class)
        return klass(config)
    else:
        # Default to Redis backend
        if isinstance(config, RedisConfig):
            return create_async_redis_backend(config)
        else:
            raise ValueError("Provide a custom async_cache_backend_class for non-Redis backend.")


def create_redis_backend(
    config: RedisConfig,
    redis_client: redis.Redis | None = None,
) -> RedisCacheBackend:
    """
    Create a Redis cache backend.

    Args:
        redis_client: Custom Redis client (optional)
        redis_config: Custom Redis configuration (optional)

    Returns:
        RedisCacheBackend instance
    """
    return RedisCacheBackend(config, redis_client=redis_client)


def create_async_redis_backend(
    config: RedisConfig,
    redis_client: async_redis.Redis | None = None,
) -> AsyncRedisCacheBackend:
    """
    Create an async Redis cache backend.

    Args:
        redis_client: Custom async Redis client (optional)
        redis_config: Custom Redis configuration (optional)

    Returns:
        AsyncRedisCacheBackend instance
    """
    return AsyncRedisCacheBackend(config, redis_client=redis_client)


def create_cache_manager(
    name: str | None = None,
    config: ConfigBase | None = None,
    backend: CacheBackend | None = None,
    async_backend: AsyncCacheBackend | None = None,
    create_async_backend: bool = False,
) -> CacheManager:
    """
    Create a cache manager with sync backend.

    Args:
        name: Name of the cache manager (optional)
        config: Configuration object (optional, uses RedisConfig if not provided)
        create_async_backend: Whether to create an async backend as well (default: False)
        backend: Custom sync cache backend (optional)
        async_backend: Custom async cache backend (optional)

    Returns:
        CacheManager instance with sync backend
    """
    cache_config = config or RedisConfig()
    if backend is None:
        backend = create_backend_from_config(cache_config)
    if async_backend is None and create_async_backend:
        async_backend = create_async_backend_from_config(cache_config)
    return CacheManager(cache_config, name=name, backend=backend, async_backend=async_backend)


def create_redis_client_from_config(
    redis_config: RedisConfig | None = None,
) -> "redis.Redis":
    """Create a Redis client from configuration settings."""
    from .config import RedisConfig

    cfg = redis_config or RedisConfig()

    if cfg.url:
        # Merge additional kwargs with URL-based connection
        url_kwargs = {
            "decode_responses": True,
            "socket_timeout": cfg.socket_timeout,
            "max_connections": cfg.max_connections,
        }
        # Merge additional connection kwargs
        url_kwargs.update(cfg.additional_connection_kwargs)
        return redis.Redis.from_url(cfg.url, **url_kwargs)

    connection_kwargs = {
        "host": cfg.host,
        "port": cfg.port,
        "db": cfg.db,
        "decode_responses": True,
        "ssl": cfg.ssl,
        "max_connections": cfg.max_connections,
    }

    if cfg.password:
        connection_kwargs["password"] = cfg.password

    if cfg.username:
        connection_kwargs["username"] = cfg.username

    if cfg.socket_timeout:
        connection_kwargs["socket_timeout"] = cfg.socket_timeout

    # Merge additional connection kwargs
    connection_kwargs.update(cfg.additional_connection_kwargs)

    return redis.Redis(**connection_kwargs)


def create_async_redis_client_from_config(
    redis_config: RedisConfig | None = None,
) -> "redis.asyncio.Redis":
    """Create an async Redis client from configuration settings."""
    from .config import RedisConfig

    cfg = redis_config or RedisConfig()

    if cfg.url:
        # Merge additional kwargs with URL-based connection
        url_kwargs = {
            "decode_responses": True,
            "socket_timeout": cfg.socket_timeout,
            "max_connections": cfg.max_connections,
        }
        # Merge additional connection kwargs
        url_kwargs.update(cfg.additional_connection_kwargs)
        return async_redis.Redis.from_url(cfg.url, **url_kwargs)

    connection_kwargs = {
        "host": cfg.host,
        "port": cfg.port,
        "db": cfg.db,
        "decode_responses": True,
        "ssl": cfg.ssl,
        "max_connections": cfg.max_connections,
    }

    if cfg.password:
        connection_kwargs["password"] = cfg.password

    if cfg.username:
        connection_kwargs["username"] = cfg.username

    if cfg.socket_timeout:
        connection_kwargs["socket_timeout"] = cfg.socket_timeout

    # Merge additional connection kwargs
    connection_kwargs.update(cfg.additional_connection_kwargs)

    return async_redis.Redis(**connection_kwargs)
