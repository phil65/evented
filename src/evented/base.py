"""Event sources for Evented."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

from evented.configs import EmailConfig, FileWatchConfig, TimeEventConfig, WebhookConfig
from evented.log import get_logger


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    from evented.configs import EventConfig
    from evented.event_data import EventData


logger = get_logger(__name__)


class EventSource(ABC):
    """Base class for event sources."""

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Initialize connection to event source."""

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close connection to event source."""

    @abstractmethod
    def events(self) -> AsyncGenerator[EventData]:
        """Get event iterator.

        Returns:
            AsyncIterator yielding events from this source

        Note: This is a coroutine that returns an AsyncIterator
        """
        raise NotImplementedError

    @classmethod
    def from_config(cls, config: EventConfig) -> EventSource:
        """Create event source from configuration.

        Args:
            config: Event source configuration

        Returns:
            Configured event source instance

        Raises:
            ValueError: If source type is unknown or disabled
        """
        if not config.enabled:
            msg = f"Source {config.name} is disabled"
            raise ValueError(msg)
        logger.info("Creating event source: %s (%s)", config.name, config.type)
        match config:
            case FileWatchConfig():
                from evented.file_watcher import FileSystemEventSource

                return FileSystemEventSource(config)
            case WebhookConfig():
                from evented.webhook_watcher import WebhookEventSource

                return WebhookEventSource(config)
            case EmailConfig():
                from evented.email_watcher import EmailEventSource

                return EmailEventSource(config)
            case TimeEventConfig():
                from evented.timed_watcher import TimeEventSource

                return TimeEventSource(config)
            case _:
                msg = f"Unknown event source type: {config.type}"
                raise ValueError(msg)
