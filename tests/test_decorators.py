"""Tests for simple_dep_cache.decorators module."""

import asyncio

import pytest

from simple_dep_cache.context import reset as reset_context
from simple_dep_cache.decorators import cache_with_deps
from simple_dep_cache.fakes import FakeAsyncCacheBackend, FakeCacheBackend


@pytest.fixture
def fake_backend():
    """Provide a fake cache backend for testing."""
    from simple_dep_cache.config import RedisConfig

    config = RedisConfig()
    config.prefix = "test"
    return FakeCacheBackend(config)


@pytest.fixture
def fake_async_backend():
    """Provide a fake async cache backend for testing."""
    from simple_dep_cache.config import RedisConfig

    config = RedisConfig()
    config.prefix = "test"
    return FakeAsyncCacheBackend(config)


@pytest.fixture
def cache_manager(fake_backend):
    """Provide a cache manager with fake backend."""
    from simple_dep_cache.config import RedisConfig
    from simple_dep_cache.manager import CacheManager

    config = RedisConfig()
    config.prefix = "test"
    return CacheManager(config=config, backend=fake_backend)


@pytest.fixture
def async_cache_manager(fake_async_backend):
    """Provide an async cache manager with fake async backend."""
    from simple_dep_cache.config import RedisConfig
    from simple_dep_cache.manager import CacheManager

    config = RedisConfig()
    config.prefix = "test"
    return CacheManager(config=config, async_backend=fake_async_backend)


@pytest.fixture
def mock_get_manager(cache_manager):
    """Mock get_or_create_cache_manager to use fake cache manager."""
    from simple_dep_cache import decorators
    from simple_dep_cache import manager as manager_module

    original_get_manager = decorators.get_or_create_cache_manager
    original_manager_get_manager = manager_module.get_or_create_cache_manager

    def mock_get_manager_impl(name=None):
        if name == "test" or name is None:
            return cache_manager
        # For other names, create managers with same fake backend but different configs
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import CacheManager

        config = RedisConfig()
        config.prefix = name
        return CacheManager(config=config, backend=cache_manager.backend)

    decorators.get_or_create_cache_manager = mock_get_manager_impl
    manager_module.get_or_create_cache_manager = mock_get_manager_impl

    yield

    # Restore original function
    decorators.get_or_create_cache_manager = original_get_manager
    manager_module.get_or_create_cache_manager = original_manager_get_manager


@pytest.fixture
def mock_get_async_manager(async_cache_manager):
    """Mock get_or_create_cache_manager to use fake async cache manager."""
    from simple_dep_cache import decorators
    from simple_dep_cache import manager as manager_module

    original_get_manager = decorators.get_or_create_cache_manager
    original_manager_get_manager = manager_module.get_or_create_cache_manager

    def mock_get_manager_impl(name=None):
        if name == "test" or name is None:
            return async_cache_manager
        # For other names, create managers with same fake backend but different configs
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import CacheManager

        config = RedisConfig()
        config.prefix = name
        return CacheManager(config=config, async_backend=async_cache_manager.async_backend)

    decorators.get_or_create_cache_manager = mock_get_manager_impl
    manager_module.get_or_create_cache_manager = mock_get_manager_impl

    yield

    # Restore original function
    decorators.get_or_create_cache_manager = original_get_manager
    manager_module.get_or_create_cache_manager = original_manager_get_manager


