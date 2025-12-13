"""Helpers."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, overload


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine


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
        return await result  # ty: ignore[invalid-return-type]

    return result


def run_background(coro: Coroutine[Any, Any, Any], name: str | None = None) -> None:
    """Run a coroutine in the background and track it."""
    try:
        asyncio.create_task(coro, name=name)  # noqa: RUF006

    except RuntimeError:
        # No running loop - use fire_and_forget
        try:
            loop = asyncio.get_running_loop()
            _task = loop.create_task(coro)  # noqa: RUF006
        except RuntimeError:
            # No running loop - use new loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()
