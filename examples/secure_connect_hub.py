"""BACnet Secure Connect (BACnet/SC) hub server example.

Starts an SC hub that accepts WebSocket connections from SC nodes and
routes traffic between them.  The hub also acts as an SC node itself,
registering objects in an ``ObjectDatabase`` that can be read by
connected clients.

Optionally enables the node switch for direct peer-to-peer connections,
bypassing the hub for unicast traffic between nodes that have resolved
each other's addresses.

TLS certificate setup
~~~~~~~~~~~~~~~~~~~~~~

BACnet/SC mandates mutual TLS 1.3.  You need three PEM files:

- **device.key** -- private key for this hub device
- **device.crt** -- operational certificate signed by the BACnet CA
- **ca.crt** -- the BACnet CA certificate chain (clients must present
  certificates signed by this CA)

For testing you can use ``allow_plaintext=True`` and ``ws://`` URIs to
skip TLS entirely (never do this in production).

Usage::

    python examples/secure_connect_hub.py
"""

import asyncio
import logging
import signal

from bac_py.network.npdu import decode_npdu
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.device import DeviceObject
from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.hub_function import SCHubConfig
from bac_py.transport.sc.node_switch import SCNodeSwitchConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC
from bac_py.types.enums import EngineeringUnits, PropertyIdentifier

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

# Enable direct peer connections (optional, set to False to disable)
ENABLE_DIRECT_CONNECTIONS = True
DIRECT_CONNECT_PORT = 4444

# BACnet device instance for this hub node
DEVICE_INSTANCE = 1000


def create_object_database() -> ObjectDatabase:
    """Create and populate the object database for this hub node.

    The hub is a regular BACnet device that exposes objects.  Remote SC
    nodes can read/write these objects by sending APDUs through the hub
    connection.
    """
    db = ObjectDatabase()

    # Every BACnet device requires a Device object
    device = DeviceObject(
        DEVICE_INSTANCE,
        object_name="SC-Hub-Device",
        description="BACnet/SC Hub running bac-py",
    )
    db.add(device)

    # Add some example objects that connected nodes can read
    ai1 = AnalogInputObject(1, object_name="Zone-Temperature")
    ai1.write_property(PropertyIdentifier.PRESENT_VALUE, 72.5)
    ai1.write_property(PropertyIdentifier.UNITS, EngineeringUnits.DEGREES_FAHRENHEIT)
    db.add(ai1)

    ai2 = AnalogInputObject(2, object_name="Zone-Humidity")
    ai2.write_property(PropertyIdentifier.PRESENT_VALUE, 45.0)
    ai2.write_property(PropertyIdentifier.UNITS, EngineeringUnits.PERCENT_RELATIVE_HUMIDITY)
    db.add(ai2)

    return db


async def main() -> None:
    """Start the SC hub and serve BACnet objects."""
    # --- Build transport config with hub function ---
    hub_config = SCHubConfig(
        bind_address=HUB_BIND_ADDRESS,
        bind_port=HUB_BIND_PORT,
        tls_config=TLS_CONFIG,
        max_connections=100,
    )

    # Optional: enable direct peer-to-peer connections via node switch
    node_switch_config = None
    if ENABLE_DIRECT_CONNECTIONS:
        node_switch_config = SCNodeSwitchConfig(
            enable=True,
            bind_address=HUB_BIND_ADDRESS,
            bind_port=DIRECT_CONNECT_PORT,
            tls_config=TLS_CONFIG,
        )

    config = SCTransportConfig(
        # The hub does not connect to another hub as a client, so no
        # primary_hub_uri is needed.  If you want the hub to also be a
        # client of another hub (e.g. hub chaining), set this.
        primary_hub_uri="",
        hub_function_config=hub_config,
        node_switch_config=node_switch_config,
        tls_config=TLS_CONFIG,
    )
    transport = SCTransport(config)

    # --- Set up object database ---
    db = create_object_database()

    # --- Register a receive callback for incoming NPDUs ---
    def on_receive(npdu_bytes: bytes, source_mac: bytes) -> None:
        """Handle incoming NPDUs from connected SC nodes.

        In a full application, you would decode the APDU, dispatch to
        a service handler (ReadProperty, WriteProperty, etc.), encode
        the response, and send it back via transport.send_unicast().
        """
        source = SCVMAC(source_mac)
        npdu = decode_npdu(npdu_bytes)
        print(f"Received NPDU from {source}: network_msg={npdu.is_network_message}")

        if not npdu.is_network_message and npdu.apdu:
            print(f"  APDU ({len(npdu.apdu)} bytes): {npdu.apdu[:20].hex()}...")
            # TODO: decode APDU, look up object in db, build response,
            # and send_unicast() back to source_mac.

    transport.on_receive(on_receive)

    # --- Start the transport (starts the hub WebSocket server) ---
    await transport.start()

    print(f"SC Hub listening on {HUB_BIND_ADDRESS}:{HUB_BIND_PORT}")
    print(f"Hub VMAC: {SCVMAC(transport.local_mac)}")
    if ENABLE_DIRECT_CONNECTIONS:
        print(f"Direct connections on port {DIRECT_CONNECT_PORT}")
    print(f"Device instance: {DEVICE_INSTANCE}")
    print(f"Objects: {len(list(db))} registered")
    print("Press Ctrl+C to stop.\n")

    # --- Run until interrupted ---
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Periodically log hub status
    try:
        while not stop_event.is_set():
            hub_fn = transport.hub_function
            if hub_fn:
                print(f"Connected nodes: {hub_fn.connection_count}")
            try:
                async with asyncio.timeout(30.0):
                    await stop_event.wait()
            except TimeoutError:
                continue
    except asyncio.CancelledError:
        pass

    # --- Clean shutdown ---
    print("\nShutting down hub...")
    await transport.stop()
    print("Hub stopped.")


if __name__ == "__main__":
    asyncio.run(main())
