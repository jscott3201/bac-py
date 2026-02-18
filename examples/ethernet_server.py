"""BACnet Ethernet (Clause 7) server example.

Starts a BACnet server using raw IEEE 802.3/802.2 Ethernet frames via
``BACnetApplication`` and ``DefaultServerHandlers``.  This transport
sends BACnet packets directly on the Ethernet LAN without IP/UDP.

Requirements:

- **Linux**: raw sockets require ``CAP_NET_RAW`` or root privileges.
  The MAC address is auto-detected from the interface.
- **macOS**: requires a BPF device (``/dev/bpf*``), typically root.
  You must provide an explicit ``ethernet_mac`` since BPF does not
  expose the interface MAC directly.

Usage::

    sudo python examples/ethernet_server.py
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

# Network interface for raw Ethernet frames
ETHERNET_INTERFACE = "eth0"

# Explicit 6-byte MAC address (required on macOS, auto-detected on Linux)
# Set to None for auto-detection on Linux.
ETHERNET_MAC: bytes | None = None
# ETHERNET_MAC = bytes([0x02, 0x42, 0xAC, 0x11, 0x00, 0x02])  # example

# BACnet device instance for this server
DEVICE_INSTANCE = 600


async def main() -> None:
    """Start an Ethernet server with sample objects and full APDU dispatch."""
    config = DeviceConfig(
        instance_number=DEVICE_INSTANCE,
        name="Ethernet-Server",
        ethernet_interface=ETHERNET_INTERFACE,
        ethernet_mac=ETHERNET_MAC,
    )
    app = BACnetApplication(config)
    await app.start()

    # Create device object
    device = DeviceObject(
        DEVICE_INSTANCE,
        object_name="Ethernet-Server",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-ethernet-server",
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

    print(f"Ethernet server running on {ETHERNET_INTERFACE}: device {DEVICE_INSTANCE}")
    print(f"Objects: {len(list(app.object_db))} registered")
    print("Press Ctrl+C to stop.\n")

    # Block until SIGTERM/SIGINT
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    print("\nShutting down Ethernet server...")
    await app.stop()
    print("Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
