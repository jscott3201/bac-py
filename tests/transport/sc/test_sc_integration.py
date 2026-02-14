"""Integration tests for BACnet/SC hub + node communication.

Tests SC hub function, hub connector with failover, direct connections,
and end-to-end NPDU exchange between SC nodes using in-process loopback
WebSocket connections (no TLS / no Docker networking required).

Moved from docker/scenarios/ — these run entirely in a single process.
"""

from __future__ import annotations

import asyncio

import pytest

from bac_py.transport.sc import SCTransport, SCTransportConfig
from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
from bac_py.transport.sc.node_switch import SCNodeSwitchConfig
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

pytestmark = pytest.mark.asyncio


def _plaintext_tls() -> SCTLSConfig:
    return SCTLSConfig(allow_plaintext=True)


# --- Hub + Two Nodes ---


async def test_two_nodes_exchange_via_hub():
    """Two SC nodes connect to a hub and exchange unicast NPDUs."""
    hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    await hub.start()
    port = hub._server.sockets[0].getsockname()[1]

    received_by_t2: list[tuple[bytes, bytes]] = []

    t1 = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    t2 = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    t2.on_receive(lambda npdu, mac: received_by_t2.append((npdu, mac)))

    await t1.start()
    await t2.start()
    await t1.hub_connector.wait_connected(timeout=5)
    await t2.hub_connector.wait_connected(timeout=5)

    # t1 sends unicast NPDU to t2
    t1.send_unicast(b"\x01\x04\x00\x05", t2.local_mac)
    await asyncio.sleep(0.5)

    assert len(received_by_t2) >= 1
    assert received_by_t2[0][0] == b"\x01\x04\x00\x05"

    await t1.stop()
    await t2.stop()
    await hub.stop()


async def test_broadcast_reaches_all_nodes():
    """A broadcast NPDU reaches all other connected nodes."""
    hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    await hub.start()
    port = hub._server.sockets[0].getsockname()[1]

    received_by_t2: list[bytes] = []
    received_by_t3: list[bytes] = []

    t1 = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    t2 = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    t3 = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    t2.on_receive(lambda npdu, _mac: received_by_t2.append(npdu))
    t3.on_receive(lambda npdu, _mac: received_by_t3.append(npdu))

    await t1.start()
    await t2.start()
    await t3.start()
    await t1.hub_connector.wait_connected(timeout=5)
    await t2.hub_connector.wait_connected(timeout=5)
    await t3.hub_connector.wait_connected(timeout=5)

    t1.send_broadcast(b"\x01\x08\x00\xff")
    await asyncio.sleep(0.5)

    assert len(received_by_t2) >= 1
    assert len(received_by_t3) >= 1
    assert received_by_t2[0] == b"\x01\x08\x00\xff"
    assert received_by_t3[0] == b"\x01\x08\x00\xff"

    await t1.stop()
    await t2.stop()
    await t3.stop()
    await hub.stop()


# --- Hub Failover ---


async def test_failover_to_secondary_hub():
    """When the primary hub is unavailable, the connector fails over."""
    failover_hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    await failover_hub.start()
    failover_port = failover_hub._server.sockets[0].getsockname()[1]

    transport = SCTransport(
        SCTransportConfig(
            primary_hub_uri="ws://127.0.0.1:19999",  # Unreachable
            failover_hub_uri=f"ws://127.0.0.1:{failover_port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    await transport.start()
    connected = await transport.hub_connector.wait_connected(timeout=10)
    assert connected

    from bac_py.transport.sc.types import SCHubConnectionStatus

    assert transport.hub_connector.connection_status == SCHubConnectionStatus.CONNECTED_TO_FAILOVER

    await transport.stop()
    await failover_hub.stop()


# --- Direct Connections ---


async def test_direct_connection_between_nodes():
    """Two nodes establish a direct connection for unicast traffic."""
    from bac_py.transport.sc.node_switch import SCNodeSwitch

    peer_vmac = SCVMAC.random()
    peer_uuid = DeviceUUID.generate()
    peer = SCNodeSwitch(
        peer_vmac,
        peer_uuid,
        config=SCNodeSwitchConfig(
            enable=True,
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    received: list[bytes] = []

    async def on_msg(msg, raw=None):
        if hasattr(msg, "payload"):
            received.append(msg.payload)

    peer.on_message = on_msg
    await peer.start()
    port = peer._server.sockets[0].getsockname()[1]

    local = SCNodeSwitch(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCNodeSwitchConfig(
            enable=True,
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    await local.start()

    ok = await local.establish_direct(peer_vmac, [f"ws://127.0.0.1:{port}"])
    assert ok

    from bac_py.transport.sc.bvlc import SCMessage
    from bac_py.transport.sc.types import BvlcSCFunction

    msg = SCMessage(
        BvlcSCFunction.ENCAPSULATED_NPDU,
        message_id=42,
        payload=b"\xca\xfe\xba\xbe",
    )
    ok = await local.send_direct(peer_vmac, msg)
    assert ok
    await asyncio.sleep(0.3)
    assert len(received) >= 1
    assert received[0] == b"\xca\xfe\xba\xbe"

    await local.stop()
    await peer.stop()


# --- Stress: Concurrent Messages ---


async def test_concurrent_messages():
    """Multiple nodes send messages concurrently without errors."""
    hub = SCHubFunction(
        SCVMAC.random(),
        DeviceUUID.generate(),
        config=SCHubConfig(
            bind_address="127.0.0.1",
            bind_port=0,
            tls_config=_plaintext_tls(),
        ),
    )
    await hub.start()
    port = hub._server.sockets[0].getsockname()[1]

    count = 0

    def on_recv(npdu, _mac):
        nonlocal count
        count += 1

    receiver = SCTransport(
        SCTransportConfig(
            primary_hub_uri=f"ws://127.0.0.1:{port}",
            tls_config=_plaintext_tls(),
            min_reconnect_time=0.1,
        )
    )
    receiver.on_receive(on_recv)
    await receiver.start()
    await receiver.hub_connector.wait_connected(timeout=5)

    senders = []
    for _ in range(3):
        t = SCTransport(
            SCTransportConfig(
                primary_hub_uri=f"ws://127.0.0.1:{port}",
                tls_config=_plaintext_tls(),
                min_reconnect_time=0.1,
            )
        )
        await t.start()
        await t.hub_connector.wait_connected(timeout=5)
        senders.append(t)

    # Each sender sends 10 unicast messages with small delays to avoid
    # overwhelming the single-process event loop
    for sender in senders:
        for i in range(10):
            sender.send_unicast(bytes([i]), receiver.local_mac)
            await asyncio.sleep(0.01)

    # Wait for messages to propagate through the hub
    for _ in range(30):
        if count >= 25:
            break
        await asyncio.sleep(0.1)
    assert count >= 25  # Allow for some message loss in test env

    for t in senders:
        await t.stop()
    await receiver.stop()
    await hub.stop()
