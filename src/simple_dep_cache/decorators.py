import asyncio
import hashlib
from collections.abc import Callable
from functools import wraps

from .config import config
from .context import (
    clear_current_dependencies,
    get_current_dependencies,
    set_cache_manager,
    set_current_cache_key,
    set_current_dependencies,
)
from .manager import AsyncCacheManager, CacheManager


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


def cache_with_deps(
    *,
    cache_manager: CacheManager | None = None,
    ttl: int | None = None,
    key_prefix: str | None = None,
    dependencies: set | None = None,
    cache_exception_types: list[type[Exception]] | None = None,
) -> Callable:
    """
    Decorator for caching function results with dependency tracking.

    Args:
        cache_manager: The cache manager instance to use (optional)
        ttl: Time to live in seconds (optional)
        key_prefix: Custom prefix for cache keys (optional)
        dependencies: Additional dependencies to track (optional)
        cache_exception_types: List of exception types to cache.
            If None or empty, exceptions are not cached (optional)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # If caching is disabled, just execute the function
            if not config.cache_enabled:
                return func(*args, **kwargs)

            # Use provided cache manager or create default one
            active_cache_manager = cache_manager or CacheManager()

            # Generate cache key
            cache_key = _generate_cache_key(func, args, kwargs)
            if key_prefix:
                cache_key = f"{key_prefix}:{cache_key}"

            # Check cache first
            cached_result = active_cache_manager.get(cache_key)
            if cached_result is not None:
                # If cached result is an exception, re-raise it
                if isinstance(cached_result, Exception):
                    raise cached_result
                return cached_result

            # Set up context for dependency tracking
            old_dependencies = get_current_dependencies()
            clear_current_dependencies()
            set_current_cache_key(cache_key)
            set_cache_manager(active_cache_manager)

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Get dependencies collected during execution
                collected_dependencies = get_current_dependencies()

                # Combine collected dependencies with additional dependencies
                all_dependencies = set()
                if collected_dependencies:
                    all_dependencies.update(collected_dependencies)
                if dependencies:
                    all_dependencies.update(dependencies)

                # Cache the result with dependencies
                active_cache_manager.set(
                    cache_key,
                    result,
                    ttl,
                    all_dependencies if all_dependencies else None,
                )

                return result
            except Exception as exc:
                # Check if we should cache this exception type
                should_cache_exception = cache_exception_types and any(
                    isinstance(exc, exc_type) for exc_type in cache_exception_types
                )

                if should_cache_exception:
                    # Get dependencies collected during execution
                    collected_dependencies = get_current_dependencies()

                    # Combine collected dependencies with additional dependencies
                    all_dependencies = set()
                    if collected_dependencies:
                        all_dependencies.update(collected_dependencies)
                    if dependencies:
                        all_dependencies.update(dependencies)

                    # Cache the exception with dependencies
                    active_cache_manager.set(
                        cache_key,
                        exc,
                        ttl,
                        all_dependencies if all_dependencies else None,
                    )

                # Re-raise the exception whether we cached it or not
                raise
            finally:
                # Restore previous context
                set_current_dependencies(old_dependencies)
                set_current_cache_key(None)

        return wrapper

    return decorator


def async_cache_with_deps(
    *,
    cache_manager: AsyncCacheManager | None = None,
    ttl: int | None = None,
    key_prefix: str | None = None,
    dependencies: set | None = None,
    cache_exception_types: list[type[Exception]] | None = None,
) -> Callable:
    """
    Async decorator for caching function results with dependency tracking.

    Args:
        cache_manager: The async cache manager instance to use (optional)
        ttl: Time to live in seconds (optional)
        key_prefix: Custom prefix for cache keys (optional)
        dependencies: Additional dependencies to track (optional)
        cache_exception_types: List of exception types to cache.
            If None or empty, exceptions are not cached (optional)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # If caching is disabled, just execute the function
            if not config.cache_enabled:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)

            # Use provided cache manager or create default one
            active_cache_manager = cache_manager or AsyncCacheManager()

            # Generate cache key
            cache_key = _generate_cache_key(func, args, kwargs)
            if key_prefix:
                cache_key = f"{key_prefix}:{cache_key}"

            # Check cache first
            cached_result = await active_cache_manager.get(cache_key)
            if cached_result is not None:
                # If cached result is an exception, re-raise it
                if isinstance(cached_result, Exception):
                    raise cached_result
                return cached_result

            # Set up context for dependency tracking
            old_dependencies = get_current_dependencies()
            clear_current_dependencies()
            set_current_cache_key(cache_key)
            set_cache_manager(active_cache_manager)

            try:
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Get dependencies collected during execution
                collected_dependencies = get_current_dependencies()

                # Combine collected dependencies with additional dependencies
                all_dependencies = set()
                if collected_dependencies:
                    all_dependencies.update(collected_dependencies)
                if dependencies:
                    all_dependencies.update(dependencies)

                # Cache the result with dependencies
                await active_cache_manager.set(
                    cache_key,
                    result,
                    ttl,
                    all_dependencies if all_dependencies else None,
                )

                return result
            except Exception as exc:
                # Check if we should cache this exception type
                should_cache_exception = cache_exception_types and any(
                    isinstance(exc, exc_type) for exc_type in cache_exception_types
                )

                if should_cache_exception:
                    # Get dependencies collected during execution
                    collected_dependencies = get_current_dependencies()

                    # Combine collected dependencies with additional dependencies
                    all_dependencies = set()
                    if collected_dependencies:
                        all_dependencies.update(collected_dependencies)
                    if dependencies:
                        all_dependencies.update(dependencies)

                    # Cache the exception with dependencies
                    await active_cache_manager.set(
                        cache_key,
                        exc,
                        ttl,
                        all_dependencies if all_dependencies else None,
                    )

                # Re-raise the exception whether we cached it or not
                raise
            finally:
                # Restore previous context
                set_current_dependencies(old_dependencies)
                set_current_cache_key(None)

        return wrapper

    return decorator
