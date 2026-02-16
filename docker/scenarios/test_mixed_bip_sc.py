"""Scenario 15: Mixed BIP-to-SC NPDU routing through a cross-transport router.

A BACnet/IP test client constructs NPDUs with DNET/DADR targeting SC nodes
on network 2. The BIP↔SC router forwards them over WebSocket to SC echo
nodes which reply with proper routed NPDU headers so the response traverses
the router back to the BIP side.
"""

from __future__ import annotations

import asyncio
import os
import struct
from typing import TYPE_CHECKING

import pytest

from bac_py.network.address import BACnetAddress
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.transport.bip import BIPTransport

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

ROUTER_ADDRESS = os.environ.get("ROUTER_ADDRESS", "172.30.1.188")
ROUTER_PORT = int(os.environ.get("ROUTER_PORT", "47808"))
SC_NETWORK = int(os.environ.get("SC_NETWORK", "2"))
SC_NODE1_VMAC = os.environ.get("SC_NODE1_VMAC", "02CC00000001")
SC_NODE2_VMAC = os.environ.get("SC_NODE2_VMAC", "02CC00000002")

ECHO_TIMEOUT = 15

pytestmark = pytest.mark.asyncio


def _vmac_bytes(vmac_hex: str) -> bytes:
    """Convert a hex VMAC string to bytes."""
    return bytes.fromhex(vmac_hex)


def _router_mac() -> bytes:
    """Build the 6-byte BIP MAC for the router (4-byte IP + 2-byte port)."""
    parts = ROUTER_ADDRESS.split(".")
    ip_bytes = bytes(int(p) for p in parts)
    port_bytes = struct.pack("!H", ROUTER_PORT)
    return ip_bytes + port_bytes


def _build_routed_npdu(dest_vmac: bytes, payload: bytes) -> bytes:
    """Build an NPDU with DNET/DADR targeting an SC node."""
    npdu = NPDU(
        destination=BACnetAddress(network=SC_NETWORK, mac_address=dest_vmac),
        apdu=payload,
        expecting_reply=True,
    )
    return encode_npdu(npdu)


async def _send_and_receive(
    transport: BIPTransport,
    npdu_bytes: bytes,
    router_mac: bytes,
    timeout: float = ECHO_TIMEOUT,
) -> NPDU:
    """Send an NPDU to the router and wait for the echo response."""
    received: asyncio.Queue[tuple[bytes, bytes]] = asyncio.Queue()
    transport.on_receive(lambda data, mac: received.put_nowait((data, mac)))

    transport.send_unicast(npdu_bytes, router_mac)

    try:
        async with asyncio.timeout(timeout):
            while True:
                resp_bytes, _source_mac = await received.get()
                resp_npdu = decode_npdu(resp_bytes)
                # Skip network-layer messages (like I-Am-Router-To-Network)
                if not resp_npdu.is_network_message:
                    return resp_npdu
    except TimeoutError:
        pytest.fail(f"No echo response within {timeout}s")
        raise  # unreachable, satisfies type checker


@pytest.fixture
async def transport() -> AsyncGenerator[BIPTransport]:
    t = BIPTransport(interface="0.0.0.0", port=0)
    await t.start()
    yield t
    await t.stop()


# --- Tests ---


async def test_unicast_to_node1(transport: BIPTransport) -> None:
    """Send routed NPDU to SC node1, verify echo response routes back."""
    dest = _vmac_bytes(SC_NODE1_VMAC)
    router_mac = _router_mac()
    payload = b"\x01\x04\x00\x05"

    npdu_bytes = _build_routed_npdu(dest, payload)
    resp = await _send_and_receive(transport, npdu_bytes, router_mac)

    assert resp.apdu == b"ECHO:" + payload


async def test_unicast_to_node2(transport: BIPTransport) -> None:
    """Send routed NPDU to SC node2, verify echo response routes back."""
    dest = _vmac_bytes(SC_NODE2_VMAC)
    router_mac = _router_mac()
    payload = b"\x02\x08\x00\xab"

    npdu_bytes = _build_routed_npdu(dest, payload)
    resp = await _send_and_receive(transport, npdu_bytes, router_mac)

    assert resp.apdu == b"ECHO:" + payload


async def test_multiple_payloads(transport: BIPTransport) -> None:
    """Send 5 sequential round-trips through the router."""
    dest = _vmac_bytes(SC_NODE1_VMAC)
    router_mac = _router_mac()

    for i in range(5):
        payload = f"MSG-{i:04d}".encode()
        npdu_bytes = _build_routed_npdu(dest, payload)
        resp = await _send_and_receive(transport, npdu_bytes, router_mac)
        assert resp.apdu == b"ECHO:" + payload


async def test_large_npdu(transport: BIPTransport) -> None:
    """Send a ~1000 byte payload across the BIP/SC transport boundary."""
    dest = _vmac_bytes(SC_NODE1_VMAC)
    router_mac = _router_mac()
    payload = bytes(range(256)) * 3 + bytes(range(232))  # 1000 bytes
    assert len(payload) == 1000

    npdu_bytes = _build_routed_npdu(dest, payload)
    resp = await _send_and_receive(transport, npdu_bytes, router_mac)

    assert resp.apdu == b"ECHO:" + payload
