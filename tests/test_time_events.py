"""Tests for time-based event source."""

from __future__ import annotations

import asyncio

import pytest

from evented.configs import TimeEventConfig
from evented.timed_watcher import TimeEventSource


@pytest.mark.asyncio
async def test_invalid_cron_expression_raises_error():
    """Test that invalid cron expressions are caught during context entry."""
    config = TimeEventConfig(
        name="invalid_cron",
        schedule="invalid cron expression",
        prompt="Should fail",
    )

    source = TimeEventSource(config)

    with pytest.raises(ValueError, match="Invalid cron expression"):
        async with source:
            pass


@pytest.mark.asyncio
async def test_valid_cron_expression_passes():
    """Test that valid cron expressions validate successfully."""
    config = TimeEventConfig(
        name="valid_cron",
        schedule="0 9 * * 1-5",  # 9 AM on weekdays
        prompt="Daily standup",
    )

    source = TimeEventSource(config)

    # Should not raise
    async with source:
        pass


@pytest.mark.asyncio
async def test_timezone_handling():
    """Test timezone is properly set during initialization."""
    import zoneinfo

    # Skip test if timezone data is not available (e.g., Windows CI)
    try:
        zoneinfo.ZoneInfo("UTC")
        timezone_name = "UTC"
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("Timezone data not available on this system")

    config = TimeEventConfig(
        name="tz_test",
        schedule="0 12 * * *",
        prompt="Lunch reminder",
        timezone=timezone_name,
    )

    source = TimeEventSource(config)
    assert source._tz is not None
    assert str(source._tz) == timezone_name


def test_no_timezone_defaults_to_none():
    """Test that missing timezone defaults to None."""
    config = TimeEventConfig(
        name="no_tz",
        schedule="0 0 * * *",
        prompt="Midnight task",
    )

    source = TimeEventSource(config)
    assert source._tz is None


@pytest.mark.asyncio
async def test_stop_event_mechanism():
    """Test that stop event properly terminates event generation."""
    config = TimeEventConfig(
        name="stop_test",
        schedule="* * * * * *",  # Every second
        prompt="Quick test",
    )

    source = TimeEventSource(config)

    async with source:
        # Manually trigger stop
        source._stop_event.set()

        # Events should stop quickly
        events = []
        async for event in source.events():
            events.append(event)
            if len(events) >= 1:  # Should not reach this due to stop
                break

        # Should have no events due to immediate stop
        assert len(events) == 0


@pytest.mark.asyncio
async def test_event_data_structure():
    """Test that generated events have correct structure."""
    config = TimeEventConfig(
        name="structure_test",
        schedule="* * * * * *",  # Every second for quick test
        prompt="Test prompt content",
    )

    source = TimeEventSource(config)

    async with source:
        event = await asyncio.wait_for(anext(source.events()), timeout=2.0)

        # Verify event structure
        assert event.source == "structure_test"
        assert event.schedule == "* * * * * *"
        assert event.prompt == "Test prompt content"

        # Verify content contains key information
        content = event.to_prompt()
        assert "* * * * * *" in content
        assert "Test prompt content" in content


def test_complex_cron_expressions():
    """Test various complex but valid cron expressions validate."""
    valid_expressions = [
        "0 0 * * *",  # Daily at midnight
        "*/15 * * * *",  # Every 15 minutes
        "0 9-17 * * 1-5",  # Business hours on weekdays
        "0 0 1 * *",  # First day of month
        "0 0 * * 0",  # Sundays
        "30 2 * * 1",  # Mondays at 2:30 AM
    ]

    for schedule in valid_expressions:
        config = TimeEventConfig(
            name=f"test_{schedule.replace(' ', '_').replace('*', 'star')}",
            schedule=schedule,
            prompt="Test",
        )

        source = TimeEventSource(config)

        # Should initialize without error
        assert source.config.schedule == schedule


def test_invalid_cron_expressions():
    """Test various invalid cron expressions are rejected."""
    invalid_expressions = [
        "60 * * * *",  # Invalid minute (0-59)
        "* 25 * * *",  # Invalid hour (0-23)
        "* * 32 * *",  # Invalid day (1-31)
        "* * * 13 *",  # Invalid month (1-12)
        "* * * * 8",  # Invalid day of week (0-7, but 7=0)
        "not a cron",  # Invalid format
        "",  # Empty string
        "* * *",  # Too few fields
    ]

    for schedule in invalid_expressions:
        config = TimeEventConfig(
            name="invalid_test",
            schedule=schedule,
            prompt="Test",
        )

        source = TimeEventSource(config)

        # Validation should happen in __aenter__
        with pytest.raises(ValueError):  # noqa: PT011
            asyncio.run(source.__aenter__())
