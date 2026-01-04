"""Event source configuration.

This is a lightweight config-only package for fast imports.
For the actual event sources, use `from evented import ...`.
"""

from __future__ import annotations

from evented_config.configs import (
    DEFAULT_TEMPLATE,
    EmailConfig,
    EventConfig,
    EventSourceConfig,
    FileWatchConfig,
    TimeEventConfig,
    WebhookConfig,
)


__all__ = [
    "DEFAULT_TEMPLATE",
    "EmailConfig",
    "EventConfig",
    "EventSourceConfig",
    "FileWatchConfig",
    "TimeEventConfig",
    "WebhookConfig",
]
