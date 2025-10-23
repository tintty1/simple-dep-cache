"""Tests for simple_dep_cache.config module."""

import os
from unittest.mock import patch

from simple_dep_cache.config import ConfigBase, RedisConfig


class TestConfigBase:
    """Test cases for ConfigBase class."""

    def test_default_configuration_values(self):
        """Test that default configuration values are correct."""
        config = ConfigBase()

        # Test default values
        assert config.cache_enabled is True
        assert config.callback_error_silent is True
        assert config.serializer_class is None
        assert config.prefix == "cache"
        assert config.cache_backend_class is None
        assert config.async_cache_backend_class is None

    @patch.dict(
        os.environ,
        {
            "DEP_CACHE_ENABLED": "false",
            "DEP_CACHE_CALLBACK_SILENT": "false",
            "DEP_CACHE_SERIALIZER": "myapp.CustomSerializer",
            "DEP_CACHE_PREFIX": "myprefix",
            "DEP_CACHE_BACKEND_CLASS": "myapp.CustomBackend",
            "DEP_CACHE_ASYNC_BACKEND_CLASS": "myapp.CustomAsyncBackend",
        },
    )
    def test_configuration_from_environment(self):
        """Test that configuration reads from environment variables."""
        config = ConfigBase()

        assert config.cache_enabled is False
        assert config.callback_error_silent is False
        assert config.serializer_class == "myapp.CustomSerializer"
        assert config.prefix == "myprefix"
        assert config.cache_backend_class == "myapp.CustomBackend"
        assert config.async_cache_backend_class == "myapp.CustomAsyncBackend"

    def test_programmatic_configuration_override(self):
        """Test that configuration can be overridden programmatically."""
        config = ConfigBase()

        # Override values programmatically
        config.cache_enabled = False
        config.callback_error_silent = False
        config.serializer_class = "myapp.CustomSerializer"
        config.prefix = "myprefix"
        config.cache_backend_class = "myapp.CustomBackend"
        config.async_cache_backend_class = "myapp.CustomAsyncBackend"

        # Verify overrides
        assert config.cache_enabled is False
        assert config.callback_error_silent is False
        assert config.serializer_class == "myapp.CustomSerializer"
        assert config.prefix == "myprefix"
        assert config.cache_backend_class == "myapp.CustomBackend"
        assert config.async_cache_backend_class == "myapp.CustomAsyncBackend"

    @patch.dict(os.environ, {"DEP_CACHE_ENABLED": "false"})
    def test_programmatic_override_takes_precedence(self):
        """Test that programmatic values take precedence over environment variables."""
        config = ConfigBase()

        # Override programmatically after initialization
        config.cache_enabled = True

        # Should use programmatic value, not environment
        assert config.cache_enabled is True

    def test_to_dict(self):
        """Test configuration serialization to dictionary."""
        config = ConfigBase()
        config.cache_enabled = False
        config.prefix = "test"

        config_dict = config.to_dict()
        expected = {
            "cache_enabled": False,
            "callback_error_silent": True,
            "serializer_class": None,
            "prefix": "test",
            "cache_backend_class": None,
            "async_cache_backend_class": None,
        }

        assert config_dict == expected

    def test_reset(self):
        """Test configuration reset to environment values."""
        config = ConfigBase()

        # Override values
        config.cache_enabled = False
        config.prefix = "modified"

        # Reset should restore environment defaults
        config.reset()

        assert config.cache_enabled is True
        assert config.prefix == "cache"


class TestRedisConfig:
    """Test cases for RedisConfig class."""

    def test_default_redis_configuration(self):
        """Test that default Redis configuration values are correct."""
        config = RedisConfig()

        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.password is None
        assert config.username is None
        assert config.ssl is False
        assert config.socket_timeout is None
        assert config.max_connections == 50
        assert config.url is None

    @patch.dict(
        os.environ,
        {
            "REDIS_URL": "redis://test:6379/1",
            "REDIS_HOST": "test-host",
            "REDIS_PORT": "1234",
            "REDIS_DB": "5",
            "REDIS_PASSWORD": "secret",
            "REDIS_USERNAME": "user",
            "REDIS_SSL": "true",
            "REDIS_SOCKET_TIMEOUT": "30.5",
            "REDIS_MAX_CONNECTIONS": "100",
        },
    )
    def test_redis_configuration_from_environment(self):
        """Test that Redis configuration reads from environment variables."""
        config = RedisConfig()

        assert config.url == "redis://test:6379/1"
        assert config.host == "test-host"
        assert config.port == 1234
        assert config.db == 5
        assert config.password == "secret"
        assert config.username == "user"
        assert config.ssl is True
        assert config.socket_timeout == 30.5
        assert config.max_connections == 100

    def test_redis_programmatic_override(self):
        """Test that Redis configuration can be overridden programmatically."""
        config = RedisConfig()

        # Override values programmatically
        config.host = "custom-host"
        config.port = 9999
        config.db = 2
        config.password = "secret"
        config.username = "admin"
        config.ssl = True
        config.socket_timeout = 60.0
        config.max_connections = 200
        config.url = "redis://custom:9999/2"

        # Verify overrides
        assert config.host == "custom-host"
        assert config.port == 9999
        assert config.db == 2
        assert config.password == "secret"
        assert config.username == "admin"
        assert config.ssl is True
        assert config.socket_timeout == 60.0
        assert config.max_connections == 200
        assert config.url == "redis://custom:9999/2"

    def test_redis_to_dict_includes_base_config(self):
        """Test that RedisConfig.to_dict includes both base and Redis config."""
        config = RedisConfig()
        config.cache_enabled = False
        config.prefix = "redis-test"
        config.host = "redis-host"
        config.port = 9999

        config_dict = config.to_dict()

        # Should include base config
        assert config_dict["cache_enabled"] is False
        assert config_dict["prefix"] == "redis-test"

        # Should include Redis config
        assert config_dict["host"] == "redis-host"
        assert config_dict["port"] == 9999

    def test_redis_reset(self):
        """Test Redis configuration reset."""
        config = RedisConfig()

        # Override both base and Redis values
        config.cache_enabled = False
        config.host = "custom"
        config.port = 9999

        # Reset should restore all defaults
        config.reset()

        assert config.cache_enabled is True
        assert config.host == "localhost"
        assert config.port == 6379

    @patch.dict(os.environ, {"REDIS_SOCKET_TIMEOUT": "invalid"})
    def test_invalid_socket_timeout_handling(self):
        """Test handling of invalid socket timeout values."""
        config = RedisConfig()
        assert config.socket_timeout is None

    @patch.dict(os.environ, {"REDIS_PORT": "invalid"})
    def test_invalid_port_handling(self):
        """Test handling of invalid port values."""
        config = RedisConfig()
        assert config.port == 6379  # Should fall back to default