class TestCacheWithDepsBasicFunctionality:
    """Test basic functionality of cache_with_deps decorator."""

    def setup_method(self):
        """Reset context before each test."""
        reset_context()

    def test_sync_function_caching(self, mock_get_manager):
        """Test basic sync function caching."""
        call_count = 0

        @cache_with_deps(name="test")
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "name": f"User {user_id}"}

        # First call should execute function
        result1 = get_user(123)
        assert result1 == {"id": 123, "name": "User 123"}
        assert call_count == 1

        # Second call should return cached result
        result2 = get_user(123)
        assert result2 == {"id": 123, "name": "User 123"}
        assert call_count == 1  # No additional calls

    @pytest.mark.asyncio
    async def test_async_function_caching(self, mock_get_async_manager):
        """Test basic async function caching."""
        call_count = 0

        @cache_with_deps(name="test")
        async def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)  # Simulate async operation
            return {"id": user_id, "name": f"User {user_id}"}

        # First call should execute function
        result1 = await get_user(123)
        assert result1 == {"id": 123, "name": "User 123"}
        assert call_count == 1

        # Second call should return cached result
        result2 = await get_user(123)
        assert result2 == {"id": 123, "name": "User 123"}
        assert call_count == 1  # No additional calls

    def test_function_with_ttl(self, mock_get_manager):
        """Test function with TTL."""
        call_count = 0

        @cache_with_deps(name="test", ttl=60)
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "name": f"User {user_id}"}

        # Call function
        result = get_user(123)
        assert result == {"id": 123, "name": "User 123"}
        assert call_count == 1

        # Call again with same args, should use cache
        result = get_user(123)
        assert call_count == 1

    def test_function_with_dependencies(self, mock_get_manager):
        """Test function with explicit dependencies."""
        call_count = 0

        @cache_with_deps(name="test", dependencies={"user:123"})
        def get_user_posts(user_id: int):
            nonlocal call_count
            call_count += 1
            return [{"id": 1, "title": "Post 1"}]

        # First call
        result1 = get_user_posts(123)
        assert result1 == [{"id": 1, "title": "Post 1"}]
        assert call_count == 1

        # Second call should use cache
        result2 = get_user_posts(123)
        assert result2 == [{"id": 1, "title": "Post 1"}]
        assert call_count == 1

        # Invalidate dependency and call again
        # Note: get_or_create_cache_manager is already mocked by the fixture
        from simple_dep_cache.manager import get_or_create_cache_manager

        manager = get_or_create_cache_manager("test")
        manager.invalidate_dependency("user:123")
        result3 = get_user_posts(123)
        assert call_count == 2  # Should re-execute

    def test_exception_caching(self, mock_get_manager):
        """Test exception caching functionality."""
        call_count = 0

        @cache_with_deps(name="test", cache_exception_types=[ValueError])
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")

        # First call should cache the exception
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        assert call_count == 1

        # Second call should raise cached exception without re-executing
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        assert call_count == 1

    def test_exception_not_cached_when_type_not_listed(self, mock_get_manager):
        """Test that exceptions not in cache_exception_types are not cached."""
        call_count = 0

        @cache_with_deps(name="test", cache_exception_types=[KeyError])
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")

        # First call should raise and not cache
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        assert call_count == 1

        # Second call should re-execute (not cached)
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        assert call_count == 2

    def test_caching_disabled(self, monkeypatch):
        """Test behavior when caching is disabled."""

        # Mock get_or_create_cache_manager to return None
        def mock_get_manager(name=None):
            return None

        from simple_dep_cache import decorators
        from simple_dep_cache import manager as manager_module

        monkeypatch.setattr(decorators, "get_or_create_cache_manager", mock_get_manager)
        monkeypatch.setattr(manager_module, "get_or_create_cache_manager", mock_get_manager)

        call_count = 0

        @cache_with_deps(name="test")
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "name": f"User {user_id}"}

        # All calls should execute function (no caching)
        result1 = get_user(123)
        assert result1 == {"id": 123, "name": "User 123"}
        assert call_count == 1

        result2 = get_user(123)
        assert result2 == {"id": 123, "name": "User 123"}
        assert call_count == 2  # Should re-execute


