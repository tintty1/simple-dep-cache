import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config import ConfigBase

logger = logging.getLogger(__name__)


class CacheEventType(Enum):
    """Types of cache events."""

    HIT = "hit"
    MISS = "miss"
    SET = "set"
    DELETE = "delete"
    INVALIDATE = "invalidate"
    CLEAR = "clear"


@dataclass
class CacheEvent:
    """Cache event data."""

    event_type: CacheEventType
    key: str
    timestamp: float
    value: Any = None
    dependencies: set[str] | None = None
    ttl: int | None = None
    count: int | None = None  # For bulk operations

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class EventEmitter:
    """Simple event emitter for cache events."""

    def __init__(self, config: ConfigBase):
        self.config = config
        self._callbacks: dict[CacheEventType, list[Callable]] = {
            event_type: [] for event_type in CacheEventType
        }
        self._global_callbacks: list[Callable] = []

    def on(self, event_type: CacheEventType, callback: Callable[[CacheEvent], None]) -> None:
        """Register a callback for a specific event type."""
        self._callbacks[event_type].append(callback)

    def on_all(self, callback: Callable[[CacheEvent], None]) -> None:
        """Register a callback for all event types."""
        self._global_callbacks.append(callback)

    def off(self, event_type: CacheEventType, callback: Callable[[CacheEvent], None]) -> bool:
        """Unregister a callback for a specific event type."""
        if callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)
            return True
        return False

    def off_all(self, callback: Callable[[CacheEvent], None]) -> bool:
        """Unregister a callback from all events."""
        if callback in self._global_callbacks:
            self._global_callbacks.remove(callback)
            return True
        return False

    def emit(self, event: CacheEvent) -> None:
        """Emit an event to all registered callbacks."""
        # Call specific event callbacks
        for callback in self._callbacks[event.event_type]:
            try:
                callback(event)
            except Exception as e:
                if not self.config.callback_error_silent:
                    logger.exception("Error in cache event callback: %s", e)

        # Call global callbacks
        for callback in self._global_callbacks:
            try:
                callback(event)
            except Exception as e:
                if not self.config.callback_error_silent:
                    logger.exception("Error in cache event callback: %s", e)

    def clear_all(self) -> None:
        """Clear all callbacks."""
        for event_type in CacheEventType:
            self._callbacks[event_type].clear()
        self._global_callbacks.clear()


# Pre-built callback functions for common use cases
class StatsCollector:
    """Collect cache statistics."""

    def __init__(self):
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "invalidations": 0,
            "clears": 0,
        }
        self.start_time = time.time()

    def __call__(self, event: CacheEvent) -> None:
        """Callback to collect stats."""
        if event.event_type == CacheEventType.HIT:
            self.stats["hits"] += 1
        elif event.event_type == CacheEventType.MISS:
            self.stats["misses"] += 1
        elif event.event_type == CacheEventType.SET:
            self.stats["sets"] += 1
        elif event.event_type == CacheEventType.DELETE:
            self.stats["deletes"] += event.count or 1
        elif event.event_type == CacheEventType.INVALIDATE:
            self.stats["invalidations"] += event.count or 1
        elif event.event_type == CacheEventType.CLEAR:
            self.stats["clears"] += event.count or 1

    def get_hit_ratio(self) -> float:
        """Get cache hit ratio."""
        total = self.stats["hits"] + self.stats["misses"]
        return self.stats["hits"] / total if total > 0 else 0.0

    def get_stats(self) -> dict:
        """Get all stats with additional computed metrics."""
        runtime = time.time() - self.start_time
        return {
            **self.stats,
            "hit_ratio": self.get_hit_ratio(),
            "total_operations": sum(self.stats.values()),
            "runtime_seconds": runtime,
            "ops_per_second": sum(self.stats.values()) / runtime if runtime > 0 else 0,
        }

    def reset(self) -> None:
        """Reset all statistics."""
        for key in self.stats:
            self.stats[key] = 0
        self.start_time = time.time()


def create_logger_callback(name: str = "cache") -> Callable[[CacheEvent], None]:
    """Create a callback that logs cache events."""

    def logger_callback(event: CacheEvent) -> None:
        if event.event_type in (CacheEventType.HIT, CacheEventType.MISS):
            print(f"[{name}] {event.event_type.value.upper()}: {event.key}")
        elif event.event_type == CacheEventType.SET:
            deps_str = f" deps={list(event.dependencies)}" if event.dependencies else ""
            ttl_str = f" ttl={event.ttl}s" if event.ttl else ""
            print(f"[{name}] SET: {event.key}{deps_str}{ttl_str}")
        elif event.event_type == CacheEventType.INVALIDATE:
            print(f"[{name}] INVALIDATE: {event.key} (cleared {event.count} entries)")
        elif event.event_type in (CacheEventType.DELETE, CacheEventType.CLEAR):
            count_str = f" ({event.count} entries)" if event.count else ""
            print(f"[{name}] {event.event_type.value.upper()}: {event.key}{count_str}")

    return logger_callback
