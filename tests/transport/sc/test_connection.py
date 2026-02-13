import asyncio

import pytest

from bac_py.transport.sc.bvlc import (
    BvlcResultPayload,
    ConnectAcceptPayload,
    ConnectRequestPayload,
    SCMessage,
)
from bac_py.transport.sc.connection import (
    SCConnection,
    SCConnectionConfig,
    SCConnectionRole,
    SCConnectionState,
)
from bac_py.transport.sc.types import BvlcSCFunction, SCResultCode
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID
from bac_py.transport.sc.websocket import SCWebSocket

SC_SUBPROTOCOL = "hub.bsc.bacnet.org"


async def _start_ws_pair():
    """Create a connected client/server WebSocket pair on loopback."""
    accepted_future: asyncio.Future[SCWebSocket] = asyncio.get_event_loop().create_future()

    async def on_connect(reader, writer):
        try:
            ws = await SCWebSocket.accept(reader, writer, SC_SUBPROTOCOL)
            if not accepted_future.done():
                accepted_future.set_result(ws)
        except Exception as exc:
            if not accepted_future.done():
                accepted_future.set_exception(exc)

    server = await asyncio.start_server(on_connect, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client_ws = await SCWebSocket.connect(
        f"ws://127.0.0.1:{port}", ssl_ctx=None, subprotocol=SC_SUBPROTOCOL
    )
    server_ws = await asyncio.wait_for(accepted_future, timeout=5)
    return server, client_ws, server_ws


class TestInitiatingPeerLifecycle:
    async def test_full_lifecycle_connected(self):
        """IDLE → AWAITING_ACCEPT → CONNECTED → disconnect → IDLE."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            local_vmac = SCVMAC.random()
            local_uuid = DeviceUUID.generate()
            remote_vmac = SCVMAC.random()
            remote_uuid = DeviceUUID.generate()

            conn = SCConnection(local_vmac, local_uuid)
            connected_event = asyncio.Event()
            disconnected_event = asyncio.Event()
            conn.on_connected = connected_event.set
            conn.on_disconnected = disconnected_event.set

            # Start initiating in background
            init_task = asyncio.ensure_future(conn.initiate(client_ws))

            # Server side: read Connect-Request, send Connect-Accept
            raw = await asyncio.wait_for(server_ws.recv(), timeout=5)
            msg = SCMessage.decode(raw)
            assert msg.function == BvlcSCFunction.CONNECT_REQUEST
            req = ConnectRequestPayload.decode(msg.payload)
            assert req.vmac == local_vmac

            accept_payload = ConnectAcceptPayload(remote_vmac, remote_uuid, 1600, 1497).encode()
            accept_msg = SCMessage(
                BvlcSCFunction.CONNECT_ACCEPT,
                message_id=msg.message_id,
                payload=accept_payload,
            )
            await server_ws.send(accept_msg.encode())

            await asyncio.wait_for(init_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            assert conn.state == SCConnectionState.CONNECTED
            assert conn.peer_vmac == remote_vmac
            assert conn.peer_uuid == remote_uuid
            assert conn.peer_max_bvlc == 1600

            # Disconnect
            disconnect_task = asyncio.ensure_future(conn.disconnect())

            # Server reads Disconnect-Request, sends Disconnect-ACK
            raw = await asyncio.wait_for(server_ws.recv(), timeout=5)
            msg = SCMessage.decode(raw)
            assert msg.function == BvlcSCFunction.DISCONNECT_REQUEST
            ack = SCMessage(BvlcSCFunction.DISCONNECT_ACK, message_id=msg.message_id)
            await server_ws.send(ack.encode())

            await asyncio.wait_for(disconnect_task, timeout=5)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await server_ws.close()
            server.close()
            await server.wait_closed()

    async def test_connect_timeout(self):
        """IDLE → AWAITING_ACCEPT → IDLE on timeout."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCConnectionConfig(connect_wait_timeout=0.5),
            )
            # Don't respond from server — let it timeout
            await conn.initiate(client_ws)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await server_ws.close()
            server.close()
            await server.wait_closed()

    async def test_vmac_collision_nak(self):
        """AWAITING_ACCEPT → IDLE on VMAC collision NAK."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            collision_detected = asyncio.Event()
            conn.on_vmac_collision = collision_detected.set

            init_task = asyncio.ensure_future(conn.initiate(client_ws))

            # Server: read Connect-Request, send NAK with NODE_DUPLICATE_VMAC
            raw = await asyncio.wait_for(server_ws.recv(), timeout=5)
            msg = SCMessage.decode(raw)
            nak_payload = BvlcResultPayload(
                BvlcSCFunction.CONNECT_REQUEST,
                SCResultCode.NAK,
                error_header_marker=0x00,
                error_class=7,
                error_code=0x0071,  # NODE_DUPLICATE_VMAC
            ).encode()
            nak_msg = SCMessage(
                BvlcSCFunction.BVLC_RESULT,
                message_id=msg.message_id,
                payload=nak_payload,
            )
            await server_ws.send(nak_msg.encode())

            await asyncio.wait_for(init_task, timeout=5)
            assert conn.state == SCConnectionState.IDLE
            assert collision_detected.is_set()
        finally:
            await server_ws.close()
            server.close()
            await server.wait_closed()

    async def test_generic_nak(self):
        """AWAITING_ACCEPT → IDLE on generic NAK."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            init_task = asyncio.ensure_future(conn.initiate(client_ws))

            raw = await asyncio.wait_for(server_ws.recv(), timeout=5)
            msg = SCMessage.decode(raw)
            nak_payload = BvlcResultPayload(
                BvlcSCFunction.CONNECT_REQUEST,
                SCResultCode.NAK,
                error_header_marker=0x00,
                error_class=7,
                error_code=0x000B,  # BVLC_FUNCTION_UNKNOWN
            ).encode()
            nak_msg = SCMessage(
                BvlcSCFunction.BVLC_RESULT,
                message_id=msg.message_id,
                payload=nak_payload,
            )
            await server_ws.send(nak_msg.encode())

            await asyncio.wait_for(init_task, timeout=5)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await server_ws.close()
            server.close()
            await server.wait_closed()