class TestNestedFunctionsWithDependencies:
    """Test nested decorated functions with dependencies."""

    def setup_method(self):
        """Reset context before each test."""
        import simple_dep_cache.manager as manager_module

        manager_module._managers = {}
        reset_context()

    def test_nested_functions_same_manager(self):
        """Test S1: Nested functions with same manager - dependencies merge to outer."""
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import get_or_create_cache_manager

        config = RedisConfig()

        backend = FakeCacheBackend(config)
        manager = get_or_create_cache_manager("my_manager", config=config, backend=backend)

        assert manager is not None

        outer_calls = 0
        inner_calls = 0

        @cache_with_deps(name="my_manager", dependencies={"user:1"})
        def get_user_with_posts(user_id: int):
            nonlocal outer_calls
            outer_calls += 1
            posts = get_posts_for_user(user_id)  # Inner function call
            return {"user": f"user_{user_id}", "posts": posts}

        @cache_with_deps(name="my_manager", dependencies={"post:123"})
        def get_posts_for_user(user_id: int):
            nonlocal inner_calls
            inner_calls += 1
            return [{"id": 123, "title": "Post 123"}]

        # Execute outer function
        result = get_user_with_posts(1)
        assert result == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 1
        assert inner_calls == 1

        # Execute again - both should use cache
        result2 = get_user_with_posts(1)

        assert result2 == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 1
        assert inner_calls == 1

        # Invalidate user dependency - should invalidate outer function
        # Outer function depends on both ["user:1", "post:123"] due to merging
        manager.invalidate_dependency("user:1")

        result3 = get_user_with_posts(1)

        assert result3 == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 2  # Outer re-executed
        assert inner_calls == 1  # Inner still cached

        manager.invalidate_dependency("post:123")
        result4 = get_user_with_posts(1)
        assert result4 == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 3  # Outer re-executed again
        assert inner_calls == 2  # Inner re-executed

    def test_nested_functions_different_managers(self):
        """Test S2: Nested functions with different managers - manager isolation."""
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import get_or_create_cache_manager

        config1 = RedisConfig()
        config1.prefix = "manager1"
        config2 = RedisConfig()
        config2.prefix = "manager2"

        backend1 = FakeCacheBackend(config1)
        backend2 = FakeCacheBackend(config2)

        manager1 = get_or_create_cache_manager("manager1", config=config1, backend=backend1)
        manager2 = get_or_create_cache_manager("manager2", config=config2, backend=backend2)

        assert manager1 is not None
        assert manager2 is not None

        outer_calls = 0
        inner_calls = 0

        @cache_with_deps(name="manager1", dependencies={"user:1"})
        def get_user_with_posts(user_id: int):
            nonlocal outer_calls
            outer_calls += 1
            posts = get_posts_for_user(user_id)  # Inner function uses different manager
            return {"user": f"user_{user_id}", "posts": posts}

        @cache_with_deps(name="manager2", dependencies={"post:123"})
        def get_posts_for_user(user_id: int):
            nonlocal inner_calls
            inner_calls += 1
            return [{"id": 123, "title": "Post 123"}]

        # Execute outer function
        result = get_user_with_posts(1)
        assert result == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 1
        assert inner_calls == 1

        # Execute again - both should use cache
        result2 = get_user_with_posts(1)
        assert outer_calls == 1
        assert inner_calls == 1

        # Invalidate post dependency from manager1 - only affects outer function
        # Inner function uses manager2, so it stays cached
        manager1.invalidate_dependency("post:123")

        result3 = get_user_with_posts(1)
        assert outer_calls == 1  # Outer still cached
        assert inner_calls == 1  # Inner still cached

        manager2.invalidate_dependency("post:123")
        result4 = get_user_with_posts(1)
        assert outer_calls == 1  # Outer still cached
        assert inner_calls == 1  # outer cached, so inner did not get called

        manager1.invalidate_dependency("user:1")
        result5 = get_user_with_posts(1)
        assert outer_calls == 2  # Outer re-executed
        assert inner_calls == 2  # Inner re-executed

    @pytest.mark.asyncio
    async def test_nested_async_functions_same_manager(self):
        """Test async nested functions with same manager."""
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import get_or_create_cache_manager

        config1 = RedisConfig()
        config1.prefix = "manager1"
        config2 = RedisConfig()
        config2.prefix = "manager1"

        async_backend1 = FakeAsyncCacheBackend(config1)
        async_backend2 = FakeAsyncCacheBackend(config2)

        manager1 = get_or_create_cache_manager(
            "manager1", config=config1, async_backend=async_backend1
        )
        manager2 = get_or_create_cache_manager(
            "manager1", config=config2, async_backend=async_backend2
        )
        assert manager1 is not None
        assert (
            manager1 is manager2
        )  # since the manager1 is already created, config and async_backend are ignored

        outer_calls = 0
        inner_calls = 0

        @cache_with_deps(name="manager1", dependencies={"user:1"})
        async def get_user_with_posts(user_id: int):
            nonlocal outer_calls
            outer_calls += 1
            posts = await get_posts_for_user(user_id)
            return {"user": f"user_{user_id}", "posts": posts}

        @cache_with_deps(name="manager1", dependencies={"post:123"})
        async def get_posts_for_user(user_id: int):
            nonlocal inner_calls
            inner_calls += 1
            await asyncio.sleep(0)  # Simulate async operation
            return [{"id": 123, "title": "Post 123"}]

        # Execute outer function
        result = await get_user_with_posts(1)
        assert result == {"user": "user_1", "posts": [{"id": 123, "title": "Post 123"}]}
        assert outer_calls == 1
        assert inner_calls == 1

        # Execute again - both should use cache
        result2 = await get_user_with_posts(1)
        assert outer_calls == 1
        assert inner_calls == 1

        # Invalidate user dependency - should invalidate outer function
        await manager1.ainvalidate_dependency("user:1")

        result3 = await get_user_with_posts(1)
        assert outer_calls == 2  # Outer re-executed
        assert inner_calls == 1  # Inner still cached


