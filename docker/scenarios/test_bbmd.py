"""Scenario 2: Foreign device registration and BBMD forwarding over real UDP.

NOTE: These tests require cross-network UDP routing and broadcast forwarding
which Docker bridge networks do not provide. All tests are skipped when running
under Docker Compose. They pass with host networking or on a physical LAN.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from bac_py import Client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

BBMD = os.environ.get("BBMD_ADDRESS", "172.30.1.30")
SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.31")
SERVER_INSTANCE = int(os.environ.get("SERVER_INSTANCE", "201"))
BBMD_INSTANCE = int(os.environ.get("BBMD_INSTANCE", "200"))

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(
        reason="BBMD tests require cross-network routing; Docker bridge networks are isolated"
    ),
]


@pytest.fixture
async def fd_client() -> AsyncGenerator[Client]:
    """Client registered as foreign device with the BBMD."""
    async with Client(
        instance_number=901,
        port=0,
        bbmd_address=BBMD,
        bbmd_ttl=60,
    ) as c:
        yield c


async def test_register_and_discover(fd_client: Client) -> None:
    assert fd_client.is_foreign_device
    assert fd_client.foreign_device_status is not None


async def test_read_bdt(fd_client: Client) -> None:
    bdt = await fd_client.read_bdt(BBMD)
    # BBMD should have at least its own entry (or empty for FD-only mode)
    assert isinstance(bdt, list)


async def test_read_fdt_shows_registration(fd_client: Client) -> None:
    fdt = await fd_client.read_fdt(BBMD)
    assert len(fdt) >= 1
    # Our registration should appear in the FDT
    addresses = [e.address for e in fdt]
    assert any(a for a in addresses)  # At least one FDT entry


async def test_read_through_bbmd(fd_client: Client) -> None:
    value = await fd_client.read(SERVER, "ai,1", "present-value")
    assert isinstance(value, float)
