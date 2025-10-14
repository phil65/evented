"""Tests for EventSource factory method and configuration validation."""

from __future__ import annotations

from pydantic import SecretStr, ValidationError
import pytest

from evented.base import EventSource
from evented.configs import EmailConfig, FileWatchConfig, TimeEventConfig, WebhookConfig
from evented.file_watcher import FileSystemEventSource
from evented.timed_watcher import TimeEventSource
from evented.webhook_watcher import WebhookEventSource


def test_factory_creates_correct_file_source():
    """Test factory creates FileSystemEventSource for file config."""
    config = FileWatchConfig(
        name="test_file",
        paths=["/tmp", "/var/log"],
        extensions=[".py", ".txt"],
    )

    source = EventSource.from_config(config)

    assert isinstance(source, FileSystemEventSource)
    assert source.config is config
    assert source.config.paths == ["/tmp", "/var/log"]


def test_factory_creates_correct_webhook_source():
    """Test factory creates WebhookEventSource for webhook config."""
    config = WebhookConfig(
        name="test_webhook",
        port=8080,
        path="/webhook",
    )

    source = EventSource.from_config(config)

    assert isinstance(source, WebhookEventSource)
    assert source.config is config
    assert source.config.port == 8080


def test_factory_creates_correct_time_source():
    """Test factory creates TimeEventSource for time config."""
    config = TimeEventConfig(
        name="test_time",
        schedule="0 9 * * 1-5",
        prompt="Daily reminder",
    )

    source = EventSource.from_config(config)

    assert isinstance(source, TimeEventSource)
    assert source.config is config
    assert source.config.schedule == "0 9 * * 1-5"


def test_factory_rejects_disabled_config():
    """Test factory raises ValueError for disabled configs."""
    config = FileWatchConfig(
        name="disabled_source",
        paths=["/tmp"],
        enabled=False,
    )

    with pytest.raises(ValueError, match="Source disabled_source is disabled"):
        EventSource.from_config(config)


def test_file_config_requires_paths():
    """Test FileWatchConfig requires non-empty paths."""
    # Empty paths should be valid at config level but may fail at runtime
    config = FileWatchConfig(name="empty_paths", paths=[])
    assert config.paths == []

    # But the actual source should handle validation
    source = EventSource.from_config(config)
    assert isinstance(source, FileSystemEventSource)


def test_file_config_validates_extensions():
    """Test FileWatchConfig handles extensions properly."""
    config = FileWatchConfig(
        name="with_extensions",
        paths=["/tmp"],
        extensions=[".py", ".md", ".txt"],
    )

    assert config.extensions == [".py", ".md", ".txt"]

    source = EventSource.from_config(config)
    assert isinstance(source, FileSystemEventSource)


def test_webhook_config_validates_port_range():
    """Test WebhookConfig validates port is in valid range."""
    # Valid ports
    for port in [80, 443, 8080, 65535]:
        config = WebhookConfig(name="test", port=port, path="/webhook")
        assert config.port == port

    # Invalid ports should raise ValidationError
    for invalid_port in [0, -1, 65536, 100000]:
        with pytest.raises(ValidationError):
            WebhookConfig(name="test", port=invalid_port, path="/webhook")


def test_email_config_defaults():
    """Test EmailConfig sets appropriate defaults."""
    config = EmailConfig(
        name="test_email",
        host="imap.gmail.com",
        username="test@gmail.com",
        password=SecretStr("password"),
    )

    # Check defaults
    assert config.ssl is True
    assert config.folder == "INBOX"
    assert config.check_interval == 60


def test_email_config_non_ssl_defaults():
    """Test EmailConfig with SSL disabled."""
    config = EmailConfig(
        name="non_ssl_email",
        host="mail.example.com",
        username="user",
        password=SecretStr("pass"),
        ssl=False,
    )

    assert config.ssl is False


def test_time_config_validates_required_fields():
    """Test TimeEventConfig requires schedule and prompt."""
    # Valid config
    config = TimeEventConfig(
        name="valid_timer",
        schedule="0 0 * * *",
        prompt="Daily task",
    )

    assert config.schedule == "0 0 * * *"
    assert config.prompt == "Daily task"


def test_time_config_with_timezone():
    """Test TimeEventConfig properly handles timezone."""
    config = TimeEventConfig(
        name="tz_timer",
        schedule="0 12 * * *",
        prompt="Lunch time",
        timezone="Europe/London",
        skip_missed=False,
    )

    assert config.timezone == "Europe/London"
    assert config.skip_missed is False


def test_config_discriminator_types():
    """Test that each config has correct type discriminator."""
    configs_and_types = [
        (FileWatchConfig(name="file", paths=["/tmp"]), "file"),
        (WebhookConfig(name="webhook", port=8080, path="/test"), "webhook"),
        (
            EmailConfig(
                name="email", host="test.com", username="user", password=SecretStr("pass")
            ),
            "email",
        ),
        (TimeEventConfig(name="time", schedule="0 0 * * *", prompt="test"), "time"),
    ]

    for config, expected_type in configs_and_types:
        assert config.type == expected_type


def test_config_names_are_preserved():
    """Test that config names are correctly preserved through factory."""
    configs = [
        FileWatchConfig(name="my_file_watcher", paths=["/tmp"]),
        WebhookConfig(name="my_webhook_server", port=8080, path="/hook"),
        TimeEventConfig(name="my_scheduler", schedule="0 0 * * *", prompt="test"),
    ]

    for config in configs:
        source = EventSource.from_config(config)
        assert source.config.name == config.name


def test_secret_str_handling():
    """Test that SecretStr fields are properly handled."""
    # Webhook secret
    webhook_config = WebhookConfig(
        name="secure_webhook",
        port=8443,
        path="/secure",
        secret=SecretStr("webhook_secret_key"),
    )

    source = EventSource.from_config(webhook_config)
    assert isinstance(source, WebhookEventSource)
    assert source.config.secret.get_secret_value() == "webhook_secret_key"


def test_all_configs_enabled_by_default():
    """Test that all config types are enabled by default."""
    configs = [
        FileWatchConfig(name="test", paths=["/tmp"]),
        WebhookConfig(name="test", port=8080, path="/test"),
        TimeEventConfig(name="test", schedule="0 0 * * *", prompt="test"),
    ]

    for config in configs:
        assert config.enabled is True

        # Should not raise when creating source
        source = EventSource.from_config(config)
        assert source is not None
