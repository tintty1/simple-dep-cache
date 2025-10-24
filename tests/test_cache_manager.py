"""Tests for simple_dep_cache.manager module."""

from unittest.mock import MagicMock

import pytest

from simple_dep_cache.backends import AsyncCacheBackend, CacheBackend
from simple_dep_cache.config import ConfigBase
from simple_dep_cache.events import CacheEventType
from simple_dep_cache.manager import CacheManager, get_or_create_cache_manager


class FakeCacheBackend(CacheBackend):
    """A simple in-memory fake backend for testing."""

    def __init__(self, config: ConfigBase):
        super().__init__(config)
        self._storage = {}
        self._deps_storage = {}
        self._disabled = not config.cache_enabled

    def set(self, key: str, value, ttl: int = None, dependencies: set = None) -> None:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        self._storage[self._cache_key(key)] = {
            "value": value,
            "ttl": ttl,
            "dependencies": dependencies or set(),
        }

        # Track dependencies
        if dependencies:
            for dep in dependencies:
                deps_key = self._deps_key(dep)
                if deps_key not in self._deps_storage:
                    self._deps_storage[deps_key] = set()
                self._deps_storage[deps_key].add(self._cache_key(key))

    def get(self, key: str):
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        return self._storage.get(self._cache_key(key), {}).get("value")

    def delete(self, *keys: str) -> int:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        count = 0
        for key in keys:
            cache_key = self._cache_key(key)
            if cache_key in self._storage:
                del self._storage[cache_key]
                count += 1
        return count

    def clear(self, pattern: str = "*") -> int:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        if pattern == "*":
            count = len(self._storage)
            self._storage.clear()
            return count
        # Simple pattern matching - match prefixes for testing
        # Need to account for the cache prefix
        prefix = pattern.rstrip("*")
        # Convert pattern to full key pattern with cache prefix
        full_pattern = f"{self.prefix}:{prefix}"
        count = 0
        keys_to_delete = []
        for key in self._storage:
            if key.startswith(full_pattern):
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del self._storage[key]
            count += 1
        return count

    def exists(self, key: str) -> bool:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        return self._cache_key(key) in self._storage

    def ttl(self, key: str) -> int:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        cache_key = self._cache_key(key)
        if cache_key not in self._storage:
            return -2
        ttl = self._storage[cache_key].get("ttl")
        return ttl if ttl is not None else -1

    def invalidate_dependency(self, dependency: str) -> int:
        if self._disabled:
            raise RuntimeError("Cache is disabled")
        deps_key = self._deps_key(dependency)
        if deps_key not in self._deps_storage:
            return 0

        keys_to_delete = self._deps_storage[deps_key]
        count = 0
        for cache_key in keys_to_delete:
            if cache_key in self._storage:
                del self._storage[cache_key]
                count += 1

        # Clear the dependency tracking
        del self._deps_storage[deps_key]

        # Remove this dependency from all key dependency sets
        for dep_key in self._deps_storage:
            self._deps_storage[dep_key].discard(dependency)

        return count


class FakeAsyncCacheBackend(AsyncCacheBackend):
    """A simple in-memory fake async backend for testing that wraps the sync backend."""

    def __init__(self, config: ConfigBase):
        super().__init__(config)
        self._sync_backend = FakeCacheBackend(config)

    async def set(self, key: str, value, ttl: int = None, dependencies: set = None) -> None:
        return self._sync_backend.set(key, value, ttl, dependencies)

    async def get(self, key: str):
        return self._sync_backend.get(key)

    async def delete(self, *keys: str) -> int:
        return self._sync_backend.delete(*keys)

    async def clear(self, pattern: str = "*") -> int:
        return self._sync_backend.clear(pattern)

    async def exists(self, key: str) -> bool:
        return self._sync_backend.exists(key)

    async def ttl(self, key: str) -> int:
        return self._sync_backend.ttl(key)

    async def invalidate_dependency(self, dependency: str) -> int:
        return self._sync_backend.invalidate_dependency(dependency)


