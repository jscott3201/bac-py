"""BACnet/IPv6 (Annex U) client example.

Demonstrates using bac-py over BACnet/IPv6 with multicast discovery and
property reads. IPv6 transport uses 3-byte VMACs and the ``ff02::bac0``
multicast group by default.

For the server counterpart, see ``ipv6_server.py``.

Usage::

    python examples/ipv6_client.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Run an IPv6 client: discover devices and read properties."""
    # Create a client using BACnet/IPv6 transport.
    # The default multicast group is ff02::bac0 (BACnet well-known).
    async with Client(
        instance_number=999,
        ipv6=True,
        # interface="::" binds to all IPv6 interfaces (default when ipv6=True)
        # multicast_address="ff02::bac0" is the default
        # vmac is auto-generated if not provided
    ) as client:
        print("BACnet/IPv6 client started")

        # Discover devices via IPv6 multicast Who-Is
        devices = await client.discover(timeout=5.0)
        print(f"Discovered {len(devices)} device(s):")
        for dev in devices:
            print(f"  Device {dev.instance} at {dev.address_str}")

        # Read properties from the first discovered device
        if devices:
            target = devices[0].address_str
            name = await client.read(target, "device," + str(devices[0].instance), "object-name")
            print(f"\nDevice name: {name}")

            vendor = await client.read(target, "device," + str(devices[0].instance), "vendor-name")
            print(f"Vendor: {vendor}")


if __name__ == "__main__":
    asyncio.run(main())
