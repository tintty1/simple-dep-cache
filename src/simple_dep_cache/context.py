from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import AsyncCacheManager, CacheManager

_current_cache_key: ContextVar[str | None] = ContextVar("current_cache_key", default=None)
_current_dependencies: ContextVar[None | set[str]] = ContextVar(
    "current_dependencies", default=None
)
_current_cache_manager: ContextVar["CacheManager | AsyncCacheManager | None"] = ContextVar(
    "current_cache_manager", default=None
)
_current_cache_ttl: ContextVar[int | None] = ContextVar("current_cache_ttl", default=None)


def set_current_cache_key(key: None | str) -> None:
    """Set the current cache key in context."""
    _current_cache_key.set(key)


def current_cache_key() -> str | None:
    """Get the current cache key from context."""
    return _current_cache_key.get()


def add_dependency(dependency: str) -> None:
    """Add a dependency to the current cache context."""
    deps = (_current_dependencies.get() or set()).copy()
    deps.add(dependency)
    _current_dependencies.set(deps)


def get_current_dependencies() -> set[str]:
    """Get all dependencies for the current cache context."""
    return (_current_dependencies.get() or set()).copy()


def clear_current_dependencies() -> None:
    """Clear all dependencies in the current context."""
    _current_dependencies.set(set())


def set_current_dependencies(dependencies: None | set[str]) -> None:
    """Set the current dependencies."""
    _current_dependencies.set(dependencies)


def get_cache_manager() -> "CacheManager | AsyncCacheManager | None":
    """Get the current cache manager from context."""
    return _current_cache_manager.get()


def set_cache_manager(cache_manager: "None | CacheManager | AsyncCacheManager") -> None:
    """Set the current cache manager in context."""
    _current_cache_manager.set(cache_manager)


def set_cache_ttl(ttl: int | None) -> None:
    """Set the current cache TTL in context."""
    _current_cache_ttl.set(ttl)


def get_cache_ttl() -> int | None:
    """Get the current cache TTL from context."""
    return _current_cache_ttl.get()
