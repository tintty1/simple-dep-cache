import time
from unittest.mock import Mock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio

from simple_dep_cache.events import CacheEventType
from simple_dep_cache.manager import AsyncCacheManager


@pytest_asyncio.fixture
async def async_redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def async_cache_manager(async_redis_client):
    manager = AsyncCacheManager(redis_client=async_redis_client, prefix="test")
    yield manager
    await manager.close()


@pytest.fixture
def event_listener():
    return Mock()


class TestAsyncCacheManager:
    @pytest.mark.asyncio
    @patch("simple_dep_cache.manager.create_async_redis_client_from_config")
    async def test_init_default_redis(self, mock_create_async_redis):
        from unittest.mock import AsyncMock

        mock_redis = Mock()
        mock_redis.aclose = AsyncMock()
        mock_create_async_redis.return_value = mock_redis

        manager = AsyncCacheManager()

        assert manager.prefix == "cache"
        assert manager.redis is mock_redis
        mock_create_async_redis.assert_called_once()

        await manager.close()

    @pytest.mark.asyncio
    async def test_init_custom_redis_and_prefix(self, async_redis_client):
        manager = AsyncCacheManager(redis_client=async_redis_client, prefix="custom")
        assert manager.prefix == "custom"
        assert manager.redis == async_redis_client

    @pytest.mark.asyncio
    async def test_cache_key_generation(self, async_cache_manager):
        assert async_cache_manager._cache_key("test") == "test:test"

    @pytest.mark.asyncio
    async def test_deps_key_generation(self, async_cache_manager):
        assert async_cache_manager._deps_key("dep1") == "test:deps:dep1"

    @pytest.mark.asyncio
    async def test_set_simple_value(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        result = await async_cache_manager.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", ttl=60)
        result = await async_cache_manager.get("key1")
        assert result == "value1"
        ttl = await async_cache_manager.redis.ttl(async_cache_manager._cache_key("key1"))
        assert ttl <= 60

    @pytest.mark.asyncio
    async def test_set_with_dependencies(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", dependencies={"dep1", "dep2"})

        result = await async_cache_manager.get("key1")
        assert result == "value1"

        dep1_members = await async_cache_manager.redis.smembers(
            async_cache_manager._deps_key("dep1")
        )
        dep2_members = await async_cache_manager.redis.smembers(
            async_cache_manager._deps_key("dep2")
        )

        assert dep1_members == {async_cache_manager._cache_key("key1")}
        assert dep2_members == {async_cache_manager._cache_key("key1")}

    @pytest.mark.asyncio
    async def test_set_with_ttl_and_dependencies(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})

        result = await async_cache_manager.get("key1")
        assert result == "value1"

        dep_members = await async_cache_manager.redis.smembers(
            async_cache_manager._deps_key("dep1")
        )
        assert dep_members == {async_cache_manager._cache_key("key1")}

        ttl = await async_cache_manager.redis.ttl(async_cache_manager._deps_key("dep1"))
        assert 50 < ttl <= 60

    @pytest.mark.asyncio
    async def test_set_dependency_ttl_management(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})
        await async_cache_manager.set("key2", "value2", ttl=30, dependencies={"dep1"})

        ttl = await async_cache_manager.redis.ttl(async_cache_manager._deps_key("dep1"))
        assert 50 < ttl <= 60

    @pytest.mark.asyncio
    async def test_set_emits_event(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.SET, event_listener)

        await async_cache_manager.set("key1", "value1", ttl=60, dependencies={"dep1"})

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.SET
        assert event.key == "key1"
        assert event.value == "value1"
        assert event.dependencies == {"dep1"}
        assert event.ttl == 60

    @pytest.mark.asyncio
    async def test_get_existing_value(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        result = await async_cache_manager.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_value(self, async_cache_manager):
        result = await async_cache_manager.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_emits_hit_event(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.HIT, event_listener)
        await async_cache_manager.set("key1", "value1")

        await async_cache_manager.get("key1")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.HIT
        assert event.key == "key1"
        assert event.value == "value1"

    @pytest.mark.asyncio
    async def test_get_emits_miss_event(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.MISS, event_listener)

        await async_cache_manager.get("nonexistent")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.MISS
        assert event.key == "nonexistent"

    @pytest.mark.asyncio
    async def test_delete_single_key(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        await async_cache_manager.set("key2", "value2")

        count = await async_cache_manager.delete("key1")

        assert count == 1
        assert await async_cache_manager.get("key1") is None
        assert await async_cache_manager.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_delete_multiple_keys(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        await async_cache_manager.set("key2", "value2")
        await async_cache_manager.set("key3", "value3")

        count = await async_cache_manager.delete("key1", "key2")

        assert count == 2
        assert await async_cache_manager.get("key1") is None
        assert await async_cache_manager.get("key2") is None
        assert await async_cache_manager.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_keys(self, async_cache_manager):
        count = await async_cache_manager.delete("nonexistent1", "nonexistent2")
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_emits_events(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.DELETE, event_listener)
        await async_cache_manager.set("key1", "value1")
        await async_cache_manager.set("key2", "value2")

        await async_cache_manager.delete("key1", "key2")

        assert event_listener.call_count == 2
        events = [call[0][0] for call in event_listener.call_args_list]
        assert all(event.event_type == CacheEventType.DELETE for event in events)
        assert {event.key for event in events} == {"key1", "key2"}

    @pytest.mark.asyncio
    async def test_clear_all(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        await async_cache_manager.set("key2", "value2")

        count = await async_cache_manager.clear()

        assert count == 2
        assert await async_cache_manager.get("key1") is None
        assert await async_cache_manager.get("key2") is None

    @pytest.mark.asyncio
    async def test_clear_with_pattern(self, async_cache_manager):
        await async_cache_manager.set("user:1", "value1")
        await async_cache_manager.set("user:2", "value2")
        await async_cache_manager.set("product:1", "value3")

        count = await async_cache_manager.clear("user:*")

        assert count == 2
        assert await async_cache_manager.get("user:1") is None
        assert await async_cache_manager.get("user:2") is None
        assert await async_cache_manager.get("product:1") == "value3"

    @pytest.mark.asyncio
    async def test_clear_emits_event(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.CLEAR, event_listener)
        await async_cache_manager.set("key1", "value1")

        await async_cache_manager.clear()

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.CLEAR
        assert event.key == "*"
        assert event.count == 1

    @pytest.mark.asyncio
    async def test_invalidate_dependency(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", dependencies={"dep1"})
        await async_cache_manager.set("key2", "value2", dependencies={"dep1", "dep2"})
        await async_cache_manager.set("key3", "value3", dependencies={"dep2"})

        count = await async_cache_manager.invalidate_dependency("dep1")

        assert count == 2
        assert await async_cache_manager.get("key1") is None
        assert await async_cache_manager.get("key2") is None
        assert await async_cache_manager.get("key3") == "value3"

        exists = await async_cache_manager.redis.exists(async_cache_manager._deps_key("dep1"))
        assert not exists

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_dependency(self, async_cache_manager):
        count = await async_cache_manager.invalidate_dependency("nonexistent")
        assert count == 0

    @pytest.mark.asyncio
    async def test_invalidate_dependency_emits_event(self, async_cache_manager, event_listener):
        async_cache_manager.events.on(CacheEventType.INVALIDATE, event_listener)
        await async_cache_manager.set("key1", "value1", dependencies={"dep1"})

        await async_cache_manager.invalidate_dependency("dep1")

        event_listener.assert_called_once()
        event = event_listener.call_args[0][0]
        assert event.event_type == CacheEventType.INVALIDATE
        assert event.key == "dep1"
        assert event.count == 1

    @pytest.mark.asyncio
    async def test_exists_true(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        exists = await async_cache_manager.exists("key1")
        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, async_cache_manager):
        exists = await async_cache_manager.exists("nonexistent")
        assert exists is False

    @pytest.mark.asyncio
    async def test_ttl_with_expiration(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", ttl=60)
        ttl = await async_cache_manager.ttl("key1")
        assert 50 < ttl <= 60

    @pytest.mark.asyncio
    async def test_ttl_without_expiration(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1")
        ttl = await async_cache_manager.ttl("key1")
        assert ttl == -1

    @pytest.mark.asyncio
    async def test_ttl_nonexistent_key(self, async_cache_manager):
        ttl = await async_cache_manager.ttl("nonexistent")
        assert ttl == -2

    @pytest.mark.asyncio
    async def test_close(self, async_redis_client):
        manager = AsyncCacheManager(redis_client=async_redis_client, prefix="test")
        await manager.close()

    @pytest.mark.asyncio
    async def test_complex_data_types(self, async_cache_manager):
        test_data = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }

        await async_cache_manager.set("complex", test_data)
        result = await async_cache_manager.get("complex")
        assert result == test_data

    @pytest.mark.asyncio
    async def test_dependency_chain_invalidation(self, async_cache_manager):
        await async_cache_manager.set("base", "value", dependencies={"dep1"})
        await async_cache_manager.set("derived1", "value", dependencies={"base"})
        await async_cache_manager.set("derived2", "value", dependencies={"derived1"})

        await async_cache_manager.invalidate_dependency("dep1")

        assert await async_cache_manager.get("base") is None
        assert await async_cache_manager.get("derived1") == "value"
        assert await async_cache_manager.get("derived2") == "value"

    @pytest.mark.asyncio
    async def test_multiple_dependencies_same_key(self, async_cache_manager):
        await async_cache_manager.set("key1", "value1", dependencies={"dep1", "dep2", "dep3"})

        await async_cache_manager.invalidate_dependency("dep2")

        assert await async_cache_manager.get("key1") is None

        exists_dep2 = await async_cache_manager.redis.exists(async_cache_manager._deps_key("dep2"))
        exists_dep1 = await async_cache_manager.redis.exists(async_cache_manager._deps_key("dep1"))
        exists_dep3 = await async_cache_manager.redis.exists(async_cache_manager._deps_key("dep3"))

        assert not exists_dep2
        assert exists_dep1
        assert exists_dep3

    @pytest.mark.asyncio
    async def test_event_emission_timing(self, async_cache_manager):
        events = []

        def capture_event(event):
            events.append((event.event_type, time.time()))

        async_cache_manager.events.on(CacheEventType.SET, capture_event)
        async_cache_manager.events.on(CacheEventType.HIT, capture_event)
        async_cache_manager.events.on(CacheEventType.MISS, capture_event)

        start_time = time.time()
        await async_cache_manager.set("key1", "value1")
        await async_cache_manager.get("key1")
        await async_cache_manager.get("nonexistent")
        end_time = time.time()

        assert len(events) == 3
        assert events[0][0] == CacheEventType.SET
        assert events[1][0] == CacheEventType.HIT
        assert events[2][0] == CacheEventType.MISS

        for _, timestamp in events:
            assert start_time <= timestamp <= end_time

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, async_cache_manager):
        import asyncio

        async def set_values():
            tasks = []
            for i in range(10):
                task = async_cache_manager.set(f"key{i}", f"value{i}")
                tasks.append(task)
            await asyncio.gather(*tasks)

        async def get_values():
            tasks = []
            for i in range(10):
                task = async_cache_manager.get(f"key{i}")
                tasks.append(task)
            return await asyncio.gather(*tasks)

        await set_values()
        results = await get_values()

        expected = [f"value{i}" for i in range(10)]
        assert results == expected

    @pytest.mark.asyncio
    async def test_concurrent_dependency_invalidation(self, async_cache_manager):
        import asyncio

        await async_cache_manager.set("key1", "value1", dependencies={"shared_dep"})
        await async_cache_manager.set("key2", "value2", dependencies={"shared_dep"})
        await async_cache_manager.set("key3", "value3", dependencies={"shared_dep"})

        tasks = [
            async_cache_manager.invalidate_dependency("shared_dep"),
            async_cache_manager.get("key1"),
            async_cache_manager.get("key2"),
            async_cache_manager.get("key3"),
        ]

        results = await asyncio.gather(*tasks)
        count = results[0]
        values = results[1:]

        assert count == 3
        assert all(value is None for value in values)
