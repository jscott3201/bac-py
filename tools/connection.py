"""Async bridge between Click (sync) and BACnetClient (async)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.client import BACnetClient

T = TypeVar("T")


def run_command(
    interface: str,
    port: int,
    instance: int,
    coro_factory: Callable[[BACnetClient], Coroutine[Any, Any, T]],
) -> T:
    """Create a BACnet application, build a client, and run a coroutine.

    This bridges Click's synchronous world with the async BACnetClient API.

    Args:
        interface: Local network interface to bind to.
        port: Local BACnet/IP port.
        instance: Local device instance number.
        coro_factory: Callable that receives a BACnetClient and returns
            a coroutine to execute.

    Returns:
        The return value of the coroutine.
    """

    async def _run() -> T:
        config = DeviceConfig(
            instance_number=instance,
            interface=interface,
            port=port,
        )
        async with BACnetApplication(config) as app:
            client = BACnetClient(app)
            return await coro_factory(client)

    return asyncio.run(_run())
