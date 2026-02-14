"""Generate test certificates and demonstrate TLS-secured BACnet/SC communication.

BACnet Secure Connect (Annex AB) mandates mutual TLS 1.3 for all WebSocket
connections.  Each device needs a private key + certificate signed by a
trusted BACnet CA, and every peer must present the CA certificate to verify
incoming connections.

This script has two phases:

1. **Certificate generation** -- Creates a self-signed EC P-256 test PKI
   (CA + three device certificates) in ``./sc_test_certs/``.  EC P-256 is the
   recommended curve for BACnet/SC: compact, fast, and native to TLS 1.3.

2. **TLS demo** -- Starts an SC hub on ``wss://127.0.0.1:4443`` with mutual
   TLS, connects two nodes using their own certificates, sends a test NPDU
   from node 1 to node 2 through the hub, and verifies delivery.

The generated certificates are suitable for local testing only (1-year
validity, self-signed CA, localhost SAN).

Prerequisites::

    pip install bac-py[secure]
    # or: uv sync --group dev

Usage::

    python examples/sc_generate_certs.py

The script creates ``./sc_test_certs/`` with eight PEM files::

    ca.key       CA private key
    ca.crt       CA self-signed certificate
    hub.key      Hub device private key
    hub.crt      Hub device certificate (signed by CA)
    node1.key    Node 1 device private key
    node1.crt    Node 1 device certificate (signed by CA)
    node2.key    Node 2 device private key
    node2.crt    Node 2 device certificate (signed by CA)
"""

import asyncio
import datetime
import ipaddress
import logging
import shutil
import signal
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.hub_function import SCHubConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC
from bac_py.types.enums import NetworkPriority

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CERT_DIR = Path("./sc_test_certs")
HUB_BIND_ADDRESS = "127.0.0.1"
HUB_BIND_PORT = 4443
HUB_URI = f"wss://{HUB_BIND_ADDRESS}:{HUB_BIND_PORT}"


# ---------------------------------------------------------------------------
# Phase 1: Certificate generation
# ---------------------------------------------------------------------------


