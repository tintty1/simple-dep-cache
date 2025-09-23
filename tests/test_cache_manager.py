import time
from unittest.mock import Mock, patch

import fakeredis
import pytest

from simple_dep_cache.events import CacheEventType
from simple_dep_cache.manager import CacheManager, get_default_cache_manager


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache_manager(redis_client):
    return CacheManager(redis_client=redis_client, prefix="test")


@pytest.fixture
def event_listener():
    return Mock()


class TestCacheManager:
    @patch("simple_dep_cache.manager.create_redis_client_from_config")
    def test_init_default_redis(self, mock_create_redis):
        mock_redis = Mock()
        mock_create_redis.return_value = mock_redis

        manager = CacheManager()

        assert manager.prefix == "cache"
        assert manager.redis is mock_redis
        mock_create_redis.assert_called_once()

    def test_init_custom_redis_and_prefix(self, redis_client):
        manager = CacheManager(redis_client=redis_client, prefix="custom")
        assert manager.prefix == "custom"
        assert manager.redis == redis_client

    def test_cache_key_generation(self, cache_manager):
        assert cache_manager._cache_key("test") == "test:test"

    def test_deps_key_generation(self, cache_manager):
        assert cache_manager._deps_key("dep1") == "test:deps:dep1"

    def test_set_simple_value(self, cache_manager):
        cache_manager.set("key1", "value1")
        assert cache_manager.get("key1") == "value1"

    def test_set_with_ttl(self, cache_manager):
        cache_manager.set("key1", "value1", ttl=60)
        assert cache_manager.get("key1") == "value1"
        assert cache_manager.redis.ttl(cache_manager._cache_key("key1")) <= 60

    def test_set_with_dependencies(self, cache_manager):
        cache_manager.set("key1", "value1", dependencies={"dep1", "dep2"})

        assert cache_manager.get("key1") == "value1"
        assert cache_manager.redis.smembers(cache_manager._deps_key("dep1")) == {
            cache_manager._cache_key("key1")
        }
        assert cache_manager.redis.smembers(cache_manager._deps_key("dep2")) == {
            cache_manager._cache_key("key1")
        }

    def test_set_with_ttl_and_dependencies(self, cache_manager):
        cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})

        assert cache_manager.get("key1") == "value1"
        assert cache_manager.redis.smembers(cache_manager._deps_key("dep1")) == {
            cache_manager._cache_key("key1")
        }
        assert 50 < cache_manager.redis.ttl(cache_manager._deps_key("dep1")) <= 60

    def test_set_dependency_ttl_management(self, cache_manager):
        cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})
        cache_manager.set("key2", "value2", ttl=30, dependencies={"dep1"})

        ttl = cache_manager.redis.ttl(cache_manager._deps_key("dep1"))
        assert 50 < ttl <= 60

    def test_set_emits_event(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.SET, event_listener)

        cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.SET
        assert event.key == "key1"
        assert event.value == "value1"
        assert event.dependencies == {"dep1"}
        assert event.ttl == 60

    def test_get_existing_value(self, cache_manager):
        cache_manager.set("key1", "value1")
        result = cache_manager.get("key1")
        assert result == "value1"

    def test_get_nonexistent_value(self, cache_manager):
        result = cache_manager.get("nonexistent")
        assert result is None

    def test_get_emits_hit_event(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.HIT, event_listener)
        cache_manager.set("key1", "value1")

        cache_manager.get("key1")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.HIT
        assert event.key == "key1"
        assert event.value == "value1"

    def test_get_emits_miss_event(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.MISS, event_listener)

        cache_manager.get("nonexistent")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.MISS
        assert event.key == "nonexistent"

    def test_delete_single_key(self, cache_manager):
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        count = cache_manager.delete("key1")

        assert count == 1
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key2") == "value2"

    def test_delete_multiple_keys(self, cache_manager):
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")
        cache_manager.set("key3", "value3")

        count = cache_manager.delete("key1", "key2")

        assert count == 2
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key2") is None
        assert cache_manager.get("key3") == "value3"

    def test_delete_nonexistent_keys(self, cache_manager):
        count = cache_manager.delete("nonexistent1", "nonexistent2")
        assert count == 0

    def test_delete_emits_events(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.DELETE, event_listener)
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        cache_manager.delete("key1", "key2")

        assert event_listener.call_count == 2
        events = [call[0][0] for call in event_listener.call_args_list]
        assert all(event.event_type == CacheEventType.DELETE for event in events)
        assert {event.key for event in events} == {"key1", "key2"}

    def test_clear_all(self, cache_manager):
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        count = cache_manager.clear()

        assert count == 2
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key2") is None

    def test_clear_with_pattern(self, cache_manager):
        cache_manager.set("user:1", "value1")
        cache_manager.set("user:2", "value2")
        cache_manager.set("product:1", "value3")

        count = cache_manager.clear("user:*")

        assert count == 2
        assert cache_manager.get("user:1") is None
        assert cache_manager.get("user:2") is None
        assert cache_manager.get("product:1") == "value3"

    def test_clear_emits_event(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.CLEAR, event_listener)
        cache_manager.set("key1", "value1")

        cache_manager.clear()

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.CLEAR
        assert event.key == "*"
        assert event.count == 1

    def test_invalidate_dependency(self, cache_manager):
        cache_manager.set("key1", "value1", dependencies={"dep1"})
        cache_manager.set("key2", "value2", dependencies={"dep1", "dep2"})
        cache_manager.set("key3", "value3", dependencies={"dep2"})

        count = cache_manager.invalidate_dependency("dep1")

        assert count == 2
        assert cache_manager.get("key1") is None
        assert cache_manager.get("key2") is None
        assert cache_manager.get("key3") == "value3"
        assert not cache_manager.redis.exists(cache_manager._deps_key("dep1"))

    def test_invalidate_nonexistent_dependency(self, cache_manager):
        count = cache_manager.invalidate_dependency("nonexistent")
        assert count == 0

    def test_invalidate_dependency_emits_event(self, cache_manager, event_listener):
        cache_manager.events.on(CacheEventType.INVALIDATE, event_listener)
        cache_manager.set("key1", "value1", dependencies={"dep1"})

        cache_manager.invalidate_dependency("dep1")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.INVALIDATE
        assert event.key == "dep1"
        assert event.count == 1

    def test_exists_true(self, cache_manager):
        cache_manager.set("key1", "value1")
        assert cache_manager.exists("key1") is True

    def test_exists_false(self, cache_manager):
        assert cache_manager.exists("nonexistent") is False

    def test_ttl_with_expiration(self, cache_manager):
        cache_manager.set("key1", "value1", ttl=60)
        ttl = cache_manager.ttl("key1")
        assert 50 < ttl <= 60

    def test_ttl_without_expiration(self, cache_manager):
        cache_manager.set("key1", "value1")
        ttl = cache_manager.ttl("key1")
        assert ttl == -1

    def test_ttl_nonexistent_key(self, cache_manager):
        ttl = cache_manager.ttl("nonexistent")
        assert ttl == -2

    def test_complex_data_types(self, cache_manager):
        test_data = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }

        cache_manager.set("complex", test_data)
        result = cache_manager.get("complex")
        assert result == test_data

    def test_dependency_chain_invalidation(self, cache_manager):
        cache_manager.set("base", "value", dependencies={"dep1"})
        cache_manager.set("derived1", "value", dependencies={"base"})
        cache_manager.set("derived2", "value", dependencies={"derived1"})

        cache_manager.invalidate_dependency("dep1")

        assert cache_manager.get("base") is None
        assert cache_manager.get("derived1") == "value"
        assert cache_manager.get("derived2") == "value"

    def test_multiple_dependencies_same_key(self, cache_manager):
        cache_manager.set("key1", "value1", dependencies={"dep1", "dep2", "dep3"})

        cache_manager.invalidate_dependency("dep2")

        assert cache_manager.get("key1") is None
        assert not cache_manager.redis.exists(cache_manager._deps_key("dep2"))
        assert cache_manager.redis.exists(cache_manager._deps_key("dep1"))
        assert cache_manager.redis.exists(cache_manager._deps_key("dep3"))

    def test_event_emission_timing(self, cache_manager):
        events = []

        def capture_event(event):
            events.append((event.event_type, time.time()))

        cache_manager.events.on(CacheEventType.SET, capture_event)
        cache_manager.events.on(CacheEventType.HIT, capture_event)
        cache_manager.events.on(CacheEventType.MISS, capture_event)

        start_time = time.time()
        cache_manager.set("key1", "value1")
        cache_manager.get("key1")
        cache_manager.get("nonexistent")
        end_time = time.time()

        assert len(events) == 3
        assert events[0][0] == CacheEventType.SET
        assert events[1][0] == CacheEventType.HIT
        assert events[2][0] == CacheEventType.MISS

        for _, timestamp in events:
            assert start_time <= timestamp <= end_time


