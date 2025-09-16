from contextvars import ContextVar

_current_cache_key: ContextVar[str | None] = ContextVar("current_cache_key", default=None)
_current_dependencies: ContextVar[None | set[str]] = ContextVar(
    "current_dependencies", default=None
)


def set_current_cache_key(key: str) -> None:
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


def set_current_dependencies(dependencies: set[str]) -> None:
    """Set the current dependencies."""
    _current_dependencies.set(dependencies)
