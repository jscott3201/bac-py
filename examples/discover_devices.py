"""Discover BACnet devices on the network.

Sends a Who-Is broadcast and collects I-Am responses into
:class:`~bac_py.DiscoveredDevice` objects.

Usage::

    python examples/discover_devices.py
"""

import asyncio
import logging

from bac_py import Client

# Uncomment for detailed protocol traces; use DEBUG for request-level detail
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


async def main() -> None:
    """Discover and list all BACnet devices."""
    async with Client(instance_number=999) as client:
        # Discover all devices (3-second listen window)
        devices = await client.discover(timeout=3.0)

        print(f"Found {len(devices)} device(s):\n")
        for dev in devices:
            print(f"  Instance: {dev.instance}")
            print(f"  Address:  {dev.address_str}")
            print(f"  Vendor:   {dev.vendor_id}")
            print(f"  Max APDU: {dev.max_apdu_length}")
            print(f"  Segmentation: {dev.segmentation_supported}")
            print()

        # Discover devices in a specific instance range
        subset = await client.discover(low_limit=100, high_limit=200, timeout=3.0)
        print(f"Found {len(subset)} device(s) in range 100-200.")


if __name__ == "__main__":
    asyncio.run(main())
