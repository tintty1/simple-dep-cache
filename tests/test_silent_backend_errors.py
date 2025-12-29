"""Tests for the silent_backend_errors parameter in cache_with_deps decorator."""

from unittest.mock import Mock

import pytest

from simple_dep_cache.decorators import cache_with_deps
from simple_dep_cache.fakes import FakeAsyncCacheBackend, FakeCacheBackend, FakeConfig
from simple_dep_cache.manager import get_or_create_cache_manager


class TestSilentBackendErrors:
    """Test cases for silent_backend_errors parameter."""

    def test_silent_backend_errors_on_get(self):
        """Test that backend errors during get are silently logged."""
        # Create a fake backend that will raise an error on get
        config = FakeConfig(prefix="test_get_error")
        backend = FakeCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_get_error", config=config, backend=backend
        )
        assert cache_manager is not None

        # Mock the backend's get method to raise an error
        backend.get = Mock(side_effect=ConnectionError("Redis connection failed"))

        call_count = 0

        @cache_with_deps(name=cache_manager.name, silent_backend_errors=True)
        def my_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Should execute function normally despite backend error
        result = my_function(5)
        assert result == 10
        assert call_count == 1

    def test_silent_backend_errors_on_set(self):
        """Test that backend errors during set are silently logged."""
        # Create a fake backend that will raise an error on set
        config = FakeConfig(prefix="test_set_error")
        backend = FakeCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_set_error", config=config, backend=backend
        )
        assert cache_manager is not None

        # Mock the backend's set method to raise an error
        backend.set = Mock(side_effect=ConnectionError("Redis connection failed"))

        call_count = 0

        @cache_with_deps(name=cache_manager.name, silent_backend_errors=True)
        def my_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Should execute function normally despite backend error
        result = my_function(5)
        assert result == 10
        assert call_count == 1

    def test_silent_backend_errors_disabled_by_default(self):
        """Test that backend errors are raised by default (silent_backend_errors=False)."""
        # Create a fake backend that will raise an error on get
        config = FakeConfig(prefix="test_error_default")
        backend = FakeCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_error_default", config=config, backend=backend
        )
        assert cache_manager is not None

        # Mock the backend's get method to raise an error
        backend.get = Mock(side_effect=ConnectionError("Redis connection failed"))

        @cache_with_deps(name=cache_manager.name)
        def my_function(x):
            return x * 2

        # Should raise the backend error
        with pytest.raises(ConnectionError, match="Redis connection failed"):
            my_function(5)

    @pytest.mark.asyncio
    async def test_silent_backend_errors_with_async(self):
        """Test that silent_backend_errors works with async functions."""
        # Create a fake async backend that will raise an error on get
        config = FakeConfig(prefix="test_async_error")
        async_backend = FakeAsyncCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_async_error",
            config=config,
            async_backend=async_backend,
            create_async_backend=True,
        )
        assert cache_manager is not None

        # Mock the backend's get method to raise an error
        async def mock_get(key):
            raise ConnectionError("Redis connection failed")

        async_backend.get = mock_get

        call_count = 0

        @cache_with_deps(name=cache_manager.name, silent_backend_errors=True)
        async def my_async_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Should execute function normally despite backend error
        result = await my_async_function(5)
        assert result == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_silent_backend_errors_async_disabled_by_default(self):
        """Test that backend errors are raised by default in async functions."""
        # Create a fake async backend that will raise an error on get
        config = FakeConfig(prefix="test_async_error_default")
        async_backend = FakeAsyncCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_async_error_default",
            config=config,
            async_backend=async_backend,
            create_async_backend=True,
        )
        assert cache_manager is not None

        # Mock the backend's get method to raise an error
        async def mock_get(key):
            raise ConnectionError("Redis connection failed")

        async_backend.get = mock_get

        @cache_with_deps(name=cache_manager.name)
        async def my_async_function(x):
            return x * 2

        # Should raise the backend error
        with pytest.raises(ConnectionError, match="Redis connection failed"):
            await my_async_function(5)

    def test_silent_backend_errors_multiple_calls(self):
        """Test that function executes correctly with persistent backend errors."""
        config = FakeConfig(prefix="test_multiple_calls")
        backend = FakeCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_multiple_calls", config=config, backend=backend
        )
        assert cache_manager is not None

        # Mock the backend to always fail
        backend.get = Mock(side_effect=ConnectionError("Redis connection failed"))
        backend.set = Mock(side_effect=ConnectionError("Redis connection failed"))

        call_count = 0

        @cache_with_deps(name=cache_manager.name, silent_backend_errors=True)
        def my_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Call multiple times - should work each time
        result1 = my_function(5)
        result2 = my_function(10)
        result3 = my_function(5)  # Same arg as first call

        assert result1 == 10
        assert result2 == 20
        assert result3 == 10
        assert call_count == 3  # Function called every time (no caching due to backend errors)

    def test_silent_backend_errors_partial_failure(self):
        """Test behavior when only get fails but set works."""
        config = FakeConfig(prefix="test_partial_failure")
        backend = FakeCacheBackend(config)
        cache_manager = get_or_create_cache_manager(
            name="test_partial_failure", config=config, backend=backend
        )
        assert cache_manager is not None

        # Mock the backend's get to fail, but set works normally
        backend.get = Mock(side_effect=ConnectionError("Redis connection failed"))
        call_count = 0

        @cache_with_deps(name=cache_manager.name, silent_backend_errors=True)
        def my_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call: get fails, function executes, set succeeds
        result1 = my_function(5)
        assert result1 == 10
        assert call_count == 1

        # Second call: get still fails, function executes again
        result2 = my_function(5)
        assert result2 == 10
        assert call_count == 2  # Function called again due to get failure
