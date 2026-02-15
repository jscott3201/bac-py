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


@pytest.fixture
def sc_tls_config() -> object | None:
    """SC TLS config from TLS_CERT_DIR/TLS_CERT_NAME env vars, or None."""
    cert_dir = os.environ.get("TLS_CERT_DIR", "")
    cert_name = os.environ.get("TLS_CERT_NAME", "")
    if cert_dir and cert_name:
        from bac_py.transport.sc.tls import SCTLSConfig

        return SCTLSConfig(
            private_key_path=os.path.join(cert_dir, f"{cert_name}.key"),
            certificate_path=os.path.join(cert_dir, f"{cert_name}.crt"),
            ca_certificates_path=os.path.join(cert_dir, "ca.crt"),
        )
    return None


@pytest.fixture
def sc_hub_uri() -> str:
    """SC hub WebSocket URI from env."""
    host = os.environ.get("SC_HUB_ADDRESS", "172.30.1.120")
    port = os.environ.get("SC_HUB_PORT", "4443")
    scheme = "wss" if os.environ.get("TLS_CERT_DIR") else "ws"
    return f"{scheme}://{host}:{port}"


@pytest.fixture
def sc_node1_vmac() -> str:
    """SC node1 VMAC hex string from env."""
    return os.environ.get("SC_NODE1_VMAC", "02AA00000001")


@pytest.fixture
def sc_node2_vmac() -> str:
    """SC node2 VMAC hex string from env."""
    return os.environ.get("SC_NODE2_VMAC", "02AA00000002")


@pytest.fixture
def sc_stress_hub_uri() -> str:
    """SC stress hub WebSocket URI from env."""
    host = os.environ.get("SC_STRESS_HUB_ADDRESS", "172.30.1.130")
    port = os.environ.get("SC_STRESS_HUB_PORT", "4443")
    scheme = "wss" if os.environ.get("TLS_CERT_DIR") else "ws"
    return f"{scheme}://{host}:{port}"


@pytest.fixture
def sc_stress_node1_vmac() -> str:
    """SC stress node1 VMAC hex string from env."""
    return os.environ.get("SC_STRESS_NODE1_VMAC", "02BB00000001")


@pytest.fixture
def sc_stress_node2_vmac() -> str:
    """SC stress node2 VMAC hex string from env."""
    return os.environ.get("SC_STRESS_NODE2_VMAC", "02BB00000002")
