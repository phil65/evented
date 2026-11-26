"""Smoke test: the package imports and reports its version."""

import evented


def test_package_imports() -> None:
    """The package can be imported and exposes a version string."""
    assert isinstance(evented.__version__, str)
