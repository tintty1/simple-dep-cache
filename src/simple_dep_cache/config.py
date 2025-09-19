import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis
    import redis.asyncio


def _str_to_bool(value: str | bool) -> bool:
    """Convert string environment variable to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes", "on"):
            return True
    return False


def _str_to_int(value: str, default: int) -> int:
    """Convert string environment variable to integer."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class Config:
    """Configuration settings for simple_dep_cache."""

    @property
    def cache_enabled(self) -> bool:
        """Whether caching is enabled. Can be disabled with DEP_CACHE_ENABLED=false."""
        return _str_to_bool(os.getenv("DEP_CACHE_ENABLED", "true"))

    @property
    def callback_error_silent(self) -> bool:
        """Whether to silently ignore callback errors or print traceback.

        Set DEP_CACHE_CALLBACK_SILENT=false to print tracebacks.
        """
        return _str_to_bool(os.getenv("DEP_CACHE_CALLBACK_SILENT", "true"))

    @property
    def redis_url(self) -> str | None:
        """Redis connection URL. Takes precedence over host/port/db settings.

        Example: redis://localhost:6379/0 or redis://user:pass@host:port/db
        Environment variable: REDIS_URL
        """
        return os.getenv("REDIS_URL")

    @property
    def redis_host(self) -> str:
        """Redis host. Default: localhost
        Environment variable: REDIS_HOST
        """
        return os.getenv("REDIS_HOST", "localhost")

    @property
    def redis_port(self) -> int:
        """Redis port. Default: 6379
        Environment variable: REDIS_PORT
        """
        return _str_to_int(os.getenv("REDIS_PORT", "6379"), 6379)

    @property
    def redis_db(self) -> int:
        """Redis database number. Default: 0
        Environment variable: REDIS_DB
        """
        return _str_to_int(os.getenv("REDIS_DB", "0"), 0)

    @property
    def redis_password(self) -> str | None:
        """Redis password. Default: None
        Environment variable: REDIS_PASSWORD
        """
        return os.getenv("REDIS_PASSWORD")

    @property
    def redis_username(self) -> str | None:
        """Redis username (for Redis 6+). Default: None
        Environment variable: REDIS_USERNAME
        """
        return os.getenv("REDIS_USERNAME")

    @property
    def redis_ssl(self) -> bool:
        """Whether to use SSL/TLS for Redis connection. Default: False
        Environment variable: REDIS_SSL
        """
        return _str_to_bool(os.getenv("REDIS_SSL", "false"))

    @property
    def redis_socket_timeout(self) -> float | None:
        """Redis socket timeout in seconds. Default: None
        Environment variable: REDIS_SOCKET_TIMEOUT
        """
        timeout_str = os.getenv("REDIS_SOCKET_TIMEOUT")
        if timeout_str:
            try:
                return float(timeout_str)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def redis_connection_pool_max_connections(self) -> int:
        """Maximum connections in Redis connection pool. Default: 50
        Environment variable: REDIS_MAX_CONNECTIONS
        """
        return _str_to_int(os.getenv("REDIS_MAX_CONNECTIONS", "50"), 50)

    @property
    def serializer_class(self) -> str | None:
        """Serializer class to use for cache values. Default: simple_dep_cache.types.JSONSerializer
        Environment variable: DEP_CACHE_SERIALIZER

        Example: mypackage.CustomPickleSerializer
        The class must inherit from simple_dep_cache.types.BaseSerializer
        """
        return os.getenv("DEP_CACHE_SERIALIZER")


def create_redis_client_from_config(
    config_instance: Config | None = None,
) -> "redis.Redis":
    """Create a Redis client from configuration settings."""
    import redis

    cfg = config_instance or config

    if cfg.redis_url:
        return redis.Redis.from_url(
            cfg.redis_url,
            decode_responses=True,
            socket_timeout=cfg.redis_socket_timeout,
            max_connections=cfg.redis_connection_pool_max_connections,
        )

    connection_kwargs = {
        "host": cfg.redis_host,
        "port": cfg.redis_port,
        "db": cfg.redis_db,
        "decode_responses": True,
        "ssl": cfg.redis_ssl,
        "max_connections": cfg.redis_connection_pool_max_connections,
    }

    if cfg.redis_password:
        connection_kwargs["password"] = cfg.redis_password

    if cfg.redis_username:
        connection_kwargs["username"] = cfg.redis_username

    if cfg.redis_socket_timeout:
        connection_kwargs["socket_timeout"] = cfg.redis_socket_timeout

    return redis.Redis(**connection_kwargs)


def create_async_redis_client_from_config(
    config_instance: Config | None = None,
) -> "redis.asyncio.Redis":
    """Create an async Redis client from configuration settings."""
    import redis.asyncio as async_redis

    cfg = config_instance or config

    if cfg.redis_url:
        return async_redis.Redis.from_url(
            cfg.redis_url,
            decode_responses=True,
            socket_timeout=cfg.redis_socket_timeout,
            max_connections=cfg.redis_connection_pool_max_connections,
        )

    connection_kwargs = {
        "host": cfg.redis_host,
        "port": cfg.redis_port,
        "db": cfg.redis_db,
        "decode_responses": True,
        "ssl": cfg.redis_ssl,
        "max_connections": cfg.redis_connection_pool_max_connections,
    }

    if cfg.redis_password:
        connection_kwargs["password"] = cfg.redis_password

    if cfg.redis_username:
        connection_kwargs["username"] = cfg.redis_username

    if cfg.redis_socket_timeout:
        connection_kwargs["socket_timeout"] = cfg.redis_socket_timeout

    return async_redis.Redis(**connection_kwargs)


# Global config instance
config = Config()
