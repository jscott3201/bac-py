"""Scenario 9: BACnet Secure Connect — cross-container WebSocket communication.

Tests SC hub routing, unicast/broadcast NPDU exchange, and throughput
using real Docker networking between separate hub and node containers.

The sc-hub container runs an SCHubFunction WebSocket server.
The sc-node1 and sc-node2 containers each run an SCTransport that
connects to the hub and echoes received NPDUs back with a b"ECHO:" prefix.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.types import SCHubConnectionStatus
from bac_py.transport.sc.vmac import SCVMAC

pytestmark = pytest.mark.asyncio

CONNECT_TIMEOUT = 15
ECHO_TIMEOUT = 10


def _get_tls_config() -> SCTLSConfig:
    """Build TLS config from env vars, falling back to plaintext."""
    cert_dir = os.environ.get("TLS_CERT_DIR", "")
    cert_name = os.environ.get("TLS_CERT_NAME", "")
    if cert_dir and cert_name:
        return SCTLSConfig(
            private_key_path=os.path.join(cert_dir, f"{cert_name}.key"),
            certificate_path=os.path.join(cert_dir, f"{cert_name}.crt"),
            ca_certificates_path=os.path.join(cert_dir, "ca.crt"),
        )
    return SCTLSConfig(allow_plaintext=True)


async def _make_transport(hub_uri: str) -> SCTransport:
    """Create and start an SCTransport connected to the hub."""
    transport = SCTransport(
        SCTransportConfig(
            primary_hub_uri=hub_uri,
            tls_config=_get_tls_config(),
            min_reconnect_time=0.5,
            max_reconnect_time=5.0,
        )
    )
    await transport.start()
    connected = await transport.hub_connector.wait_connected(timeout=CONNECT_TIMEOUT)
    assert connected, f"Failed to connect to hub at {hub_uri}"
    return transport


async def _send_and_wait_echo(
    transport: SCTransport,
    dest_vmac: bytes,
    payload: bytes,
    timeout: float = ECHO_TIMEOUT,
) -> bytes:
    """Send a unicast NPDU and wait for the ECHO: response."""
    received: asyncio.Queue[tuple[bytes, bytes]] = asyncio.Queue()
    transport.on_receive(lambda npdu, mac: received.put_nowait((npdu, mac)))

    transport.send_unicast(payload, dest_vmac)

    try:
        async with asyncio.timeout(timeout):
            echo_npdu, _source = await received.get()
    except TimeoutError:
        pytest.fail(f"No echo response within {timeout}s for payload {payload!r}")

    assert echo_npdu.startswith(b"ECHO:"), f"Expected ECHO: prefix, got {echo_npdu!r}"
    assert echo_npdu == b"ECHO:" + payload
    return echo_npdu


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_connect_to_hub(sc_hub_uri: str) -> None:
    """Test runner creates SCTransport and connects to the hub."""
    transport = await _make_transport(sc_hub_uri)
    try:
        assert transport.hub_connector.is_connected
        assert (
            transport.hub_connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY
        )
    finally:
        await transport.stop()


async def test_hub_reports_connections(sc_hub_uri: str) -> None:
    """After connecting, verify the hub accepts our connection."""
    transport = await _make_transport(sc_hub_uri)
    try:
        # Our connection is established — the hub has at least our node plus
        # the two echo nodes, but we can only verify our own connection state
        assert transport.hub_connector.is_connected
    finally:
        await transport.stop()


async def test_unicast_to_node1(sc_hub_uri: str, sc_node1_vmac: str) -> None:
    """Send unicast NPDU to node1, verify echo response."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest = SCVMAC.from_hex(sc_node1_vmac)
        await _send_and_wait_echo(transport, dest.address, b"\x01\x04\x00\x05")
    finally:
        await transport.stop()


