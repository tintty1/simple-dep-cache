"""Tests for async event-callback dispatch on the cache manager."""

import pytest

from simple_dep_cache.config import ConfigBase
from simple_dep_cache.events import CacheEvent, CacheEventType
from simple_dep_cache.fakes import FakeAsyncCacheBackend, FakeCacheBackend
from simple_dep_cache.manager import CacheManager


def _sync_manager():
    config = ConfigBase(prefix="t")
    return CacheManager(config, name="t", backend=FakeCacheBackend(config))


def _async_manager():
    config = ConfigBase(prefix="t")
    return CacheManager(config, name="t", async_backend=FakeAsyncCacheBackend(config))


class TestSyncDispatch:
    def test_sync_callback_runs_on_sync_op(self):
        seen = []
        m = _sync_manager()
        m.on_event(CacheEventType.INVALIDATE, lambda e: seen.append(e.key))
        m.invalidate_dependency("dep:1")
        assert seen == ["dep:1"]

    def test_async_callback_on_sync_op_raises(self):
        m = _sync_manager()

        async def acb(event):  # noqa: RUF029
            pass

        m.on_event(CacheEventType.INVALIDATE, acb)
        with pytest.raises(RuntimeError, match="async callback"):
            m.invalidate_dependency("dep:1")

    def test_emit_skips_async_callbacks(self):
        # EventEmitter.emit itself must never try to call an async callback.
        sync_seen, async_seen = [], []
        m = _sync_manager()

        async def acb(event):
            async_seen.append(event.key)

        m.on_event(CacheEventType.SET, lambda e: sync_seen.append(e.key))
        m.on_event(CacheEventType.SET, acb)
        # direct emit -> only sync callback runs, no coroutine leaked
        m.events.emit(CacheEvent(event_type=CacheEventType.SET, key="k", timestamp=0.0))
        assert sync_seen == ["k"]
        assert async_seen == []


class TestAsyncDispatch:
    @pytest.mark.asyncio
    async def test_async_callback_runs_on_async_op(self):
        seen = []
        m = _async_manager()

        async def acb(event):
            seen.append(event.key)

        m.on_event(CacheEventType.INVALIDATE, acb)
        await m.ainvalidate_dependency("dep:1")
        assert seen == ["dep:1"]

    @pytest.mark.asyncio
    async def test_sync_callback_also_runs_on_async_op(self):
        seen = []
        m = _async_manager()
        m.on_event(CacheEventType.INVALIDATE, lambda e: seen.append(e.key))
        await m.ainvalidate_dependency("dep:1")
        assert seen == ["dep:1"]

    @pytest.mark.asyncio
    async def test_both_sync_and_async_run_on_async_op(self):
        sync_seen, async_seen = [], []
        m = _async_manager()

        async def acb(event):
            async_seen.append(event.key)

        m.on_event(CacheEventType.INVALIDATE, lambda e: sync_seen.append(e.key))
        m.on_event(CacheEventType.INVALIDATE, acb)
        await m.ainvalidate_dependency("dep:1")
        assert sync_seen == ["dep:1"]
        assert async_seen == ["dep:1"]


class TestHasAsyncCallbacks:
    def test_detection(self):
        m = _sync_manager()
        assert m.events.has_async_callbacks(CacheEventType.SET) is False
        m.on_event(CacheEventType.SET, lambda e: None)
        assert m.events.has_async_callbacks(CacheEventType.SET) is False

        async def acb(event):
            pass

        m.on_event(CacheEventType.SET, acb)
        assert m.events.has_async_callbacks(CacheEventType.SET) is True

    def test_global_async_callback_detected(self):
        m = _sync_manager()

        async def acb(event):
            pass

        m.on_all_events(acb)
        assert m.events.has_async_callbacks(CacheEventType.HIT) is True
