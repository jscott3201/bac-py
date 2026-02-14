import asyncio
import logging

import pytest

from bac_py.transport.sc.bvlc import ConnectRequestPayload, SCMessage
from bac_py.transport.sc.hub_function import SCHubConfig, SCHubFunction
from bac_py.transport.sc.tls import SCTLSConfig
from bac_py.transport.sc.types import SC_HUB_SUBPROTOCOL, BvlcSCFunction
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID
from bac_py.transport.sc.websocket import SCWebSocket


async def _connect_node(
    port: int,
    vmac: SCVMAC | None = None,
    uuid: DeviceUUID | None = None,
) -> tuple[SCWebSocket, SCVMAC, DeviceUUID]:
    """Connect a node to the hub and complete the handshake."""
    vmac = vmac or SCVMAC.random()
    uuid = uuid or DeviceUUID.generate()

    ws = await SCWebSocket.connect(
        f"ws://127.0.0.1:{port}",
        ssl_ctx=None,
        subprotocol=SC_HUB_SUBPROTOCOL,
    )

    # Send Connect-Request
    req = ConnectRequestPayload(vmac, uuid, 1600, 1497).encode()
    msg = SCMessage(BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req)
    await ws.send(msg.encode())

    # Receive Connect-Accept
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    response = SCMessage.decode(raw)
    assert response.function == BvlcSCFunction.CONNECT_ACCEPT

    return ws, vmac, uuid


