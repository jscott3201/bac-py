"""BACnet/IPv6 (Annex U) server example.

Starts a BACnet/IPv6 server using ``BACnetApplication`` and
``DefaultServerHandlers``.  IPv6 transport uses 3-byte VMACs and the
``ff02::bac0`` multicast group by default.

For the client counterpart, see ``ipv6_client.py``.

Usage::

    python examples/ipv6_server.py
"""

import asyncio
import logging
import signal

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.server import DefaultServerHandlers
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
from bac_py.objects.device import DeviceObject
from bac_py.types.enums import EngineeringUnits

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration -- adjust these for your deployment
# ---------------------------------------------------------------------------

# BACnet device instance for this server
DEVICE_INSTANCE = 500


async def main() -> None:
    """Start an IPv6 server with sample objects and full APDU dispatch."""
    config = DeviceConfig(
        instance_number=DEVICE_INSTANCE,
        name="IPv6-Server",
        ipv6=True,
        # interface="::" binds to all IPv6 interfaces (default when ipv6=True)
        # multicast_address="ff02::bac0" is the BACnet well-known group (default)
        # vmac is auto-generated if not provided
    )
    app = BACnetApplication(config)
    await app.start()

    # Create device object
    device = DeviceObject(
        DEVICE_INSTANCE,
        object_name="IPv6-Server",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-ipv6-server",
    )
    app.object_db.add(device)

    # Sample objects
    ai = AnalogInputObject(
        1,
        object_name="Temperature",
        present_value=72.5,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    ao = AnalogOutputObject(
        1,
        object_name="Setpoint-Output",
        present_value=68.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
    )
    av = AnalogValueObject(
        1,
        object_name="Setpoint",
        present_value=70.0,
        units=EngineeringUnits.DEGREES_FAHRENHEIT,
        commandable=True,
    )
    bi = BinaryInputObject(1, object_name="Occupancy")
    bv = BinaryValueObject(1, object_name="Override", commandable=True)

    for obj in (ai, ao, av, bi, bv):
        app.object_db.add(obj)

    # Register default service handlers (ReadProperty, WriteProperty, Who-Is, etc.)
    handlers = DefaultServerHandlers(app, app.object_db, device)
    handlers.register()

    print(f"IPv6 server running: device {DEVICE_INSTANCE}")
    print(f"Objects: {len(list(app.object_db))} registered")
    print("Press Ctrl+C to stop.\n")

    # Block until SIGTERM/SIGINT
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    print("\nShutting down IPv6 server...")
    await app.stop()
    print("Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
