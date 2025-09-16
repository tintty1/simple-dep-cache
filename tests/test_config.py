import os
from unittest.mock import patch

from simple_dep_cache.config import (
    Config,
    _str_to_bool,
    _str_to_int,
)


class TestConfig:
    def test_str_to_bool_true_values(self):
        assert _str_to_bool("true") is True
        assert _str_to_bool("True") is True
        assert _str_to_bool("1") is True
        assert _str_to_bool("yes") is True
        assert _str_to_bool("on") is True
        assert _str_to_bool(True) is True

    def test_str_to_bool_false_values(self):
        assert _str_to_bool("false") is False
        assert _str_to_bool("0") is False
        assert _str_to_bool("no") is False
        assert _str_to_bool("") is False
        assert _str_to_bool(False) is False

    def test_str_to_int_valid(self):
        assert _str_to_int("42", 0) == 42
        assert _str_to_int("0", 10) == 0

    def test_str_to_int_invalid(self):
        assert _str_to_int("invalid", 42) == 42
        assert _str_to_int("", 10) == 10

    @patch.dict(os.environ, {"DEP_CACHE_ENABLED": "false"})
    def test_cache_enabled_false(self):
        config = Config()
        assert config.cache_enabled is False

    @patch.dict(os.environ, {}, clear=True)
    def test_cache_enabled_default(self):
        config = Config()
        assert config.cache_enabled is True

    @patch.dict(os.environ, {"DEP_CACHE_CALLBACK_SILENT": "false"})
    def test_callback_error_silent_false(self):
        config = Config()
        assert config.callback_error_silent is False

    @patch.dict(os.environ, {"REDIS_URL": "redis://test:6379/1"})
    def test_redis_url(self):
        config = Config()
        assert config.redis_url == "redis://test:6379/1"

    @patch.dict(os.environ, {"REDIS_HOST": "test-host"})
    def test_redis_host(self):
        config = Config()
        assert config.redis_host == "test-host"

    @patch.dict(os.environ, {}, clear=True)
    def test_redis_host_default(self):
        config = Config()
        assert config.redis_host == "localhost"

    @patch.dict(os.environ, {"REDIS_PORT": "1234"})
    def test_redis_port(self):
        config = Config()
        assert config.redis_port == 1234

    @patch.dict(os.environ, {}, clear=True)
    def test_redis_port_default(self):
        config = Config()
        assert config.redis_port == 6379

    @patch.dict(os.environ, {"REDIS_DB": "5"})
    def test_redis_db(self):
        config = Config()
        assert config.redis_db == 5

    @patch.dict(os.environ, {"REDIS_PASSWORD": "secret"})
    def test_redis_password(self):
        config = Config()
        assert config.redis_password == "secret"

    @patch.dict(os.environ, {"REDIS_USERNAME": "user"})
    def test_redis_username(self):
        config = Config()
        assert config.redis_username == "user"

    @patch.dict(os.environ, {"REDIS_SSL": "true"})
    def test_redis_ssl(self):
        config = Config()
        assert config.redis_ssl is True

    @patch.dict(os.environ, {"REDIS_SOCKET_TIMEOUT": "30.5"})
    def test_redis_socket_timeout(self):
        config = Config()
        assert config.redis_socket_timeout == 30.5

    @patch.dict(os.environ, {"REDIS_SOCKET_TIMEOUT": "invalid"})
    def test_redis_socket_timeout_invalid(self):
        config = Config()
        assert config.redis_socket_timeout is None

    @patch.dict(os.environ, {"REDIS_MAX_CONNECTIONS": "100"})
    def test_redis_max_connections(self):
        config = Config()
        assert config.redis_connection_pool_max_connections == 100
