"""Tests for simple_dep_cache.manager module."""

import pytest

import simple_dep_cache.manager as manager_module
from simple_dep_cache.config import ConfigBase
from simple_dep_cache.events import CacheEventType
from simple_dep_cache.fakes import FakeAsyncCacheBackend, FakeCacheBackend
from simple_dep_cache.manager import CacheManager, get_or_create_cache_manager


class TestGetOrCreateCacheManager:
    """Test cases for get_or_create_cache_manager function."""

    def setup_method(self):
        """Reset the cache managers before each test."""
        manager_module._managers = {}

    def test_get_or_create_new_manager(self):
        """Test creating a new cache manager."""
        config = ConfigBase()
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        manager = get_or_create_cache_manager(name="test_manager", config=config, backend=backend)

        assert manager is not None
        assert manager.name == "test_manager"
        assert isinstance(manager, CacheManager)

    def test_get_or_create_new_manager_name_not_provided(self):
        """Test creating a new cache manager."""
        config = ConfigBase()
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        manager = get_or_create_cache_manager(config=config, backend=backend)

        assert manager is not None
        assert manager.name == config.prefix  # use prefix as name
        assert isinstance(manager, CacheManager)

    def test_get_existing_manager(self):
        """Test getting an existing cache manager."""
        config = ConfigBase()
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        # Create manager
        manager1 = get_or_create_cache_manager(name="test_manager", config=config, backend=backend)

        # Get same manager again
        manager2 = get_or_create_cache_manager(name="test_manager")

        assert manager1 is manager2

    def test_get_or_create_disabled_cache(self):
        """Test when cache is disabled."""
        config = ConfigBase()
        config.cache_enabled = False

        with pytest.warns(UserWarning, match="Caching is disabled in the configuration."):
            manager = get_or_create_cache_manager(name="test_manager", config=config)

        assert manager is None


class TestCacheManager:
    """Test cases for CacheManager class."""

    def test_manager_initialization(self):
        """Test manager initialization with sync backend."""
        config = ConfigBase()
        config.prefix = "test"
        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        assert manager.config is config
        assert manager.backend is backend
        assert manager.async_backend is None
        assert manager.prefix == "test"
        assert manager.name == "test"

    def test_manager_initialization_with_async_backend(self):
        """Test manager initialization with async backend."""
        config = ConfigBase()
        config.prefix = "test"
        async_backend = FakeAsyncCacheBackend(config)

        manager = CacheManager(config=config, async_backend=async_backend)

        assert manager.config is config
        assert manager.backend is None
        assert manager.async_backend is async_backend
        assert manager.prefix == "test"
        assert manager.name == "test"

    def test_manager_initialization_requires_backend(self):
        """Test that manager requires at least one backend."""
        config = ConfigBase()

        with pytest.raises(
            ValueError, match="Must specify either 'backend', 'async_backend', or both"
        ):
            CacheManager(config=config)

    def test_sync_operations(self):
        """Test sync cache operations."""
        config = ConfigBase()
        config.prefix = "test"
        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        # Test set and get
        manager.set("key1", "value1")
        assert manager.get("key1") == "value1"

        # Test with dependencies
        manager.set("key2", "value2", dependencies={"dep1"})
        assert manager.get("key2") == "value2"

        # Test exists
        assert manager.exists("key1") is True
        assert manager.exists("nonexistent") is False

        # Test delete
        count = manager.delete("key1")
        assert count == 1
        assert manager.get("key1") is None

        # Test clear - first clear existing cache
        manager.clear("*")
        manager.set("key3", "value3")
        count = manager.clear("*")
        assert count == 1
        assert manager.get("key3") is None

    def test_dependency_invalidation(self):
        """Test dependency invalidation."""
        config = ConfigBase()
        config.prefix = "test"
        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        # Set cache with dependencies
        manager.set("key1", "value1", dependencies={"dep1", "dep2"})
        manager.set("key2", "value2", dependencies={"dep2"})
        manager.set("key3", "value3", dependencies={"dep3"})

        # Invalidate dependency
        count = manager.invalidate_dependency("dep2")
        assert count == 2  # key1 and key2 should be invalidated

        # Check remaining cache
        assert manager.get("key1") is None
        assert manager.get("key2") is None
        assert manager.get("key3") == "value3"

    def test_sync_operations_require_sync_backend(self):
        """Test that sync operations require sync backend."""
        config = ConfigBase()
        async_backend = FakeAsyncCacheBackend(config)

        manager = CacheManager(config=config, async_backend=async_backend)

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.set("key", "value")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.get("key")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.delete("key")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.clear()

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.invalidate_dependency("dep")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.exists("key")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.ttl("key")

    def test_events(self):
        """Test event emission."""
        config = ConfigBase()
        config.prefix = "test"
        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        # Test event collection
        events = []
        manager.on_all_events(lambda event: events.append(event))

        # Set operation
        manager.set("key1", "value1", ttl=60, dependencies={"dep1"})
        assert len(events) == 1
        assert events[0].event_type == CacheEventType.SET
        assert events[0].key == "key1"
        assert events[0].value == "value1"
        assert events[0].ttl == 60
        assert events[0].dependencies == {"dep1"}

        # Get operation - cache hit
        manager.get("key1")
        assert len(events) == 2
        assert events[1].event_type == CacheEventType.HIT
        assert events[1].key == "key1"
        assert events[1].value == "value1"

        # Get operation - cache miss
        manager.get("nonexistent")
        assert len(events) == 3
        assert events[2].event_type == CacheEventType.MISS
        assert events[2].key == "nonexistent"

        # Delete operation
        manager.delete("key1")
        assert len(events) == 4
        assert events[3].event_type == CacheEventType.DELETE
        assert events[3].key == "key1"
        assert events[3].count == 1

        # Invalidate operation
        manager.set("key2", "value2", dependencies={"dep2"})
        manager.invalidate_dependency("dep2")
        assert len(events) == 6  # SET + INVALIDATE
        assert events[5].event_type == CacheEventType.INVALIDATE
        assert events[5].key == "dep2"
        assert events[5].count == 1

        # Clear operation
        manager.set("key3", "value3")
        manager.clear("*")
        assert len(events) == 8  # SET + CLEAR
        assert events[7].event_type == CacheEventType.CLEAR
        assert events[7].key == "*"
        assert events[7].count == 1


