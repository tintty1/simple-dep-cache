"""Tests for simple_dep_cache.redis_backends module."""

import fakeredis
import pytest

from simple_dep_cache.config import RedisConfig
from simple_dep_cache.redis_backends import RedisCacheBackend


class TestRedisCacheBackend:
    """Test cases for RedisCacheBackend class."""

    @pytest.fixture
    def config(self):
        """Create a RedisConfig instance for testing."""
        config = RedisConfig()
        config.cache_enabled = True
        return config

    @pytest.fixture
    def fake_redis(self):
        """Create a fake Redis client for testing."""
        return fakeredis.FakeRedis()

    @pytest.fixture
    def backend(self, config, fake_redis):
        """Create a RedisCacheBackend instance with fake Redis."""
        return RedisCacheBackend(config, redis_client=fake_redis)

    def test_cache_key_generation(self, backend):
        """Test that cache keys are generated with correct prefix."""
        backend.prefix = "test"
        assert backend._cache_key("mykey") == "test:mykey"

    def test_deps_key_generation(self, backend):
        """Test that dependency keys are generated with correct prefix."""
        backend.prefix = "test"
        assert backend._deps_key("mydep") == "test:deps:mydep"

    def test_set_and_get_simple_value(self, backend):
        """Test setting and getting a simple value."""
        backend.set("test_key", "test_value")
        result = backend.get("test_key")
        assert result == "test_value"

    def test_get_nonexistent_key(self, backend):
        """Test getting a key that doesn't exist."""
        result = backend.get("nonexistent_key")
        assert result is None

    def test_set_and_get_complex_value(self, backend):
        """Test setting and getting a complex value."""
        complex_data = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        backend.set("complex_key", complex_data)
        result = backend.get("complex_key")
        assert result == complex_data

    def test_set_with_ttl(self, backend, fake_redis):
        """Test setting a value with TTL."""
        backend.set("ttl_key", "ttl_value", ttl=60)

        # Key should exist initially
        assert backend.exists("ttl_key") is True
        assert backend.get("ttl_key") == "ttl_value"

        # Mock the passage of time by deleting the key
        fake_redis.delete("cache:ttl_key")
        assert backend.exists("ttl_key") is False

    def test_set_with_dependencies(self, backend):
        """Test setting a value with dependencies."""
        backend.set("key1", "value1", dependencies={"dep1", "dep2"})
        backend.set("key2", "value2", dependencies={"dep1"})

        # Both keys should exist
        assert backend.get("key1") == "value1"
        assert backend.get("key2") == "value2"

        # Invalidate dependency
        count = backend.invalidate_dependency("dep1")

        # Both keys should be invalidated
        assert count == 2  # Both keys depended on dep1
        assert backend.get("key1") is None
        assert backend.get("key2") is None

    def test_set_with_ttl_and_dependencies(self, backend, fake_redis):
        """Test setting a value with both TTL and dependencies."""
        backend.set("key", "value", ttl=60, dependencies={"dep1"})

        # Key should exist
        assert backend.exists("key") is True

        # Dependency tracking key should also exist (Redis exists returns 1 for True)
        deps_key = backend._deps_key("dep1")
        assert fake_redis.exists(deps_key) == 1

    def test_delete_single_key(self, backend):
        """Test deleting a single key."""
        backend.set("test_key", "test_value")
        assert backend.exists("test_key") is True

        count = backend.delete("test_key")
        assert count == 1
        assert backend.exists("test_key") is False

    def test_delete_multiple_keys(self, backend):
        """Test deleting multiple keys."""
        backend.set("key1", "value1")
        backend.set("key2", "value2")
        backend.set("key3", "value3")

        count = backend.delete("key1", "key3")
        assert count == 2
        assert backend.exists("key1") is False
        assert backend.exists("key3") is False  # Should be deleted
        assert backend.exists("key2") is True  # Should still exist

    def test_clear_with_pattern(self, backend):
        """Test clearing keys matching a pattern."""
        backend.set("test:1", "value1")
        backend.set("test:2", "value2")
        backend.set("other:1", "value3")

        count = backend.clear("test:*")
        assert count == 2
        assert backend.exists("test:1") is False
        assert backend.exists("test:2") is False
        assert backend.exists("other:1") is True

    def test_clear_all(self, backend):
        """Test clearing all keys."""
        backend.set("key1", "value1")
        backend.set("key2", "value2")

        count = backend.clear("*")
        assert count == 2
        assert backend.exists("key1") is False
        assert backend.exists("key2") is False

    def test_exists(self, backend):
        """Test checking if a key exists."""
        assert backend.exists("nonexistent") is False

        backend.set("existing", "value")
        assert backend.exists("existing") is True

    def test_ttl(self, backend):
        """Test getting TTL for a key."""
        # Test non-existent key
        assert backend.ttl("nonexistent") == -2

        # Test key without TTL
        backend.set("persistent_key", "value")
        assert backend.ttl("persistent_key") == -1

        # Test key with TTL
        backend.set("ttl_key", "value", ttl=60)
        # TTL might be slightly less due to timing, so check that it's positive
        assert backend.ttl("ttl_key") > 0

    def test_invalidate_nonexistent_dependency(self, backend):
        """Test invalidating a dependency that doesn't exist."""
        count = backend.invalidate_dependency("nonexistent_dep")
        assert count == 0

    def test_disabled_cache_behavior(self, config):
        """Test behavior when cache is disabled."""
        config.cache_enabled = False
        backend = RedisCacheBackend(config)

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            backend.set("key", "value")

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            backend.get("key")
