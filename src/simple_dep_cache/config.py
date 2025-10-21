import os
from typing import TYPE_CHECKING, Any

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


def _str_to_float(value: str, default: float) -> float:
    """Convert string environment variable to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class ConfigBase:
    """Base configuration settings for simple_dep_cache with dynamic property support."""

    def __init__(self):
        self._cache_enabled: bool | None = None
        self._callback_error_silent: bool | None = None
        self._serializer_class: str | None = None

    @property
    def cache_enabled(self) -> bool:
        """Whether caching is enabled. Can be disabled with DEP_CACHE_ENABLED=false."""
        if self._cache_enabled is not None:
            return self._cache_enabled
        return _str_to_bool(os.getenv("DEP_CACHE_ENABLED", "true"))

    @cache_enabled.setter
    def cache_enabled(self, value: bool):
        """Set cache enabled status."""
        self._cache_enabled = bool(value)

    @property
    def callback_error_silent(self) -> bool:
        """Whether to silently ignore callback errors or print traceback.

        Set DEP_CACHE_CALLBACK_SILENT=false to print tracebacks.
        """
        if self._callback_error_silent is not None:
            return self._callback_error_silent
        return _str_to_bool(os.getenv("DEP_CACHE_CALLBACK_SILENT", "true"))

    @callback_error_silent.setter
    def callback_error_silent(self, value: bool):
        """Set callback error silent status."""
        self._callback_error_silent = bool(value)

    @property
    def serializer_class(self) -> str | None:
        """Serializer class to use for cache values. Default: simple_dep_cache.types.JSONSerializer

        Environment variable: DEP_CACHE_SERIALIZER

        Example: mypackage.CustomPickleSerializer
        The class must inherit from simple_dep_cache.types.BaseSerializer
        """
        if self._serializer_class is not None:
            return self._serializer_class
        return os.getenv("DEP_CACHE_SERIALIZER")

    @serializer_class.setter
    def serializer_class(self, value: str | None):
        """Set serializer class name."""
        self._serializer_class = value

    def reset(self) -> None:
        """Reset all configuration values to defaults (environment variables)."""
        self._cache_enabled = None
        self._callback_error_silent = None
        self._serializer_class = None

    def to_dict(self) -> dict[str, Any]:
        """Return current configuration as dictionary."""
        return {
            "cache_enabled": self.cache_enabled,
            "callback_error_silent": self.callback_error_silent,
            "serializer_class": self.serializer_class,
        }


class RedisConfig:
    """Redis-specific configuration settings."""

    def __init__(self):
        self._url: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._db: int | None = None
        self._password: str | None = None
        self._username: str | None = None
        self._ssl: bool | None = None
        self._socket_timeout: float | None = None
        self._max_connections: int | None = None

    @property
    def url(self) -> str | None:
        """Redis connection URL. Takes precedence over host/port/db settings.

        Example: redis://localhost:6379/0 or redis://user:pass@host:port/db
        Environment variable: REDIS_URL
        """
        if self._url is not None:
            return self._url
        return os.getenv("REDIS_URL")

    @url.setter
    def url(self, value: str | None):
        """Set Redis connection URL."""
        self._url = value

    @property
    def host(self) -> str:
        """Redis host. Default: localhost
        Environment variable: REDIS_HOST
        """
        if self._host is not None:
            return self._host
        return os.getenv("REDIS_HOST", "localhost")

    @host.setter
    def host(self, value: str):
        """Set Redis host."""
        self._host = value

    @property
    def port(self) -> int:
        """Redis port. Default: 6379
        Environment variable: REDIS_PORT
        """
        if self._port is not None:
            return self._port
        return _str_to_int(os.getenv("REDIS_PORT", "6379"), 6379)

    @port.setter
    def port(self, value: int):
        """Set Redis port."""
        self._port = int(value)

    @property
    def db(self) -> int:
        """Redis database number. Default: 0
        Environment variable: REDIS_DB
        """
        if self._db is not None:
            return self._db
        return _str_to_int(os.getenv("REDIS_DB", "0"), 0)

    @db.setter
    def db(self, value: int):
        """Set Redis database number."""
        self._db = int(value)

    @property
    def password(self) -> str | None:
        """Redis password. Default: None
        Environment variable: REDIS_PASSWORD
        """
        if self._password is not None:
            return self._password
        return os.getenv("REDIS_PASSWORD")

    @password.setter
    def password(self, value: str | None):
        """Set Redis password."""
        self._password = value

    @property
    def username(self) -> str | None:
        """Redis username (for Redis 6+). Default: None
        Environment variable: REDIS_USERNAME
        """
        if self._username is not None:
            return self._username
        return os.getenv("REDIS_USERNAME")

    @username.setter
    def username(self, value: str | None):
        """Set Redis username."""
        self._username = value

    @property
    def ssl(self) -> bool:
        """Whether to use SSL/TLS for Redis connection. Default: False
        Environment variable: REDIS_SSL
        """
        if self._ssl is not None:
            return self._ssl
        return _str_to_bool(os.getenv("REDIS_SSL", "false"))

    @ssl.setter
    def ssl(self, value: bool):
        """Set Redis SSL setting."""
        self._ssl = bool(value)

    @property
    def socket_timeout(self) -> float | None:
        """Redis socket timeout in seconds. Default: None
        Environment variable: REDIS_SOCKET_TIMEOUT
        """
        if self._socket_timeout is not None:
            return self._socket_timeout
        timeout_str = os.getenv("REDIS_SOCKET_TIMEOUT")
        if timeout_str:
            return _str_to_float(timeout_str, 0.0)
        return None

    @socket_timeout.setter
    def socket_timeout(self, value: float | None):
        """Set Redis socket timeout."""
        self._socket_timeout = float(value) if value is not None else None

    @property
    def max_connections(self) -> int:
        """Maximum connections in Redis connection pool. Default: 50
        Environment variable: REDIS_MAX_CONNECTIONS
        """
        if self._max_connections is not None:
            return self._max_connections
        return _str_to_int(os.getenv("REDIS_MAX_CONNECTIONS", "50"), 50)

    @max_connections.setter
    def max_connections(self, value: int):
        """Set maximum connections."""
        self._max_connections = int(value)

    def reset(self) -> None:
        """Reset all Redis configuration values to defaults (environment variables)."""
        self._url = None
        self._host = None
        self._port = None
        self._db = None
        self._password = None
        self._username = None
        self._ssl = None
        self._socket_timeout = None
        self._max_connections = None

    def to_dict(self) -> dict[str, Any]:
        """Return current Redis configuration as dictionary."""
        return {
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": self.password,
            "username": self.username,
            "ssl": self.ssl,
            "socket_timeout": self.socket_timeout,
            "max_connections": self.max_connections,
        }


class Config:
    """Main configuration class that combines base and Redis-specific settings."""

    def __init__(self):
        self.base = ConfigBase()
        self.redis = RedisConfig()

    # Delegate base properties
    @property
    def cache_enabled(self) -> bool:
        return self.base.cache_enabled

    @cache_enabled.setter
    def cache_enabled(self, value: bool):
        self.base.cache_enabled = value

    @property
    def callback_error_silent(self) -> bool:
        return self.base.callback_error_silent

    @callback_error_silent.setter
    def callback_error_silent(self, value: bool):
        self.base.callback_error_silent = value

    @property
    def serializer_class(self) -> str | None:
        return self.base.serializer_class

    @serializer_class.setter
    def serializer_class(self, value: str | None):
        self.base.serializer_class = value

    # Delegate Redis properties for backwards compatibility
    @property
    def redis_url(self) -> str | None:
        """Backwards compatibility property."""
        return self.redis.url

    @property
    def redis_host(self) -> str:
        """Backwards compatibility property."""
        return self.redis.host

    @property
    def redis_port(self) -> int:
        """Backwards compatibility property."""
        return self.redis.port

    @property
    def redis_db(self) -> int:
        """Backwards compatibility property."""
        return self.redis.db

    @property
    def redis_password(self) -> str | None:
        """Backwards compatibility property."""
        return self.redis.password

    @property
    def redis_username(self) -> str | None:
        """Backwards compatibility property."""
        return self.redis.username

    @property
    def redis_ssl(self) -> bool:
        """Backwards compatibility property."""
        return self.redis.ssl

    @property
    def redis_socket_timeout(self) -> float | None:
        """Backwards compatibility property."""
        return self.redis.socket_timeout

    @property
    def redis_connection_pool_max_connections(self) -> int:
        """Backwards compatibility property."""
        return self.redis.max_connections

    def reset(self) -> None:
        """Reset all configuration values to defaults."""
        self.base.reset()
        self.redis.reset()

    def to_dict(self) -> dict[str, Any]:
        """Return all configuration as dictionary."""
        return {
            "base": self.base.to_dict(),
            "redis": self.redis.to_dict(),
        }


def create_redis_client_from_config(
    redis_config: RedisConfig | None = None,
) -> "redis.Redis":
    """Create a Redis client from configuration settings."""
    import redis

    cfg = redis_config or RedisConfig()

    if cfg.url:
        return redis.Redis.from_url(
            cfg.url,
            decode_responses=True,
            socket_timeout=cfg.socket_timeout,
            max_connections=cfg.max_connections,
        )

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

    return redis.Redis(**connection_kwargs)


def create_async_redis_client_from_config(
    redis_config: RedisConfig | None = None,
) -> "redis.asyncio.Redis":
    """Create an async Redis client from configuration settings."""
    import redis.asyncio as async_redis

    cfg = redis_config or RedisConfig()

    if cfg.url:
        return async_redis.Redis.from_url(
            cfg.url,
            decode_responses=True,
            socket_timeout=cfg.socket_timeout,
            max_connections=cfg.max_connections,
        )

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

    return async_redis.Redis(**connection_kwargs)


# Global config instance
config = Config()