class TestAsyncCacheManager:
    """Test cases for async CacheManager operations."""

    @pytest.mark.asyncio
    async def test_async_operations(self):
        """Test async cache operations."""
        config = ConfigBase()
        config.prefix = "test"
        async_backend = FakeAsyncCacheBackend(config)

        manager = CacheManager(config=config, async_backend=async_backend)

        # Test set and get
        await manager.aset("key1", "value1")
        assert await manager.aget("key1") == "value1"

        # Test with dependencies
        await manager.aset("key2", "value2", dependencies={"dep1"})
        assert await manager.aget("key2") == "value2"

        # Test exists
        assert await manager.aexists("key1") is True
        assert await manager.aexists("nonexistent") is False

        # Test delete
        count = await manager.adelete("key1")
        assert count == 1
        assert await manager.aget("key1") is None

        # Test clear - first clear existing cache
        await manager.aclear("*")
        await manager.aset("key3", "value3")
        count = await manager.aclear("*")
        assert count == 1
        assert await manager.aget("key3") is None

    @pytest.mark.asyncio
    async def test_async_dependency_invalidation(self):
        """Test async dependency invalidation."""
        config = ConfigBase()
        config.prefix = "test"
        async_backend = FakeAsyncCacheBackend(config)

        manager = CacheManager(config=config, async_backend=async_backend)

        # Set cache with dependencies
        await manager.aset("key1", "value1", dependencies={"dep1", "dep2"})
        await manager.aset("key2", "value2", dependencies={"dep2"})
        await manager.aset("key3", "value3", dependencies={"dep3"})

        # Invalidate dependency
        count = await manager.ainvalidate_dependency("dep2")
        assert count == 2  # key1 and key2 should be invalidated

        # Check remaining cache
        assert await manager.aget("key1") is None
        assert await manager.aget("key2") is None
        assert await manager.aget("key3") == "value3"

    @pytest.mark.asyncio
    async def test_async_operations_fallback_to_sync(self):
        """Test that async operations fall back to sync backend when async backend
        is not available."""
        config = ConfigBase()
        config.prefix = "test"
        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        # These should work with warnings
        with pytest.warns(UserWarning, match="Using sync backend with async method"):
            await manager.aset("key1", "value1")
            result = await manager.aget("key1")
            assert result == "value1"

        with pytest.warns(UserWarning, match="Using sync backend with async method"):
            exists = await manager.aexists("key1")
            assert exists is True

        with pytest.warns(UserWarning, match="Using sync backend with async method"):
            ttl = await manager.attl("key1")
            assert ttl == -1

    @pytest.mark.asyncio
    async def test_async_operations_require_backend(self):
        """Test that async operations require at least one backend."""
        config = ConfigBase()

        backend = FakeCacheBackend(config)

        manager = CacheManager(config=config, backend=backend)

        manager.backend = None

        with pytest.raises(RuntimeError, match="No backend available"):
            await manager.aset("key", "value")

        with pytest.raises(RuntimeError, match="No backend available"):
            await manager.aget("key")

    @pytest.mark.asyncio
    async def test_async_close(self):
        """Test async close operation."""
        config = ConfigBase()
        config.prefix = "test"
        async_backend = FakeAsyncCacheBackend(config)

        manager = CacheManager(config=config, async_backend=async_backend)

        # This should not raise an error
        await manager.aclose()

        # Test with sync backend only (should not raise error)
        backend = FakeCacheBackend(config)
        manager2 = CacheManager(config=config, backend=backend)
        await manager2.aclose()  # Should work fine, just logs warning
