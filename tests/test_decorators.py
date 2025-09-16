import asyncio
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio

from simple_dep_cache.context import (
    add_dependency,
    get_current_dependencies,
    set_current_cache_key,
    set_current_dependencies,
)
from simple_dep_cache.decorators import async_cache_with_deps, cache_with_deps
from simple_dep_cache.manager import AsyncCacheManager, CacheManager


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache_manager(redis_client):
    return CacheManager(redis_client=redis_client, prefix="test")


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


class TestCacheWithDeps:
    def test_basic_caching(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @patch("simple_dep_cache.manager.create_redis_client_from_config")
    def test_default_cache_manager(self, mock_create_redis):
        mock_redis = fakeredis.FakeRedis(decode_responses=True)
        mock_create_redis.return_value = mock_redis
        call_count = 0

        @cache_with_deps()
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    def test_caching_with_ttl(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, ttl=60)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    def test_caching_with_key_prefix(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, key_prefix="prefix")
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    def test_caching_with_additional_dependencies(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, dependencies={"external_dep"})
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        cache_manager.invalidate_dependency("external_dep")
        result3 = expensive_function(5)
        assert result3 == 10
        assert call_count == 2

    def test_caching_with_tracked_dependencies(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("tracked_dep")
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        cache_manager.invalidate_dependency("tracked_dep")
        result3 = expensive_function(5)
        assert result3 == 10
        assert call_count == 2

    def test_caching_with_combined_dependencies(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, dependencies={"static_dep"})
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("dynamic_dep")
            return x * 2

        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        cache_manager.invalidate_dependency("static_dep")
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 2

        result3 = expensive_function(5)
        assert call_count == 2

        cache_manager.invalidate_dependency("dynamic_dep")
        result4 = expensive_function(5)
        assert result4 == 10
        assert call_count == 3

    def test_different_arguments_different_cache(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(10)
        result3 = expensive_function(5)

        assert result1 == 10
        assert result2 == 20
        assert result3 == 10
        assert call_count == 2

    def test_kwargs_in_cache_key(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x, multiplier=2):
            nonlocal call_count
            call_count += 1
            return x * multiplier

        result1 = expensive_function(5, multiplier=2)
        result2 = expensive_function(5, multiplier=3)
        result3 = expensive_function(5, multiplier=2)

        assert result1 == 10
        assert result2 == 15
        assert result3 == 10
        assert call_count == 2

    @patch.dict("os.environ", {"DEP_CACHE_ENABLED": "false"})
    def test_caching_disabled_by_config(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 2

    def test_context_restoration(self, cache_manager):
        old_deps = {"existing_dep"}
        set_current_dependencies(old_deps)
        set_current_cache_key("existing_key")

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            add_dependency("function_dep")
            return x * 2

        result = expensive_function(5)

        assert result == 10
        assert get_current_dependencies() == old_deps

    def test_exception_handling_restores_context(self, cache_manager):
        old_deps = {"existing_dep"}
        set_current_dependencies(old_deps)
        set_current_cache_key("existing_key")

        @cache_with_deps(cache_manager=cache_manager)
        def failing_function(x):
            add_dependency("function_dep")
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function(5)

        assert get_current_dependencies() == old_deps


class TestAsyncCacheWithDeps:
    @pytest.mark.asyncio
    async def test_basic_caching_async_func(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_async_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_async_function(5)
        result2 = await expensive_async_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_basic_caching_sync_func(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        def expensive_sync_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_sync_function(5)
        result2 = await expensive_sync_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    @patch("simple_dep_cache.manager.create_async_redis_client_from_config")
    async def test_default_cache_manager(self, mock_create_async_redis):
        mock_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        mock_create_async_redis.return_value = mock_redis
        call_count = 0

        @async_cache_with_deps()
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        await mock_redis.aclose()

    @pytest.mark.asyncio
    async def test_caching_with_ttl(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, ttl=60)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_caching_with_key_prefix(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, key_prefix="prefix")
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_caching_with_additional_dependencies(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, dependencies={"external_dep"})
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        await async_cache_manager.invalidate_dependency("external_dep")
        result3 = await expensive_function(5)
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_caching_with_tracked_dependencies(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("tracked_dep")
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        await async_cache_manager.invalidate_dependency("tracked_dep")
        result3 = await expensive_function(5)
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_caching_with_combined_dependencies(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, dependencies={"static_dep"})
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("dynamic_dep")
            return x * 2

        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        await async_cache_manager.invalidate_dependency("static_dep")
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 2

        result3 = await expensive_function(5)
        assert call_count == 2

        await async_cache_manager.invalidate_dependency("dynamic_dep")
        result4 = await expensive_function(5)
        assert result4 == 10
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_different_arguments_different_cache(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(10)
        result3 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 20
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_kwargs_in_cache_key(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x, multiplier=2):
            nonlocal call_count
            call_count += 1
            return x * multiplier

        result1 = await expensive_function(5, multiplier=2)
        result2 = await expensive_function(5, multiplier=3)
        result3 = await expensive_function(5, multiplier=2)

        assert result1 == 10
        assert result2 == 15
        assert result3 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"DEP_CACHE_ENABLED": "false"})
    async def test_caching_disabled_by_config_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"DEP_CACHE_ENABLED": "false"})
    async def test_caching_disabled_by_config_sync(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_context_restoration(self, async_cache_manager):
        old_deps = {"existing_dep"}
        set_current_dependencies(old_deps)
        set_current_cache_key("existing_key")

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            add_dependency("function_dep")
            return x * 2

        result = await expensive_function(5)

        assert result == 10
        assert get_current_dependencies() == old_deps

    @pytest.mark.asyncio
    async def test_exception_handling_restores_context(self, async_cache_manager):
        old_deps = {"existing_dep"}
        set_current_dependencies(old_deps)
        set_current_cache_key("existing_key")

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def failing_function(x):
            add_dependency("function_dep")
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await failing_function(5)

        assert get_current_dependencies() == old_deps

    @pytest.mark.asyncio
    async def test_concurrent_cached_calls(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call should cache the result
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Subsequent concurrent calls should all hit cache
        tasks = [expensive_function(5) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(result == 10 for result in results)
        assert call_count == 1
