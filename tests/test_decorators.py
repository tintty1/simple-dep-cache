import asyncio
import logging
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio

from simple_dep_cache.context import (
    add_dependency,
    get_current_dependencies,
    set_cache_ttl,
    set_current_cache_key,
    set_current_dependencies,
)
from simple_dep_cache.decorators import (
    _get_cache_key_for_arg,
    async_cache_with_deps,
    cache_with_deps,
)
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
        # Reset global manager state for clean test
        import simple_dep_cache.manager as manager_module

        manager_module._default_sync_manager = None

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

    def test_exception_caching_enabled(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, cache_exception_types=[ValueError])
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # First call should raise and cache the exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 1

        # Second call with same arguments should retrieve cached exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 1  # Should not increment, exception was cached

        # Positive value should work normally
        result = failing_function(5)
        assert result == 10
        assert call_count == 2

    def test_exception_caching_disabled_by_default(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # Exception should not be cached when cache_exception_types is not provided
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 1

        # Second call should execute function again
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 2

    def test_exception_caching_specific_types(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, cache_exception_types=[ValueError])
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x == -1:
                raise ValueError("ValueError message")
            elif x == -2:
                raise RuntimeError("RuntimeError message")
            return x * 2

        # ValueError should be cached
        with pytest.raises(ValueError, match="ValueError message"):
            failing_function(-1)
        assert call_count == 1

        with pytest.raises(ValueError, match="ValueError message"):
            failing_function(-1)
        assert call_count == 1  # Should not increment

        # RuntimeError should not be cached (not in cache_exception_types)
        with pytest.raises(RuntimeError, match="RuntimeError message"):
            failing_function(-2)
        assert call_count == 2

        with pytest.raises(RuntimeError, match="RuntimeError message"):
            failing_function(-2)
        assert call_count == 3  # Should increment since not cached

    def test_exception_caching_with_dependencies(self, cache_manager):
        call_count = 0

        @cache_with_deps(
            cache_manager=cache_manager,
            cache_exception_types=[ValueError],
            dependencies={"static_dep"},
        )
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("dynamic_dep")
            raise ValueError(f"Error: {x}")

        # Cache the exception
        with pytest.raises(ValueError, match="Error: 5"):
            failing_function(5)
        assert call_count == 1

        # Should hit cache
        with pytest.raises(ValueError, match="Error: 5"):
            failing_function(5)
        assert call_count == 1

        # Invalidate static dependency - should clear cache
        cache_manager.invalidate_dependency("static_dep")
        with pytest.raises(ValueError, match="Error: 5"):
            failing_function(5)
        assert call_count == 2

        # Cache again and invalidate dynamic dependency
        with pytest.raises(ValueError, match="Error: 5"):
            failing_function(5)
        assert call_count == 2

        cache_manager.invalidate_dependency("dynamic_dep")
        with pytest.raises(ValueError, match="Error: 5"):
            failing_function(5)
        assert call_count == 3

    def test_exception_caching_with_ttl(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, cache_exception_types=[ValueError], ttl=60)
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Error: {x}")

        # Cache the exception
        with pytest.raises(ValueError, match="Error: 1"):
            failing_function(1)
        assert call_count == 1

        # Should hit cache
        with pytest.raises(ValueError, match="Error: 1"):
            failing_function(1)
        assert call_count == 1

    def test_exception_caching_inheritance(self, cache_manager):
        call_count = 0

        class CustomError(ValueError):
            pass

        @cache_with_deps(cache_manager=cache_manager, cache_exception_types=[ValueError])
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x == 1:
                raise ValueError("Base error")
            elif x == 2:
                raise CustomError("Custom error")
            return x

        # Base ValueError should be cached
        with pytest.raises(ValueError, match="Base error"):
            failing_function(1)
        assert call_count == 1

        with pytest.raises(ValueError, match="Base error"):
            failing_function(1)
        assert call_count == 1  # Cached

        # CustomError (subclass of ValueError) should also be cached
        with pytest.raises(CustomError, match="Custom error"):
            failing_function(2)
        assert call_count == 2

        # The cached exception should have the same type and message
        # but will be a different instance due to serialization/deserialization
        with pytest.raises(Exception, match="Custom error") as exc_info:
            failing_function(2)
        assert call_count == 2  # Cached due to inheritance

        # Verify the cached exception maintains the correct type name
        # Note: Due to serialization, it might be a dynamically created type
        # but should still have the same name and message
        cached_exc = exc_info.value
        assert type(cached_exc).__name__ == "CustomError"
        assert str(cached_exc) == "Custom error"


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
        # Reset global manager state for clean test
        import simple_dep_cache.manager as manager_module

        manager_module._default_async_manager = None

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
    async def test_exception_caching_enabled_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(
            cache_manager=async_cache_manager, cache_exception_types=[ValueError]
        )
        async def failing_async_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # First call should raise and cache the exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_async_function(-1)
        assert call_count == 1

        # Second call with same arguments should retrieve cached exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_async_function(-1)
        assert call_count == 1  # Should not increment, exception was cached

        # Positive value should work normally
        result = await failing_async_function(5)
        assert result == 10
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exception_caching_enabled_sync_in_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(
            cache_manager=async_cache_manager, cache_exception_types=[ValueError]
        )
        def failing_sync_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # First call should raise and cache the exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_sync_function(-1)
        assert call_count == 1

        # Second call with same arguments should retrieve cached exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_sync_function(-1)
        assert call_count == 1  # Should not increment, exception was cached

    @pytest.mark.asyncio
    async def test_exception_caching_disabled_by_default_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # Exception should not be cached when cache_exception_types is not provided
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_function(-1)
        assert call_count == 1

        # Second call should execute function again
        with pytest.raises(ValueError, match="Negative value: -1"):
            await failing_function(-1)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exception_caching_specific_types_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(
            cache_manager=async_cache_manager, cache_exception_types=[ValueError]
        )
        async def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x == -1:
                raise ValueError("ValueError message")
            elif x == -2:
                raise RuntimeError("RuntimeError message")
            return x * 2

        # ValueError should be cached
        with pytest.raises(ValueError, match="ValueError message"):
            await failing_function(-1)
        assert call_count == 1

        with pytest.raises(ValueError, match="ValueError message"):
            await failing_function(-1)
        assert call_count == 1  # Should not increment

        # RuntimeError should not be cached (not in cache_exception_types)
        with pytest.raises(RuntimeError, match="RuntimeError message"):
            await failing_function(-2)
        assert call_count == 2

        with pytest.raises(RuntimeError, match="RuntimeError message"):
            await failing_function(-2)
        assert call_count == 3  # Should increment since not cached

    @pytest.mark.asyncio
    async def test_exception_caching_with_dependencies_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(
            cache_manager=async_cache_manager,
            cache_exception_types=[ValueError],
            dependencies={"static_dep"},
        )
        async def failing_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("dynamic_dep")
            raise ValueError(f"Error: {x}")

        # Cache the exception
        with pytest.raises(ValueError, match="Error: 5"):
            await failing_function(5)
        assert call_count == 1

        # Should hit cache
        with pytest.raises(ValueError, match="Error: 5"):
            await failing_function(5)
        assert call_count == 1

        # Invalidate static dependency - should clear cache
        await async_cache_manager.invalidate_dependency("static_dep")
        with pytest.raises(ValueError, match="Error: 5"):
            await failing_function(5)
        assert call_count == 2

        # Cache again and invalidate dynamic dependency
        with pytest.raises(ValueError, match="Error: 5"):
            await failing_function(5)
        assert call_count == 2

        await async_cache_manager.invalidate_dependency("dynamic_dep")
        with pytest.raises(ValueError, match="Error: 5"):
            await failing_function(5)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exception_caching_inheritance_async(self, async_cache_manager):
        call_count = 0

        class CustomError(ValueError):
            pass

        @async_cache_with_deps(
            cache_manager=async_cache_manager, cache_exception_types=[ValueError]
        )
        async def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x == 1:
                raise ValueError("Base error")
            elif x == 2:
                raise CustomError("Custom error")
            return x

        # Base ValueError should be cached
        with pytest.raises(ValueError, match="Base error"):
            await failing_function(1)
        assert call_count == 1

        with pytest.raises(ValueError, match="Base error"):
            await failing_function(1)
        assert call_count == 1  # Cached

        # CustomError (subclass of ValueError) should also be cached
        with pytest.raises(CustomError, match="Custom error"):
            await failing_function(2)
        assert call_count == 2

        # The cached exception should have the same type and message
        # but will be a different instance due to serialization/deserialization
        with pytest.raises(Exception, match="Custom error") as exc_info:
            await failing_function(2)
        assert call_count == 2  # Cached due to inheritance

        # Verify the cached exception maintains the correct type name
        # Note: Due to serialization, it might be a dynamically created type
        # but should still have the same name and message
        cached_exc = exc_info.value
        assert type(cached_exc).__name__ == "CustomError"
        assert str(cached_exc) == "Custom error"

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


class TestCacheKeyGeneration:
    def test_get_cache_key_for_arg_basic_types(self):
        # Test basic types use string representation
        assert _get_cache_key_for_arg(42) == "42"
        assert _get_cache_key_for_arg("hello") == "hello"
        assert _get_cache_key_for_arg(True) == "True"

    def test_get_cache_key_for_arg_custom_cache_key_method(self):
        class CustomObject:
            def __cache_key__(self):
                return "custom_key_123"

        obj = CustomObject()
        assert _get_cache_key_for_arg(obj) == "custom_key_123"

    def test_get_cache_key_for_arg_cache_key_attribute(self):
        class CustomObject:
            _cache_key = "attribute_key_789"

        obj = CustomObject()
        assert _get_cache_key_for_arg(obj) == "attribute_key_789"

    def test_get_cache_key_for_arg_django_like_model(self):
        class DjangoLikeModel:
            pk = 123

            def __str__(self):
                return "DjangoLikeModel object (123)"

        obj = DjangoLikeModel()
        assert _get_cache_key_for_arg(obj) == "DjangoLikeModel::123"

    def test_get_cache_key_for_arg_object_with_id(self):
        class ObjectWithId:
            id = 456

            def __str__(self):
                return "ObjectWithId object (456)"

        obj = ObjectWithId()
        assert _get_cache_key_for_arg(obj) == "ObjectWithId::456"

    def test_get_cache_key_for_arg_priority_order(self):
        # __cache_key__ method should take priority over pk/id
        class ModelWithCacheKey:
            pk = 123
            id = 456

            def __cache_key__(self):
                return "custom_override"

        obj = ModelWithCacheKey()
        assert _get_cache_key_for_arg(obj) == "custom_override"

        # _cache_key attribute should take priority over pk/id
        class ModelWithCacheKeyAttr:
            pk = 123
            id = 456
            _cache_key = "attr_override"

        obj2 = ModelWithCacheKeyAttr()
        assert _get_cache_key_for_arg(obj2) == "attr_override"

        # pk should take priority over id
        class ModelWithBoth:
            pk = 123
            id = 456

        obj3 = ModelWithBoth()
        assert _get_cache_key_for_arg(obj3) == "ModelWithBoth::123"

    def test_cache_with_custom_objects(self, cache_manager):
        call_count = 0

        class User:
            def __init__(self, user_id):
                self.id = user_id

            def __cache_key__(self):
                return f"User::{self.id}"

        @cache_with_deps(cache_manager=cache_manager)
        def get_user_data(user):
            nonlocal call_count
            call_count += 1
            return f"data_for_{user.id}"

        user1 = User(123)
        user2 = User(123)  # Different object, same ID
        user3 = User(456)  # Different ID

        # Same logical user should hit cache
        result1 = get_user_data(user1)
        result2 = get_user_data(user2)

        assert result1 == "data_for_123"
        assert result2 == "data_for_123"
        assert call_count == 1

        # Different user should miss cache
        result3 = get_user_data(user3)
        assert result3 == "data_for_456"
        assert call_count == 2

    def test_cache_with_mixed_argument_types(self, cache_manager):
        call_count = 0

        class Model:
            def __init__(self, model_id):
                self.id = model_id

            def __cache_key__(self):
                return f"Model::{self.id}"

        @cache_with_deps(cache_manager=cache_manager)
        def complex_function(model, count, name="default"):
            nonlocal call_count
            call_count += 1
            return f"{model.id}_{count}_{name}"

        model1 = Model(42)
        model2 = Model(42)  # Same logical model

        # Same arguments should hit cache
        result1 = complex_function(model1, 10, name="test")
        result2 = complex_function(model2, 10, name="test")

        assert result1 == "42_10_test"
        assert result2 == "42_10_test"
        assert call_count == 1

        # Different arguments should miss cache
        result3 = complex_function(model1, 20, name="test")
        assert result3 == "42_20_test"
        assert call_count == 2


class TestTTLFunctionality:
    def test_set_cache_ttl_sync(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Function can set TTL during execution
            set_cache_ttl(300)
            return x * 2

        # Initially no TTL set
        result1 = expensive_function(5)
        result2 = expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        # Verify TTL was applied by checking Redis
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = cache_manager._cache_key(_generate_cache_key(expensive_function, (5,), {}))
        ttl = cache_manager.redis.ttl(cache_key)
        assert ttl > 250  # Should be close to 300

    def test_context_ttl_overrides_decorator_sync(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, ttl=100)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Function sets TTL during execution - this should override decorator
            set_cache_ttl(300)
            return x * 2

        result = expensive_function(5)

        assert result == 10
        assert call_count == 1

        # Verify function TTL was used (300s), not decorator TTL (100s)
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = cache_manager._cache_key(_generate_cache_key(expensive_function, (5,), {}))
        ttl = cache_manager.redis.ttl(cache_key)
        assert ttl > 250  # Should be close to 300, not 100

    @pytest.mark.asyncio
    async def test_set_cache_ttl_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Function can set TTL during execution
            set_cache_ttl(300)
            return x * 2

        # Initially no TTL set
        result1 = await expensive_function(5)
        result2 = await expensive_function(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1

        # Verify TTL was applied by checking Redis
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = async_cache_manager._cache_key(
            _generate_cache_key(expensive_function, (5,), {})
        )
        ttl = await async_cache_manager.redis.ttl(cache_key)
        assert ttl > 250  # Should be close to 300

    @pytest.mark.asyncio
    async def test_context_ttl_overrides_decorator_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, ttl=100)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Function sets TTL during execution - this should override decorator
            set_cache_ttl(300)
            return x * 2

        result = await expensive_function(5)

        assert result == 10
        assert call_count == 1

        # Verify function TTL was used (300s), not decorator TTL (100s)
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = async_cache_manager._cache_key(
            _generate_cache_key(expensive_function, (5,), {})
        )
        ttl = await async_cache_manager.redis.ttl(cache_key)
        assert ttl > 250  # Should be close to 300, not 100

    def test_decorator_ttl_when_no_context_sync(self, cache_manager):
        call_count = 0

        @cache_with_deps(cache_manager=cache_manager, ttl=100)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Clear any context TTL
        set_cache_ttl(None)
        result = expensive_function(8)

        assert result == 16
        assert call_count == 1

        # Verify decorator TTL was used
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = cache_manager._cache_key(_generate_cache_key(expensive_function, (8,), {}))
        ttl = cache_manager.redis.ttl(cache_key)
        assert 90 < ttl <= 100  # Should be close to 100

    @pytest.mark.asyncio
    async def test_decorator_ttl_when_no_context_async(self, async_cache_manager):
        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager, ttl=100)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Clear any context TTL
        set_cache_ttl(None)
        result = await expensive_function(8)

        assert result == 16
        assert call_count == 1

        # Verify decorator TTL was used
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = async_cache_manager._cache_key(
            _generate_cache_key(expensive_function, (8,), {})
        )
        ttl = await async_cache_manager.redis.ttl(cache_key)
        assert 90 < ttl <= 100  # Should be close to 100

    def test_cache_ttl_context_isolation_sync(self, cache_manager):
        """Test that decorated functions execute with clean TTL context."""
        from simple_dep_cache.context import get_cache_ttl

        call_count = 0

        @cache_with_deps(cache_manager=cache_manager)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Verify TTL context is cleared inside function
            assert get_cache_ttl() is None
            return x * 2

        # Set TTL before calling function
        set_cache_ttl(200)
        result = expensive_function(10)

        assert result == 20
        assert call_count == 1

        # After function execution, context should be restored
        assert get_cache_ttl() == 200

        # Verify the cache was set with no TTL (function didn't set one)
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = cache_manager._cache_key(_generate_cache_key(expensive_function, (10,), {}))
        ttl = cache_manager.redis.ttl(cache_key)
        assert ttl == -1  # No TTL set

    @pytest.mark.asyncio
    async def test_cache_ttl_context_isolation_async(self, async_cache_manager):
        """Test that decorated functions execute with clean TTL context (async)."""
        from simple_dep_cache.context import get_cache_ttl

        call_count = 0

        @async_cache_with_deps(cache_manager=async_cache_manager)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            # Verify TTL context is cleared inside function
            assert get_cache_ttl() is None
            return x * 2

        # Set TTL before calling function
        set_cache_ttl(250)
        result = await expensive_function(10)

        assert result == 20
        assert call_count == 1

        # After function execution, context should be restored
        assert get_cache_ttl() == 250

        # Verify the cache was set with no TTL (function didn't set one)
        from simple_dep_cache.decorators import _generate_cache_key

        cache_key = async_cache_manager._cache_key(
            _generate_cache_key(expensive_function, (10,), {})
        )
        ttl = await async_cache_manager.redis.ttl(cache_key)
        assert ttl == -1  # No TTL set


class TestCallbackFunctionality:
    def test_callback_on_cache_miss_and_hit_sync(self, cache_manager):
        """Test callback is called correctly on cache miss and hit for sync decorator."""
        call_count = 0
        callback_calls = []

        def test_callback(**kwargs):
            callback_calls.append(kwargs)

        @cache_with_deps(cache_manager=cache_manager, callback=test_callback)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should be cache miss
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        assert len(callback_calls) == 1
        assert callback_calls[0]["is_hit"] is False
        assert callback_calls[0]["cached_result"] is None
        assert callback_calls[0]["args"] == (5,)

        # Second call - should be cache hit
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment
        assert len(callback_calls) == 2
        assert callback_calls[1]["is_hit"] is True
        assert callback_calls[1]["cached_result"] == 10
        assert callback_calls[1]["args"] == (5,)

    def test_callback_with_different_arguments_sync(self, cache_manager):
        """Test callback behavior with different function arguments."""
        call_count = 0
        callback_calls = []

        def test_callback(**kwargs):
            callback_calls.append(kwargs)

        @cache_with_deps(cache_manager=cache_manager, callback=test_callback)
        def expensive_function(x, multiplier=2):
            nonlocal call_count
            call_count += 1
            return x * multiplier

        # Different arguments should result in different cache entries
        expensive_function(5, multiplier=2)  # miss
        expensive_function(5, multiplier=3)  # miss
        expensive_function(5, multiplier=2)  # hit
        expensive_function(5, multiplier=3)  # hit

        assert call_count == 2
        assert len(callback_calls) == 4

        # Check miss calls
        assert callback_calls[0]["is_hit"] is False
        assert callback_calls[0]["args"] == (5,)
        assert callback_calls[0]["kwargs"] == {"multiplier": 2}

        assert callback_calls[1]["is_hit"] is False
        assert callback_calls[1]["args"] == (5,)
        assert callback_calls[1]["kwargs"] == {"multiplier": 3}

        # Check hit calls
        assert callback_calls[2]["is_hit"] is True
        assert callback_calls[3]["is_hit"] is True

    def test_callback_exception_does_not_break_function_sync(self, cache_manager, caplog):
        """Test that callback exceptions don't break the main function flow."""
        call_count = 0

        def failing_callback(**kwargs):
            raise ValueError("Callback error")

        @cache_with_deps(cache_manager=cache_manager, callback=failing_callback)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Capture log messages at WARNING level
        with caplog.at_level(logging.WARNING):
            result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Check that warning was logged
        assert "Cache callback exception occurred" in caplog.text
        assert "Callback error" in caplog.text
        caplog.clear()

        # Second call should still hit cache (and log warning again)
        with caplog.at_level(logging.WARNING):
            result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1

        # Check that warning was logged again
        assert "Cache callback exception occurred" in caplog.text

    @pytest.mark.asyncio
    async def test_callback_on_cache_miss_and_hit_async(self, async_cache_manager):
        """Test callback is called correctly on cache miss and hit for async decorator."""
        call_count = 0
        callback_calls = []

        def test_callback(**kwargs):
            callback_calls.append(kwargs)

        @async_cache_with_deps(cache_manager=async_cache_manager, callback=test_callback)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should be cache miss
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        assert len(callback_calls) == 1
        assert callback_calls[0]["is_hit"] is False
        assert callback_calls[0]["cached_result"] is None

        # Second call - should be cache hit
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment
        assert len(callback_calls) == 2
        assert callback_calls[1]["is_hit"] is True
        assert callback_calls[1]["cached_result"] == 10

    @pytest.mark.asyncio
    async def test_async_callback_support(self, async_cache_manager):
        """Test that async callbacks are supported in async decorator."""
        call_count = 0
        callback_calls = []

        async def async_test_callback(**kwargs):
            callback_calls.append(kwargs)

        @async_cache_with_deps(cache_manager=async_cache_manager, callback=async_test_callback)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should be cache miss
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        assert len(callback_calls) == 1
        assert callback_calls[0]["is_hit"] is False

        # Second call - should be cache hit
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1
        assert len(callback_calls) == 2
        assert callback_calls[1]["is_hit"] is True

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_break_function_async(
        self, async_cache_manager, caplog
    ):
        """Test that callback exceptions don't break the main function flow (async)."""
        call_count = 0

        def failing_callback(**kwargs):
            raise ValueError("Callback error")

        @async_cache_with_deps(cache_manager=async_cache_manager, callback=failing_callback)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Function should work normally despite callback failure
        with caplog.at_level(logging.WARNING):
            result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Check that warning was logged
        assert "Async cache callback exception occurred" in caplog.text
        assert "Callback error" in caplog.text
        caplog.clear()

        # Second call should still hit cache (and log warning again)
        with caplog.at_level(logging.WARNING):
            result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1

        # Check that warning was logged again
        assert "Async cache callback exception occurred" in caplog.text

    @pytest.mark.asyncio
    async def test_async_callback_exception_does_not_break_function(
        self, async_cache_manager, caplog
    ):
        """Test that async callback exceptions don't break the main function flow."""
        call_count = 0

        async def failing_async_callback(**kwargs):
            raise ValueError("Async callback error")

        @async_cache_with_deps(cache_manager=async_cache_manager, callback=failing_async_callback)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Function should work normally despite async callback failure
        with caplog.at_level(logging.WARNING):
            result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Check that warning was logged
        assert "Async cache callback exception occurred" in caplog.text
        assert "Async callback error" in caplog.text
        caplog.clear()

        # Second call should still hit cache (and log warning again)
        with caplog.at_level(logging.WARNING):
            result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1

        # Check that warning was logged again
        assert "Async cache callback exception occurred" in caplog.text

    def test_callback_with_dependencies_sync(self, cache_manager):
        """Test callback works correctly with dependency tracking."""
        call_count = 0
        callback_calls = []

        def test_callback(**kwargs):
            callback_calls.append(kwargs)

        @cache_with_deps(
            cache_manager=cache_manager, dependencies={"static_dep"}, callback=test_callback
        )
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            add_dependency("dynamic_dep")
            return x * 2

        # First call - miss
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1
        assert len(callback_calls) == 1
        assert callback_calls[0]["is_hit"] is False

        # Second call - hit
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1
        assert len(callback_calls) == 2
        assert callback_calls[1]["is_hit"] is True

        # Invalidate dependency - should cause miss
        cache_manager.invalidate_dependency("static_dep")
        result3 = expensive_function(5)
        assert result3 == 10
        assert call_count == 2
        assert len(callback_calls) == 3
        assert callback_calls[2]["is_hit"] is False

    def test_callback_with_exception_caching_sync(self, cache_manager):
        """Test callback behavior with exception caching."""
        call_count = 0
        callback_calls = []

        def test_callback(**kwargs):
            callback_calls.append(kwargs)

        @cache_with_deps(
            cache_manager=cache_manager, cache_exception_types=[ValueError], callback=test_callback
        )
        def failing_function(x):
            nonlocal call_count
            call_count += 1
            if x < 0:
                raise ValueError(f"Negative value: {x}")
            return x * 2

        # First call with exception - should cache the exception
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 1
        assert len(callback_calls) == 1
        assert callback_calls[0]["is_hit"] is False

        # Second call with same exception - should hit cache
        with pytest.raises(ValueError, match="Negative value: -1"):
            failing_function(-1)
        assert call_count == 1  # Should not increment
        assert len(callback_calls) == 2
        assert callback_calls[1]["is_hit"] is True
        # cached_result should be the serialized exception
        assert callback_calls[1]["cached_result"] is not None

    def test_callback_parameters_sync(self, cache_manager):
        """Test that callback receives all expected parameters."""
        callback_calls = []

        def detailed_callback(**kwargs):
            callback_calls.append(kwargs)

        @cache_with_deps(cache_manager=cache_manager, callback=detailed_callback)
        def test_function(x, y=10):
            return x + y

        test_function(5, y=20)

        assert len(callback_calls) == 1
        callback_kwargs = callback_calls[0]

        # Check all expected parameters are present
        assert "func" in callback_kwargs
        assert "cache_manager" in callback_kwargs
        assert "args" in callback_kwargs
        assert "kwargs" in callback_kwargs
        assert "is_hit" in callback_kwargs
        assert "cached_result" in callback_kwargs

        # Function should be a callable with the same name as the original function
        assert callable(callback_kwargs["func"])
        assert callback_kwargs["func"].__name__ == test_function.__name__
        assert callback_kwargs["cache_manager"] == cache_manager
        assert callback_kwargs["args"] == (5,)
        assert callback_kwargs["kwargs"] == {"y": 20}
        assert callback_kwargs["is_hit"] is False
        assert callback_kwargs["cached_result"] is None

    @pytest.mark.asyncio
    async def test_callback_parameters_async(self, async_cache_manager):
        """Test that async callback receives all expected parameters."""
        callback_calls = []

        async def detailed_async_callback(**kwargs):
            callback_calls.append(kwargs)

        @async_cache_with_deps(cache_manager=async_cache_manager, callback=detailed_async_callback)
        async def test_function(x, y=10):
            return x + y

        await test_function(5, y=20)

        assert len(callback_calls) == 1
        callback_kwargs = callback_calls[0]

        # Check all expected parameters are present
        assert "func" in callback_kwargs
        assert "cache_manager" in callback_kwargs
        assert "args" in callback_kwargs
        assert "kwargs" in callback_kwargs
        assert "is_hit" in callback_kwargs
        assert "cached_result" in callback_kwargs

        # Function should be a callable with the same name as the original function
        assert callable(callback_kwargs["func"])
        assert callback_kwargs["func"].__name__ == test_function.__name__
        assert callback_kwargs["cache_manager"] == async_cache_manager
        assert callback_kwargs["args"] == (5,)
        assert callback_kwargs["kwargs"] == {"y": 20}
        assert callback_kwargs["is_hit"] is False
        assert callback_kwargs["cached_result"] is None