class TestAcceptingPeerLifecycle:
    async def test_full_lifecycle_connected(self):
        """IDLE → AWAITING_REQUEST → CONNECTED → disconnect from initiator → IDLE."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            local_vmac = SCVMAC.random()
            local_uuid = DeviceUUID.generate()
            remote_vmac = SCVMAC.random()
            remote_uuid = DeviceUUID.generate()

            conn = SCConnection(local_vmac, local_uuid)
            connected_event = asyncio.Event()
            conn.on_connected = connected_event.set

            # Start accepting in background
            accept_task = asyncio.ensure_future(conn.accept(server_ws))

            # Client sends Connect-Request
            req_payload = ConnectRequestPayload(remote_vmac, remote_uuid, 1600, 1497).encode()
            req_msg = SCMessage(BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload)
            await client_ws.send(req_msg.encode())

            # Client reads Connect-Accept
            raw = await asyncio.wait_for(client_ws.recv(), timeout=5)
            accept = SCMessage.decode(raw)
            assert accept.function == BvlcSCFunction.CONNECT_ACCEPT
            accept_p = ConnectAcceptPayload.decode(accept.payload)
            assert accept_p.vmac == local_vmac
            assert accept_p.uuid == local_uuid

            await asyncio.wait_for(accept_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            assert conn.state == SCConnectionState.CONNECTED
            assert conn.peer_vmac == remote_vmac
            assert conn.role == SCConnectionRole.ACCEPTING

            # Clean up
            await conn.disconnect()
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()

    async def test_accept_timeout(self):
        """AWAITING_REQUEST → IDLE on timeout (no Connect-Request)."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCConnectionConfig(connect_wait_timeout=0.5),
            )
            await conn.accept(server_ws)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()

    async def test_vmac_collision_rejected(self):
        """AWAITING_REQUEST → IDLE when VMAC checker rejects."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())

            def reject_all(vmac: SCVMAC, uuid: DeviceUUID) -> bool:
                return False  # Reject everything

            accept_task = asyncio.ensure_future(conn.accept(server_ws, vmac_checker=reject_all))

            # Client sends Connect-Request
            req_payload = ConnectRequestPayload(
                SCVMAC.random(), DeviceUUID.generate(), 1600, 1497
            ).encode()
            req_msg = SCMessage(BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload)
            await client_ws.send(req_msg.encode())

            # Client should receive NAK
            raw = await asyncio.wait_for(client_ws.recv(), timeout=5)
            nak = SCMessage.decode(raw)
            assert nak.function == BvlcSCFunction.BVLC_RESULT
            result = BvlcResultPayload.decode(nak.payload)
            assert result.result_code == SCResultCode.NAK
            assert result.error_code == 0x0071  # NODE_DUPLICATE_VMAC

            await asyncio.wait_for(accept_task, timeout=5)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()

    async def test_wrong_message_type_rejected(self):
        """AWAITING_REQUEST → IDLE when non-Connect-Request received."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(
                SCVMAC.random(),
                DeviceUUID.generate(),
                config=SCConnectionConfig(connect_wait_timeout=2.0),
            )
            accept_task = asyncio.ensure_future(conn.accept(server_ws))

            # Send a heartbeat instead of connect request
            msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=1)
            await client_ws.send(msg.encode())

            await asyncio.wait_for(accept_task, timeout=5)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()


