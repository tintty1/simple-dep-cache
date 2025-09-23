import asyncio
import hashlib
from collections.abc import Callable
from functools import wraps
from typing import Any, NamedTuple

from .config import config
from .context import (
    clear_current_dependencies,
    current_cache_key,
    get_cache_manager,
    get_cache_ttl,
    get_current_dependencies,
    set_cache_manager,
    set_cache_ttl,
    set_current_cache_key,
    set_current_dependencies,
)
from .manager import (
    AsyncCacheManager,
    CacheManager,
    get_default_async_cache_manager,
    get_default_cache_manager,
)


class _ContextState(NamedTuple):
    """Represents the saved context state for restoration."""

    dependencies: set | None
    cache_key: str | None
    cache_manager: CacheManager | AsyncCacheManager | None
    cache_ttl: int | None


class _ContextState(NamedTuple):
    """Represents the saved context state for restoration."""

    dependencies: set | None
    cache_key: str | None
    cache_manager: CacheManager | AsyncCacheManager | None
    cache_ttl: int | None


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


def _generate_cache_key_with_prefix(
    func: Callable, args: tuple, kwargs: dict, key_prefix: str | None
) -> str:
    """Generate cache key with optional prefix."""
    cache_key = _generate_cache_key(func, args, kwargs)
    if key_prefix:
        cache_key = f"{key_prefix}:{cache_key}"
    return cache_key


def _handle_cache_hit(cached_result: Any) -> Any:
    """Handle cache hit, re-raising exceptions if needed."""
    if cached_result is not None:
        if isinstance(cached_result, Exception):
            raise cached_result
        return cached_result
    return None


def _setup_context(
    cache_key: str, cache_manager: CacheManager | AsyncCacheManager
) -> _ContextState:
    """Set up context for dependency tracking and return old state."""
    old_state = _ContextState(
        dependencies=get_current_dependencies(),
        cache_key=current_cache_key(),
        cache_manager=get_cache_manager(),
        cache_ttl=get_cache_ttl(),
    )

    clear_current_dependencies()
    set_current_cache_key(cache_key)
    set_cache_manager(cache_manager)
    set_cache_ttl(None)

    return old_state


def _restore_context(context_state: _ContextState) -> None:
    """Restore previous context values."""
    set_current_dependencies(context_state.dependencies)
    set_current_cache_key(context_state.cache_key)
    set_cache_manager(context_state.cache_manager)
    set_cache_ttl(context_state.cache_ttl)


def _collect_and_merge_dependencies(dependencies: set | None) -> set:
    """Collect dependencies from execution and merge with static dependencies."""
    collected_dependencies = get_current_dependencies()
    all_dependencies = set()

    if collected_dependencies:
        all_dependencies.update(collected_dependencies)
    if dependencies:
        all_dependencies.update(dependencies)

    return all_dependencies


def _resolve_effective_ttl(context_ttl: int | None, decorator_ttl: int | None) -> int | None:
    """Resolve effective TTL with context taking precedence."""
    return context_ttl if context_ttl is not None else decorator_ttl


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
    all_dependencies = _collect_and_merge_dependencies(dependencies)

    effective_ttl = _resolve_effective_ttl(get_cache_ttl(), ttl)
    if exception is None:
        cache_manager.set(
            cache_key,
            result,
            effective_ttl,
            all_dependencies if all_dependencies else None,
        )
    else:
        if _should_cache_exception(exception, cache_exception_types):
            cache_manager.set(
                cache_key,
                exception,
                effective_ttl,
                all_dependencies if all_dependencies else None,
            )


async def _cache_result_or_exception_async(
    cache_manager: AsyncCacheManager,
    cache_key: str,
    result: Any,
    exception: Exception | None,
    dependencies: set | None,
    ttl: int | None,
    cache_exception_types: list[type[Exception]] | None,
) -> None:
    """Cache result or exception for async operations."""
    all_dependencies = _collect_and_merge_dependencies(dependencies)
    effective_ttl = _resolve_effective_ttl(get_cache_ttl(), ttl)

    if exception is None:
        await cache_manager.set(
            cache_key,
            result,
            effective_ttl,
            all_dependencies if all_dependencies else None,
        )
    else:
        if _should_cache_exception(exception, cache_exception_types):
            await cache_manager.set(
                cache_key,
                exception,
                effective_ttl,
                all_dependencies if all_dependencies else None,
            )


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

            # Use provided cache manager or get default one
            active_cache_manager = cache_manager or get_default_cache_manager()

            cache_key = _generate_cache_key_with_prefix(func, args, kwargs, key_prefix)

            cached_result = active_cache_manager.get(cache_key)
            cache_hit_result = _handle_cache_hit(cached_result)
            if cache_hit_result is not None:
                return cache_hit_result

            # Set up context for dependency tracking
            old_context = _setup_context(cache_key, active_cache_manager)

            result = None
            exception = None
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                exception = exc
            finally:
                _cache_result_or_exception_sync(
                    active_cache_manager,
                    cache_key,
                    result,
                    exception,
                    dependencies,
                    ttl,
                    cache_exception_types,
                )

                _restore_context(old_context)

            if exception is not None:
                raise exception
            return result

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

            # Use provided cache manager or get default one
            active_cache_manager = cache_manager or get_default_async_cache_manager()

            cache_key = _generate_cache_key_with_prefix(func, args, kwargs, key_prefix)

            cached_result = await active_cache_manager.get(cache_key)
            cache_hit_result = _handle_cache_hit(cached_result)
            if cache_hit_result is not None:
                return cache_hit_result

            # Set up context for dependency tracking
            old_context = _setup_context(cache_key, active_cache_manager)

            result = None
            exception = None
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
            except Exception as exc:
                exception = exc
            finally:
                await _cache_result_or_exception_async(
                    active_cache_manager,
                    cache_key,
                    result,
                    exception,
                    dependencies,
                    ttl,
                    cache_exception_types,
                )

                _restore_context(old_context)

            if exception is not None:
                raise exception
            return result

        return wrapper

    return decorator
