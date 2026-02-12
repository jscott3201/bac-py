"""Alarm management: summary, event info, and acknowledgment.

Demonstrates querying active alarms from a device, checking event
state information, and acknowledging alarm conditions.

Usage::

    python examples/alarm_management.py
"""

import asyncio
import datetime

from bac_py import Client
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import EventState
from bac_py.types.primitives import BACnetTime


async def main() -> None:
    """Query alarms and acknowledge one."""
    async with Client(instance_number=999) as client:
        addr = "192.168.1.100"

        # Get a summary of all active alarms on the device
        alarm_summary = await client.get_alarm_summary(addr)
        print("Active alarms:")
        for entry in alarm_summary.list_of_alarm_summaries:
            print(f"  {entry.object_identifier}: state={entry.alarm_state}")

        # Get detailed event information (supports pagination)
        event_info = await client.get_event_information(addr)
        print(f"\nEvent summaries ({len(event_info.list_of_event_summaries)} events):")
        for summary in event_info.list_of_event_summaries:
            print(f"  {summary.object_identifier}: {summary.event_state}")

        if event_info.more_events:
            # Fetch the next page
            last_oid = event_info.list_of_event_summaries[-1].object_identifier
            more = await client.get_event_information(
                addr, last_received_object_identifier=last_oid
            )
            print(f"  ... plus {len(more.list_of_event_summaries)} more")

        # Acknowledge an alarm (using string object identifier)
        now = datetime.datetime.now(tz=datetime.UTC)
        time_stamp = BACnetTimeStamp(
            choice=0,
            value=BACnetTime(now.hour, now.minute, now.second, 0),
        )
        await client.acknowledge_alarm(
            addr,
            acknowledging_process_identifier=1,
            event_object_identifier="ai,1",
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=time_stamp,
            acknowledgment_source="operator",
            time_of_acknowledgment=time_stamp,
        )
        print("\nAlarm acknowledged for ai,1")


if __name__ == "__main__":
    asyncio.run(main())
