"""Sans-I/O WebSocket wrapper for BACnet/SC (AB.7).

Uses the ``websockets`` library's sans-I/O protocol objects together with
``asyncio`` TCP/TLS streams.  Each :class:`SCWebSocket` instance owns one
WebSocket connection backed by a ``(StreamReader, StreamWriter)`` pair.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from websockets.client import ClientProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, ProtocolError
from websockets.frames import Close, Frame, Opcode
from websockets.http11 import Request
from websockets.server import ServerProtocol
from websockets.typing import Subprotocol
from websockets.uri import parse_uri

if TYPE_CHECKING:
    import ssl
    from asyncio import StreamReader, StreamWriter

logger = logging.getLogger(__name__)

# Read buffer size for asyncio streams
_READ_SIZE = 65536


def _drain_to_send(protocol: ClientProtocol | ServerProtocol) -> bytes:
    """Collect all pending outgoing data from the protocol."""
    chunks = protocol.data_to_send()
    return b"".join(chunks)


class SCWebSocket:
    """Async WebSocket connection using the websockets sans-I/O protocol.

    Each instance represents one open WebSocket connection and is backed
    by asyncio ``StreamReader``/``StreamWriter`` objects.  All framing is
    handled by the ``websockets`` sans-I/O ``ClientProtocol`` or
    ``ServerProtocol``.
    """

    def __init__(
        self,
        reader: StreamReader,
        writer: StreamWriter,
        protocol: ClientProtocol | ServerProtocol,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._protocol = protocol

    # -- Client factory --

    @classmethod
    async def connect(
        cls,
        uri: str,
        ssl_ctx: ssl.SSLContext | None,
        subprotocol: str,
    ) -> SCWebSocket:
        """Initiate a WebSocket client connection.

        :param uri: WebSocket URI (``wss://host:port/path``).
        :param ssl_ctx: TLS context, or None for plaintext ``ws://``.
        :param subprotocol: WebSocket subprotocol to negotiate.
        """
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        default_port = 443 if parsed.scheme == "wss" else 80
        port = parsed.port or default_port
        use_ssl = ssl_ctx if parsed.scheme == "wss" else None

        reader, writer = await asyncio.open_connection(host, port, ssl=use_ssl)

        ws_uri = parse_uri(uri)
        protocol = ClientProtocol(ws_uri, subprotocols=[Subprotocol(subprotocol)])

        request = protocol.connect()
        protocol.send_request(request)
        outgoing = _drain_to_send(protocol)
        if outgoing:
            writer.write(outgoing)
            await writer.drain()

        # Read HTTP response
        while True:
            data = await reader.read(_READ_SIZE)
            if not data:
                msg = "Connection closed during WebSocket handshake"
                raise ConnectionError(msg)
            protocol.receive_data(data)

            if protocol.handshake_exc is not None:
                raise protocol.handshake_exc

            # Check for events that indicate handshake completion
            events = protocol.events_received()
            if events:
                break

            # Also check if there's data to send (e.g. during upgrade)
            outgoing = _drain_to_send(protocol)
            if outgoing:
                writer.write(outgoing)
                await writer.drain()

        return cls(reader, writer, protocol)

    # -- Server factory --

    @classmethod
    async def accept(
        cls,
        reader: StreamReader,
        writer: StreamWriter,
        subprotocol: str,
    ) -> SCWebSocket:
        """Accept an inbound WebSocket connection on existing streams.

        :param reader: asyncio StreamReader from accepted connection.
        :param writer: asyncio StreamWriter from accepted connection.
        :param subprotocol: WebSocket subprotocol to accept.
        """
        protocol = ServerProtocol(subprotocols=[Subprotocol(subprotocol)])

        # Read the HTTP upgrade request
        while True:
            data = await reader.read(_READ_SIZE)
            if not data:
                msg = "Connection closed before WebSocket handshake"
                raise ConnectionError(msg)
            protocol.receive_data(data)

            events = protocol.events_received()
            if events:
                request = events[0]
                if not isinstance(request, Request):
                    msg = f"Expected HTTP request, got {type(request)}"
                    raise ProtocolError(msg)
                break

        # Accept the connection with the desired subprotocol
        response = protocol.accept(request)
        protocol.send_response(response)
        outgoing = _drain_to_send(protocol)
        if outgoing:
            writer.write(outgoing)
            await writer.drain()

        if protocol.handshake_exc is not None:
            raise protocol.handshake_exc

        return cls(reader, writer, protocol)

    # -- I/O operations --

    async def send(self, data: bytes) -> None:
        """Send a binary WebSocket frame."""
        self._protocol.send_binary(data)
        outgoing = _drain_to_send(self._protocol)
        if outgoing:
            self._writer.write(outgoing)
            await self._writer.drain()

    async def recv(self) -> bytes:
        """Receive the next binary WebSocket message.

        :raises ConnectionClosedOK: On graceful close.
        :raises ConnectionClosedError: On abnormal close.
        """
        while True:
            events = self._protocol.events_received()
            for event in events:
                if isinstance(event, Frame):
                    if event.opcode == Opcode.BINARY:
                        return bytes(event.data)
                    if event.opcode == Opcode.CLOSE:
                        rcvd = Close.parse(event.data) if event.data else None
                        await self._flush_outgoing()
                        raise ConnectionClosedOK(rcvd, None, rcvd_then_sent=None)
                    if event.opcode in (Opcode.PING, Opcode.PONG):
                        await self._flush_outgoing()
                        continue
                    continue

            # Need more data from the network
            data = await self._reader.read(_READ_SIZE)
            if not data:
                raise ConnectionClosedError(None, None, rcvd_then_sent=None)
            self._protocol.receive_data(data)

            if self._protocol.handshake_exc is not None:
                raise self._protocol.handshake_exc

            await self._flush_outgoing()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Initiate graceful WebSocket close."""
        try:
            self._protocol.send_close(code, reason)
            outgoing = _drain_to_send(self._protocol)
            if outgoing:
                self._writer.write(outgoing)
                await self._writer.drain()
            # Wait briefly for close acknowledgement
            try:
                async with asyncio.timeout(5):
                    data = await self._reader.read(_READ_SIZE)
                    if data:
                        self._protocol.receive_data(data)
            except (TimeoutError, OSError, ConnectionError):
                pass
        except (OSError, ConnectionError):
            pass
        finally:
            self._close_transport()

    async def _flush_outgoing(self) -> None:
        """Write any pending protocol output to the transport."""
        outgoing = _drain_to_send(self._protocol)
        if outgoing:
            self._writer.write(outgoing)
            with contextlib.suppress(OSError, ConnectionError):
                await self._writer.drain()

    def _close_transport(self) -> None:
        """Close the underlying TCP connection."""
        try:
            if not self._writer.is_closing():
                self._writer.close()
        except (OSError, RuntimeError):
            pass

    @property
    def is_open(self) -> bool:
        """Return True if the WebSocket connection appears open."""
        from websockets.protocol import State

        return self._protocol.state is State.OPEN

    @property
    def subprotocol(self) -> str | None:
        """Return the negotiated WebSocket subprotocol."""
        return self._protocol.subprotocol
