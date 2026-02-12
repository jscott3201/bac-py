"""Send BACnet text messages.

Demonstrates confirmed (reliable) and unconfirmed (fire-and-forget)
text messaging using the high-level Client API.

Usage::

    python examples/text_message.py
"""

import asyncio

from bac_py import Client
from bac_py.types.enums import MessagePriority


async def main() -> None:
    """Send text messages to a BACnet device."""
    async with Client(instance_number=999) as client:
        addr = "192.168.1.100"

        # Send a confirmed text message (waits for acknowledgment)
        await client.send_text_message(addr, "Scheduled maintenance at 2pm")
        print("Confirmed message sent.")

        # Send an urgent confirmed message
        await client.send_text_message(
            addr,
            "High temperature alarm in zone 3!",
            message_priority=MessagePriority.URGENT,
        )
        print("Urgent message sent.")

        # Send an unconfirmed (broadcast) message
        await client.send_text_message(
            "192.168.1.255",
            "System restart in 5 minutes",
            confirmed=False,
        )
        print("Broadcast message sent.")


if __name__ == "__main__":
    asyncio.run(main())
