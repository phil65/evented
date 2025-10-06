"""Eventic package."""

from __future__ import annotations

from importlib.metadata import version

try:
    __version__ = version("eventic")
except Exception:
    __version__ = "unknown"


__all__ = ["__version__"]
