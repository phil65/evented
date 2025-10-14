"""File event source."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from evented.base import EventSource
from evented.event_data import FileEventData


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from types import TracebackType

    from watchfiles import Change
    from watchfiles.main import FileChange

    from evented.configs import FileWatchConfig
    from evented.event_data import ChangeType, EventData


class ExtensionFilter:
    """Filter for specific file extensions."""

    def __init__(self, extensions: list[str], ignore_paths: list[str] | None = None):
        """Initialize filter.

        Args:
            extensions: File extensions to watch (e.g. ['.py', '.md'])
            ignore_paths: Paths to ignore
        """
        from watchfiles.filters import DefaultFilter

        self.extensions = tuple(e if e.startswith(".") else f".{e}" for e in extensions)
        self._default_filter = DefaultFilter(ignore_paths=ignore_paths)

    def __call__(self, change: Change, path: str) -> bool:
        """Check if file should be watched."""
        return path.endswith(self.extensions) and self._default_filter(change, path)


class FileSystemEventSource(EventSource):
    """Watch file system changes using watchfiles."""

    def __init__(self, config: FileWatchConfig):
        """Initialize file system watcher.

        Args:
            config: File watch configuration
        """
        self.config = config
        self._watch: AsyncIterator[set[FileChange]] | None = None
        self._stop_event: asyncio.Event | None = None

    async def __aenter__(self) -> Self:
        """Set up watchfiles watcher."""
        if not self.config.paths:
            msg = "No paths specified to watch"
            raise ValueError(msg)

        from watchfiles.main import awatch

        self._stop_event = asyncio.Event()
        watch_filter = None  # Create filter from extensions if provided
        if self.config.extensions:
            to_ignore = self.config.ignore_paths
            watch_filter = ExtensionFilter(self.config.extensions, ignore_paths=to_ignore)

        self._watch = awatch(
            *self.config.paths,
            watch_filter=watch_filter,
            debounce=self.config.debounce,
            stop_event=self._stop_event,
            recursive=self.config.recursive,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop watchfiles watcher."""
        if self._stop_event:
            self._stop_event.set()
        self._watch = None
        self._stop_event = None

    async def events(self) -> AsyncGenerator[EventData]:
        """Get file system events."""
        from watchfiles import Change

        if not self._watch:
            msg = "Source not connected"
            raise RuntimeError(msg)
        change_to_type: dict[Change, ChangeType] = {
            Change.added: "added",
            Change.modified: "modified",
            Change.deleted: "deleted",
        }
        async for changes in self._watch:
            for change, path in changes:
                if change not in change_to_type:
                    continue
                typ = change_to_type[change]
                yield FileEventData.create(self.config.name, path=str(path), type=typ)
