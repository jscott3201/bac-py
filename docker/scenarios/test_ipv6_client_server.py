"""Scenario 13: BACnet/IPv6 (Annex U) client/server read, write, and discovery."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from bac_py import Client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

SERVER = os.environ.get("SERVER_ADDRESS", "fd00:bac:1::10")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "700"))

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client() -> AsyncGenerator[Client]:
    async with Client(instance_number=900, ipv6=True, port=0) as c:
        yield c


# --- ReadProperty ---


async def test_read_present_value(client: Client) -> None:
    value = await client.read(f"[{SERVER}]", "ai,1", "present-value")
    assert isinstance(value, float)
    assert value == pytest.approx(72.5)


async def test_read_object_name(client: Client) -> None:
    name = await client.read(f"[{SERVER}]", "ai,1", "object-name")
    assert name == "Temperature"


# --- ReadPropertyMultiple ---


async def test_read_multiple_objects(client: Client) -> None:
    result = await client.read_multiple(
        f"[{SERVER}]",
        {
            "ai,1": ["present-value", "object-name"],
            "av,1": ["present-value"],
        },
    )
    assert len(result) >= 2


# --- WriteProperty + readback ---


async def test_write_and_readback(client: Client) -> None:
    await client.write(f"[{SERVER}]", "av,1", "present-value", 25.0)
    value = await client.read(f"[{SERVER}]", "av,1", "present-value")
    assert value == pytest.approx(25.0)
    # Restore original
    await client.write(f"[{SERVER}]", "av,1", "present-value", 70.0)


async def test_write_with_priority(client: Client) -> None:
    await client.write(f"[{SERVER}]", "ao,1", "present-value", 50.0, priority=8)
    value = await client.read(f"[{SERVER}]", "ao,1", "present-value")
    assert value == pytest.approx(50.0)
    # Relinquish the priority
    await client.write(f"[{SERVER}]", "ao,1", "present-value", None, priority=8)


# --- Object list ---


async def test_get_object_list(client: Client) -> None:
    obj_list = await client.get_object_list(f"[{SERVER}]", INSTANCE)
    assert len(obj_list) >= 6  # device + ai + ao + av + bi + bv
