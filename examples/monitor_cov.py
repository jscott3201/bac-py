"""Monitor BACnet COV (Change of Value) notifications.

Subscribes to COV on an object, prints notifications for 60 seconds,
then unsubscribes.  Uses the convenience API which accepts string
addresses and object identifiers.

Usage::

    python examples/monitor_cov.py
"""

import asyncio
import logging

from bac_py import Client, decode_cov_values

# Uncomment for detailed protocol traces; use DEBUG for request-level detail
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

DEVICE_ADDRESS = "192.168.1.100"
PROCESS_ID = 1  # Subscriber-managed identifier


async def main() -> None:
    """Subscribe to COV and print notifications."""
    async with Client(instance_number=999) as client:

        def on_notification(notification, source):
            values = decode_cov_values(notification)
            print(f"COV from {source}:")
            for name, value in values.items():
                print(f"  {name}: {value}")

        await client.subscribe_cov_ex(
            DEVICE_ADDRESS,
            "ai,1",
            process_id=PROCESS_ID,
            callback=on_notification,
            confirmed=True,
            lifetime=3600,
        )
        print(f"Subscribed to COV on {DEVICE_ADDRESS} analog-input,1")
        print("Listening for 60 seconds (Ctrl+C to stop)...\n")

        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            await client.unsubscribe_cov_ex(DEVICE_ADDRESS, "ai,1", process_id=PROCESS_ID)
            print("\nUnsubscribed.")


if __name__ == "__main__":
    asyncio.run(main())