class TestGetOrCreateCacheManager:
    """Test cases for get_or_create_cache_manager function."""

    def test_get_or_create_new_manager(self):
        """Test creating a new cache manager."""
        config = ConfigBase()
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        manager = get_or_create_cache_manager(name="test_manager", config=config, backend=backend)

        assert manager is not None
        assert manager.name == "test_manager"
        assert isinstance(manager, CacheManager)

    def test_get_existing_manager(self):
        """Test getting an existing cache manager."""
        config = ConfigBase()
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        # Create first manager
        manager1 = get_or_create_cache_manager(name="test_manager", config=config, backend=backend)

        # Get same manager again
        manager2 = get_or_create_cache_manager(
            name="test_manager",
            config=config,  # This should be ignored
            backend=backend,  # This should be ignored
        )

        assert manager1 is manager2
        assert manager1.config is manager2.config

    def test_cache_disabled_returns_none(self):
        """Test that disabled cache returns None."""
        config = ConfigBase()
        config.cache_enabled = False

        with pytest.warns(UserWarning, match="Caching is disabled"):
            manager = get_or_create_cache_manager(config=config)
            assert manager is None

    def test_auto_name_from_config(self):
        """Test that manager name defaults to config prefix when not provided."""
        config = ConfigBase()
        config.prefix = "custom_prefix"
        config.cache_enabled = True
        backend = FakeCacheBackend(config)

        manager = get_or_create_cache_manager(config=config, backend=backend)

        assert manager.name == "custom_prefix"


