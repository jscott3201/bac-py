"""Property-level COV (Change of Value) subscriptions.

Subscribes to COV on a specific property of an object with a custom
COV increment, rather than the default COV properties for the object type.
Contrast with ``monitor_cov.py`` which uses object-level subscriptions.

Usage::

    python examples/cov_property.py
"""

import asyncio

from bac_py import Client, decode_cov_values

DEVICE_ADDRESS = "192.168.1.100"
PROCESS_ID = 2  # Subscriber-managed identifier (unique per subscription)


async def main() -> None:
    """Subscribe to property-level COV and print notifications."""
    async with Client(instance_number=999) as client:

        def on_notification(notification, source):
            values = decode_cov_values(notification)
            print(f"Property COV from {source}:")
            for name, value in values.items():
                print(f"  {name}: {value}")

        # Register the callback for our process ID
        client.app.register_cov_callback(PROCESS_ID, on_notification)

        # Subscribe to present-value on analog-input,1 with a COV increment
        # of 0.5 (only notify when the value changes by >= 0.5)
        await client.subscribe_cov_property(
            DEVICE_ADDRESS,
            "ai,1",
            property_identifier="pv",
            process_id=PROCESS_ID,
            confirmed=True,
            lifetime=3600,
            cov_increment=0.5,
        )
        print(f"Subscribed to pv on {DEVICE_ADDRESS} analog-input,1 (increment=0.5)")
        print("Listening for 60 seconds (Ctrl+C to stop)...\n")

        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            # Unsubscribe by sending a cancel (lifetime=0, no issue_confirmed_notifications)
            await client.unsubscribe_cov_ex(DEVICE_ADDRESS, "ai,1", process_id=PROCESS_ID)
            client.app.unregister_cov_callback(PROCESS_ID)
            print("\nUnsubscribed.")


if __name__ == "__main__":
    asyncio.run(main())
