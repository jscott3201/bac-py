"""Client operations examples for bac-py.

Demonstrates advanced client operations including COV subscriptions,
device management, file access, object management, and time
synchronization.
"""

import asyncio

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.network.address import GLOBAL_BROADCAST, BACnetAddress
from bac_py.services.errors import BACnetError, BACnetTimeoutError
from bac_py.services.file_access import StreamReadAccess, StreamWriteAccess
from bac_py.services.read_range import RangeByPosition
from bac_py.types.enums import (
    EnableDisable,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier


def make_address(ip: str, port: int = 0xBAC0) -> BACnetAddress:
    """Build a BACnetAddress from an IP string and port."""
    parts = [int(p) for p in ip.split(".")]
    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)


# ---------------------------------------------------------------------------
# COV (Change of Value) subscriptions
# ---------------------------------------------------------------------------


async def subscribe_to_cov() -> None:
    """Subscribe to Change-of-Value notifications from a remote object.

    COV subscriptions allow the client to be notified whenever a
    monitored property changes, rather than polling. The remote
    device sends notifications (confirmed or unconfirmed) when the
    value changes beyond the object's COV increment.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        process_id = 42  # Unique ID to match callbacks to subscriptions

        # Register a callback for COV notifications
        def on_value_change(notification, source):
            print(f"COV notification from {source}:")
            print(f"  Object: {notification.monitored_object_identifier}")
            print(f"  Process ID: {notification.subscriber_process_identifier}")

        app.register_cov_callback(process_id, on_value_change)

        try:
            # Subscribe with confirmed notifications, 5-minute lifetime
            await client.subscribe_cov(
                target,
                obj_id,
                process_id=process_id,
                confirmed=True,
                lifetime=300,  # seconds
            )
            print(f"Subscribed to COV for {obj_id} (lifetime=300s)")

            # Wait for notifications
            print("Listening for value changes (30 seconds)...")
            await asyncio.sleep(30)

            # Unsubscribe when done
            await client.unsubscribe_cov(target, obj_id, process_id=process_id)
            print("Unsubscribed from COV")

        except BACnetError as e:
            print(f"COV subscription failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("COV subscription timed out")
        finally:
            app.unregister_cov_callback(process_id)


async def subscribe_unconfirmed_cov() -> None:
    """Subscribe with unconfirmed COV notifications.

    Unconfirmed notifications are fire-and-forget - the remote device
    does not wait for an acknowledgment. This reduces network traffic
    but notifications may be lost.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.BINARY_INPUT, 1)
        process_id = 100

        def on_change(notification, source):
            print(f"Unconfirmed COV from {source}: {notification}")

        app.register_cov_callback(process_id, on_change)

        try:
            await client.subscribe_cov(
                target,
                obj_id,
                process_id=process_id,
                confirmed=False,  # Unconfirmed notifications
                lifetime=600,
            )
            print("Subscribed with unconfirmed notifications")

            await asyncio.sleep(30)

            await client.unsubscribe_cov(target, obj_id, process_id=process_id)

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        finally:
            app.unregister_cov_callback(process_id)


# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------


async def device_communication_control() -> None:
    """Control a remote device's communication state.

    Can enable, disable, or disable-initiation on a remote device.
    An optional duration limits how long the state persists.
    An optional password may be required by the target device.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        try:
            # Disable communication for 5 minutes
            await client.device_communication_control(
                target,
                enable_disable=EnableDisable.DISABLE,
                time_duration=5,  # minutes
                password=None,  # or a string like "secret"
            )
            print("Device communication disabled for 5 minutes")

            # Re-enable communication
            await client.device_communication_control(
                target,
                enable_disable=EnableDisable.ENABLE,
            )
            print("Device communication re-enabled")

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out")


async def reinitialize_device() -> None:
    """Request a remote device to reinitialize (reboot).

    Supports cold start (full reboot) and warm start (software restart).
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        try:
            await client.reinitialize_device(
                target,
                reinitialized_state=ReinitializedState.WARMSTART,
                password=None,
            )
            print("Warm start requested")

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Request timed out")


