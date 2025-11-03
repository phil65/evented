"""Evented: main package.

Event emitters.
"""

from __future__ import annotations

from importlib.metadata import version

__version__ = version("evented")
__title__ = "Evented"

__author__ = "Philipp Temminghoff"
__author_email__ = "philipptemminghoff@googlemail.com"
__copyright__ = "Copyright (c) 2025 Philipp Temminghoff"
__license__ = "MIT"
__url__ = "https://github.com/phil65/evented"


from evented.base import EventSource
from evented.configs import (
    EmailConfig,
    EventSourceConfig,
    FileWatchConfig,
    TimeEventConfig,
    WebhookConfig,
)
from evented.email_watcher import EmailEventSource
from evented.file_watcher import FileSystemEventSource
from evented.webhook_watcher import WebhookEventSource
from evented.event_data import (
    EventData,
    FileEventData,
    TimeEventData,
    EmailEventData,
    WebhookEventData,
    FunctionResultEventData,
)

__all__ = [
    "EmailConfig",
    "EmailEventData",
    "EmailEventSource",
    "EventData",
    "EventSource",
    "EventSourceConfig",
    "FileEventData",
    "FileSystemEventSource",
    "FileWatchConfig",
    "FunctionResultEventData",
    "TimeEventConfig",
    "TimeEventData",
    "WebhookConfig",
    "WebhookEventData",
    "WebhookEventSource",
    "__version__",
]
