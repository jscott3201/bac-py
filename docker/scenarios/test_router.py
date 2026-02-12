"""Scenario 3: Cross-network routing and discovery over real UDP.

NOTE: These tests require UDP broadcast forwarding across Docker networks
which bridge networks do not provide. All tests are skipped when running
under Docker Compose. They pass with host networking or on a physical LAN.
"""

from __future__ import annotations

import os

import pytest

from bac_py import Client

ROUTER = os.environ.get("ROUTER_ADDRESS", "172.30.1.50")
SERVER_NET2 = os.environ.get("SERVER_NET2_ADDRESS", "172.30.2.10")
SERVER_NET2_INSTANCE = int(os.environ.get("SERVER_NET2_INSTANCE", "301"))
ROUTER_INSTANCE = int(os.environ.get("ROUTER_INSTANCE", "300"))
NETWORK_1 = int(os.environ.get("NETWORK_1", "1"))
NETWORK_2 = int(os.environ.get("NETWORK_2", "2"))

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(
        reason="Router tests require broadcast forwarding; Docker bridge networks are isolated"
    ),
]


@pytest.fixture
async def client():
    async with Client(instance_number=902, port=0) as c:
        yield c


async def test_who_is_router_finds_networks(client: Client):
    routers = await client.who_is_router_to_network(timeout=5.0)
    assert len(routers) >= 1
    all_networks = []
    for r in routers:
        all_networks.extend(r.networks)
    assert NETWORK_2 in all_networks


async def test_discover_across_router(client: Client):
    devices = await client.discover(destination=f"{NETWORK_2}:*", timeout=5.0, expected_count=1)
    instances = [d.instance for d in devices]
    assert SERVER_NET2_INSTANCE in instances


async def test_read_across_router(client: Client):
    # First discover to learn the remote address
    devices = await client.discover(destination=f"{NETWORK_2}:*", timeout=5.0, expected_count=1)
    remote = next(d for d in devices if d.instance == SERVER_NET2_INSTANCE)

    value = await client.read(remote.address_str, "ai,1", "present-value")
    assert isinstance(value, float)
    assert value == pytest.approx(72.5)
