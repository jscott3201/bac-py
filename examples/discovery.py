"""Device and object discovery examples for bac-py.

Demonstrates Who-Is/I-Am device discovery and Who-Has/I-Have
object discovery on a BACnet network.
"""

import asyncio

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient
from bac_py.network.address import LOCAL_BROADCAST, BACnetAddress
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


def make_address(ip: str, port: int = 0xBAC0) -> BACnetAddress:
    """Build a BACnetAddress from an IP string and port."""
    parts = [int(p) for p in ip.split(".")]
    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)


async def discover_all_devices() -> None:
    """Discover all BACnet devices on the network.

    Sends a global Who-Is broadcast and collects I-Am responses
    for 5 seconds.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        print("Sending Who-Is broadcast (waiting 5 seconds)...")
        devices = await client.who_is(timeout=5.0)

        if not devices:
            print("No devices found on the network.")
            return

        print(f"Found {len(devices)} device(s):\n")
        for iam in devices:
            print(f"  Device Instance: {iam.object_identifier.instance_number}")
            print(f"  Max APDU Length: {iam.max_apdu_length}")
            print(f"  Segmentation:    {iam.segmentation_supported}")
            print(f"  Vendor ID:       {iam.vendor_id}")
            print()


async def discover_device_range() -> None:
    """Discover devices within a specific instance number range.

    Only devices with instance numbers between low_limit and
    high_limit (inclusive) will respond.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        # Search for devices with instance numbers 1 through 100
        print("Searching for devices with instances 1-100...")
        devices = await client.who_is(
            low_limit=1,
            high_limit=100,
            timeout=3.0,
        )

        print(f"Found {len(devices)} device(s) in range 1-100")
        for iam in devices:
            print(f"  Device {iam.object_identifier.instance_number}")


async def discover_local_network() -> None:
    """Discover devices on the local network only.

    Uses LOCAL_BROADCAST instead of GLOBAL_BROADCAST to limit
    discovery to directly-connected devices (no router traversal).
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        print("Discovering devices on local network only...")
        devices = await client.who_is(
            destination=LOCAL_BROADCAST,
            timeout=3.0,
        )

        print(f"Found {len(devices)} local device(s)")
        for iam in devices:
            print(f"  Device {iam.object_identifier.instance_number}")


async def discover_specific_device() -> None:
    """Check if a specific device exists on the network.

    Uses matching low_limit and high_limit to target a single
    device instance number.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        target_instance = 42
        print(f"Looking for device instance {target_instance}...")

        devices = await client.who_is(
            low_limit=target_instance,
            high_limit=target_instance,
            timeout=3.0,
        )

        if devices:
            iam = devices[0]
            print(f"Device {target_instance} found!")
            print(f"  Max APDU: {iam.max_apdu_length}")
            print(f"  Vendor ID: {iam.vendor_id}")
        else:
            print(f"Device {target_instance} not found on the network.")


async def discover_object_by_id() -> None:
    """Find which device owns a specific object using Who-Has.

    Sends a Who-Has request searching for a specific object
    identifier and collects I-Have responses.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        target_obj = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        print(f"Searching for {target_obj}...")

        results = await client.who_has(
            object_identifier=target_obj,
            timeout=3.0,
        )

        if not results:
            print("No device claims to have this object.")
            return

        for ihave in results:
            print(f"  Device {ihave.device_identifier.instance_number} has:")
            print(f"    Object: {ihave.object_identifier}")
            print(f"    Name:   {ihave.object_name}")


async def discover_object_by_name() -> None:
    """Find an object by its name using Who-Has.

    Searches across all devices for an object with a matching name.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        search_name = "Outside Air Temperature"
        print(f"Searching for object named '{search_name}'...")

        results = await client.who_has(
            object_name=search_name,
            timeout=3.0,
        )

        if not results:
            print(f"No object named '{search_name}' found on the network.")
            return

        for ihave in results:
            print(f"  Device {ihave.device_identifier.instance_number}:")
            print(f"    Object:  {ihave.object_identifier}")
            print(f"    Name:    {ihave.object_name}")


async def discover_and_read() -> None:
    """Discover devices, then read properties from each one.

    A common workflow: first discover what's on the network,
    then query each device for details.
    """
    config = DeviceConfig(instance_number=999, interface="0.0.0.0")

    async with BACnetApplication(config) as app:
        client = BACnetClient(app)

        # Step 1: Discover devices
        print("Step 1: Discovering devices...")
        devices = await client.who_is(timeout=3.0)
        print(f"Found {len(devices)} device(s)\n")

        # Step 2: Read the object name from each discovered device
        for iam in devices:
            instance = iam.object_identifier.instance_number
            device_id = ObjectIdentifier(ObjectType.DEVICE, instance)

            # We need the device's address to send a unicast read.
            # In a real scenario, you'd track the source address from
            # the I-Am response. Here we demonstrate the pattern.
            print(f"Device {instance}:")
            print(f"  Max APDU:  {iam.max_apdu_length}")
            print(f"  Vendor ID: {iam.vendor_id}")
            print()


if __name__ == "__main__":
    print("=== Discover All Devices ===")
    asyncio.run(discover_all_devices())

    print("\n=== Discover Device Range ===")
    asyncio.run(discover_device_range())

    print("\n=== Discover Local Network ===")
    asyncio.run(discover_local_network())

    print("\n=== Discover Specific Device ===")
    asyncio.run(discover_specific_device())

    print("\n=== Discover Object by ID ===")
    asyncio.run(discover_object_by_id())

    print("\n=== Discover Object by Name ===")
    asyncio.run(discover_object_by_name())

    print("\n=== Discover and Read ===")
    asyncio.run(discover_and_read())
