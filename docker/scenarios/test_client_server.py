"""Scenario 1: Basic client/server read, write, and discovery over real UDP."""

from __future__ import annotations

import os

import pytest

from bac_py import Client

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.10")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "100"))

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with Client(instance_number=900, port=0) as c:
        yield c


# --- ReadProperty ---


async def test_read_present_value(client: Client):
    value = await client.read(SERVER, "ai,1", "present-value")
    assert isinstance(value, float)
    assert value == pytest.approx(72.5)


async def test_read_object_name(client: Client):
    name = await client.read(SERVER, "ai,1", "object-name")
    assert name == "Temperature"


# --- ReadPropertyMultiple ---


async def test_read_multiple_objects(client: Client):
    result = await client.read_multiple(
        SERVER,
        {
            "ai,1": ["present-value", "object-name"],
            "av,1": ["present-value"],
        },
    )
    assert "analog-input,1" in result or "ai,1" in result
    # Find the AI entry regardless of key format
    ai_key = next(k for k in result if ("1" in k and "input" in k.lower()) or k == "ai,1")
    ai = result[ai_key]
    assert "present-value" in ai or "pv" in ai


# --- WriteProperty + readback ---


async def test_write_and_readback(client: Client):
    await client.write(SERVER, "av,1", "present-value", 25.0)
    value = await client.read(SERVER, "av,1", "present-value")
    assert value == pytest.approx(25.0)
    # Restore original
    await client.write(SERVER, "av,1", "present-value", 70.0)


async def test_write_with_priority(client: Client):
    await client.write(SERVER, "ao,1", "present-value", 50.0, priority=8)
    value = await client.read(SERVER, "ao,1", "present-value")
    assert value == pytest.approx(50.0)
    # Relinquish the priority
    await client.write(SERVER, "ao,1", "present-value", None, priority=8)


# --- Discovery ---


@pytest.mark.skip(
    reason="Who-Is/I-Am requires broadcast; Docker bridge networks don't route broadcasts"
)
async def test_who_is_discovers_server(client: Client):
    devices = await client.discover(destination=SERVER, timeout=5.0, expected_count=1)
    assert len(devices) >= 1
    instances = [d.instance for d in devices]
    assert INSTANCE in instances


@pytest.mark.skip(
    reason="Who-Is/I-Am requires broadcast; Docker bridge networks don't route broadcasts"
)
async def test_discover_with_range(client: Client):
    devices = await client.discover(
        low_limit=INSTANCE,
        high_limit=INSTANCE,
        destination=SERVER,
        timeout=5.0,
        expected_count=1,
    )
    assert len(devices) == 1
    assert devices[0].instance == INSTANCE


# --- Object list ---


async def test_get_object_list(client: Client):
    obj_list = await client.get_object_list(SERVER, INSTANCE)
    assert len(obj_list) >= 6  # device + ai + ao + av + bi + bv


# --- WritePropertyMultiple ---


async def test_write_multiple(client: Client):
    await client.write_multiple(
        SERVER,
        {"av,1": {"present-value": 30.0}},
    )
    value = await client.read(SERVER, "av,1", "present-value")
    assert value == pytest.approx(30.0)
    # Restore
    await client.write(SERVER, "av,1", "present-value", 70.0)
