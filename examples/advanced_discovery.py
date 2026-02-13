"""Advanced discovery: Who-Has, unconfigured devices, and hierarchy traversal.

Demonstrates discovery techniques beyond basic Who-Is, including finding
objects by name, discovering unconfigured devices via Who-Am-I (Clause 19.7),
and walking Structured View hierarchies.

Usage::

    python examples/advanced_discovery.py
"""

import asyncio

from bac_py import Client

DEVICE_ADDRESS = "192.168.1.100"


async def main() -> None:
    """Discover objects and devices using advanced techniques."""
    async with Client(instance_number=999) as client:
        # Find objects by name across the network
        results = await client.who_has(object_name="Room Temperature", timeout=3.0)
        print("Who-Has by name 'Room Temperature':")
        for response in results:
            print(
                f"  Device {response.device_identifier} has "
                f"{response.object_identifier} ({response.object_name})"
            )

        # Find objects by identifier
        results = await client.who_has(object_identifier="ai,1", timeout=3.0)
        print("\nWho-Has by identifier 'ai,1':")
        for response in results:
            print(
                f"  Device {response.device_identifier} has "
                f"{response.object_identifier} ({response.object_name})"
            )

        # Find objects within a specific device range
        results = await client.who_has(
            object_name="Zone Setpoint",
            low_limit=100,
            high_limit=200,
            timeout=3.0,
        )
        print(f"\nWho-Has in range 100-200: {len(results)} result(s)")

        # Discover unconfigured devices (Who-Am-I / You-Are, Clause 19.7)
        unconfigured = await client.discover_unconfigured(timeout=5.0)
        print(f"\nUnconfigured devices: {len(unconfigured)}")
        for dev in unconfigured:
            print(
                f"  vendor={dev.vendor_id}, model={dev.model_name}, "
                f"serial={dev.serial_number}, address={dev.address}"
            )

        # Traverse a Structured View hierarchy
        children = await client.traverse_hierarchy(DEVICE_ADDRESS, root="sv,1", max_depth=5)
        print(f"\nStructured View sv,1 hierarchy ({len(children)} objects):")
        for oid in children:
            print(f"  {oid}")


if __name__ == "__main__":
    asyncio.run(main())
