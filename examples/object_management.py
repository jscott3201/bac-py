"""Object management: create, list, and delete objects.

Demonstrates the object lifecycle on a remote BACnet device using
the high-level Client API with string-based identifiers.

Usage::

    python examples/object_management.py
"""

import asyncio

from bac_py import Client

DEVICE_ADDRESS = "192.168.1.100"


async def main() -> None:
    """Create, enumerate, and delete a BACnet object."""
    async with Client(instance_number=999) as client:
        # List all objects on the device
        objects = await client.get_object_list(DEVICE_ADDRESS, device_instance=1000)
        print(f"Device has {len(objects)} object(s):")
        for oid in objects:
            print(f"  {oid}")

        # Create an analog-value object (server assigns the instance)
        new_oid = await client.create_object(DEVICE_ADDRESS, object_type="av")
        print(f"\nCreated object: {new_oid}")

        # Create an object with a specific identifier
        specific_oid = await client.create_object(DEVICE_ADDRESS, object_identifier="av,100")
        print(f"Created object with specific ID: {specific_oid}")

        # Verify the new objects appear in the object list
        updated = await client.get_object_list(DEVICE_ADDRESS, device_instance=1000)
        print(f"\nDevice now has {len(updated)} object(s)")

        # Delete the objects
        await client.delete_object(DEVICE_ADDRESS, "av,100")
        print("Deleted av,100")

        await client.delete_object(DEVICE_ADDRESS, new_oid)
        print(f"Deleted {new_oid}")


if __name__ == "__main__":
    asyncio.run(main())
