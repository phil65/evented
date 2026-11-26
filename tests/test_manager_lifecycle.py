from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

from evented.event_manager import EventManager
from evented_config import TimeEventConfig, WebhookConfig


if TYPE_CHECKING:
    from evented.event_data import EventData


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _processor_tasks() -> list[asyncio.Task[object]]:
    return [
        t
        for t in asyncio.all_tasks()
        if t.get_name().startswith("event_processor_") and not t.done()
    ]


async def test_cleanup_stops_every_processing_task() -> None:
    manager = EventManager()
    await manager.add_source(WebhookConfig(name="w1", port=_free_port(), path="/hook"))
    await manager.add_source(WebhookConfig(name="w2", port=_free_port(), path="/hook"))
    assert len(_processor_tasks()) == 2  # noqa: PLR2004
    await manager.cleanup()
    assert _processor_tasks() == []


async def test_removed_time_source_emits_nothing() -> None:
    events: list[EventData] = []
    manager = EventManager(event_callbacks=[events.append])
    await manager.add_source(TimeEventConfig(name="t", schedule="* * * * * *", prompt="tick"))
    await asyncio.sleep(0.1)
    await manager.remove_source("t")
    count = len(events)
    await asyncio.sleep(1.2)
    assert len(events) == count
    assert _processor_tasks() == []


async def test_manager_can_be_entered_again_after_cleanup() -> None:
    config = TimeEventConfig(name="t", schedule="0 0 1 1 *", prompt="x")
    manager = EventManager([config])
    async with manager:
        assert "t" in manager._sources
    async with manager:
        assert "t" in manager._sources
        assert manager.enabled


async def test_callback_removing_itself_does_not_skip_the_next() -> None:
    from evented.event_data import FunctionResultEventData

    manager = EventManager()
    calls: list[str] = []

    def once(event: EventData) -> None:
        calls.append("once")
        manager.remove_callback(once)

    manager.add_callback(once)
    manager.add_callback(lambda event: calls.append("other"))
    await manager.emit_event(FunctionResultEventData(source="s", result=1))
    assert calls == ["once", "other"]


async def test_generated_names_do_not_collide_after_removal() -> None:
    manager = EventManager()
    first = await manager.add_timed_event("0 0 1 1 *", "a")
    await manager.add_timed_event("0 0 1 1 *", "b")
    await manager.remove_source(first.config.name)
    await manager.add_timed_event("0 0 1 1 *", "c")  # raised "already exists"
    assert len(manager._sources) == 2  # noqa: PLR2004
    await manager.cleanup()


async def test_tracked_sync_function_keeps_its_emit_task() -> None:
    import gc

    from evented import helpers

    manager = EventManager()
    events: list[EventData] = []

    async def slow(event: EventData) -> None:
        await asyncio.sleep(0.05)
        events.append(event)

    manager.add_callback(slow)

    @manager.track("sync")
    def work() -> int:
        return 1

    work()
    assert helpers._background_tasks
    gc.collect()
    await asyncio.sleep(0.1)
    assert len(events) == 1
