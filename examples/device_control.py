"""Device control: communication control, reinitialization, and time sync.

Demonstrates device management operations including enabling/disabling
communications, warm/cold restarting a device, and synchronizing its clock.

Usage::

    python examples/device_control.py
"""

import asyncio
import datetime

from bac_py import Client
from bac_py.types.primitives import BACnetDate, BACnetTime

DEVICE_ADDRESS = "192.168.1.100"


async def main() -> None:
    """Control a BACnet device."""
    async with Client(instance_number=999) as client:
        # Disable communications for 5 minutes (accepts string or enum)
        await client.device_communication_control(
            DEVICE_ADDRESS,
            enable_disable="disable",
            time_duration=5,
            password="admin",
        )
        print("Communications disabled for 5 minutes.")

        # Re-enable communications
        await client.device_communication_control(
            DEVICE_ADDRESS,
            enable_disable="enable",
            password="admin",
        )
        print("Communications re-enabled.")

        # Warm-restart the device (accepts string or enum)
        await client.reinitialize_device(
            DEVICE_ADDRESS,
            reinitialized_state="warmstart",
            password="admin",
        )
        print("Warm restart initiated.")

        # Synchronize the device clock with local time
        now = datetime.datetime.now()
        date = BACnetDate(now.year, now.month, now.day, now.weekday() + 1)
        time = BACnetTime(now.hour, now.minute, now.second, 0)
        client.time_synchronization(DEVICE_ADDRESS, date, time)
        print(f"Time synchronized to {now:%Y-%m-%d %H:%M:%S}")

        # Synchronize using UTC time
        utc_now = datetime.datetime.now(tz=datetime.UTC)
        utc_date = BACnetDate(utc_now.year, utc_now.month, utc_now.day, utc_now.weekday() + 1)
        utc_time = BACnetTime(utc_now.hour, utc_now.minute, utc_now.second, 0)
        client.utc_time_synchronization(DEVICE_ADDRESS, utc_date, utc_time)
        print(f"UTC time synchronized to {utc_now:%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    asyncio.run(main())
