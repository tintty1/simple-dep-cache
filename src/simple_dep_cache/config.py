import os
from typing import Any


def _str_to_bool(value: str | bool) -> bool:
    """Convert string environment variable to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes", "on"):
            return True
    return False


def _str_to_int(value: str, default: int | None = None) -> None | int:
    """Convert string environment variable to integer."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _str_to_float(value: str, default: float | None = None) -> None | float:
    """Convert string environment variable to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class ConfigBase:
    """Base configuration settings for simple_dep_cache with dynamic property support."""

    def __init__(
        self,
        cache_enabled: bool | None = None,
        callback_error_silent: bool | None = None,
        serializer_class: str | None = None,
        prefix: str | None = None,
        cache_backend_class: str | None = None,
        async_cache_backend_class: str | None = None,
    ):
        self._cache_enabled = cache_enabled
        self._callback_error_silent = callback_error_silent
        self._serializer_class = serializer_class
        self._prefix = prefix
        self._cache_backend_class = cache_backend_class
        self._async_cache_backend_class = async_cache_backend_class

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

    @property
    def prefix(self) -> str:
        """Cache key prefix. Default: cache
        Environment variable: DEP_CACHE_PREFIX
        """
        if self._prefix is not None:
            return self._prefix
        return os.getenv("DEP_CACHE_PREFIX", "cache")

    @prefix.setter
    def prefix(self, value: str):
        """Set cache key prefix."""
        self._prefix = value

    @property
    def cache_backend_class(self) -> str | None:
        """Cache backend class to use. Default: simple_dep_cache.redis_backends.RedisCacheBackend

        Environment variable: DEP_CACHE_BACKEND_CLASS

        Example: mypackage.CustomBackend
        The class must inherit from simple_dep_cache.backends.CacheBackend
        """
        if self._cache_backend_class is not None:
            return self._cache_backend_class
        return os.getenv("DEP_CACHE_BACKEND_CLASS")

    @cache_backend_class.setter
    def cache_backend_class(self, value: str | None):
        """Set cache backend class name."""
        self._cache_backend_class = value

    @property
    def async_cache_backend_class(self) -> str | None:
        """Async cache backend class to use.
        Default: simple_dep_cache.redis_backends.AsyncRedisCacheBackend

        Environment variable: DEP_CACHE_ASYNC_BACKEND_CLASS

        Example: mypackage.CustomAsyncBackend
        The class must inherit from simple_dep_cache.backends.AsyncCacheBackend
        """
        if self._async_cache_backend_class is not None:
            return self._async_cache_backend_class
        return os.getenv("DEP_CACHE_ASYNC_BACKEND_CLASS")

    @async_cache_backend_class.setter
    def async_cache_backend_class(self, value: str | None):
        """Set async cache backend class name."""
        self._async_cache_backend_class = value

    def reset(self) -> None:
        """Reset all configuration values to defaults (environment variables)."""
        self._cache_enabled = None
        self._callback_error_silent = None
        self._serializer_class = None
        self._prefix = None
        self._cache_backend_class = None
        self._async_cache_backend_class = None

    def to_dict(self) -> dict[str, Any]:
        """Return current configuration as dictionary."""
        return {
            "cache_enabled": self.cache_enabled,
            "callback_error_silent": self.callback_error_silent,
            "serializer_class": self.serializer_class,
            "prefix": self.prefix,
            "cache_backend_class": self.cache_backend_class,
            "async_cache_backend_class": self.async_cache_backend_class,
        }


class RedisConfig(ConfigBase):
    """Redis-specific configuration settings."""

    def __init__(
        self,
        cache_enabled: bool | None = None,
        callback_error_silent: bool | None = None,
        serializer_class: str | None = None,
        prefix: str | None = None,
        cache_backend_class: str | None = None,
        async_cache_backend_class: str | None = None,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        db: int | None = None,
        password: str | None = None,
        username: str | None = None,
        ssl: bool | None = None,
        socket_timeout: float | None = None,
        max_connections: int | None = None,
        **additional_connection_kwargs,
    ):
        super().__init__(
            cache_enabled=cache_enabled,
            callback_error_silent=callback_error_silent,
            serializer_class=serializer_class,
            prefix=prefix,
            cache_backend_class=cache_backend_class,
            async_cache_backend_class=async_cache_backend_class,
        )
        self._url = url
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._username = username
        self._ssl = ssl
        self._socket_timeout = socket_timeout
        self._max_connections = max_connections
        self._additional_connection_kwargs = additional_connection_kwargs

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
        return _str_to_int(os.getenv("REDIS_PORT", "6379")) or 6379

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
        return _str_to_int(os.getenv("REDIS_DB", "0")) or 0

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
        if not timeout_str:
            return None
        return _str_to_float(timeout_str, None)

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
        return _str_to_int(os.getenv("REDIS_MAX_CONNECTIONS", "50")) or 50

    @max_connections.setter
    def max_connections(self, value: int):
        """Set maximum connections."""
        self._max_connections = int(value)

    @property
    def additional_connection_kwargs(self) -> dict[str, Any]:
        """Additional keyword arguments to pass to Redis client connection.

        These kwargs will be merged with the standard Redis connection parameters.
        Can be used for advanced Redis configuration options.
        """
        return getattr(self, "_additional_connection_kwargs", {})

    @additional_connection_kwargs.setter
    def additional_connection_kwargs(self, value: dict[str, Any]):
        """Set additional connection kwargs."""
        self._additional_connection_kwargs = dict(value) if value is not None else {}

    def reset(self) -> None:
        """Reset all Redis configuration values to defaults (environment variables)."""
        super().reset()
        self._url = None
        self._host = None
        self._port = None
        self._db = None
        self._password = None
        self._username = None
        self._ssl = None
        self._socket_timeout = None
        self._max_connections = None
        self._additional_connection_kwargs = {}

    def to_dict(self) -> dict[str, Any]:
        """Return current Redis configuration as dictionary, merging with base config."""
        base_config = super().to_dict()
        redis_config = {
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": self.password,
            "username": self.username,
            "ssl": self.ssl,
            "socket_timeout": self.socket_timeout,
            "max_connections": self.max_connections,
            "additional_connection_kwargs": self.additional_connection_kwargs,
        }
        # Merge base config with Redis-specific config
        return {**base_config, **redis_config}
