"""Shared pytest configuration for Docker integration tests."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: Docker integration test")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark all tests in docker/scenarios as integration tests."""
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture
def server_address() -> str:
    """Target server IP from env."""
    return os.environ.get("SERVER_ADDRESS", "172.30.1.10")


@pytest.fixture
def server_instance() -> int:
    """Target server device instance from env."""
    return int(os.environ.get("SERVER_INSTANCE", "100"))


@pytest.fixture
def bbmd_address() -> str:
    """BBMD IP from env."""
    return os.environ.get("BBMD_ADDRESS", "172.30.1.30")


@pytest.fixture
def bbmd_instance() -> int:
    """BBMD device instance from env."""
    return int(os.environ.get("BBMD_INSTANCE", "200"))


@pytest.fixture
def router_address() -> str:
    """Router IP from env."""
    return os.environ.get("ROUTER_ADDRESS", "172.30.1.50")


@pytest.fixture
def router_instance() -> int:
    """Router device instance from env."""
    return int(os.environ.get("ROUTER_INSTANCE", "300"))
