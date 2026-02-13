"""Smoke test to verify package imports correctly."""

import bac_py


def test_version() -> None:
    assert bac_py.__version__ == "1.3.3"
