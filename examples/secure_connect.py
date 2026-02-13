"""BACnet Secure Connect (BACnet/SC) client example.

Connects to an SC hub over WebSocket/TLS and sends a ReadProperty
request to a remote SC device addressed by its VMAC.  This demonstrates
the lower-level ``SCTransport`` API since the high-level ``Client``
does not yet integrate with SC transport.

TLS certificate setup
~~~~~~~~~~~~~~~~~~~~~~

BACnet/SC mandates mutual TLS 1.3.  You need three PEM files:

- **device.key** -- private key for this device
- **device.crt** -- operational certificate signed by the BACnet CA
- **ca.crt** -- the BACnet CA certificate chain

For testing you can use ``allow_plaintext=True`` and ``ws://`` URIs to
skip TLS entirely (never do this in production).

Usage::

    python examples/secure_connect.py
"""

import asyncio
import logging

from bac_py.encoding.apdu import ConfirmedRequestPDU, encode_apdu
from bac_py.network.npdu import NPDU, encode_npdu
from bac_py.services.read_property import ReadPropertyRequest
from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    NetworkPriority,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration -- adjust these for your network
# ---------------------------------------------------------------------------

# Hub WebSocket URI (use wss:// with real TLS certificates in production)
PRIMARY_HUB_URI = "ws://192.168.1.200:4443"

# TLS configuration (set allow_plaintext=False and provide real cert paths
# for production deployments)
TLS_CONFIG = SCTLSConfig(
    # private_key_path="/path/to/device.key",
    # certificate_path="/path/to/device.crt",
    # ca_certificates_path="/path/to/ca.crt",
    allow_plaintext=True,  # Testing only -- production requires TLS 1.3
)

# Remote SC device to read from (6-byte VMAC in hex)
REMOTE_VMAC = "02:AA:BB:CC:DD:01"

# Object and property to read
TARGET_OBJECT = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
TARGET_PROPERTY = PropertyIdentifier.PRESENT_VALUE


async def main() -> None:
    """Connect to an SC hub and read a property from a remote SC device."""
    config = SCTransportConfig(
        primary_hub_uri=PRIMARY_HUB_URI,
        tls_config=TLS_CONFIG,
    )
    transport = SCTransport(config)

    # --- Received-response plumbing ---
    response_event = asyncio.Event()
    response_data: dict[str, bytes] = {}

    def on_receive(npdu_bytes: bytes, source_mac: bytes) -> None:
        """Handle incoming NPDUs from the hub."""
        response_data["npdu"] = npdu_bytes
        response_data["source"] = source_mac
        response_event.set()

    transport.on_receive(on_receive)

    # --- Start transport and wait for hub connection ---
    await transport.start()
    connected = await transport.hub_connector.wait_connected(timeout=10.0)
    if not connected:
        print("Failed to connect to hub within 10 seconds.")
        await transport.stop()
        return

    print(f"Connected to hub: {PRIMARY_HUB_URI}")
    print(f"Local VMAC: {SCVMAC(transport.local_mac)}")

    # --- Build a ReadProperty request ---
    # 1. Encode the service request parameters
    service_data = ReadPropertyRequest(
        object_identifier=TARGET_OBJECT,
        property_identifier=TARGET_PROPERTY,
    ).encode()

    # 2. Wrap in a Confirmed-Request APDU
    apdu = encode_apdu(
        ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=False,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=ConfirmedServiceChoice.READ_PROPERTY,
            service_request=service_data,
        )
    )

    # 3. Wrap in an NPDU (no routing, expect a reply)
    npdu_bytes = (
        encode_npdu(
            NPDU(
                version=1,
                is_network_message=False,
                expecting_reply=True,
                priority=NetworkPriority.NORMAL,
            )
        )
        + apdu
    )

    # --- Send unicast to the remote VMAC ---
    dest_vmac = SCVMAC.from_hex(REMOTE_VMAC)
    transport.send_unicast(npdu_bytes, dest_vmac.address)
    print(f"Sent ReadProperty request to VMAC {dest_vmac}")

    # --- Wait for the response ---
    try:
        async with asyncio.timeout(5.0):
            await response_event.wait()
    except TimeoutError:
        print("No response received within 5 seconds.")
        await transport.stop()
        return

    print(f"Response from VMAC {SCVMAC(response_data['source'])}")
    print(f"Raw NPDU ({len(response_data['npdu'])} bytes): {response_data['npdu'].hex()}")

    # --- Clean shutdown ---
    await transport.stop()
    print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