class TestCacheManager:
    """Test cases for CacheManager class."""

    @pytest.fixture
    def config(self):
        """Create a ConfigBase instance for testing."""
        config = ConfigBase()
        config.cache_enabled = True
        return config

    @pytest.fixture
    def backend(self, config):
        """Create a FakeCacheBackend instance for testing."""
        return FakeCacheBackend(config)

    @pytest.fixture
    def manager(self, config, backend):
        """Create a CacheManager instance for testing."""
        return CacheManager(config=config, backend=backend)

    def test_manager_properties(self, manager):
        """Test manager properties."""
        assert manager.name == manager.prefix
        assert manager.config is not None
        assert manager.backend is not None

    def test_set_and_get_round_trip(self, manager):
        """Test that set/get operations work as expected."""
        # Set a value
        manager.set("test_key", "test_value")

        # Get the value back
        result = manager.get("test_key")
        assert result == "test_value"

    def test_get_nonexistent_key(self, manager):
        """Test getting a key that doesn't exist."""
        result = manager.get("nonexistent_key")
        assert result is None

    def test_set_with_ttl(self, manager):
        """Test setting a value with TTL."""
        manager.set("ttl_key", "ttl_value", ttl=60)

        # Key should exist
        assert manager.exists("ttl_key") is True

        # TTL should be positive
        ttl = manager.ttl("ttl_key")
        assert ttl == 60

    def test_set_with_dependencies(self, manager):
        """Test setting a value with dependencies."""
        manager.set("key1", "value1", dependencies={"dep1", "dep2"})
        manager.set("key2", "value2", dependencies={"dep1"})

        # Both keys should exist
        assert manager.get("key1") == "value1"
        assert manager.get("key2") == "value2"

        # Invalidate dependency
        count = manager.invalidate_dependency("dep1")
        assert count == 2  # Both keys depended on dep1

        # Both keys should be invalidated
        assert manager.get("key1") is None
        assert manager.get("key2") is None

    def test_delete_operations(self, manager):
        """Test delete operations."""
        manager.set("key1", "value1")
        manager.set("key2", "value2")
        manager.set("key3", "value3")

        # Delete single key
        count = manager.delete("key1")
        assert count == 1
        assert manager.get("key1") is None
        assert manager.get("key2") == "value2"

        # Delete multiple keys
        count = manager.delete("key2", "key3")
        assert count == 2
        assert manager.get("key2") is None
        assert manager.get("key3") is None

    def test_clear_operations(self, manager):
        """Test clear operations."""
        manager.set("test:1", "value1")
        manager.set("test:2", "value2")
        manager.set("other:1", "value3")

        # Clear with pattern
        count = manager.clear("test:*")
        assert count == 2
        assert manager.get("test:1") is None
        assert manager.get("test:2") is None
        assert manager.get("other:1") == "value3"

        # Clear all
        count = manager.clear("*")
        assert count == 1
        assert manager.get("other:1") is None

    def test_exists_operations(self, manager):
        """Test exists operations."""
        assert manager.exists("nonexistent") is False

        manager.set("existing", "value")
        assert manager.exists("existing") is True

    def test_ttl_operations(self, manager):
        """Test TTL operations."""
        # Non-existent key
        assert manager.ttl("nonexistent") == -2

        # Key without TTL
        manager.set("persistent_key", "value")
        assert manager.ttl("persistent_key") == -1

        # Key with TTL
        manager.set("ttl_key", "value", ttl=60)
        ttl = manager.ttl("ttl_key")
        assert ttl == 60

    def test_invalidate_nonexistent_dependency(self, manager):
        """Test invalidating a dependency that doesn't exist."""
        count = manager.invalidate_dependency("nonexistent_dep")
        assert count == 0

    def test_no_sync_backend_error(self, config):
        """Test error when no sync backend is available."""
        # Create a mock async backend to satisfy the requirement
        mock_async_backend = MagicMock()
        manager = CacheManager(config=config, backend=None, async_backend=mock_async_backend)

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.set("key", "value")

        with pytest.raises(RuntimeError, match="No sync backend available"):
            manager.get("key")

    def test_event_emission_on_set(self, manager):
        """Test that events are emitted on set operations."""
        events = []

        def event_handler(event):
            events.append(event)

        manager.on_event(CacheEventType.SET, event_handler)

        manager.set("test_key", "test_value", ttl=60, dependencies={"dep1"})

        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.SET
        assert event.key == "test_key"
        assert event.value == "test_value"
        assert event.ttl == 60
        assert event.dependencies == {"dep1"}

    def test_event_emission_on_hit_and_miss(self, manager):
        """Test that hit/miss events are emitted correctly."""
        events = []

        def event_handler(event):
            events.append(event)

        manager.on_event(CacheEventType.HIT, event_handler)
        manager.on_event(CacheEventType.MISS, event_handler)

        # Set a value
        manager.set("test_key", "test_value")

        # Get existing value - should emit HIT
        result = manager.get("test_key")
        assert result == "test_value"

        # Get non-existing value - should emit MISS
        result = manager.get("nonexistent")
        assert result is None

        # Should have one HIT and one MISS
        hit_events = [e for e in events if e.event_type == CacheEventType.HIT]
        miss_events = [e for e in events if e.event_type == CacheEventType.MISS]

        assert len(hit_events) == 1
        assert len(miss_events) == 1
        assert hit_events[0].key == "test_key"
        assert miss_events[0].key == "nonexistent"

    def test_event_emission_on_delete(self, manager):
        """Test that events are emitted on delete operations."""
        events = []

        def event_handler(event):
            events.append(event)

        manager.on_event(CacheEventType.DELETE, event_handler)

        manager.set("key1", "value1")
        manager.set("key2", "value2")

        manager.delete("key1", "key2")

        # Should emit delete events for both keys
        delete_events = [e for e in events if e.event_type == CacheEventType.DELETE]
        assert len(delete_events) == 2
        assert delete_events[0].key == "key1"
        assert delete_events[1].key == "key2"

    def test_event_emission_on_clear(self, manager):
        """Test that events are emitted on clear operations."""
        events = []

        def event_handler(event):
            events.append(event)

        manager.on_event(CacheEventType.CLEAR, event_handler)

        manager.set("test:1", "value1")
        manager.set("test:2", "value2")

        count = manager.clear("test:*")
        assert count == 2

        # Should emit one clear event
        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.CLEAR
        assert event.key == "test:*"
        assert event.count == 2

    def test_event_emission_on_invalidate(self, manager):
        """Test that events are emitted on dependency invalidation."""
        events = []

        def event_handler(event):
            events.append(event)

        manager.on_event(CacheEventType.INVALIDATE, event_handler)

        manager.set("key1", "value1", dependencies={"dep1"})
        manager.set("key2", "value2", dependencies={"dep1"})

        count = manager.invalidate_dependency("dep1")
        assert count == 2

        # Should emit one invalidate event
        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.INVALIDATE
        assert event.key == "dep1"
        assert event.count == 2

    def test_event_callback_management(self, manager):
        """Test adding and removing event callbacks."""
        events = []

        def event_handler(event):
            events.append(event)

        # Add callback
        manager.on_event(CacheEventType.SET, event_handler)

        manager.set("test_key", "test_value")
        assert len(events) == 1

        # Remove callback
        removed = manager.remove_event_callback(CacheEventType.SET, event_handler)
        assert removed is True

        manager.set("test_key2", "test_value2")
        assert len(events) == 1  # Should not have increased

        # Try to remove non-existent callback
        removed = manager.remove_event_callback(CacheEventType.SET, event_handler)
        assert removed is False

    def test_all_events_callback(self, manager):
        """Test callback that listens to all events."""
        events = []

        def all_events_handler(event):
            events.append(event)

        manager.on_all_events(all_events_handler)

        # Trigger different types of events
        manager.set("key1", "value1")
        manager.get("key1")  # HIT
        manager.get("nonexistent")  # MISS
        manager.delete("key1")

        # Should have captured all events
        event_types = [e.event_type for e in events]
        assert CacheEventType.SET in event_types
        assert CacheEventType.HIT in event_types
        assert CacheEventType.MISS in event_types
        assert CacheEventType.DELETE in event_types

    def test_clear_all_event_callbacks(self, manager):
        """Test clearing all event callbacks."""
        events = []

        def event_handler(event):
            events.append(event)

        # Add callbacks for different events
        manager.on_event(CacheEventType.SET, event_handler)
        manager.on_event(CacheEventType.DELETE, event_handler)
        manager.on_all_events(event_handler)

        # Clear all callbacks
        manager.clear_all_event_callbacks()

        # Trigger events - should not be captured
        manager.set("test_key", "test_value")
        manager.delete("test_key")

        assert len(events) == 0

    def test_complex_value_serialization(self, manager):
        """Test serialization of complex values."""
        complex_data = {
            "string": "test",
            "number": 42,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
            "boolean": True,
            "none": None,
        }

        manager.set("complex_key", complex_data)
        result = manager.get("complex_key")

        assert result == complex_data

    def test_error_handling(self, manager):
        """Test error handling in manager operations."""
        # This mainly tests that operations don't crash unexpectedly
        # The underlying backend tests cover more detailed error scenarios

        manager.set("test", "value")
        result = manager.get("test")
        assert result == "value"

        # Operations on non-existent keys should be safe
        assert manager.get("nonexistent") is None
        assert manager.exists("nonexistent") is False
        assert manager.ttl("nonexistent") == -2

    def test_disabled_cache_behavior(self):
        """Test behavior when cache is disabled."""
        config = ConfigBase()
        config.cache_enabled = False
        backend = FakeCacheBackend(config)

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            backend.set("key", "value")

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            backend.get("key")


