"""Discover BACnet devices through a BBMD as a foreign device.

Registers with a remote BBMD, discovers devices on the BBMD's network,
and reads the BDT and FDT tables.

Usage::

    python examples/foreign_device.py
"""

import asyncio

from bac_py import Client

BBMD_ADDRESS = "192.168.1.1"


async def main() -> None:
    """Register as a foreign device and discover devices."""
    async with Client(
        instance_number=999,
        bbmd_address=BBMD_ADDRESS,
        bbmd_ttl=60,
    ) as client:
        print(f"Registered as foreign device with BBMD {BBMD_ADDRESS}")
        print(f"Status: {client.foreign_device_status}\n")

        # Discover devices on the BBMD's network
        devices = await client.discover(timeout=5.0)
        print(f"Discovered {len(devices)} device(s):")
        for dev in devices:
            print(f"  Device {dev.instance} at {dev.address_str}")

        # Read BDT from the BBMD
        bdt = await client.read_bdt(BBMD_ADDRESS)
        print(f"\nBDT has {len(bdt)} entries:")
        for entry in bdt:
            print(f"  {entry.address} mask={entry.mask}")

        # Read FDT from the BBMD
        fdt = await client.read_fdt(BBMD_ADDRESS)
        print(f"\nFDT has {len(fdt)} entries:")
        for fdt_entry in fdt:
            print(f"  {fdt_entry.address} ttl={fdt_entry.ttl}s remaining={fdt_entry.remaining}s")


if __name__ == "__main__":
    asyncio.run(main())
