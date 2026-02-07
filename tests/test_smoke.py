"""Smoke test to verify package imports correctly."""

import bac_py


def test_version() -> None:
    assert bac_py.__version__ == "0.1.0"
