import asyncio
import logging

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from bac_py.transport.sc.types import SC_DIRECT_SUBPROTOCOL, SC_HUB_SUBPROTOCOL
from bac_py.transport.sc.websocket import SCWebSocket


async def _start_ws_server(subprotocol: str = SC_HUB_SUBPROTOCOL):
    """Start a loopback WebSocket server, return (server, port, accepted_ws_future)."""
    accepted_future: asyncio.Future[SCWebSocket] = asyncio.get_event_loop().create_future()

    async def on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            ws = await SCWebSocket.accept(reader, writer, subprotocol)
            if not accepted_future.done():
                accepted_future.set_result(ws)
        except Exception as exc:
            if not accepted_future.done():
                accepted_future.set_exception(exc)

    server = await asyncio.start_server(on_connect, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, accepted_future


class TestSCWebSocketClientServer:
    async def test_connect_and_accept(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)
            assert client_ws.is_open
            assert server_ws.is_open
            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_send_recv_binary(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            # Client → Server
            test_data = b"\x01\x02\x03\x04\x05"
            await client_ws.send(test_data)
            received = await asyncio.wait_for(server_ws.recv(), timeout=5)
            assert received == test_data

            # Server → Client
            response_data = b"\x0a\x0b\x0c"
            await server_ws.send(response_data)
            received = await asyncio.wait_for(client_ws.recv(), timeout=5)
            assert received == response_data

            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_large_binary_message(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            # Send a large message (larger than typical BACnet NPDU)
            large_data = bytes(range(256)) * 20  # 5120 bytes
            await client_ws.send(large_data)
            received = await asyncio.wait_for(server_ws.recv(), timeout=5)
            assert received == large_data

            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_multiple_messages(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            for i in range(10):
                msg = bytes([i]) * (i + 1)
                await client_ws.send(msg)
                received = await asyncio.wait_for(server_ws.recv(), timeout=5)
                assert received == msg

            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_graceful_close_by_client(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            await client_ws.close()

            # Server should detect the close
            with pytest.raises((ConnectionClosedOK, ConnectionClosedError, ConnectionError)):
                await asyncio.wait_for(server_ws.recv(), timeout=5)
        finally:
            server.close()
            await server.wait_closed()


class TestSCWebSocketSubprotocol:
    async def test_hub_subprotocol(self):
        server, port, accepted = await _start_ws_server(SC_HUB_SUBPROTOCOL)
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)
            # At least one side should report the subprotocol
            assert (
                client_ws.subprotocol == SC_HUB_SUBPROTOCOL
                or server_ws.subprotocol == SC_HUB_SUBPROTOCOL
            )
            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()

    async def test_direct_subprotocol(self):
        server, port, accepted = await _start_ws_server(SC_DIRECT_SUBPROTOCOL)
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_DIRECT_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)
            assert (
                client_ws.subprotocol == SC_DIRECT_SUBPROTOCOL
                or server_ws.subprotocol == SC_DIRECT_SUBPROTOCOL
            )
            await client_ws.close()
            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()


class TestSCWebSocketConnectionErrors:
    async def test_connect_refused(self):
        with pytest.raises((ConnectionRefusedError, OSError)):
            await SCWebSocket.connect(
                "ws://127.0.0.1:19999",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )

    async def test_recv_after_connection_lost(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            # Force-close the server side transport
            server_ws._close_transport()

            # Client should detect the closed connection
            with pytest.raises((ConnectionClosedError, ConnectionClosedOK, ConnectionError)):
                await asyncio.wait_for(client_ws.recv(), timeout=5)
        finally:
            server.close()
            await server.wait_closed()

    async def test_is_open_property(self):
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            assert client_ws.is_open
            await client_ws.close()
            # After close, is_open should be False
            assert not client_ws.is_open

            await server_ws.close()
        finally:
            server.close()
            await server.wait_closed()


class TestWebSocketFrameSizeLimit:
    """Verify max_frame_size enforcement in recv()."""

    async def test_oversized_frame_dropped(self, caplog):
        """Frames exceeding max_frame_size are silently dropped."""
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            # Set a small frame size limit on the server side
            server_ws._max_frame_size = 10

            # Send oversized then valid message — recv() should skip the big one
            await client_ws.send(b"\x00" * 50)  # over limit
            await asyncio.sleep(0.05)
            await client_ws.send(b"\x04\x05\x06")  # within limit

            with caplog.at_level(logging.WARNING, logger="bac_py.transport.sc"):
                data = await asyncio.wait_for(server_ws.recv(), timeout=5)
            assert data == b"\x04\x05\x06"
            assert any("too large" in m for m in caplog.messages)

            client_ws._close_transport()
            server_ws._close_transport()
        finally:
            server.close()
            await server.wait_closed()

    async def test_no_frame_size_limit_accepts_all(self):
        """With max_frame_size=0 (default), all frames pass through."""
        server, port, accepted = await _start_ws_server()
        try:
            client_ws = await SCWebSocket.connect(
                f"ws://127.0.0.1:{port}",
                ssl_ctx=None,
                subprotocol=SC_HUB_SUBPROTOCOL,
            )
            server_ws = await asyncio.wait_for(accepted, timeout=5)

            assert server_ws._max_frame_size == 0  # Default

            # Large frame should be accepted
            large = b"\xaa" * 5000
            await client_ws.send(large)
            data = await asyncio.wait_for(server_ws.recv(), timeout=5)
            assert data == large

            client_ws._close_transport()
            server_ws._close_transport()
        finally:
            server.close()
            await server.wait_closed()
