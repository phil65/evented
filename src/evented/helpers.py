"""Helpers."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, overload

from evented.log import get_logger


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine


logger = get_logger(__name__)


@overload
async def execute[T](
    func: Callable[..., Awaitable[T]],
    *args: Any,
    use_thread: bool = False,
    **kwargs: Any,
) -> T: ...


@overload
async def execute[T](
    func: Callable[..., T | Awaitable[T]],
    *args: Any,
    use_thread: bool = False,
    **kwargs: Any,
) -> T: ...


async def execute[T](
    func: Callable[..., T | Awaitable[T]],
    *args: Any,
    use_thread: bool = False,
    **kwargs: Any,
) -> T:
    """Execute callable, handling both sync and async cases."""
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)  # type: ignore[no-any-return]

    if use_thread:
        result = await asyncio.to_thread(func, *args, **kwargs)
    else:
        result = func(*args, **kwargs)

    if inspect.iscoroutine(result) or inspect.isawaitable(result):
        return await result

    return result


_background_tasks: set[asyncio.Task[Any]] = set()
"""Strong references to background tasks (the loop only keeps weak ones)."""


def run_background(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Run a coroutine in the background.

    On the running loop: as a task that is kept referenced until it is done. From
    another thread: on `loop` if it is running. Without any loop: to completion in a
    new loop (blocking the caller).
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        task = running.create_task(coro, name=name)
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        task.add_done_callback(_log_task_error)
    elif loop is not None and loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, loop)
    else:
        asyncio.run(coro)


def _log_task_error(task: asyncio.Task[Any]) -> None:
    if not task.cancelled() and (exc := task.exception()):
        logger.error("Background task %s failed", task.get_name(), exc_info=exc)
