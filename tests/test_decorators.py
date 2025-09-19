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