class TestMultiManagerNonNested:
    """Test non-nested functions with multiple managers."""

    def setup_method(self):
        """Reset context before each test."""
        reset_context()

    def test_non_nested_multi_manager_functions(self):
        """Test S3: Non-nested functions with different managers."""
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import CacheManager

        config1 = RedisConfig()
        config1.prefix = "user_cache"
        config2 = RedisConfig()
        config2.prefix = "post_cache"

        backend1 = FakeCacheBackend(config1)
        backend2 = FakeCacheBackend(config2)

        manager1 = CacheManager(config=config1, backend=backend1)
        manager2 = CacheManager(config=config2, backend=backend2)

        user_calls = 0
        post_calls = 0

        @cache_with_deps(name="user_cache", dependencies={"user:1"})
        def get_user(user_id: int):
            nonlocal user_calls
            user_calls += 1
            return {"id": user_id, "name": f"User {user_id}"}

        @cache_with_deps(name="post_cache", dependencies={"post:123"})
        def get_post(post_id: int):
            nonlocal post_calls
            post_calls += 1
            return {"id": post_id, "title": f"Post {post_id}"}

        # Execute both functions
        user_result = get_user(1)
        post_result = get_post(123)

        assert user_result == {"id": 1, "name": "User 1"}
        assert post_result == {"id": 123, "title": "Post 123"}
        assert user_calls == 1
        assert post_calls == 1

        # Execute again - both should use cache
        user_result2 = get_user(1)
        post_result2 = get_post(123)
        assert user_calls == 1
        assert post_calls == 1

        # Invalidate user dependency - only affects user function
        manager1.invalidate_dependency("user:1")

        user_result3 = get_user(1)
        post_result3 = get_post(123)  # Should still use cache

        assert user_calls == 2  # User re-executed
        assert post_calls == 1  # Post still cached

        # Invalidate post dependency - only affects post function
        manager2.invalidate_dependency("post:123")

        user_result4 = get_user(1)  # Should still use cache
        post_result4 = get_post(123)  # Should re-execute

        assert user_calls == 2  # User still cached
        assert post_calls == 2  # Post re-executed

    @pytest.mark.asyncio
    async def test_non_nested_multi_manager_async(self):
        """Test S3: Non-nested async functions with different managers."""
        from simple_dep_cache.config import RedisConfig
        from simple_dep_cache.manager import CacheManager

        config1 = RedisConfig()
        config1.prefix = "user_cache"
        config2 = RedisConfig()
        config2.prefix = "post_cache"

        async_backend1 = FakeAsyncCacheBackend(config1)
        async_backend2 = FakeAsyncCacheBackend(config2)

        manager1 = CacheManager(config=config1, async_backend=async_backend1)
        manager2 = CacheManager(config=config2, async_backend=async_backend2)

        user_calls = 0
        post_calls = 0

        @cache_with_deps(name="user_cache", dependencies={"user:1"})
        async def get_user(user_id: int):
            nonlocal user_calls
            user_calls += 1
            await asyncio.sleep(0)
            return {"id": user_id, "name": f"User {user_id}"}

        @cache_with_deps(name="post_cache", dependencies={"post:123"})
        async def get_post(post_id: int):
            nonlocal post_calls
            post_calls += 1
            await asyncio.sleep(0)
            return {"id": post_id, "title": f"Post {post_id}"}

        # Execute both functions
        user_result, post_result = await asyncio.gather(get_user(1), get_post(123))

        assert user_result == {"id": 1, "name": "User 1"}
        assert post_result == {"id": 123, "title": "Post 123"}
        assert user_calls == 1
        assert post_calls == 1

        # Execute again - both should use cache
        user_result2, post_result2 = await asyncio.gather(get_user(1), get_post(123))
        assert user_calls == 1
        assert post_calls == 1

        # Invalidate user dependency - only affects user function
        await manager1.ainvalidate_dependency("user:1")

        user_result3, post_result3 = await asyncio.gather(get_user(1), get_post(123))

        assert user_calls == 2  # User re-executed
        assert post_calls == 1  # Post still cached

        # Invalidate post dependency - only affects post function
        await manager2.ainvalidate_dependency("post:123")

        user_result4, post_result4 = await asyncio.gather(get_user(1), get_post(123))

        assert user_calls == 2  # User still cached
        assert post_calls == 2  # Post re-executed


