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

    name: str = Field(
        title="Event source name",
        examples=["file_watcher", "webhook_handler", "daily_report"],
    )
    """Unique identifier for this event source."""

    enabled: bool = True
    """Whether this event source is active."""

    template: str = Field(
        default=DEFAULT_TEMPLATE,
        title="Event template",
        examples=[
            "Event: {{ content }}",
            "{{ timestamp }}: {{ source }} - {{ content }}",
            "Alert from {{ source }}: {{ content }}\nMetadata: {{ metadata }}",
        ],
    )
    """Jinja2 template for formatting events."""

    include_metadata: bool = Field(default=True, title="Include metadata")
    """Control metadata visibility in template."""

    include_timestamp: bool = Field(default=True, title="Include timestamp")
    """Control timestamp visibility in template."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Event source"})


class FileWatchConfig(EventSourceConfig):
    """File watching event source."""

    type: Literal["file"] = Field("file", init=False)
    """File / folder content change events."""

    paths: list[str] = Field(
        title="Watch paths",
        examples=[
            ["/home/user/documents", "/var/log"],
            ["./config", "./src"],
        ],
    )
    """Paths or patterns to watch for changes."""

    extensions: list[str] | None = Field(
        default=None,
        title="File extensions",
        examples=[
            [".py", ".js", ".ts"],
            [".yaml", ".yml", ".json"],
        ],
    )
    """File extensions to monitor (e.g. ['.py', '.md'])."""

    ignore_paths: list[str] | None = Field(
        default=None,
        title="Ignore paths",
        examples=[
            [".git", "__pycache__", "node_modules"],
            ["/tmp/*", "*.cache"],
        ],
    )
    """Paths or patterns to ignore."""

    recursive: bool = Field(default=True, title="Watch recursively")
    """Whether to watch subdirectories."""

    debounce: int = Field(
        default=1600, ge=0, title="Debounce time (ms)", examples=[500, 1000, 3000]
    )
    """Minimum time (ms) between trigger events."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "File watching"})


class WebhookConfig(EventSourceConfig):
    """Webhook event source."""

    type: Literal["webhook"] = Field("webhook", init=False)
    """webhook-based event."""

    port: int = Field(default=..., ge=1, le=65535, title="Server port", examples=[8080, 3000])
    """Port to listen on."""

    path: str = Field(title="Webhook path", examples=["/webhook", "/github-webhook", "/api/events"])
    """URL path to handle requests."""

    secret: SecretStr | None = Field(default=None, title="Webhook secret")
    """Optional secret for request validation."""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Webhook"})


class TimeEventConfig(EventSourceConfig):
    """Time-based event source configuration."""

    type: Literal["time"] = Field("time", init=False)
    """Time event."""

    schedule: str = Field(
        title="Cron schedule",
        examples=[
            "0 9 * * 1-5",  # weekdays at 9am
            "*/15 * * * *",  # every 15 minutes
            "0 0 * * 0",  # every Sunday at midnight
        ],
    )
    """Cron expression for scheduling (e.g. '0 9 * * 1-5' for weekdays at 9am)"""

    prompt: str = Field(
        title="Trigger prompt",
        examples=["Generate daily report", "Check system status", "Send weekly summary"],
    )
    """Prompt to send to the agent when the schedule triggers."""

    timezone: str | None = Field(
        default=None,
        title="Timezone",
        examples=["UTC", "America/New_York", "Europe/London", "Asia/Tokyo"],
    )
    """Timezone for schedule (defaults to system timezone)"""

    skip_missed: bool = Field(default=False, title="Skip missed executions")
    """Whether to skip executions missed while agent was inactive"""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Time event"})


class EmailConfig(EventSourceConfig):
    """Email event source configuration.

    Monitors an email inbox for new messages and converts them to events.
    """

    type: Literal["email"] = Field("email", init=False)
    """Email event."""

    host: str = Field(
        title="IMAP server",
        examples=["imap.gmail.com", "imap.outlook.com", "mail.company.com"],
    )
    """IMAP server hostname (e.g. 'imap.gmail.com')"""

    port: int = Field(ge=1, le=65535, default=993, title="IMAP port", examples=[993, 143, 587])
    """Server port (defaults to 993 for IMAP SSL)"""

    username: str = Field(
        title="Email username",
        examples=["user@gmail.com", "notifications@company.com", "monitor"],
    )
    """Email account username/address"""

    password: SecretStr = Field(title="Email password")
    """Account password or app-specific password"""

    folder: str = Field(
        default="INBOX",
        title="Email folder",
        examples=["INBOX", "Alerts", "Notifications", "INBOX/Reports"],
    )
    """Folder/mailbox to monitor"""

    ssl: bool = Field(default=True, title="Use SSL/TLS")
    """Whether to use SSL/TLS connection"""

    check_interval: int = Field(
        default=60, gt=0, title="Check interval (seconds)", examples=[30, 60, 300]
    )
    """How often to check for new emails (in seconds)"""

    mark_seen: bool = Field(default=True, title="Mark emails as seen")
    """Whether to mark processed emails as seen"""

    filters: dict[str, str] = Field(
        default_factory=dict,
        title="Email filters",
        examples=[
            {"SUBJECT": "Alert", "FROM": "system@company.com"},
            {"SUBJECT": "ERROR", "TO": "alerts@company.com"},
            {"FROM": "monitoring@company.com", "SUBJECT": "Warning"},
        ],
    )
    """Filtering rules for emails (subject, from, etc)"""

    max_size: int | None = Field(
        default=None,
        ge=0,
        title="Max email size (bytes)",
        examples=[1048576, 5242880, 10485760],
    )
    """Size limit for processed emails in bytes"""

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Email"})


EventConfig = Annotated[
    FileWatchConfig | WebhookConfig | EmailConfig | TimeEventConfig,
    Field(discriminator="type"),
]
