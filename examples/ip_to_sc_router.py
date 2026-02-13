"""BACnet/IP-to-SC gateway router example.

Bridges a traditional BACnet/IP network (network 1) and a BACnet Secure
Connect network (network 2), transparently routing all NPDU traffic
between them.

Real-world scenario
~~~~~~~~~~~~~~~~~~~

Building modernisation -- existing BACnet/IP controllers (air handlers,
VAVs) on network 1 communicate with new BACnet/SC devices (modern
controllers with WebSocket/TLS) on network 2.  The gateway forwards
Who-Is, I-Am, ReadProperty, COV notifications, and every other NPDU
in both directions without any application-layer awareness.

Architecture::

    BACnet/IP devices                          BACnet/SC devices
    ┌──────────┐                                ┌──────────┐
    │ AHU-1    │◄─── UDP ───►┌──────────┐◄─── WS/TLS ───►│ SC Dev 1 │
    │ VAV-101  │             │ Gateway  │                  │ SC Dev 2 │
    │ VAV-102  │◄── net 1 ──►│ Router   │◄──── net 2 ────►│ SC Dev 3 │
    └──────────┘             └──────────┘                  └──────────┘

TLS certificate setup
~~~~~~~~~~~~~~~~~~~~~

BACnet/SC mandates mutual TLS 1.3.  You need three PEM files:

- **device.key** -- private key for this gateway device
- **device.crt** -- operational certificate signed by the BACnet CA
- **ca.crt** -- the BACnet CA certificate chain

For testing you can use ``allow_plaintext=True`` and ``ws://`` URIs to
skip TLS entirely (never do this in production).

Usage::

    python examples/ip_to_sc_router.py
"""

import asyncio
import logging
import signal

from bac_py.network.router import NetworkRouter, RouterPort
from bac_py.transport.bip import BIPTransport
from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration -- adjust these for your network
# ---------------------------------------------------------------------------

# BACnet/IP port (network 1)
BIP_INTERFACE = "0.0.0.0"
BIP_PORT = 0xBAC0  # 47808
BIP_NETWORK = 1

# BACnet/SC hub (network 2)
SC_HUB_URI = "ws://192.168.1.200:4443"
SC_NETWORK = 2

# TLS configuration (set allow_plaintext=False and provide real cert paths
# for production deployments)
TLS_CONFIG = SCTLSConfig(
    # private_key_path="/path/to/device.key",
    # certificate_path="/path/to/device.crt",
    # ca_certificates_path="/path/to/ca.crt",
    allow_plaintext=True,  # Testing only -- production requires TLS 1.3
)

# Hub connection timeout (seconds)
HUB_CONNECT_TIMEOUT = 15.0

# Status log interval (seconds)
STATUS_INTERVAL = 30.0


async def main() -> None:
    """Start the IP-to-SC gateway router."""
    # --- Port 1: BACnet/IP transport ---
    bip_transport = BIPTransport(interface=BIP_INTERFACE, port=BIP_PORT)
    await bip_transport.start()  # Resolves local_mac (IP:port)

    bip_port = RouterPort(
        port_id=1,
        network_number=BIP_NETWORK,
        transport=bip_transport,
        mac_address=bip_transport.local_mac,
        max_npdu_length=bip_transport.max_npdu_length,
    )

    # --- Port 2: BACnet/SC transport ---
    sc_config = SCTransportConfig(
        primary_hub_uri=SC_HUB_URI,
        tls_config=TLS_CONFIG,
    )
    sc_transport = SCTransport(sc_config)
    # SCTransport local_mac (VMAC) is available immediately from the UUID

    sc_port = RouterPort(
        port_id=2,
        network_number=SC_NETWORK,
        transport=sc_transport,
        mac_address=sc_transport.local_mac,
        max_npdu_length=sc_transport.max_npdu_length,
    )

    # --- Create the router (pure forwarding -- no local application) ---
    router = NetworkRouter([bip_port, sc_port])
    await router.start()  # Wires on_receive callbacks and starts SC transport

    # --- Wait for SC hub connection ---
    connected = await sc_transport.hub_connector.wait_connected(
        timeout=HUB_CONNECT_TIMEOUT,
    )
    if not connected:
        print(f"Failed to connect to SC hub ({SC_HUB_URI}) within {HUB_CONNECT_TIMEOUT}s.")
        await router.stop()
        await bip_transport.stop()
        return

    print("IP-to-SC Gateway Router started")
    print(f"  Port 1  BACnet/IP   network {BIP_NETWORK}  {BIP_INTERFACE}:{BIP_PORT}")
    print(f"  Port 2  BACnet/SC   network {SC_NETWORK}  {SC_HUB_URI}")
    print(f"  SC VMAC: {SCVMAC(sc_transport.local_mac)}")
    print("Press Ctrl+C to stop.\n")

    # --- Run until interrupted ---
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Periodically log routing table and SC connection status
    try:
        while not stop_event.is_set():
            entries = router.routing_table.get_all_entries()
            reachable = [e.network_number for e in entries if e.reachability.name == "REACHABLE"]
            hub_fn = sc_transport.hub_connector
            print(f"Reachable networks: {reachable}  SC hub connected: {hub_fn.is_connected}")
            try:
                async with asyncio.timeout(STATUS_INTERVAL):
                    await stop_event.wait()
            except TimeoutError:
                continue
    except asyncio.CancelledError:
        pass

    # --- Clean shutdown ---
    print("\nShutting down gateway router...")
    await router.stop()
    print("Gateway stopped.")


if __name__ == "__main__":
    asyncio.run(main())