def generate_test_pki(cert_dir: Path) -> None:
    """Generate a self-signed CA and three device certificates.

    Creates ``cert_dir`` (removing it first if it exists) and writes:

    - ``ca.key`` / ``ca.crt`` -- CA key pair and self-signed certificate
    - ``hub.key`` / ``hub.crt`` -- Hub device key and CA-signed certificate
    - ``node1.key`` / ``node1.crt`` -- Node 1 device key and CA-signed certificate
    - ``node2.key`` / ``node2.crt`` -- Node 2 device key and CA-signed certificate
    """
    if cert_dir.exists():
        shutil.rmtree(cert_dir)
    cert_dir.mkdir(parents=True)

    now = datetime.datetime.now(tz=datetime.UTC)
    validity = datetime.timedelta(days=365)

    # --- CA key + self-signed certificate ---
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BACnet Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + validity)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(cert_dir / "ca.key", ca_key)
    _write_cert(cert_dir / "ca.crt", ca_cert)
    print(f"  CA certificate:    {cert_dir / 'ca.crt'}")

    # --- Device certificates (hub + two nodes) ---
    for name in ("hub", "node1", "node2"):
        device_key = ec.generate_private_key(ec.SECP256R1())
        device_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, f"BACnet SC {name.title()}")]
        )
        device_cert = (
            x509.CertificateBuilder()
            .subject_name(device_name)
            .issuer_name(ca_name)
            .public_key(device_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + validity)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        _write_key(cert_dir / f"{name}.key", device_key)
        _write_cert(cert_dir / f"{name}.crt", device_cert)
        print(f"  {name.title():5s} certificate: {cert_dir / f'{name}.crt'}")


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    """Write an EC private key to a PEM file."""
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    """Write an X.509 certificate to a PEM file."""
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


# ---------------------------------------------------------------------------
# Phase 2: TLS-secured SC hub + node communication
# ---------------------------------------------------------------------------


async def run_tls_demo(cert_dir: Path) -> None:
    """Start an SC hub with mutual TLS, connect two nodes, and route an NPDU."""
    ca_path = str(cert_dir / "ca.crt")

    hub_tls = SCTLSConfig(
        private_key_path=str(cert_dir / "hub.key"),
        certificate_path=str(cert_dir / "hub.crt"),
        ca_certificates_path=ca_path,
    )
    node1_tls = SCTLSConfig(
        private_key_path=str(cert_dir / "node1.key"),
        certificate_path=str(cert_dir / "node1.crt"),
        ca_certificates_path=ca_path,
    )
    node2_tls = SCTLSConfig(
        private_key_path=str(cert_dir / "node2.key"),
        certificate_path=str(cert_dir / "node2.crt"),
        ca_certificates_path=ca_path,
    )

    # --- Start the hub ---
    hub_config = SCTransportConfig(
        hub_function_config=SCHubConfig(
            bind_address=HUB_BIND_ADDRESS,
            bind_port=HUB_BIND_PORT,
            tls_config=hub_tls,
        ),
        tls_config=hub_tls,
    )
    hub_transport = SCTransport(hub_config)
    await hub_transport.start()
    print(f"\nHub started on {HUB_URI}")
    print(f"  Hub VMAC: {SCVMAC(hub_transport.local_mac)}")

    # --- Connect node 2 (receiver) first ---
    node2_config = SCTransportConfig(primary_hub_uri=HUB_URI, tls_config=node2_tls)
    node2_transport = SCTransport(node2_config)

    received_event = asyncio.Event()
    received_data: dict[str, bytes] = {}

    def node2_on_receive(npdu_bytes: bytes, source_mac: bytes) -> None:
        received_data["npdu"] = npdu_bytes
        received_data["source"] = source_mac
        received_event.set()

    node2_transport.on_receive(node2_on_receive)
    await node2_transport.start()

    connected = await node2_transport.hub_connector.wait_connected(timeout=10.0)
    if not connected:
        print("ERROR: Node 2 failed to connect to hub.")
        await node2_transport.stop()
        await hub_transport.stop()
        return
    print(f"  Node 2 VMAC: {SCVMAC(node2_transport.local_mac)} (receiver)")

    # --- Connect node 1 (sender) ---
    node1_config = SCTransportConfig(primary_hub_uri=HUB_URI, tls_config=node1_tls)
    node1_transport = SCTransport(node1_config)
    await node1_transport.start()

    connected = await node1_transport.hub_connector.wait_connected(timeout=10.0)
    if not connected:
        print("ERROR: Node 1 failed to connect to hub.")
        await node1_transport.stop()
        await node2_transport.stop()
        await hub_transport.stop()
        return
    print(f"  Node 1 VMAC: {SCVMAC(node1_transport.local_mac)} (sender)")
    print("  Both nodes connected via mutual TLS 1.3")

    # --- Send a test NPDU from node 1 → node 2 through the hub ---
    test_npdu = (
        encode_npdu(
            NPDU(
                version=1,
                is_network_message=False,
                expecting_reply=False,
                priority=NetworkPriority.NORMAL,
            )
        )
        + b"Hello BACnet/SC over TLS!"
    )

    node1_transport.send_unicast(test_npdu, node2_transport.local_mac)
    print("\n  Node 1 sent test NPDU to Node 2 (routed through hub)...")

    try:
        async with asyncio.timeout(5.0):
            await received_event.wait()
    except TimeoutError:
        print("  ERROR: Node 2 did not receive NPDU within 5 seconds.")
        await node1_transport.stop()
        await node2_transport.stop()
        await hub_transport.stop()
        return

    # Verify the received NPDU
    npdu = decode_npdu(received_data["npdu"])
    payload = received_data["npdu"][2:]  # Skip NPDU header (version + control)
    source_vmac = SCVMAC(received_data["source"])

    print(f"  Node 2 received NPDU from {source_vmac}")
    print(f"  Payload: {payload.decode('utf-8', errors='replace')}")
    print(f"  Network message: {npdu.is_network_message}")

    # --- Clean shutdown ---
    await node1_transport.stop()
    await node2_transport.stop()
    await hub_transport.stop()
    print("\nTLS demo complete -- mutual TLS 1.3 verified successfully.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Generate test certificates and run the TLS demo."""
    # Handle graceful shutdown
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Phase 1: Generate certificates
    print("Phase 1: Generating test PKI...")
    generate_test_pki(CERT_DIR)
    print(f"  Certificates written to {CERT_DIR}/\n")

    # Phase 2: TLS demo
    print("Phase 2: Testing TLS-secured SC communication...")
    await run_tls_demo(CERT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
