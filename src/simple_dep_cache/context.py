from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import CacheManager


@dataclass
class CacheOperation:
    """Represents a cache operation with manager-scoped context."""

    manager_name: str | None
    cache_key: str | None
    dependencies: dict[str, set[str]]  # {manager_name: set_of_dependencies}
    cache_manager: "CacheManager | None"
    cache_ttl: int | None


# global stack to track nested cache operations
_operation_stack: ContextVar[list[CacheOperation] | None] = ContextVar(
    "operation_stack", default=None
)


def _get_current_operation() -> CacheOperation | None:
    """Get the current operation from the top of the stack."""
    stack = _operation_stack.get()
    if stack is None:
        return None
    return stack[-1] if stack else None


def push_operation_context(
    manager_name: str | None,
    cache_key: str | None,
    cache_manager: "CacheManager | None",
    cache_ttl: int | None = None,
    dependencies: None | set[str] = None,
) -> None:
    """Push a new operation context onto the stack."""
    stack = _operation_stack.get()
    if stack is None:
        stack = []
    else:
        stack = stack.copy()

    _deps = {}
    _deps[manager_name] = dependencies or set()
    new_operation = CacheOperation(
        manager_name=manager_name,
        cache_key=cache_key,
        dependencies=_deps,
        cache_manager=cache_manager,
        cache_ttl=cache_ttl,
    )
    stack.append(new_operation)
    _operation_stack.set(stack)


def pop_operation_context() -> dict[str, set[str]]:
    """Pop the current operation context from the stack and merge dependencies to parent."""
    stack = _operation_stack.get()
    if stack is None or not stack:
        return {}

    stack = stack.copy()
    current_op = stack.pop()

    if stack:
        parent_op = stack[-1]
        for manager_name, deps in current_op.dependencies.items():
            if manager_name not in parent_op.dependencies:
                parent_op.dependencies[manager_name] = set()
            parent_op.dependencies[manager_name].update(deps)

    _operation_stack.set(stack)
    return current_op.dependencies


def set_current_cache_key(key: None | str) -> None:
    """Set the current cache key in context."""
    current_op = _get_current_operation()
    if current_op:
        current_op.cache_key = key


def current_cache_key() -> str | None:
    """Get the current cache key from context."""
    current_op = _get_current_operation()
    return current_op.cache_key if current_op else None


def add_dependency(dependency: str, *, manager: str | None = None) -> None:
    """Add a dependency to the current cache context."""
    current_op = _get_current_operation()
    if not current_op:
        return  # No active operation, nothing to add to

    # Use the provided manager name or current operation's manager name
    target_manager = manager or current_op.manager_name
    if target_manager is None:
        return  # No manager name available

    # Add dependency to the current operation's dependencies dict
    if target_manager not in current_op.dependencies:
        current_op.dependencies[target_manager] = set()
    current_op.dependencies[target_manager].add(dependency)


def get_current_dependencies() -> set[str]:
    """Get all dependencies for the current operation's manager."""
    current_op = _get_current_operation()
    if not current_op or not current_op.manager_name:
        return set()

    return current_op.dependencies.get(current_op.manager_name, set()).copy()


def get_dependencies_for_manager(manager_name: str) -> set[str]:
    """Get all dependencies for a specific manager in the current operation."""
    current_op = _get_current_operation()
    if not current_op:
        return set()

    return current_op.dependencies.get(manager_name, set()).copy()


def get_all_dependencies() -> dict[str, set[str]]:
    """Get all dependencies for all managers in the current operation."""
    current_op = _get_current_operation()
    if not current_op:
        return {}

    return {manager: deps.copy() for manager, deps in current_op.dependencies.items()}


def clear_current_dependencies() -> None:
    """Clear all dependencies in the current context."""
    current_op = _get_current_operation()
    if current_op:
        current_op.dependencies.clear()


def get_cache_manager() -> "CacheManager | None":
    """Get the current cache manager from context."""
    current_op = _get_current_operation()
    return current_op.cache_manager if current_op else None


def set_cache_manager(cache_manager: "None | CacheManager") -> None:
    """Set the current cache manager in context."""
    current_op = _get_current_operation()
    if current_op:
        current_op.cache_manager = cache_manager


def set_cache_ttl(ttl: int | None) -> None:
    """Set the current cache TTL in context."""
    current_op = _get_current_operation()
    if current_op:
        current_op.cache_ttl = ttl


def get_cache_ttl() -> int | None:
    """Get the current cache TTL from context."""
    current_op = _get_current_operation()
    return current_op.cache_ttl if current_op else None


def reset() -> None:
    """Clear all dependencies by resetting the operation stack."""
    _operation_stack.set(None)