class TestMessageForwarding:
    async def test_encapsulated_npdu_forwarded(self):
        """CONNECTED state forwards Encapsulated-NPDU to on_message callback."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            received_messages: list[SCMessage] = []
            connected_event = asyncio.Event()

            async def on_msg(msg: SCMessage):
                received_messages.append(msg)

            conn.on_connected = connected_event.set
            conn.on_message = on_msg

            # Do handshake
            accept_task = asyncio.ensure_future(conn.accept(server_ws))
            req_payload = ConnectRequestPayload(
                SCVMAC.random(), DeviceUUID.generate(), 1600, 1497
            ).encode()
            await client_ws.send(
                SCMessage(
                    BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload
                ).encode()
            )
            await asyncio.wait_for(client_ws.recv(), timeout=5)
            await asyncio.wait_for(accept_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            # Now send Encapsulated-NPDU
            npdu_msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=100,
                payload=b"\x01\x04\x00\x05",
            )
            await client_ws.send(npdu_msg.encode())
            await asyncio.sleep(0.2)

            assert len(received_messages) == 1
            assert received_messages[0].function == BvlcSCFunction.ENCAPSULATED_NPDU
            assert received_messages[0].payload == b"\x01\x04\x00\x05"

            await conn.disconnect()
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()


class TestHeartbeat:
    async def test_heartbeat_request_answered(self):
        """Accepting peer responds to heartbeat with ACK."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            connected_event = asyncio.Event()
            conn.on_connected = connected_event.set

            accept_task = asyncio.ensure_future(conn.accept(server_ws))
            req_payload = ConnectRequestPayload(
                SCVMAC.random(), DeviceUUID.generate(), 1600, 1497
            ).encode()
            await client_ws.send(
                SCMessage(
                    BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload
                ).encode()
            )
            await asyncio.wait_for(client_ws.recv(), timeout=5)
            await asyncio.wait_for(accept_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            # Send heartbeat request from initiating side
            hb = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=42)
            await client_ws.send(hb.encode())

            # Should receive heartbeat ACK
            raw = await asyncio.wait_for(client_ws.recv(), timeout=5)
            ack = SCMessage.decode(raw)
            assert ack.function == BvlcSCFunction.HEARTBEAT_ACK
            assert ack.message_id == 42

            await conn.disconnect()
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()


class TestDisconnectHandling:
    async def test_disconnect_request_from_peer(self):
        """CONNECTED → IDLE on Disconnect-Request from peer."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            connected_event = asyncio.Event()
            disconnected_event = asyncio.Event()
            conn.on_connected = connected_event.set
            conn.on_disconnected = disconnected_event.set

            accept_task = asyncio.ensure_future(conn.accept(server_ws))
            req_payload = ConnectRequestPayload(
                SCVMAC.random(), DeviceUUID.generate(), 1600, 1497
            ).encode()
            await client_ws.send(
                SCMessage(
                    BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload
                ).encode()
            )
            await asyncio.wait_for(client_ws.recv(), timeout=5)
            await asyncio.wait_for(accept_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            # Peer sends Disconnect-Request
            disc = SCMessage(BvlcSCFunction.DISCONNECT_REQUEST, message_id=77)
            await client_ws.send(disc.encode())

            # Should receive Disconnect-ACK
            raw = await asyncio.wait_for(client_ws.recv(), timeout=5)
            ack = SCMessage.decode(raw)
            assert ack.function == BvlcSCFunction.DISCONNECT_ACK
            assert ack.message_id == 77

            await asyncio.wait_for(disconnected_event.wait(), timeout=5)
            assert conn.state == SCConnectionState.IDLE
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()


class TestSendMessage:
    async def test_send_when_connected(self):
        """send_message works in CONNECTED state."""
        server, client_ws, server_ws = await _start_ws_pair()
        try:
            conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
            connected_event = asyncio.Event()
            conn.on_connected = connected_event.set

            accept_task = asyncio.ensure_future(conn.accept(server_ws))
            req_payload = ConnectRequestPayload(
                SCVMAC.random(), DeviceUUID.generate(), 1600, 1497
            ).encode()
            await client_ws.send(
                SCMessage(
                    BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=req_payload
                ).encode()
            )
            await asyncio.wait_for(client_ws.recv(), timeout=5)
            await asyncio.wait_for(accept_task, timeout=5)
            await asyncio.wait_for(connected_event.wait(), timeout=5)

            # Send from connection
            test_msg = SCMessage(
                BvlcSCFunction.ENCAPSULATED_NPDU,
                message_id=200,
                payload=b"\xde\xad",
            )
            await conn.send_message(test_msg)

            raw = await asyncio.wait_for(client_ws.recv(), timeout=5)
            received = SCMessage.decode(raw)
            assert received.function == BvlcSCFunction.ENCAPSULATED_NPDU
            assert received.payload == b"\xde\xad"

            await conn.disconnect()
        finally:
            await client_ws.close()
            server.close()
            await server.wait_closed()

    async def test_send_when_not_connected_raises(self):
        conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=1)
        with pytest.raises(ConnectionError, match="not in CONNECTED"):
            await conn.send_message(msg)


class TestConnectionProperties:
    def test_initial_state(self):
        conn = SCConnection(SCVMAC.random(), DeviceUUID.generate())
        assert conn.state == SCConnectionState.IDLE
        assert conn.role is None
        assert conn.peer_vmac is None
        assert conn.peer_uuid is None

    def test_local_vmac_setter(self):
        vmac1 = SCVMAC.random()
        vmac2 = SCVMAC.random()
        conn = SCConnection(vmac1, DeviceUUID.generate())
        assert conn.local_vmac == vmac1
        conn.local_vmac = vmac2
        assert conn.local_vmac == vmac2
