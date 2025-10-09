"""Event sources for LLMling agent."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, SecretStr
from schemez import Schema


DEFAULT_TEMPLATE = """
{%- if include_timestamp %}at {{ timestamp }}{% endif %}
Event from {{ source }}:
{%- if include_metadata %}
Metadata:
{% for key, value in metadata.items() %}
{{ key }}: {{ value }}
{% endfor %}
{% endif %}
{{ content }}
"""


class EventSourceConfig(Schema):
    """Base configuration for event sources."""

    type: str = Field(init=False)
    """Discriminator field for event source types."""

    name: str
    """Unique identifier for this event source."""

    enabled: bool = True
    """Whether this event source is active."""

    template: str = DEFAULT_TEMPLATE
    """Jinja2 template for formatting events."""

    include_metadata: bool = True
    """Control metadata visibility in template."""

    include_timestamp: bool = True
    """Control timestamp visibility in template."""

    model_config = ConfigDict(frozen=True)


class FileWatchConfig(EventSourceConfig):
    """File watching event source."""

    type: Literal["file"] = Field("file", init=False)
    """File / folder content change events."""

    paths: list[str]
    """Paths or patterns to watch for changes."""

    extensions: list[str] | None = None
    """File extensions to monitor (e.g. ['.py', '.md'])."""

    ignore_paths: list[str] | None = None
    """Paths or patterns to ignore."""

    recursive: bool = True
    """Whether to watch subdirectories."""

    debounce: int = 1600
    """Minimum time (ms) between trigger events."""


class WebhookConfig(EventSourceConfig):
    """Webhook event source."""

    type: Literal["webhook"] = Field("webhook", init=False)
    """webhook-based event."""

    port: int = Field(default=..., ge=1, le=65535)
    """Port to listen on."""

    path: str
    """URL path to handle requests."""

    secret: SecretStr | None = None
    """Optional secret for request validation."""


class TimeEventConfig(EventSourceConfig):
    """Time-based event source configuration."""

    type: Literal["time"] = Field("time", init=False)
    """Time event."""

    schedule: str
    """Cron expression for scheduling (e.g. '0 9 * * 1-5' for weekdays at 9am)"""

    prompt: str
    """Prompt to send to the agent when the schedule triggers."""

    timezone: str | None = None
    """Timezone for schedule (defaults to system timezone)"""

    skip_missed: bool = False
    """Whether to skip executions missed while agent was inactive"""


class EmailConfig(EventSourceConfig):
    """Email event source configuration.

    Monitors an email inbox for new messages and converts them to events.
    """

    type: Literal["email"] = Field("email", init=False)
    """Email event."""

    host: str
    """IMAP server hostname (e.g. 'imap.gmail.com')"""

    port: int = Field(ge=1, le=65535, default=993)
    """Server port (defaults to 993 for IMAP SSL)"""

    username: str
    """Email account username/address"""

    password: SecretStr
    """Account password or app-specific password"""

    folder: str = "INBOX"
    """Folder/mailbox to monitor"""

    ssl: bool = True
    """Whether to use SSL/TLS connection"""

    check_interval: int = Field(default=60, gt=0)
    """How often to check for new emails (in seconds)"""

    mark_seen: bool = True
    """Whether to mark processed emails as seen"""

    filters: dict[str, str] = Field(default_factory=dict)
    """Filtering rules for emails (subject, from, etc)"""

    max_size: int | None = Field(default=None, ge=0)
    """Size limit for processed emails in bytes"""


EventConfig = Annotated[
    FileWatchConfig | WebhookConfig | EmailConfig | TimeEventConfig,
    Field(discriminator="type"),
]
