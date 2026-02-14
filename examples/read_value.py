"""Read a single BACnet property.

Usage::

    python examples/read_value.py
"""

import asyncio
import logging

from bac_py import Client

# Uncomment for detailed protocol traces; use DEBUG for request-level detail
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


async def main() -> None:
    """Read properties from an analog input."""
    async with Client(instance_number=999) as client:
        # Read present-value from analog-input 1 using short aliases
        value = await client.read("192.168.1.100", "ai,1", "pv")
        print(f"Present value: {value}")

        # Full property/object names also work
        name = await client.read("192.168.1.100", "analog-input,1", "object-name")
        print(f"Object name: {name}")

        # Read a specific array element (e.g. priority-array slot 8)
        priority = await client.read("192.168.1.100", "av,1", "priority-array", array_index=8)
        print(f"Priority 8: {priority}")


if __name__ == "__main__":
    asyncio.run(main())
