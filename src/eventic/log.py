"""Logging configuration for eventic."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given name.

    Args:
        name: The name of the logger, will be prefixed with 'eventic.'

    Returns:
        A logger instance
    """
    return logging.getLogger(f"eventic.{name}")
