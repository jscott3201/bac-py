"""Discover BACnet routers and remote networks.

Sends Who-Is-Router-To-Network to find routers, then discovers
devices on a remote network through the router.

Usage::

    python examples/router_discovery.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Discover routers and devices on remote networks."""
    async with Client(instance_number=999) as client:
        # Discover all routers and their reachable networks
        routers = await client.who_is_router_to_network(timeout=3.0)
        if not routers:
            print("No routers found on the local network.")
            return

        print(f"Found {len(routers)} router(s):")
        for router in routers:
            print(f"  Router at {router.address}:")
            print(f"    Networks: {router.networks}")

        # Discover devices on a specific remote network
        remote_net = routers[0].networks[0]
        print(f"\nDiscovering devices on network {remote_net}...")
        devices = await client.discover(destination=f"{remote_net}:*", timeout=5.0)
        print(f"Found {len(devices)} device(s):")
        for dev in devices:
            print(f"  Device {dev.instance} at {dev.address_str}")


if __name__ == "__main__":
    asyncio.run(main())
