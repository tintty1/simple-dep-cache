import asyncio
import hashlib
import logging
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


def _validate_callback_compatibility(
    callback: Callable | None, is_async_function: bool
) -> Callable | None:
    """
    Validate callback compatibility with function type.

    Returns None if callback is incompatible, otherwise returns the callback.
    """
    if callback is None:
        return None

    callback_is_async = asyncio.iscoroutinefunction(callback)

    if is_async_function and not callback_is_async:
        # Sync callback with async function is fine
        return callback
    elif not is_async_function and callback_is_async:
        # Async callback with sync function - warn and ignore
        import warnings

        warnings.warn(
            "Async callback provided to sync function. Callback will be ignored. "
            "Use a sync callback with sync functions.",
            UserWarning,
            stacklevel=3,
        )
        return None

    return callback


def _handle_callback_error(error: Exception, cache_manager: CacheManager, context: str) -> None:
    """
    Handle callback errors based on configuration settings.

    Args:
        error: The exception that occurred in the callback
        cache_manager: The cache manager to get config from
        context: Context description for logging (e.g., "cache hit", "cache miss")
    """
    logger = logging.getLogger(__name__)

    try:
        config = cache_manager.config
        if hasattr(config, "callback_error_silent") and not config.callback_error_silent:
            logger.error("Callback error during %s: %s", context, error, exc_info=True)
        # If callback_error_silent is True (default), silently ignore the error
    except Exception:
        # If we can't access config or there's an issue with logging, fall back to silent ignore
        pass


def _handle_backend_error(operation: str, func_name: str, error: Exception, silent: bool) -> None:
    """Handle backend errors by logging or re-raising based on silent flag."""
    if not silent:
        raise
    logger = logging.getLogger(__name__)
    logger.warning("Backend error during %s for %s: %s", operation, func_name, error, exc_info=True)


def _safe_backend_op(op: Callable, silent: bool, func_name: str, operation: str) -> Any:
    """Execute a backend operation with optional error silencing."""
    try:
        return op()
    except Exception as e:
        _handle_backend_error(operation, func_name, e, silent)
        return None


async def _safe_backend_op_async(op: Callable, silent: bool, func_name: str, operation: str) -> Any:
    """Execute an async backend operation with optional error silencing."""
    try:
        return await op()
    except Exception as e:
        _handle_backend_error(operation, func_name, e, silent)
        return None


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
    callback: Callable | None = None,
    silent_backend_errors: bool = False,
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
        callback: Callback function invoked on cache hit or miss.
            Called with keyword arguments: func, cache_manager, args, kwargs, is_hit, cached_result
            is_hit=True for cache hits, False for cache misses (optional)
        silent_backend_errors: If True, silently log backend errors (e.g., Redis connection errors)
            instead of raising them. The decorated function will execute normally when backend
            errors occur. Defaults to False (optional)
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                active_cache_manager = get_or_create_cache_manager(
                    name=name, create_async_backend=True
                )
                # If cache manager is None (caching disabled), just execute the function
                if active_cache_manager is None:
                    return await func(*args, **kwargs)

                valid_callback = _validate_callback_compatibility(callback, True)

                cache_key = _generate_cache_key(func, args, kwargs)

                # Try to get from cache with optional error silencing
                cached_result = await _safe_backend_op_async(
                    lambda: active_cache_manager.aget(cache_key),
                    silent_backend_errors,
                    func.__qualname__,
                    "cache get",
                )

                if cached_result is not None:
                    cache_hit_result = _handle_cache_hit(cached_result)
                    if cache_hit_result is not None:
                        # Invoke callback for cache hit
                        if valid_callback:
                            try:
                                if asyncio.iscoroutinefunction(valid_callback):
                                    await valid_callback(
                                        func=func,
                                        cache_manager=active_cache_manager,
                                        args=args,
                                        kwargs=kwargs,
                                        is_hit=True,
                                        cached_result=cache_hit_result,
                                    )
                                else:
                                    valid_callback(
                                        func=func,
                                        cache_manager=active_cache_manager,
                                        args=args,
                                        kwargs=kwargs,
                                        is_hit=True,
                                        cached_result=cache_hit_result,
                                    )
                            except Exception as e:
                                _handle_callback_error(e, active_cache_manager, "cache hit")
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

                    # Try to set cache with optional error silencing
                    await _safe_backend_op_async(
                        lambda: _cache_result_or_exception_async(
                            active_cache_manager,
                            cache_key,
                            result,
                            exception,
                            current_deps,
                            effective_ttl,
                            cache_exception_types,
                        ),
                        silent_backend_errors,
                        func.__qualname__,
                        "cache set",
                    )

                    # Invoke callback for cache miss
                    if valid_callback:
                        try:
                            if asyncio.iscoroutinefunction(valid_callback):
                                await valid_callback(
                                    func=func,
                                    cache_manager=active_cache_manager,
                                    args=args,
                                    kwargs=kwargs,
                                    is_hit=False,
                                    cached_result=None,
                                )
                            else:
                                valid_callback(
                                    func=func,
                                    cache_manager=active_cache_manager,
                                    args=args,
                                    kwargs=kwargs,
                                    is_hit=False,
                                    cached_result=None,
                                )
                        except Exception as e:
                            _handle_callback_error(e, active_cache_manager, "cache miss")

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

                valid_callback = _validate_callback_compatibility(callback, False)

                cache_key = _generate_cache_key(func, args, kwargs)

                # Try to get from cache with optional error silencing
                cached_result = _safe_backend_op(
                    lambda: active_cache_manager.get(cache_key),
                    silent_backend_errors,
                    func.__qualname__,
                    "cache get",
                )

                if cached_result is not None:
                    cache_hit_result = _handle_cache_hit(cached_result)
                    if cache_hit_result is not None:
                        # Invoke callback for cache hit
                        if valid_callback:
                            try:
                                valid_callback(
                                    func=func,
                                    cache_manager=active_cache_manager,
                                    args=args,
                                    kwargs=kwargs,
                                    is_hit=True,
                                    cached_result=cache_hit_result,
                                )
                            except Exception as e:
                                _handle_callback_error(e, active_cache_manager, "cache hit")
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

                    # Try to set cache with optional error silencing
                    _safe_backend_op(
                        lambda: _cache_result_or_exception_sync(
                            active_cache_manager,
                            cache_key,
                            result,
                            exception,
                            current_deps,
                            effective_ttl,
                            cache_exception_types,
                        ),
                        silent_backend_errors,
                        func.__qualname__,
                        "cache set",
                    )

                    # Invoke callback for cache miss
                    if valid_callback:
                        try:
                            valid_callback(
                                func=func,
                                cache_manager=active_cache_manager,
                                args=args,
                                kwargs=kwargs,
                                is_hit=False,
                                cached_result=None,
                            )
                        except Exception as e:
                            _handle_callback_error(e, active_cache_manager, "cache miss")

                    _restore_context()

                if exception is not None:
                    raise exception
                return result

            return sync_wrapper

    return decorator
