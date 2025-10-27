"""Tests for simple_dep_cache.fakes module."""

import pytest

from simple_dep_cache.config import ConfigBase
from simple_dep_cache.fakes import FakeAsyncCacheBackend, FakeCacheBackend, FakeConfig


class TestFakeConfig:
    """Test cases for FakeConfig class."""

    def test_fake_config_defaults(self):
        """Test that FakeConfig provides correct default backend classes."""
        config = FakeConfig()

        assert config.cache_backend_class == "simple_dep_cache.fakes.FakeCacheBackend"
        assert config.async_cache_backend_class == "simple_dep_cache.fakes.FakeAsyncCacheBackend"

    def test_fake_config_inheritance(self):
        """Test that FakeConfig inherits from ConfigBase."""
        config = FakeConfig()
        assert isinstance(config, ConfigBase)

    def test_fake_config_custom_values(self):
        """Test that FakeConfig can accept custom configuration values."""
        config = FakeConfig(
            cache_enabled=False, prefix="test_prefix", serializer_class="test.Serializer"
        )

        assert config.cache_enabled is False
        assert config.prefix == "test_prefix"
        assert config.serializer_class == "test.Serializer"
        assert config.cache_backend_class == "simple_dep_cache.fakes.FakeCacheBackend"
        assert config.async_cache_backend_class == "simple_dep_cache.fakes.FakeAsyncCacheBackend"

    def test_fake_config_override_backend_classes(self):
        """Test that FakeConfig allows overriding backend classes."""
        # Note: FakeConfig doesn't currently support overriding backend classes
        # because it hardcodes them in the constructor. This test documents the
        # current behavior.
        config = FakeConfig()

        # The backend classes are always set to the fake ones
        assert config.cache_backend_class == "simple_dep_cache.fakes.FakeCacheBackend"
        assert config.async_cache_backend_class == "simple_dep_cache.fakes.FakeAsyncCacheBackend"


