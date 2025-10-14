"""Time-based event source for scheduling agent actions."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import TimeEventData


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    from evented.configs import TimeEventConfig
    from evented.event_data import EventData


class TimeEventSource(EventSource):
    """Generates events based on cron schedule."""

    def __init__(self, config: TimeEventConfig):
        import zoneinfo

        self.config = config
        self._stop_event = asyncio.Event()
        self._tz = zoneinfo.ZoneInfo(config.timezone) if config.timezone else None

    async def __aenter__(self) -> Self:
        """Validate cron expression."""
        from croniter import croniter

        try:
            now = datetime.now(self._tz)
            croniter(self.config.schedule, now)
        except Exception as e:
            msg = f"Invalid cron expression: {e}"
            raise ValueError(msg) from e
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop event generation."""
        self._stop_event.set()

    async def events(self) -> AsyncGenerator[EventData]:
        """Generate events based on schedule."""
        from croniter import croniter

        while not self._stop_event.is_set():
            now = datetime.now(self._tz)
            cron = croniter(self.config.schedule, now)
            next_run = cron.get_next(datetime)
            delay = (next_run - now).total_seconds()  # Sleep until next run
            if delay > 0:
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break

            # Skip if we missed the schedule and skip_missed is True
            if self.config.skip_missed:
                current = datetime.now(self._tz)
                if (current - next_run).total_seconds() > 1:
                    continue

            yield TimeEventData(
                source=self.config.name,
                schedule=self.config.schedule,
                prompt=self.config.prompt,
            )
