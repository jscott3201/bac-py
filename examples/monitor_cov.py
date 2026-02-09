"""Monitor BACnet COV (Change of Value) notifications.

Subscribes to COV on an object, prints notifications for 60 seconds,
then unsubscribes.  COV subscriptions use the protocol-level API which
requires explicit address and object-identifier types.

Usage::

    python examples/monitor_cov.py
"""

import asyncio

from bac_py import Client
from bac_py.encoding.primitives import decode_all_application_values
from bac_py.network.address import parse_address
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

DEVICE_ADDRESS = "192.168.1.100"
PROCESS_ID = 1  # Subscriber-managed identifier


async def main() -> None:
    """Subscribe to COV and print notifications."""
    address = parse_address(DEVICE_ADDRESS)
    obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    async with Client(instance_number=999) as client:
        # Register a callback for incoming COV notifications.
        # The callback receives a COVNotificationRequest and the source address.
        def on_notification(notification, source):
            print(f"COV from {source}:")
            print(f"  Object: {notification.monitored_object_identifier}")
            print(f"  Time remaining: {notification.time_remaining}s")
            for pv in notification.list_of_values:
                values = decode_all_application_values(pv.value)
                prop = PropertyIdentifier(pv.property_identifier)
                print(f"  {prop.name}: {values}")

        client.app.register_cov_callback(PROCESS_ID, on_notification)

        # Subscribe to COV notifications with a 1-hour lifetime
        await client.subscribe_cov(address, obj_id, PROCESS_ID, confirmed=True, lifetime=3600)
        print(f"Subscribed to COV on {DEVICE_ADDRESS} analog-input,1")
        print("Listening for 60 seconds (Ctrl+C to stop)...\n")

        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        finally:
            await client.unsubscribe_cov(address, obj_id, PROCESS_ID)
            client.app.unregister_cov_callback(PROCESS_ID)
            print("\nUnsubscribed.")


if __name__ == "__main__":
    asyncio.run(main())
