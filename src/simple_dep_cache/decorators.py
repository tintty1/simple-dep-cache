import asyncio
import hashlib
from collections.abc import Callable
from functools import wraps
from typing import Any

from .context import (
    get_cache_ttl,
    get_current_dependencies,
    pop_operation_context,
    push_operation_context,
)
from .manager import CacheManager, get_or_create_cache_manager


def _get_cache_key_for_arg(arg) -> str:
    """Get cache key representation for a single argument."""
    # Check for custom cache key method
    if hasattr(arg, "__cache_key__"):
        cache_key = arg.__cache_key__
        if callable(cache_key):
            return str(cache_key())
        return str(cache_key)

    # Check for custom cache key attribute
    if hasattr(arg, "_cache_key"):
        return str(arg._cache_key)

    # For common types, use more stable representations
    if hasattr(arg, "pk"):  # Django model-like objects
        return f"{arg.__class__.__name__}::{arg.pk}"
    elif hasattr(arg, "id"):  # Objects with id attribute
        return f"{arg.__class__.__name__}::{arg.id}"

    # Fall back to string representation
    return str(arg)


def _generate_cache_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """Generate a cache key based on function name and arguments."""
    func_name = f"{func.__module__}.{func.__qualname__}"

    # Create a stable string representation of arguments
    arg_parts = []

    # Add positional args
    for arg in args:
        arg_parts.append(_get_cache_key_for_arg(arg))

    # Add keyword args (sorted for consistency)
    for key in sorted(kwargs.keys()):
        arg_parts.append(f"{key}={_get_cache_key_for_arg(kwargs[key])}")

    args_str = ",".join(arg_parts)
    full_key = f"{func_name}({args_str})"

    # Hash for consistent length and avoid special characters
    return hashlib.md5(full_key.encode()).hexdigest()


def _handle_cache_hit(cached_result: Any) -> Any:
    """Handle cache hit, re-raising exceptions if needed."""
    if cached_result is not None:
        if isinstance(cached_result, Exception):
            raise cached_result
        return cached_result
    return None


def _setup_context(
    cache_key: str,
    cache_manager: CacheManager,
    cache_ttl: int | None = None,
    dependencies: set[str] | None = None,
):
    """Set up context for dependency tracking and return old state."""
    push_operation_context(
        manager_name=cache_manager.name,
        cache_key=cache_key,
        cache_manager=cache_manager,
        cache_ttl=cache_ttl,
        dependencies=dependencies,
    )


def _restore_context() -> None:
    pop_operation_context()


def _should_cache_exception(
    exc: Exception, cache_exception_types: list[type[Exception]] | None
) -> bool:
    """Check if exception should be cached based on type."""
    return bool(cache_exception_types) and any(
        isinstance(exc, exc_type) for exc_type in cache_exception_types
    )


def _cache_result_or_exception_sync(
    cache_manager: CacheManager,
    cache_key: str,
    result: Any,
    exception: Exception | None,
    dependencies: set | None,
    ttl: int | None,
    cache_exception_types: list[type[Exception]] | None,
) -> None:
    """Cache result or exception for sync operations."""

    if exception is None:
        cache_manager.set(
            cache_key,
            result,
            ttl,
            dependencies,
        )
    else:
        if _should_cache_exception(exception, cache_exception_types):
            cache_manager.set(
                cache_key,
                exception,
                ttl,
                dependencies,
            )


async def _cache_result_or_exception_async(
    cache_manager: CacheManager,
    cache_key: str,
    result: Any,
    exception: Exception | None,
    dependencies: set | None,
    ttl: int | None,
    cache_exception_types: list[type[Exception]] | None,
) -> None:
    """Cache result or exception for async operations."""
    if exception is None:
        await cache_manager.aset(
            cache_key,
            result,
            ttl,
            dependencies,
        )
    else:
        if _should_cache_exception(exception, cache_exception_types):
            await cache_manager.aset(
                cache_key,
                exception,
                ttl,
                dependencies,
            )


def cache_with_deps(
    *,
    name: str | None = None,
    ttl: int | None = None,
    dependencies: set | None = None,
    cache_exception_types: list[type[Exception]] | None = None,
) -> Callable:
    """
    Decorator for caching function results with dependency tracking.

    Automatically handles both synchronous and asynchronous functions.

    Args:
        name: The cache manager name to use (optional)
        ttl: Time to live in seconds (optional)
        dependencies: Additional dependencies to track (optional)
        cache_exception_types: List of exception types to cache.
            If None or empty, exceptions are not cached (optional)
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                active_cache_manager = get_or_create_cache_manager(name=name)
                # If cache manager is None (caching disabled), just execute the function
                if active_cache_manager is None:
                    return await func(*args, **kwargs)

                cache_key = _generate_cache_key(func, args, kwargs)

                cached_result = await active_cache_manager.aget(cache_key)
                if cached_result is not None:
                    cache_hit_result = _handle_cache_hit(cached_result)
                    if cache_hit_result is not None:
                        return cache_hit_result

                _setup_context(cache_key, active_cache_manager, ttl, dependencies)

                result = None
                exception = None
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    exception = exc
                finally:
                    current_deps = get_current_dependencies()
                    effective_ttl = get_cache_ttl()
                    await _cache_result_or_exception_async(
                        active_cache_manager,
                        cache_key,
                        result,
                        exception,
                        current_deps,
                        effective_ttl,
                        cache_exception_types,
                    )

                    _restore_context()

                if exception is not None:
                    raise exception
                return result

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                active_cache_manager = get_or_create_cache_manager(name=name)
                # If cache manager is None (caching disabled), just execute the function
                if active_cache_manager is None:
                    return func(*args, **kwargs)

                cache_key = _generate_cache_key(func, args, kwargs)

                cached_result = active_cache_manager.get(cache_key)
                if cached_result is not None:
                    cache_hit_result = _handle_cache_hit(cached_result)
                    if cache_hit_result is not None:
                        return cache_hit_result

                _setup_context(cache_key, active_cache_manager, ttl, dependencies)

                result = None
                exception = None
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    exception = exc
                finally:
                    current_deps = get_current_dependencies()
                    effective_ttl = get_cache_ttl()
                    _cache_result_or_exception_sync(
                        active_cache_manager,
                        cache_key,
                        result,
                        exception,
                        current_deps,
                        effective_ttl,
                        cache_exception_types,
                    )

                    _restore_context()

                if exception is not None:
                    raise exception
                return result

            return sync_wrapper

    return decorator
