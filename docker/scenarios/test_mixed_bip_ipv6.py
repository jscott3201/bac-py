"""Scenario 14: Mixed BIP-to-IPv6 routing through a cross-transport router.

A BACnet/IP client on network 1 reads and writes objects on an IPv6 server
on network 2, routed through a BIP/IPv6 dual-stack router.  Uses direct
routed addresses (``NETWORK:HEXMAC``) to bypass broadcast-based discovery
which is unreliable on Docker bridge networks.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from bac_py import Client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

ROUTER = os.environ.get("ROUTER_ADDRESS", "172.30.1.180")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "801"))
NETWORK_2 = int(os.environ.get("NETWORK_2", "2"))
SERVER_VMAC = os.environ.get("SERVER_VMAC", "aabbcc")

# Routed address: "NETWORK:HEXMAC" format
SERVER_ADDRESS = f"{NETWORK_2}:{SERVER_VMAC}"

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client() -> AsyncGenerator[Client]:
    async with Client(instance_number=910, port=0) as c:
        c.add_route(NETWORK_2, ROUTER)
        yield c


# --- ReadProperty ---


async def test_read_present_value(client: Client) -> None:
    """Read present-value of ai,1 through the router."""
    value = await client.read(SERVER_ADDRESS, "ai,1", "present-value")
    assert isinstance(value, float)
    assert value == pytest.approx(72.5)


async def test_read_object_name(client: Client) -> None:
    """Read object-name of ai,1 through the router."""
    name = await client.read(SERVER_ADDRESS, "ai,1", "object-name")
    assert name == "Temperature"


# --- ReadPropertyMultiple ---


async def test_read_multiple_objects(client: Client) -> None:
    """RPM for multiple objects through the router."""
    result = await client.read_multiple(
        SERVER_ADDRESS,
        {
            "ai,1": ["present-value", "object-name"],
            "av,1": ["present-value"],
        },
    )
    assert len(result) >= 2


# --- WriteProperty + readback ---


async def test_write_and_readback(client: Client) -> None:
    """Write av,1 present-value and read it back through the router."""
    await client.write(SERVER_ADDRESS, "av,1", "present-value", 42.0)
    value = await client.read(SERVER_ADDRESS, "av,1", "present-value")
    assert value == pytest.approx(42.0)
    # Restore original
    await client.write(SERVER_ADDRESS, "av,1", "present-value", 70.0)


# --- WritePropertyMultiple + readback ---


async def test_write_multiple_and_readback(client: Client) -> None:
    """WPM through the router and verify with a read."""
    await client.write_multiple(
        SERVER_ADDRESS,
        {"av,1": {"present-value": 55.0}},
    )
    value = await client.read(SERVER_ADDRESS, "av,1", "present-value")
    assert value == pytest.approx(55.0)
    # Restore
    await client.write(SERVER_ADDRESS, "av,1", "present-value", 70.0)


# --- Object list ---


async def test_get_object_list(client: Client) -> None:
    """Get object list from IPv6 server through the router."""
    obj_list = await client.get_object_list(SERVER_ADDRESS, INSTANCE)
    assert len(obj_list) >= 6  # device + ai + ao + av + bi + bv