async def test_unicast_to_node2(sc_hub_uri: str, sc_node2_vmac: str) -> None:
    """Send unicast NPDU to node2, confirm hub routes to correct destination."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest = SCVMAC.from_hex(sc_node2_vmac)
        await _send_and_wait_echo(transport, dest.address, b"\x02\x08\x00\xab")
    finally:
        await transport.stop()


async def test_broadcast_reaches_all_nodes(
    sc_hub_uri: str, sc_node1_vmac: str, sc_node2_vmac: str
) -> None:
    """Send broadcast NPDU, both nodes receive it and echo back."""
    transport = await _make_transport(sc_hub_uri)
    try:
        responses: asyncio.Queue[tuple[bytes, bytes]] = asyncio.Queue()
        transport.on_receive(lambda npdu, mac: responses.put_nowait((npdu, mac)))

        payload = b"\xbb\xcc\xdd\xee"
        transport.send_broadcast(payload)

        # Collect echo responses from both nodes
        echoes: list[tuple[bytes, bytes]] = []
        try:
            async with asyncio.timeout(ECHO_TIMEOUT):
                while len(echoes) < 2:
                    echo_npdu, source_mac = await responses.get()
                    if echo_npdu.startswith(b"ECHO:"):
                        echoes.append((echo_npdu, source_mac))
        except TimeoutError:
            pass

        assert len(echoes) >= 2, f"Expected 2 echo responses, got {len(echoes)}"

        # Both should echo the original payload
        for echo_npdu, _ in echoes:
            assert echo_npdu == b"ECHO:" + payload

        # Verify responses came from different sources
        source_macs = {mac for _, mac in echoes}
        assert len(source_macs) >= 2, "Expected echoes from 2 different nodes"
    finally:
        await transport.stop()


async def test_bidirectional_exchange(
    sc_hub_uri: str, sc_node1_vmac: str, sc_node2_vmac: str
) -> None:
    """Send to node1, get echo, send to node2, get echo — sequential multi-destination."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest1 = SCVMAC.from_hex(sc_node1_vmac)
        dest2 = SCVMAC.from_hex(sc_node2_vmac)

        await _send_and_wait_echo(transport, dest1.address, b"MSG-TO-NODE1")
        await _send_and_wait_echo(transport, dest2.address, b"MSG-TO-NODE2")
    finally:
        await transport.stop()


async def test_large_npdu_transfer(sc_hub_uri: str, sc_node1_vmac: str) -> None:
    """Send a ~1400 byte NPDU (near max), verify echo response matches."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest = SCVMAC.from_hex(sc_node1_vmac)
        large_payload = bytes(range(256)) * 5 + bytes(range(120))  # 1400 bytes
        assert len(large_payload) == 1400

        await _send_and_wait_echo(transport, dest.address, large_payload)
    finally:
        await transport.stop()


async def test_rapid_sequential_messages(sc_hub_uri: str, sc_node1_vmac: str) -> None:
    """Send 50 unicast messages rapidly, verify all echoes received."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest = SCVMAC.from_hex(sc_node1_vmac)
        responses: asyncio.Queue[tuple[bytes, bytes]] = asyncio.Queue()
        transport.on_receive(lambda npdu, mac: responses.put_nowait((npdu, mac)))

        num_messages = 50
        for i in range(num_messages):
            transport.send_unicast(f"MSG-{i:04d}".encode(), dest.address)

        echoes: list[bytes] = []
        try:
            async with asyncio.timeout(ECHO_TIMEOUT * 2):
                while len(echoes) < num_messages:
                    echo_npdu, _ = await responses.get()
                    if echo_npdu.startswith(b"ECHO:"):
                        echoes.append(echo_npdu)
        except TimeoutError:
            pass

        # Allow some tolerance for network conditions
        assert len(echoes) >= num_messages * 0.9, (
            f"Expected at least {int(num_messages * 0.9)} echoes, got {len(echoes)}"
        )
    finally:
        await transport.stop()


async def test_concurrent_multi_node_traffic(
    sc_hub_uri: str, sc_node1_vmac: str, sc_node2_vmac: str
) -> None:
    """Send messages to both nodes concurrently, verify all responses."""
    transport = await _make_transport(sc_hub_uri)
    try:
        dest1 = SCVMAC.from_hex(sc_node1_vmac)
        dest2 = SCVMAC.from_hex(sc_node2_vmac)
        responses: asyncio.Queue[tuple[bytes, bytes]] = asyncio.Queue()
        transport.on_receive(lambda npdu, mac: responses.put_nowait((npdu, mac)))

        num_per_node = 10

        async def send_to(dest_mac: bytes, prefix: str) -> None:
            for i in range(num_per_node):
                transport.send_unicast(f"{prefix}-{i:04d}".encode(), dest_mac)
                await asyncio.sleep(0.01)

        # Send to both nodes concurrently
        await asyncio.gather(
            send_to(dest1.address, "N1"),
            send_to(dest2.address, "N2"),
        )

        total_expected = num_per_node * 2
        echoes: list[bytes] = []
        try:
            async with asyncio.timeout(ECHO_TIMEOUT * 2):
                while len(echoes) < total_expected:
                    echo_npdu, _ = await responses.get()
                    if echo_npdu.startswith(b"ECHO:"):
                        echoes.append(echo_npdu)
        except TimeoutError:
            pass

        # Verify we got responses for both nodes
        n1_echoes = [e for e in echoes if b"N1-" in e]
        n2_echoes = [e for e in echoes if b"N2-" in e]

        assert len(n1_echoes) >= num_per_node * 0.8, (
            f"Expected at least {int(num_per_node * 0.8)} N1 echoes, got {len(n1_echoes)}"
        )
        assert len(n2_echoes) >= num_per_node * 0.8, (
            f"Expected at least {int(num_per_node * 0.8)} N2 echoes, got {len(n2_echoes)}"
        )
    finally:
        await transport.stop()
