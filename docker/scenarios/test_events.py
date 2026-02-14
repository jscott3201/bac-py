"""Scenario 8: Alarm and event operations over real UDP."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from bac_py import Client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from bac_py.services.alarm_summary import (
    GetAlarmSummaryACK,
    GetEnrollmentSummaryACK,
    GetEventInformationACK,
)
from bac_py.types.enums import AcknowledgmentFilter

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.104")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "602"))

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client() -> AsyncGenerator[Client]:
    async with Client(instance_number=952, port=0) as c:
        yield c


# --- GetAlarmSummary ---


async def test_get_alarm_summary(client: Client) -> None:
    """GetAlarmSummary returns a valid ACK with an alarm list."""
    result = await client.get_alarm_summary(SERVER)
    assert isinstance(result, GetAlarmSummaryACK)
    # The server just started; no alarm condition may be active yet.
    # Verify the list attribute exists and is a list.
    assert isinstance(result.list_of_alarm_summaries, list)


# --- GetEventInformation ---


async def test_get_event_information(client: Client) -> None:
    """GetEventInformation returns a valid ACK with event summaries."""
    result = await client.get_event_information(SERVER)
    assert isinstance(result, GetEventInformationACK)
    assert isinstance(result.list_of_event_summaries, list)
    assert isinstance(result.more_events, bool)


# --- GetEnrollmentSummary ---


async def test_get_enrollment_summary(client: Client) -> None:
    """GetEnrollmentSummary with ALL filter returns a valid ACK."""
    result = await client.get_enrollment_summary(SERVER, AcknowledgmentFilter.ALL)
    assert isinstance(result, GetEnrollmentSummaryACK)
    assert isinstance(result.list_of_enrollment_summaries, list)


# --- ReadPropertyMultiple on extended objects ---


async def test_read_extended_server_objects(client: Client) -> None:
    """Object list from extended server has at least 25 objects."""
    obj_list = await client.get_object_list(SERVER, INSTANCE)
    # device + ai,1 + ao,1 + av,1 + bi,1 + bv,1 (6)
    # + 20 sensors (ai,2..ai,21)
    # + notification-class,1 + event-enrollment,1
    # + audit-reporter,1 + audit-log,1
    assert len(obj_list) >= 25


async def test_read_notification_class(client: Client) -> None:
    """NotificationClass object-name is 'Alarms'."""
    name = await client.read(SERVER, "notification-class,1", "object-name")
    assert name == "Alarms"


async def test_read_event_enrollment(client: Client) -> None:
    """EventEnrollment object-name is 'TempHighAlarm'."""
    name = await client.read(SERVER, "event-enrollment,1", "object-name")
    assert name == "TempHighAlarm"


# --- Read multiple sensor objects ---


async def test_read_multiple_sensors(client: Client) -> None:
    """ReadPropertyMultiple returns data for several sensor objects."""
    result = await client.read_multiple(
        SERVER,
        {
            "ai,2": ["present-value", "object-name"],
            "ai,5": ["present-value", "object-name"],
            "ai,10": ["present-value", "object-name"],
        },
    )
    # Verify we got results for all three objects (keys may use full or short form)
    assert len(result) == 3
    for _key, props in result.items():
        # Each object should have at least present-value and object-name
        assert len(props) >= 2


# --- Who-Is discovers extended server ---


@pytest.mark.skip(
    reason="Who-Is/I-Am requires broadcast; Docker bridge networks don't route broadcasts"
)
async def test_who_is_discovers_extended_server(client: Client) -> None:
    """Who-Is with instance range finds the extended server (device 602)."""
    devices = await client.discover(
        low_limit=INSTANCE,
        high_limit=INSTANCE,
        destination=SERVER,
        timeout=5.0,
        expected_count=1,
    )
    assert len(devices) >= 1
    instances = [d.instance for d in devices]
    assert INSTANCE in instances
