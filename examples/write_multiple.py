"""Write multiple BACnet properties in a single request.

Demonstrates WritePropertyMultiple using the convenience dict API.
This writes multiple property values to multiple objects in one
round-trip, which is more efficient than individual writes.

Usage::

    python examples/write_multiple.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Write multiple properties using the dict API."""
    async with Client(instance_number=999) as client:
        # Write to multiple objects in a single request
        await client.write_multiple(
            "192.168.1.100",
            {
                "av,1": {
                    "pv": 72.5,
                    "object-name": "Zone Temp Setpoint",
                },
                "av,2": {
                    "pv": 45.0,
                },
            },
        )

        # Write with a BACnet priority (1-16)
        await client.write_multiple(
            "192.168.1.100",
            {
                "av,1": {"pv": 68.0},
            },
            priority=8,
        )

        # Verify the writes by reading back
        result = await client.read_multiple(
            "192.168.1.100",
            {
                "av,1": ["pv", "object-name"],
                "av,2": ["pv"],
            },
        )
        for obj_id, props in result.items():
            print(f"{obj_id}:")
            for prop_name, value in props.items():
                print(f"  {prop_name} = {value}")


if __name__ == "__main__":
    asyncio.run(main())