class TestAsyncCacheManager:
    """Test cases for CacheManager async operations."""

    @pytest.fixture
    def config(self):
        """Create a ConfigBase instance for testing."""
        config = ConfigBase()
        config.cache_enabled = True
        return config

    @pytest.fixture
    def async_backend(self, config):
        """Create a FakeAsyncCacheBackend instance for testing."""
        return FakeAsyncCacheBackend(config)

    @pytest.fixture
    def async_manager(self, config, async_backend):
        """Create a CacheManager instance with async backend for testing."""
        return CacheManager(config=config, backend=None, async_backend=async_backend)

    @pytest.mark.asyncio
    async def test_async_set_and_get_round_trip(self, async_manager):
        """Test that async set/get operations work as expected."""
        # Set a value
        await async_manager.aset("test_key", "test_value")

        # Get the value back
        result = await async_manager.aget("test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_async_get_nonexistent_key(self, async_manager):
        """Test async getting a key that doesn't exist."""
        result = await async_manager.aget("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_async_set_with_ttl(self, async_manager):
        """Test async setting a value with TTL."""
        await async_manager.aset("ttl_key", "ttl_value", ttl=60)

        # Key should exist
        assert await async_manager.aexists("ttl_key") is True

        # TTL should be positive
        ttl = await async_manager.attl("ttl_key")
        assert ttl == 60

    @pytest.mark.asyncio
    async def test_async_set_with_dependencies(self, async_manager):
        """Test async setting a value with dependencies."""
        await async_manager.aset("key1", "value1", dependencies={"dep1", "dep2"})
        await async_manager.aset("key2", "value2", dependencies={"dep1"})

        # Both keys should exist
        assert await async_manager.aget("key1") == "value1"
        assert await async_manager.aget("key2") == "value2"

        # Invalidate dependency
        count = await async_manager.ainvalidate_dependency("dep1")
        assert count == 2  # Both keys depended on dep1

        # Both keys should be invalidated
        assert await async_manager.aget("key1") is None
        assert await async_manager.aget("key2") is None

    @pytest.mark.asyncio
    async def test_async_delete_operations(self, async_manager):
        """Test async delete operations."""
        await async_manager.aset("key1", "value1")
        await async_manager.aset("key2", "value2")
        await async_manager.aset("key3", "value3")

        # Delete single key
        count = await async_manager.adelete("key1")
        assert count == 1
        assert await async_manager.aget("key1") is None
        assert await async_manager.aget("key2") == "value2"

        # Delete multiple keys
        count = await async_manager.adelete("key2", "key3")
        assert count == 2
        assert await async_manager.aget("key2") is None
        assert await async_manager.aget("key3") is None

    @pytest.mark.asyncio
    async def test_async_clear_operations(self, async_manager):
        """Test async clear operations."""
        await async_manager.aset("test:1", "value1")
        await async_manager.aset("test:2", "value2")
        await async_manager.aset("other:1", "value3")

        # Clear with pattern
        count = await async_manager.aclear("test:*")
        assert count == 2
        assert await async_manager.aget("test:1") is None
        assert await async_manager.aget("test:2") is None
        assert await async_manager.aget("other:1") == "value3"

        # Clear all
        count = await async_manager.aclear("*")
        assert count == 1
        assert await async_manager.aget("other:1") is None

    @pytest.mark.asyncio
    async def test_async_exists_operations(self, async_manager):
        """Test async exists operations."""
        assert await async_manager.aexists("nonexistent") is False

        await async_manager.aset("existing", "value")
        assert await async_manager.aexists("existing") is True

    @pytest.mark.asyncio
    async def test_async_ttl_operations(self, async_manager):
        """Test async TTL operations."""
        # Non-existent key
        assert await async_manager.attl("nonexistent") == -2

        # Key without TTL
        await async_manager.aset("persistent_key", "value")
        assert await async_manager.attl("persistent_key") == -1

        # Key with TTL
        await async_manager.aset("ttl_key", "value", ttl=60)
        ttl = await async_manager.attl("ttl_key")
        assert ttl == 60

    @pytest.mark.asyncio
    async def test_async_invalidate_nonexistent_dependency(self, async_manager):
        """Test async invalidating a dependency that doesn't exist."""
        count = await async_manager.ainvalidate_dependency("nonexistent_dep")
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_backend_error(self, config):
        """Test error when no backend is available."""
        # Create a manager with no backends at all
        with pytest.raises(
            ValueError, match="Must specify either 'backend', 'async_backend', or both"
        ):
            CacheManager(config=config, backend=None, async_backend=None)

    @pytest.mark.asyncio
    async def test_async_event_emission_on_set(self, async_manager):
        """Test that events are emitted on async set operations."""
        events = []

        def event_handler(event):
            events.append(event)

        async_manager.on_event(CacheEventType.SET, event_handler)

        await async_manager.aset("test_key", "test_value", ttl=60, dependencies={"dep1"})

        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.SET
        assert event.key == "test_key"
        assert event.value == "test_value"
        assert event.ttl == 60
        assert event.dependencies == {"dep1"}

    @pytest.mark.asyncio
    async def test_async_event_emission_on_hit_and_miss(self, async_manager):
        """Test that hit/miss events are emitted correctly for async operations."""
        events = []

        def event_handler(event):
            events.append(event)

        async_manager.on_event(CacheEventType.HIT, event_handler)
        async_manager.on_event(CacheEventType.MISS, event_handler)

        # Set a value
        await async_manager.aset("test_key", "test_value")

        # Get existing value - should emit HIT
        result = await async_manager.aget("test_key")
        assert result == "test_value"

        # Get non-existing value - should emit MISS
        result = await async_manager.aget("nonexistent")
        assert result is None

        # Should have one HIT and one MISS
        hit_events = [e for e in events if e.event_type == CacheEventType.HIT]
        miss_events = [e for e in events if e.event_type == CacheEventType.MISS]

        assert len(hit_events) == 1
        assert len(miss_events) == 1
        assert hit_events[0].key == "test_key"
        assert miss_events[0].key == "nonexistent"

    @pytest.mark.asyncio
    async def test_async_event_emission_on_delete(self, async_manager):
        """Test that events are emitted on async delete operations."""
        events = []

        def event_handler(event):
            events.append(event)

        async_manager.on_event(CacheEventType.DELETE, event_handler)

        await async_manager.aset("key1", "value1")
        await async_manager.aset("key2", "value2")

        await async_manager.adelete("key1", "key2")

        # Should emit delete events for both keys
        delete_events = [e for e in events if e.event_type == CacheEventType.DELETE]
        assert len(delete_events) == 2
        assert delete_events[0].key == "key1"
        assert delete_events[1].key == "key2"

    @pytest.mark.asyncio
    async def test_async_event_emission_on_clear(self, async_manager):
        """Test that events are emitted on async clear operations."""
        events = []

        def event_handler(event):
            events.append(event)

        async_manager.on_event(CacheEventType.CLEAR, event_handler)

        await async_manager.aset("test:1", "value1")
        await async_manager.aset("test:2", "value2")

        count = await async_manager.aclear("test:*")
        assert count == 2

        # Should emit one clear event
        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.CLEAR
        assert event.key == "test:*"
        assert event.count == 2

    @pytest.mark.asyncio
    async def test_async_event_emission_on_invalidate(self, async_manager):
        """Test that events are emitted on async dependency invalidation."""
        events = []

        def event_handler(event):
            events.append(event)

        async_manager.on_event(CacheEventType.INVALIDATE, event_handler)

        await async_manager.aset("key1", "value1", dependencies={"dep1"})
        await async_manager.aset("key2", "value2", dependencies={"dep1"})

        count = await async_manager.ainvalidate_dependency("dep1")
        assert count == 2

        # Should emit one invalidate event
        assert len(events) == 1
        event = events[0]
        assert event.event_type == CacheEventType.INVALIDATE
        assert event.key == "dep1"
        assert event.count == 2

    @pytest.mark.asyncio
    async def test_async_complex_value_serialization(self, async_manager):
        """Test async serialization of complex values."""
        complex_data = {
            "string": "test",
            "number": 42,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
            "boolean": True,
            "none": None,
        }

        await async_manager.aset("complex_key", complex_data)
        result = await async_manager.aget("complex_key")

        assert result == complex_data

    @pytest.mark.asyncio
    async def test_async_error_handling(self, async_manager):
        """Test error handling in async manager operations."""
        # This mainly tests that operations don't crash unexpectedly
        # The underlying backend tests cover more detailed error scenarios

        await async_manager.aset("test", "value")
        result = await async_manager.aget("test")
        assert result == "value"

        # Operations on non-existent keys should be safe
        assert await async_manager.aget("nonexistent") is None
        assert await async_manager.aexists("nonexistent") is False
        assert await async_manager.attl("nonexistent") == -2

    @pytest.mark.asyncio
    async def test_async_disabled_cache_behavior(self):
        """Test behavior when cache is disabled for async operations."""
        config = ConfigBase()
        config.cache_enabled = False
        async_backend = FakeAsyncCacheBackend(config)

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            await async_backend.set("key", "value")

        with pytest.raises(RuntimeError, match="Cache is disabled"):
            await async_backend.get("key")

    @pytest.mark.asyncio
    async def test_sync_fallback_warning(self, config):
        """Test that using async methods with sync backend emits warnings."""
        # Create manager with only sync backend
        backend = FakeCacheBackend(config)
        manager = CacheManager(config=config, backend=backend, async_backend=None)

        with pytest.warns(UserWarning, match="Using sync backend with async method"):
            await manager.aset("test_key", "test_value")

        with pytest.warns(UserWarning, match="Using sync backend with async method"):
            result = await manager.aget("test_key")
            assert result == "test_value"

    @pytest.mark.asyncio
    async def test_aclose_operation(self, async_manager):
        """Test closing the async backend connection."""
        # Should not raise an exception
        await async_manager.aclose()
