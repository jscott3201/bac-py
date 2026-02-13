"""Alarm management: summary, enrollment, event info, and acknowledgment.

Demonstrates querying active alarms from a device, listing enrollment
summaries, checking event state information, and acknowledging alarm
conditions.

Usage::

    python examples/alarm_management.py
"""

import asyncio
import datetime

from bac_py import Client
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import AcknowledgmentFilter, EventState
from bac_py.types.primitives import BACnetTime


async def main() -> None:
    """Query alarms, enrollment summaries, and acknowledge one."""
    async with Client(instance_number=999) as client:
        addr = "192.168.1.100"

        # Get a summary of all active alarms on the device
        alarm_summary = await client.get_alarm_summary(addr)
        print("Active alarms:")
        for entry in alarm_summary.list_of_alarm_summaries:
            print(f"  {entry.object_identifier}: state={entry.alarm_state}")

        # Get enrollment summaries (all event-generating objects)
        enrollment = await client.get_enrollment_summary(
            addr,
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        print(f"\nEnrollment summaries ({len(enrollment.list_of_enrollment_summaries)} entries):")
        for entry in enrollment.list_of_enrollment_summaries:
            print(
                f"  {entry.object_identifier}: type={entry.event_type}, "
                f"state={entry.event_state}, priority={entry.priority}, "
                f"class={entry.notification_class}"
            )

        # Filter to only un-acknowledged enrollments
        unacked = await client.get_enrollment_summary(
            addr,
            acknowledgment_filter=AcknowledgmentFilter.NOT_ACKED,
        )
        print(f"\nUn-acknowledged enrollments: {len(unacked.list_of_enrollment_summaries)}")

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