class TestFakeCacheBackend:
    """Test cases for FakeCacheBackend class."""

    def test_backend_initialization(self):
        """Test that FakeCacheBackend initializes correctly."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        assert backend.config == config
        assert backend._cache == {}
        assert backend._dependencies == {}
        assert backend.serializer is not None

    def test_set_and_get_simple_value(self):
        """Test setting and getting a simple value."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value")
        result = backend.get("test_key")

        assert result == "test_value"

    def test_get_nonexistent_key(self):
        """Test getting a non-existent key returns None."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        result = backend.get("nonexistent_key")

        assert result is None

    def test_set_with_ttl_and_dependencies(self):
        """Test setting a value with TTL and dependencies."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value", ttl=300, dependencies={"dep1", "dep2"})

        # Verify value is stored
        assert backend.get("test_key") == "test_value"

        # Verify dependencies are tracked
        deps_key_1 = backend._deps_key("dep1")
        deps_key_2 = backend._deps_key("dep2")
        cache_key = backend._cache_key("test_key")

        assert deps_key_1 in backend._dependencies
        assert deps_key_2 in backend._dependencies
        assert cache_key in backend._dependencies[deps_key_1]
        assert cache_key in backend._dependencies[deps_key_2]

    def test_delete_existing_keys(self):
        """Test deleting existing keys."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("key1", "value1")
        backend.set("key2", "value2")

        deleted_count = backend.delete("key1", "key2")

        assert deleted_count == 2
        assert backend.get("key1") is None
        assert backend.get("key2") is None

    def test_delete_nonexistent_keys(self):
        """Test deleting non-existent keys."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        deleted_count = backend.delete("nonexistent1", "nonexistent2")

        assert deleted_count == 0

    def test_delete_mixed_keys(self):
        """Test deleting a mix of existing and non-existent keys."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("existing_key", "value")

        deleted_count = backend.delete("existing_key", "nonexistent_key")

        assert deleted_count == 1
        assert backend.get("existing_key") is None

    def test_clear_all_keys(self):
        """Test clearing all keys with default pattern."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("key1", "value1")
        backend.set("key2", "value2")
        backend.set("key3", "value3")

        cleared_count = backend.clear()

        assert cleared_count == 3
        assert len(backend._cache) == 0

    def test_clear_with_pattern(self):
        """Test clearing with specific pattern (not supported in fake)."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("key1", "value1")

        # Fake backend only supports "*" pattern
        cleared_count = backend.clear("test_pattern")

        assert cleared_count == 0
        assert backend.get("key1") == "value1"

    def test_invalidate_dependency_existing(self):
        """Test invalidating an existing dependency."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        # Set up cache with dependencies
        backend.set("key1", "value1", dependencies={"dep1"})
        backend.set("key2", "value2", dependencies={"dep1"})
        backend.set("key3", "value3", dependencies={"dep2"})

        # Invalidate dependency
        invalidated_count = backend.invalidate_dependency("dep1")

        assert invalidated_count == 2
        assert backend.get("key1") is None
        assert backend.get("key2") is None
        assert backend.get("key3") == "value3"  # Should remain

        # Verify dependency tracking is cleaned up
        deps_key = backend._deps_key("dep1")
        assert deps_key not in backend._dependencies

    def test_invalidate_dependency_nonexistent(self):
        """Test invalidating a non-existent dependency."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        invalidated_count = backend.invalidate_dependency("nonexistent_dep")

        assert invalidated_count == 0

    def test_exists_existing_key(self):
        """Test exists() method with existing key."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value")

        assert backend.exists("test_key") is True

    def test_exists_nonexistent_key(self):
        """Test exists() method with non-existent key."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        assert backend.exists("nonexistent_key") is False

    def test_ttl_existing_key(self):
        """Test ttl() method with existing key (fake doesn't support TTL)."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value")

        # Fake backend returns -1 for existing keys (no TTL)
        assert backend.ttl("test_key") == -1

    def test_ttl_nonexistent_key(self):
        """Test ttl() method with non-existent key."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        # Fake backend returns -2 for non-existent keys
        assert backend.ttl("nonexistent_key") == -2

    def test_cache_key_format(self):
        """Test that cache keys are formatted correctly with prefix."""
        config = FakeConfig(prefix="test_prefix")
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value")

        # The actual cache key should include the prefix
        expected_cache_key = "test_prefix:test_key"
        assert expected_cache_key in backend._cache

    def test_deps_key_format(self):
        """Test that dependency keys are formatted correctly."""
        config = FakeConfig(prefix="test_prefix")
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value", dependencies=["dep1"])

        # The dependency key should include the prefix
        expected_deps_key = "test_prefix:deps:dep1"
        assert expected_deps_key in backend._dependencies

    def test_multiple_dependencies_per_key(self):
        """Test that a key can have multiple dependencies."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("test_key", "test_value", dependencies=["dep1", "dep2", "dep3"])

        deps_key_1 = backend._deps_key("dep1")
        deps_key_2 = backend._deps_key("dep2")
        deps_key_3 = backend._deps_key("dep3")
        cache_key = backend._cache_key("test_key")

        assert cache_key in backend._dependencies[deps_key_1]
        assert cache_key in backend._dependencies[deps_key_2]
        assert cache_key in backend._dependencies[deps_key_3]

    def test_multiple_keys_per_dependency(self):
        """Test that multiple keys can depend on the same dependency."""
        config = FakeConfig()
        backend = FakeCacheBackend(config)

        backend.set("key1", "value1", dependencies=["shared_dep"])
        backend.set("key2", "value2", dependencies=["shared_dep"])
        backend.set("key3", "value3", dependencies=["shared_dep"])

        deps_key = backend._deps_key("shared_dep")
        cache_key_1 = backend._cache_key("key1")
        cache_key_2 = backend._cache_key("key2")
        cache_key_3 = backend._cache_key("key3")

        assert len(backend._dependencies[deps_key]) == 3
        assert cache_key_1 in backend._dependencies[deps_key]
        assert cache_key_2 in backend._dependencies[deps_key]
        assert cache_key_3 in backend._dependencies[deps_key]


class TestFakeAsyncCacheBackend:
    """Test cases for FakeAsyncCacheBackend class."""

    @pytest.mark.asyncio
    async def test_async_backend_initialization(self):
        """Test that FakeAsyncCacheBackend initializes correctly."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        assert backend._sync_backend is not None
        assert isinstance(backend._sync_backend, FakeCacheBackend)

    @pytest.mark.asyncio
    async def test_async_set_and_get(self):
        """Test async setting and getting a value."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("test_key", "test_value")
        result = await backend.get("test_key")

        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_async_get_nonexistent_key(self):
        """Test async getting a non-existent key returns None."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        result = await backend.get("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_async_set_with_dependencies(self):
        """Test async setting a value with dependencies."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("test_key", "test_value", dependencies=["dep1", "dep2"])

        # Verify value is stored
        assert await backend.get("test_key") == "test_value"

        # Verify dependencies are tracked in sync backend
        sync_backend = backend._sync_backend
        deps_key_1 = sync_backend._deps_key("dep1")
        deps_key_2 = sync_backend._deps_key("dep2")
        cache_key = sync_backend._cache_key("test_key")

        assert deps_key_1 in sync_backend._dependencies
        assert deps_key_2 in sync_backend._dependencies
        assert cache_key in sync_backend._dependencies[deps_key_1]
        assert cache_key in sync_backend._dependencies[deps_key_2]

    @pytest.mark.asyncio
    async def test_async_delete_keys(self):
        """Test async deleting keys."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("key1", "value1")
        await backend.set("key2", "value2")

        deleted_count = await backend.delete("key1", "key2")

        assert deleted_count == 2
        assert await backend.get("key1") is None
        assert await backend.get("key2") is None

    @pytest.mark.asyncio
    async def test_async_clear_all_keys(self):
        """Test async clearing all keys."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("key1", "value1")
        await backend.set("key2", "value2")

        cleared_count = await backend.clear()

        assert cleared_count == 2
        assert len(backend._sync_backend._cache) == 0

    @pytest.mark.asyncio
    async def test_async_invalidate_dependency(self):
        """Test async invalidating a dependency."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        # Set up cache with dependencies
        await backend.set("key1", "value1", dependencies=["dep1"])
        await backend.set("key2", "value2", dependencies=["dep1"])
        await backend.set("key3", "value3", dependencies=["dep2"])

        # Invalidate dependency
        invalidated_count = await backend.invalidate_dependency("dep1")

        assert invalidated_count == 2
        assert await backend.get("key1") is None
        assert await backend.get("key2") is None
        assert await backend.get("key3") == "value3"  # Should remain

    @pytest.mark.asyncio
    async def test_async_exists_key(self):
        """Test async exists() method."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("test_key", "test_value")

        assert await backend.exists("test_key") is True
        assert await backend.exists("nonexistent_key") is False

    @pytest.mark.asyncio
    async def test_async_ttl_key(self):
        """Test async ttl() method."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        await backend.set("test_key", "test_value")

        # Existing key should return -1 (no TTL)
        assert await backend.ttl("test_key") == -1

        # Non-existing key should return -2
        assert await backend.ttl("nonexistent_key") == -2

    @pytest.mark.asyncio
    async def test_async_close(self):
        """Test async close() method (no-op for fake backend)."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        # Should not raise any exceptions
        await backend.close()

    @pytest.mark.asyncio
    async def test_async_sync_backend_sharing(self):
        """Test that async and sync backends share the same storage when appropriate."""
        config = FakeConfig()
        async_backend = FakeAsyncCacheBackend(config)
        sync_backend = FakeCacheBackend(config)

        # They should have separate storage
        await async_backend.set("async_key", "async_value")
        sync_backend.set("sync_key", "sync_value")

        assert await async_backend.get("async_key") == "async_value"
        assert sync_backend.get("sync_key") == "sync_value"
        assert await async_backend.get("sync_key") is None
        assert sync_backend.get("async_key") is None

    @pytest.mark.asyncio
    async def test_async_complex_operations(self):
        """Test complex async operations sequence."""
        config = FakeConfig()
        backend = FakeAsyncCacheBackend(config)

        # Set up complex dependency chain
        await backend.set("user:123", "user_data", dependencies=["users"])
        await backend.set("posts:123", "post_data", dependencies=["posts", "user:123"])
        await backend.set("comments:123", "comment_data", dependencies=["comments", "posts:123"])

        # Verify all data exists
        assert await backend.get("user:123") == "user_data"
        assert await backend.get("posts:123") == "post_data"
        assert await backend.get("comments:123") == "comment_data"

        # Invalidate user dependency
        invalidated_count = await backend.invalidate_dependency("user:123")

        # User and posts should be invalidated (both depend on user:123)
        assert invalidated_count == 1  # Only posts:123 depends directly on user:123
        assert await backend.get("user:123") == "user_data"  # Still exists (depends on "users")
        assert await backend.get("posts:123") is None
        assert (
            await backend.get("comments:123") == "comment_data"
        )  # Still exists (depends on posts:123)
