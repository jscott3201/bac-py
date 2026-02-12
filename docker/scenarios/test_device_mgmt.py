"""Scenario 6: Device management operations over real UDP."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from bac_py import Client
from bac_py.network.address import parse_address
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.100")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "600"))

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with Client(instance_number=950, port=0) as c:
        yield c


# --- Device Communication Control ---


async def test_dcc_disable_initiation(client: Client):
    """Send DCC disable-initiation and then re-enable."""
    await client.device_communication_control(SERVER, "disable-initiation")
    # Re-enable to leave the server in a clean state
    await client.device_communication_control(SERVER, "enable")


async def test_dcc_enable(client: Client):
    """Send DCC enable succeeds without error."""
    await client.device_communication_control(SERVER, "enable")


# --- CreateObject / DeleteObject ---


async def test_create_and_delete_object(client: Client):
    """Create an analog-value, verify it exists, then delete it."""
    created_oid = await client.create_object(SERVER, object_identifier="av,99")
    assert isinstance(created_oid, ObjectIdentifier)
    assert created_oid.object_type == ObjectType.ANALOG_VALUE
    assert created_oid.instance_number == 99

    # Read back to verify it exists (object-identifier is always present)
    obj_list = await client.get_object_list(SERVER, INSTANCE)
    assert any(
        o.object_type == ObjectType.ANALOG_VALUE and o.instance_number == 99 for o in obj_list
    )

    # Delete the object
    await client.delete_object(SERVER, "av,99")

    # Verify it is gone
    obj_list = await client.get_object_list(SERVER, INSTANCE)
    assert not any(
        o.object_type == ObjectType.ANALOG_VALUE and o.instance_number == 99 for o in obj_list
    )


async def test_create_object_by_type(client: Client):
    """Create object by type string, verify result, then delete."""
    created_oid = await client.create_object(SERVER, object_type="av")
    assert isinstance(created_oid, ObjectIdentifier)
    assert created_oid.object_type == ObjectType.ANALOG_VALUE

    # Clean up -- delete the dynamically assigned object
    await client.delete_object(SERVER, created_oid)


# --- TimeSynchronization ---


async def test_time_synchronization(client: Client):
    """Send TimeSynchronization (unconfirmed) -- no exception expected."""
    now = datetime.now()
    date = BACnetDate(
        year=now.year,
        month=now.month,
        day=now.day,
        day_of_week=now.isoweekday(),
    )
    time = BACnetTime(
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        hundredth=now.microsecond // 10_000,
    )
    dest = parse_address(SERVER)
    client.time_synchronization(dest, date, time)


async def test_utc_time_synchronization(client: Client):
    """Send UTCTimeSynchronization (unconfirmed) -- no exception expected."""
    now = datetime.now(tz=UTC)
    date = BACnetDate(
        year=now.year,
        month=now.month,
        day=now.day,
        day_of_week=now.isoweekday(),
    )
    time = BACnetTime(
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        hundredth=now.microsecond // 10_000,
    )
    dest = parse_address(SERVER)
    client.utc_time_synchronization(dest, date, time)


# --- TextMessage ---


async def test_send_confirmed_text_message(client: Client):
    """Send a confirmed text message to the server."""
    await client.send_text_message(
        SERVER,
        "Integration test: confirmed message",
        confirmed=True,
    )


async def test_send_unconfirmed_text_message(client: Client):
    """Send an unconfirmed text message (fire-and-forget)."""
    await client.send_text_message(
        SERVER,
        "Integration test: unconfirmed message",
        confirmed=False,
    )


# --- Who-Has discovery ---


@pytest.mark.skip(
    reason="Who-Has/I-Have requires broadcast; Docker bridge networks don't route broadcasts"
)
async def test_who_has_by_name(client: Client):
    """Who-Has by object name returns I-Have with the matching object."""
    responses = await client.who_has(
        object_name="Temperature",
        destination=SERVER,
        timeout=5.0,
        expected_count=1,
    )
    assert len(responses) >= 1
    resp = responses[0]
    assert resp.object_identifier.object_type == ObjectType.ANALOG_INPUT
    assert resp.object_identifier.instance_number == 1


@pytest.mark.skip(
    reason="Who-Has/I-Have requires broadcast; Docker bridge networks don't route broadcasts"
)
async def test_who_has_by_identifier(client: Client):
    """Who-Has by ObjectIdentifier returns I-Have for analog-input,1."""
    oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
    responses = await client.who_has(
        object_identifier=oid,
        destination=SERVER,
        timeout=5.0,
        expected_count=1,
    )
    assert len(responses) >= 1
    resp = responses[0]
    assert resp.object_identifier == oid


# --- Object list ---


async def test_get_object_list_via_read(client: Client):
    """Read object-list property and verify at least 6 objects."""
    obj_list = await client.get_object_list(SERVER, INSTANCE)
    # Server has at minimum: device + ai + ao + av + bi + bv = 6
    assert len(obj_list) >= 6
