"""Extended device discovery with profile metadata.

Discovers BACnet devices on the network and enriches results with
Annex X profile metadata (Profile_Name, Profile_Location, Tags).
This provides richer device classification than standard Who-Is discovery.

Usage::

    python examples/extended_discovery.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Discover devices with extended profile information."""
    async with Client(instance_number=999) as client:
        # Standard discovery (Who-Is + I-Am)
        print("Standard discovery:")
        devices = await client.discover(timeout=3.0)
        for dev in devices:
            print(f"  Device {dev.instance} at {dev.address_str}")
            print(f"    vendor_id={dev.vendor_id}")

        # Extended discovery (adds Profile_Name, Profile_Location, Tags)
        print("\nExtended discovery:")
        ext_devices = await client.discover_extended(timeout=3.0, enrich_timeout=5.0)
        for dev in ext_devices:
            print(f"  Device {dev.instance} at {dev.address_str}")
            print(f"    vendor_id={dev.vendor_id}")
            if dev.profile_name:
                print(f"    profile={dev.profile_name}")
            if dev.profile_location:
                print(f"    location={dev.profile_location}")
            if dev.tags:
                print(f"    tags={dev.tags}")

        # Discover specific device range
        print("\nTargeted discovery (instances 100-200):")
        targeted = await client.discover_extended(
            low_limit=100,
            high_limit=200,
            timeout=3.0,
        )
        for dev in targeted:
            print(f"  Device {dev.instance}: {dev.profile_name or 'no profile'}")


if __name__ == "__main__":
    asyncio.run(main())
