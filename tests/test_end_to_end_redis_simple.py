"""End-to-end tests for simple_dep_cache using real Redis."""

import asyncio
import os
import time

import pytest
import redis

from simple_dep_cache.context import reset as reset_context
from simple_dep_cache.decorators import cache_with_deps
from simple_dep_cache.manager import get_or_create_cache_manager


@pytest.fixture(scope="module")
def redis_environment():
    """Set up environment variables for Redis testing."""
    os.environ["DEP_CACHE_ENABLED"] = "true"
    os.environ["REDIS_HOST"] = "localhost"
    os.environ["REDIS_PORT"] = "6379"
    os.environ["REDIS_DB"] = "0"
    yield
    # Clean up environment variables after tests
    for key in ["DEP_CACHE_ENABLED", "REDIS_HOST", "REDIS_PORT", "REDIS_DB"]:
        os.environ.pop(key, None)


@pytest.fixture(scope="function")
def reset_cache_context():
    """Reset cache context before each test."""
    import simple_dep_cache.manager as manager_module

    manager_module._managers = {}
    reset_context()


pytestmark = pytest.mark.redis_e2e


@pytest.fixture(scope="function")
def redis_client():
    """Create Redis client and check connection."""
    try:
        client = redis.Redis(host="localhost", port=6379, db=0)
        client.ping()
        yield client
        client.close()
    except (redis.ConnectionError, ConnectionRefusedError, ImportError):
        pytest.skip(
            "Redis is not running. Please start Redis with: docker-compose up -d\n"
            "Then wait a few seconds for Redis to start and run the tests again."
        )


@pytest.fixture(scope="function")
def clean_redis(redis_client):
    """Clear all Redis data before each test for test isolation."""
    redis_client.flushdb()  # Clear current database
    yield redis_client


