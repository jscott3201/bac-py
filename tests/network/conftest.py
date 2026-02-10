"""Shared fixtures for network tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from bac_py.network.router import RouterPort


def _make_transport(*, local_mac: bytes = b"\x7f\x00\x00\x01\xba\xc0") -> MagicMock:
    """Create a mock TransportPort."""
    transport = MagicMock()
    transport.local_mac = local_mac
    transport.max_npdu_length = 1497
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    return transport


def _make_port(
    port_id: int = 1,
    network_number: int = 10,
    *,
    transport: MagicMock | None = None,
) -> RouterPort:
    """Create a RouterPort with sane defaults."""
    if transport is None:
        transport = _make_transport()
    return RouterPort(
        port_id=port_id,
        network_number=network_number,
        transport=transport,
        mac_address=transport.local_mac,
        max_npdu_length=transport.max_npdu_length,
    )