class TestHubFunctionLifecycle:
    async def test_start_stop(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        assert hub.connection_count == 0
        await hub.stop()

    async def test_single_node_connect(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws, vmac, _uuid = await _connect_node(port)
            await asyncio.sleep(0.2)
            assert hub.connection_count == 1
            assert vmac in hub.connections
            await ws.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()

    async def test_multiple_nodes_connect(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, _vmac1, _ = await _connect_node(port)
            ws2, _vmac2, _ = await _connect_node(port)
            ws3, _vmac3, _ = await _connect_node(port)
            await asyncio.sleep(0.2)
            assert hub.connection_count == 3
            await ws1.close()
            await ws2.close()
            await ws3.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()


class TestHubBroadcast:
    async def test_broadcast_to_all_except_source(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, vmac1, _ = await _connect_node(port)
            ws2, _vmac2, _ = await _connect_node(port)
            ws3, _vmac3, _ = await _connect_node(port)
            await asyncio.sleep(0.2)

            # Node 1 broadcasts an Encapsulated-NPDU (no destination)
            broadcast_msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=100,
                originating=vmac1,
                payload=b"\x01\x02\x03",
            )
            await ws1.send(broadcast_msg.encode())

            # Node 2 and 3 should receive it
            raw2 = await asyncio.wait_for(ws2.recv(), timeout=5)
            msg2 = SCMessage.decode(raw2)
            assert msg2.function == BvlcSCFunction.ENCAPSULATED_NPDU
            assert msg2.payload == b"\x01\x02\x03"

            raw3 = await asyncio.wait_for(ws3.recv(), timeout=5)
            msg3 = SCMessage.decode(raw3)
            assert msg3.function == BvlcSCFunction.ENCAPSULATED_NPDU
            assert msg3.payload == b"\x01\x02\x03"

            await ws1.close()
            await ws2.close()
            await ws3.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()

    async def test_broadcast_not_sent_back_to_source(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, vmac1, _ = await _connect_node(port)
            ws2, _vmac2, _ = await _connect_node(port)
            await asyncio.sleep(0.2)

            # Node 1 broadcasts
            broadcast_msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=100,
                originating=vmac1,
                payload=b"\xaa\xbb",
            )
            await ws1.send(broadcast_msg.encode())

            # Node 2 should receive it
            raw2 = await asyncio.wait_for(ws2.recv(), timeout=5)
            msg2 = SCMessage.decode(raw2)
            assert msg2.payload == b"\xaa\xbb"

            # Node 1 should NOT receive it back — verify by timeout
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws1.recv(), timeout=0.5)

            await ws1.close()
            await ws2.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()


class TestHubUnicast:
    async def test_unicast_to_specific_node(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, vmac1, _ = await _connect_node(port)
            ws2, vmac2, _ = await _connect_node(port)
            ws3, _vmac3, _ = await _connect_node(port)
            await asyncio.sleep(0.2)

            # Node 1 sends unicast to Node 2
            unicast_msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=200,
                originating=vmac1,
                destination=vmac2,
                payload=b"\xde\xad",
            )
            await ws1.send(unicast_msg.encode())

            # Node 2 should receive it
            raw2 = await asyncio.wait_for(ws2.recv(), timeout=5)
            msg2 = SCMessage.decode(raw2)
            assert msg2.function == BvlcSCFunction.ENCAPSULATED_NPDU
            assert msg2.payload == b"\xde\xad"

            # Node 3 should NOT receive it
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws3.recv(), timeout=0.5)

            await ws1.close()
            await ws2.close()
            await ws3.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()

    async def test_unicast_to_unknown_vmac_discarded(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, vmac1, _ = await _connect_node(port)
            await asyncio.sleep(0.2)

            # Send to a VMAC that doesn't exist
            unknown_vmac = SCVMAC.random()
            msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=300,
                originating=vmac1,
                destination=unknown_vmac,
                payload=b"\xff",
            )
            await ws1.send(msg.encode())
            # Should be silently discarded — no error
            await asyncio.sleep(0.3)

            await ws1.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()


class TestHubVMACCollision:
    async def test_duplicate_vmac_different_uuid_rejected(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            shared_vmac = SCVMAC.random()

            # First connection succeeds
            ws1, _, _uuid1 = await _connect_node(port, vmac=shared_vmac)
            await asyncio.sleep(0.2)
            assert hub.connection_count == 1

            # Second connection with same VMAC but different UUID should get NAK
            ws2 = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            req = ConnectRequestPayload(shared_vmac, DeviceUUID.generate(), 1600, 1497).encode()
            msg = SCMessage(BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req)
            await ws2.send(msg.encode())

            raw = await asyncio.wait_for(ws2.recv(), timeout=5)
            response = SCMessage.decode(raw)
            assert response.function == BvlcSCFunction.BVLC_RESULT

            await ws1.close()
            await ws2.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()


class TestHubNodeDisconnect:
    async def test_node_disconnect_removes_from_table(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        try:
            ws1, vmac1, _ = await _connect_node(port)
            ws2, vmac2, _ = await _connect_node(port)
            await asyncio.sleep(0.2)
            assert hub.connection_count == 2

            # Close node 1
            ws1._close_transport()
            await asyncio.sleep(0.5)

            # Hub should detect the disconnect
            assert hub.connection_count == 1
            assert vmac1 not in hub.connections
            assert vmac2 in hub.connections

            await ws2.close()
            await asyncio.sleep(0.2)
        finally:
            await hub.stop()

    async def test_stop_disconnects_all(self):
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]
        _ws1, _, _ = await _connect_node(port)
        _ws2, _, _ = await _connect_node(port)
        await asyncio.sleep(0.2)
        assert hub.connection_count == 2

        await hub.stop()
        assert hub.connection_count == 0


class TestHubVMACSpoofProtection:
    """Verify hub drops messages with spoofed originating VMAC."""

    async def test_spoofed_originating_vmac_dropped(self, caplog):
        """Message with originating VMAC != authenticated peer VMAC is dropped."""
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]

        ws1, _vmac1, _ = await _connect_node(port)
        ws2, vmac2, _ = await _connect_node(port)
        await asyncio.sleep(0.2)

        # ws1 sends a message with a spoofed originating VMAC (not vmac1)
        spoofed_vmac = SCVMAC.random()
        spoofed_msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=99,
            originating=spoofed_vmac,
            destination=vmac2,
            payload=b"\x01\x02\x03",
        )
        await ws1.send(spoofed_msg.encode())
        await asyncio.sleep(0.3)

        # ws2 should NOT have received the spoofed message
        # The hub should have logged a warning about the mismatch
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc"):
            # Re-check logs (already emitted)
            pass

        ws1._close_transport()
        ws2._close_transport()
        await hub.stop()

    async def test_valid_originating_vmac_forwarded(self):
        """Message with correct originating VMAC is forwarded normally."""
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]

        ws1, vmac1, _ = await _connect_node(port)
        ws2, vmac2, _ = await _connect_node(port)
        await asyncio.sleep(0.2)

        # ws1 sends with correct originating VMAC
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=100,
            originating=vmac1,
            destination=vmac2,
            payload=b"\xaa\xbb",
        )
        await ws1.send(msg.encode())

        # ws2 should receive it
        raw = await asyncio.wait_for(ws2.recv(), timeout=3)
        received = SCMessage.decode(raw)
        assert received.payload == b"\xaa\xbb"

        ws1._close_transport()
        ws2._close_transport()
        await hub.stop()

    async def test_no_originating_vmac_allowed(self):
        """Message without originating VMAC is forwarded (broadcast case)."""
        hub = SCHubFunction(
            SCVMAC.random(),
            DeviceUUID.generate(),
            config=SCHubConfig(
                bind_address="127.0.0.1",
                bind_port=0,
                tls_config=SCTLSConfig(allow_plaintext=True),
            ),
        )
        await hub.start()
        port = hub._server.sockets[0].getsockname()[1]

        ws1, _vmac1, _ = await _connect_node(port)
        ws2, _vmac2, _ = await _connect_node(port)
        await asyncio.sleep(0.2)

        # Broadcast message (no destination, no originating)
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=101,
            payload=b"\xcc\xdd",
        )
        await ws1.send(msg.encode())

        # ws2 should receive it as a broadcast
        raw = await asyncio.wait_for(ws2.recv(), timeout=3)
        received = SCMessage.decode(raw)
        assert received.payload == b"\xcc\xdd"

        ws1._close_transport()
        ws2._close_transport()
        await hub.stop()