class TestRedisEndToEnd:
    """End-to-end tests using real Redis.

    These tests use the clean_redis fixture which clears Redis data before each test,
    ensuring complete test isolation. Each test starts with a fresh Redis database
    and doesn't interfere with other tests or previous test runs.
    """

    def test_basic_caching_with_redis(self, redis_environment, reset_cache_context, clean_redis):
        """Test basic caching functionality with Redis."""
        call_count = 0

        @cache_with_deps()
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

        # Different args should execute function again
        result3 = get_user(456)
        assert result3 == {"id": 456, "name": "User 456"}
        assert call_count == 2

    def test_dependency_invalidation_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test dependency invalidation with Redis."""
        call_count = 0

        @cache_with_deps(dependencies={"user:123"})
        def get_user_posts(user_id: int):
            nonlocal call_count
            call_count += 1
            return [{"id": 1, "title": "Post 1"}, {"id": 2, "title": "Post 2"}]

        # First call should execute function
        result1 = get_user_posts(123)
        assert result1 == [{"id": 1, "title": "Post 1"}, {"id": 2, "title": "Post 2"}]
        assert call_count == 1

        # Second call should use cache
        result2 = get_user_posts(123)
        assert result2 == [{"id": 1, "title": "Post 1"}, {"id": 2, "title": "Post 2"}]
        assert call_count == 1

        # Invalidate dependency and call again
        manager = get_or_create_cache_manager()
        assert manager is not None
        manager.invalidate_dependency("user:123")
        result3 = get_user_posts(123)
        assert call_count == 2  # Should re-execute

    def test_ttl_with_redis(self, redis_environment, reset_cache_context, clean_redis):
        """Test TTL functionality with Redis."""
        call_count = 0

        @cache_with_deps(ttl=5)  # 1 second TTL
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return {"id": user_id, "name": f"User {user_id}"}

        # Call function
        result = get_user(123)
        assert result == {"id": 123, "name": "User 123"}
        assert call_count == 1

        # Call again immediately - should use cache
        result = get_user(123)
        assert call_count == 1

        # Wait for TTL to expire and call again
        time.sleep(5.1)
        result = get_user(123)
        assert call_count == 2  # Should re-execute after TTL expiry

    def test_exception_caching_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test exception caching with Redis."""
        call_count = 0

        @cache_with_deps(cache_exception_types=[ValueError])
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

    def test_complex_data_serialization_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test serialization of complex data structures with Redis."""
        call_count = 0

        @cache_with_deps()
        def get_complex_data():
            nonlocal call_count
            call_count += 1
            return {
                "users": [
                    {"id": 1, "name": "Alice", "tags": ["admin", "user"]},
                    {"id": 2, "name": "Bob", "tags": ["user"]},
                ],
                "metadata": {"total": 2, "page": 1, "filters": {"active": True, "role": None}},
            }

        # First call
        result1 = get_complex_data()
        assert call_count == 1
        assert len(result1["users"]) == 2

        # Second call should use cached result
        result2 = get_complex_data()
        assert result2 == result1
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_caching_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test async caching functionality with Redis."""
        call_count = 0

        @cache_with_deps()
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
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_dependency_invalidation_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test async dependency invalidation with Redis."""
        call_count = 0

        @cache_with_deps(dependencies={"user:123"})
        async def get_user_posts(user_id: int):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)  # Simulate async operation
            return [{"id": 1, "title": "Post 1"}]

        # First call
        result1 = await get_user_posts(123)
        assert result1 == [{"id": 1, "title": "Post 1"}]
        assert call_count == 1

        # Second call should use cache
        result2 = await get_user_posts(123)
        assert result2 == [{"id": 1, "title": "Post 1"}]
        assert call_count == 1

        # Invalidate dependency and call again
        manager = get_or_create_cache_manager()
        assert manager is not None
        await manager.ainvalidate_dependency("user:123")
        result3 = await get_user_posts(123)
        assert call_count == 2  # Should re-execute

    def test_nested_functions_with_redis(self, redis_environment, reset_cache_context, clean_redis):
        """Test nested functions with Redis."""
        outer_calls = 0
        inner_calls = 0

        @cache_with_deps(dependencies={"user:1"})
        def get_user_with_posts(user_id: int):
            nonlocal outer_calls
            outer_calls += 1
            posts = get_posts_for_user(user_id)
            return {"user": f"user_{user_id}", "posts": posts}

        @cache_with_deps(dependencies={"post:123"})
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

        # Invalidate user dependency - should invalidate outer function
        manager = get_or_create_cache_manager()
        assert manager is not None
        manager.invalidate_dependency("user:1")
        result3 = get_user_with_posts(1)
        assert outer_calls == 2  # Outer re-executed
        assert inner_calls == 1  # Inner still cached

    def test_cache_key_generation_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test cache key generation with different arguments."""
        call_count = 0

        @cache_with_deps()
        def get_data(arg1, arg2=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"arg1": arg1, "arg2": arg2, "kwargs": kwargs}

        # Different arg combinations should create different cache entries
        get_data(1)
        get_data(1, "test")
        get_data(1, arg2="test")
        get_data(1, arg2="test", extra="value")
        assert call_count == 4

        # Same combinations should use cache
        get_data(1)
        get_data(1, "test")
        get_data(1, arg2="test")
        get_data(1, arg2="test", extra="value")
        assert call_count == 4  # No additional calls

    def test_multiple_functions_same_dependencies_with_redis(
        self, redis_environment, reset_cache_context, clean_redis
    ):
        """Test multiple functions with same dependencies."""
        user_calls = 0
        post_calls = 0

        @cache_with_deps(dependencies={"data:1"})
        def get_user_data():
            nonlocal user_calls
            user_calls += 1
            return {"users": ["Alice", "Bob"]}

        @cache_with_deps(dependencies={"data:1"})
        def get_post_data():
            nonlocal post_calls
            post_calls += 1
            return {"posts": ["Post 1", "Post 2"]}

        # Execute both functions
        users = get_user_data()
        posts = get_post_data()
        assert user_calls == 1
        assert post_calls == 1

        # Execute again - both should use cache
        users2 = get_user_data()
        posts2 = get_post_data()
        assert user_calls == 1
        assert post_calls == 1

        # Invalidate shared dependency
        manager = get_or_create_cache_manager()
        assert manager is not None
        manager.invalidate_dependency("data:1")

        # Both should re-execute
        users3 = get_user_data()
        posts3 = get_post_data()
        assert user_calls == 2
        assert post_calls == 2