class TestCacheKeyGeneration:
    """Test cache key generation for different argument types."""

    def setup_method(self):
        """Reset context before each test."""
        reset_context()

    def test_cache_key_with_different_args(self, cache_manager):
        """Test that different arguments generate different cache keys."""
        call_count = 0

        @cache_with_deps(name="test")
        def get_data(arg1, arg2=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"arg1": arg1, "arg2": arg2, "kwargs": kwargs}

        # Different positional args
        get_data(1)
        get_data(2)
        assert call_count == 2

        # Same args should use cache
        get_data(1)
        assert call_count == 2

        # Different keyword args
        get_data(1, arg2="test")
        assert call_count == 3

        # Same combination should use cache
        get_data(1, arg2="test")
        assert call_count == 3

    def test_cache_key_with_objects(self, cache_manager):
        """Test cache key generation with objects."""
        call_count = 0

        class User:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        @cache_with_deps(name="test")
        def get_user(user):
            nonlocal call_count
            call_count += 1
            return {"id": user.id, "name": user.name}

        user1 = User(1, "Alice")
        user2 = User(1, "Alice")  # Same data, different instance

        # Same logical data should use cache (based on string representation)
        get_user(user1)
        assert call_count == 1

        get_user(user2)
        assert call_count == 2  # Different instances = different cache keys

        # Same instance should use cache
        get_user(user1)
        assert call_count == 2
