"""BACnet Secure Connect (BACnet/SC) server example.

Starts a BACnet/SC server using ``BACnetApplication`` and
``DefaultServerHandlers``.  The server runs an SC hub function that
accepts WebSocket connections from SC nodes and provides full APDU
dispatch (ReadProperty, WriteProperty, Who-Is, etc.) via the standard
application layer.

This is the **high-level** approach to running an SC server.  For the
lower-level ``SCTransport`` API (manual NPDU/APDU handling), see
``secure_connect.py`` and ``secure_connect_hub.py``.

TLS certificate setup
~~~~~~~~~~~~~~~~~~~~~~

BACnet/SC mandates mutual TLS 1.3.  You need three PEM files:

- **device.key** -- private key for this device
- **device.crt** -- operational certificate signed by the BACnet CA
- **ca.crt** -- the BACnet CA certificate chain

For testing you can use ``allow_plaintext=True`` and ``ws://`` URIs to
skip TLS entirely (never do this in production).  See
``sc_generate_certs.py`` for generating test certificates.

Usage::

    python examples/sc_server.py
"""

import asyncio
import logging
import signal

from bac_py.app.application import BACnetApplication, DeviceConfig
from bac_py.app.server import DefaultServerHandlers
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.binary import BinaryInputObject, BinaryValueObject
from bac_py.objects.device import DeviceObject
from bac_py.transport.sc import SCTransportConfig
from bac_py.transport.sc.hub_function import SCHubConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.types.enums import EngineeringUnits

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration -- adjust these for your deployment
# ---------------------------------------------------------------------------

# Hub listens on this address and port for SC node connections
HUB_BIND_ADDRESS = "0.0.0.0"
HUB_BIND_PORT = 4443

# TLS configuration (set allow_plaintext=False and provide real cert paths
# for production deployments)
TLS_CONFIG = SCTLSConfig(
    # private_key_path="/path/to/device.key",
    # certificate_path="/path/to/device.crt",
    # ca_certificates_path="/path/to/ca.crt",
    allow_plaintext=True,  # Testing only -- production requires TLS 1.3
)

# BACnet device instance for this server
DEVICE_INSTANCE = 1000


async def main() -> None:
    """Start an SC server with sample objects and full APDU dispatch."""
    # Build SC transport config with hub function (this node IS the hub)
    sc_config = SCTransportConfig(
        hub_function_config=SCHubConfig(
            bind_address=HUB_BIND_ADDRESS,
            bind_port=HUB_BIND_PORT,
            tls_config=TLS_CONFIG,
        ),
        tls_config=TLS_CONFIG,
    )

    config = DeviceConfig(
        instance_number=DEVICE_INSTANCE,
        name="SC-Server",
        sc_config=sc_config,
    )
    app = BACnetApplication(config)
    await app.start()

    # Create device object
    device = DeviceObject(
        DEVICE_INSTANCE,
        object_name="SC-Server",
        vendor_name="bac-py",
        vendor_identifier=0,
        model_name="bac-py-sc-server",
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

    print(f"SC server listening on {HUB_BIND_ADDRESS}:{HUB_BIND_PORT}")
    print(f"Device instance: {DEVICE_INSTANCE}")
    print(f"Objects: {len(list(app.object_db))} registered")
    print("Press Ctrl+C to stop.\n")

    # Block until SIGTERM/SIGINT
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    print("\nShutting down SC server...")
    await app.stop()
    print("Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
