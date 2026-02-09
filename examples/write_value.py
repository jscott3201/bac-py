"""Write BACnet property values.

Demonstrates automatic encoding: floats become Real, ints are
encoded based on the target object/property type, and None
relinquishes a command priority.

Usage::

    python examples/write_value.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Write values to BACnet objects."""
    async with Client(instance_number=999) as client:
        # Write a float to an analog value's present-value (encoded as Real)
        await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)

        # Write an int to a binary output (auto-encoded as Enumerated)
        await client.write("192.168.1.100", "bo,1", "pv", 1, priority=8)

        # Relinquish (release) a command priority by writing None
        await client.write("192.168.1.100", "av,1", "pv", None, priority=8)

        # Write a string property
        await client.write("192.168.1.100", "av,1", "object-name", "Zone Temp Setpoint")

        print("Writes complete.")


if __name__ == "__main__":
    asyncio.run(main())
