"""Tests for async context manager behavior across event sources."""

from __future__ import annotations

import asyncio

import pytest

from evented.base import EventSource
from evented.configs import TimeEventConfig


@pytest.mark.asyncio
async def test_time_source_context_manager_lifecycle():
    """Test TimeEventSource properly handles context manager lifecycle."""
    config = TimeEventConfig(
        name="lifecycle_test",
        schedule="0 0 * * *",  # Daily at midnight
        prompt="Test prompt",
    )

    source = EventSource.from_config(config)

    # Before context: stop event should not be set
    assert not source._stop_event.is_set()

    async with source as ctx_source:
        # Context should return self
        assert ctx_source is source
        # Stop event should still not be set during active context
        assert not source._stop_event.is_set()

    # After context: stop event should be set
    assert source._stop_event.is_set()


@pytest.mark.asyncio
async def test_context_manager_exception_handling():
    """Test that context managers properly cleanup on exceptions."""
    config = TimeEventConfig(
        name="exception_test",
        schedule="0 0 * * *",
        prompt="Test",
    )

    source = EventSource.from_config(config)

    try:
        async with source:
            # Simulate an exception during context
            msg = "Test exception"
            raise ValueError(msg)  # noqa: TRY301
    except ValueError:
        pass  # Expected

    # Cleanup should still have occurred
    assert source._stop_event.is_set()


@pytest.mark.asyncio
async def test_multiple_context_entries():
    """Test that event sources can be used in multiple contexts."""
    config = TimeEventConfig(
        name="multiple_test",
        schedule="0 0 * * *",
        prompt="Test",
    )

    source = EventSource.from_config(config)

    # First context
    async with source:
        assert not source._stop_event.is_set()

    assert source._stop_event.is_set()

    # Reset for second context (sources should be reusable)
    source._stop_event = asyncio.Event()

    # Second context should work
    async with source:
        assert not source._stop_event.is_set()

    assert source._stop_event.is_set()