class TestDefaultCacheManager:
    def test_get_default_cache_manager_returns_same_instance(self):
        """Test that get_default_cache_manager returns the same instance on multiple calls."""
        manager1 = get_default_cache_manager()
        manager2 = get_default_cache_manager()

        assert manager1 is manager2
        assert isinstance(manager1, CacheManager)
        assert manager1.prefix == "cache"

    @patch("simple_dep_cache.manager.create_redis_client_from_config")
    def test_get_default_cache_manager_creates_redis_client(self, mock_create_redis):
        """Test that default manager creates Redis client from config."""
        mock_redis = Mock()
        mock_create_redis.return_value = mock_redis

        # Reset the global state by accessing the module's globals
        import simple_dep_cache.manager as manager_module

        manager_module._default_sync_manager = None

        manager = get_default_cache_manager()

        assert manager.redis is mock_redis
        mock_create_redis.assert_called_once()

    def test_get_default_cache_manager_thread_safety(self):
        """Test that default manager creation is thread-safe."""
        import threading

        import simple_dep_cache.manager as manager_module

        # Reset the global state
        manager_module._default_sync_manager = None

        managers = []
        barrier = threading.Barrier(5)

        def create_manager():
            barrier.wait()  # Ensure all threads start simultaneously
            managers.append(get_default_cache_manager())

        threads = [threading.Thread(target=create_manager) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All managers should be the same instance
        assert len({id(manager) for manager in managers}) == 1