async def time_sync() -> None:
    """Synchronize time on remote devices.

    Time synchronization is an unconfirmed service (fire-and-forget).
    Can be sent to a specific device or broadcast to all devices.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        # Current date and time
        date = BACnetDate(year=2025, month=2, day=8, day_of_week=6)
        time = BACnetTime(hour=14, minute=30, second=0, hundredth=0)

        # Broadcast local time sync to all devices
        client.time_synchronization(
            destination=GLOBAL_BROADCAST,
            date=date,
            time=time,
        )
        print("Local time synchronization broadcast sent")

        # Send UTC time sync to a specific device
        target = make_address("192.168.1.100")
        utc_date = BACnetDate(year=2025, month=2, day=8, day_of_week=6)
        utc_time = BACnetTime(hour=19, minute=30, second=0, hundredth=0)

        client.utc_time_synchronization(
            destination=target,
            date=utc_date,
            time=utc_time,
        )
        print("UTC time synchronization sent to target device")


# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------


async def read_file_stream() -> None:
    """Read a file from a remote device using stream access.

    Stream access reads raw bytes from a file object starting at
    a byte offset for a specified number of bytes.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        file_id = ObjectIdentifier(ObjectType.FILE, 1)

        try:
            ack = await client.atomic_read_file(
                target,
                file_identifier=file_id,
                access_method=StreamReadAccess(
                    file_start_position=0,
                    requested_octet_count=1024,
                ),
            )
            print(f"End of file: {ack.end_of_file}")
            print(f"Data read: {ack.access_method}")

        except BACnetError as e:
            print(f"File read error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("File read timed out")


async def write_file_stream() -> None:
    """Write data to a file on a remote device using stream access."""
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        file_id = ObjectIdentifier(ObjectType.FILE, 1)
        data_to_write = b"Hello, BACnet file system!"

        try:
            ack = await client.atomic_write_file(
                target,
                file_identifier=file_id,
                access_method=StreamWriteAccess(
                    file_start_position=0,
                    file_data=data_to_write,
                ),
            )
            print(f"Write started at position: {ack.file_start}")

        except BACnetError as e:
            print(f"File write error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("File write timed out")


# ---------------------------------------------------------------------------
# Object management
# ---------------------------------------------------------------------------


async def create_remote_object() -> None:
    """Create a new object on a remote device.

    Can auto-assign an instance number (by specifying object_type)
    or use an explicit object identifier.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        try:
            # Auto-assign instance number
            new_obj_id = await client.create_object(
                target,
                object_type=ObjectType.ANALOG_VALUE,
            )
            print(f"Created object: {new_obj_id}")

            # Or specify an explicit identifier
            explicit_id = await client.create_object(
                target,
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 100),
            )
            print(f"Created explicit object: {explicit_id}")

        except BACnetError as e:
            print(f"Create failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Create timed out")


async def delete_remote_object() -> None:
    """Delete an object on a remote device."""
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 100)

        try:
            await client.delete_object(target, obj_id)
            print(f"Deleted object: {obj_id}")

        except BACnetError as e:
            print(f"Delete failed: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Delete timed out")


# ---------------------------------------------------------------------------
# ReadRange
# ---------------------------------------------------------------------------


async def read_range_example() -> None:
    """Read a range of items from a list property.

    Useful for reading portions of large lists like trend log
    buffers or object lists without transferring the entire list.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        # Read items 1-10 from the device's object list
        device_id = ObjectIdentifier(ObjectType.DEVICE, 1)

        try:
            ack = await client.read_range(
                target,
                object_identifier=device_id,
                property_identifier=PropertyIdentifier.OBJECT_LIST,
                range_qualifier=RangeByPosition(
                    reference_index=1,
                    count=10,
                ),
            )
            print(
                f"Result flags: first={ack.result_flags.first_item}, "
                f"last={ack.result_flags.last_item}"
            )
            print(f"Item count: {ack.item_count}")
            print(f"Item data (raw): {ack.item_data.hex()}")

        except BACnetError as e:
            print(f"ReadRange error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("ReadRange timed out")


# ---------------------------------------------------------------------------
# Private transfer
# ---------------------------------------------------------------------------


async def private_transfer_example() -> None:
    """Send a vendor-specific private transfer request.

    Private transfers allow vendor-specific extensions to BACnet.
    Both confirmed (with response) and unconfirmed (fire-and-forget)
    modes are available.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)
        target = make_address("192.168.1.100")

        try:
            # Confirmed private transfer (waits for response)
            ack = await client.confirmed_private_transfer(
                target,
                vendor_id=555,
                service_number=1,
                service_parameters=b"\x01\x02\x03",
            )
            print(
                f"Private transfer response: vendor={ack.vendor_id}, service={ack.service_number}"
            )

        except BACnetError as e:
            print(f"Error: {e.error_class.name} / {e.error_code.name}")
        except BACnetTimeoutError:
            print("Private transfer timed out")

        # Unconfirmed private transfer (fire-and-forget)
        client.unconfirmed_private_transfer(
            destination=target,
            vendor_id=555,
            service_number=2,
            service_parameters=b"\x04\x05\x06",
        )
        print("Unconfirmed private transfer sent")


if __name__ == "__main__":
    print("=== COV Subscription ===")
    asyncio.run(subscribe_to_cov())

    print("\n=== Device Communication Control ===")
    asyncio.run(device_communication_control())

    print("\n=== Time Synchronization ===")
    asyncio.run(time_sync())

    print("\n=== Read File (Stream) ===")
    asyncio.run(read_file_stream())

    print("\n=== Create Remote Object ===")
    asyncio.run(create_remote_object())

    print("\n=== ReadRange ===")
    asyncio.run(read_range_example())

    print("\n=== Private Transfer ===")
    asyncio.run(private_transfer_example())
