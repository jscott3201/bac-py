"""Read multiple BACnet properties in a single request.

Uses ReadPropertyMultiple under the hood, which is more efficient
than issuing individual ReadProperty requests.

Usage::

    python examples/read_multiple.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    async with Client(instance_number=999) as client:
        results = await client.read_multiple(
            "192.168.1.100",
            {
                "ai,1": ["pv", "object-name", "units", "status-flags"],
                "ai,2": ["pv", "object-name"],
                "av,1": ["pv", "object-name"],
            },
        )

        for obj_id, props in results.items():
            print(f"{obj_id}:")
            for prop_name, value in props.items():
                print(f"  {prop_name}: {value}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
