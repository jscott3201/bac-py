"""Sans-I/O WebSocket wrapper for BACnet/SC (AB.7).

Uses the ``websockets`` library's sans-I/O protocol objects together with
``asyncio`` TCP/TLS streams.  Each :class:`SCWebSocket` instance owns one
WebSocket connection backed by a ``(StreamReader, StreamWriter)`` pair.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from websockets.client import ClientProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, ProtocolError
from websockets.frames import Close, Frame, Opcode
from websockets.http11 import Request
from websockets.protocol import State as _WSState
from websockets.server import ServerProtocol
from websockets.typing import Subprotocol
from websockets.uri import parse_uri

if TYPE_CHECKING:
    import ssl
    from asyncio import StreamReader, StreamWriter

logger = logging.getLogger(__name__)

# Read buffer size for asyncio streams
_READ_SIZE = 65536

# Write buffer high/low water marks for StreamWriter.  Lower than the
# asyncio default (64 KiB) so that backpressure triggers earlier for
# slow or dead peers — BACnet/SC frames are typically < 1600 bytes.
_WRITE_HIGH_WATER = 32768
_WRITE_LOW_WATER = 8192


def _set_nodelay(writer: StreamWriter) -> None:
    """Enable TCP_NODELAY and tune write buffer limits on the socket.

    Disables Nagle's algorithm so small BACnet/SC frames are sent immediately
    rather than being buffered.  Critical for low-latency request-response
    patterns where Nagle + delayed-ACK interaction can add 40-200ms stalls.

    Also sets write buffer water marks lower than the asyncio default so
    backpressure triggers earlier for slow peers.
    """
    sock = writer.get_extra_info("socket")
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    transport = writer.transport
    if transport is not None:
        transport.set_write_buffer_limits(high=_WRITE_HIGH_WATER, low=_WRITE_LOW_WATER)


def _drain_to_send(protocol: ClientProtocol | ServerProtocol) -> bytes:
    """Collect all pending outgoing data from the protocol."""
    chunks = protocol.data_to_send()
    return b"".join(chunks)


def _write_pending(protocol: ClientProtocol | ServerProtocol, writer: StreamWriter) -> bool:
    """Write all pending protocol data directly to the writer.

    Writes each chunk individually to avoid the ``b"".join()`` copy.
    Returns True if any data was written.
    """
    wrote = False
    for chunk in protocol.data_to_send():
        if chunk:
            writer.write(chunk)
            wrote = True
    return wrote


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
        *,
        max_frame_size: int = 0,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._protocol = protocol
        self._max_frame_size = max_frame_size
        # Buffer for events not yet consumed by recv().  When multiple
        # WebSocket frames arrive in one TCP segment, events_received()
        # returns all of them but recv() processes only one at a time.
        self._pending_events: list[Frame] = []

    # -- Client factory --

    @classmethod
    async def connect(
        cls,
        uri: str,
        ssl_ctx: ssl.SSLContext | None,
        subprotocol: str,
        *,
        handshake_timeout: float = 10.0,
        max_size: int | None = None,
    ) -> SCWebSocket:
        """Initiate a WebSocket client connection.

        :param uri: WebSocket URI (``wss://host:port/path``).
        :param ssl_ctx: TLS context, or None for plaintext ``ws://``.
        :param subprotocol: WebSocket subprotocol to negotiate.
        :param handshake_timeout: Maximum seconds for the WebSocket handshake.
        :param max_size: Maximum WebSocket message size.  Passed to the
            protocol layer so oversized frames are rejected early.
        """
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        default_port = 443 if parsed.scheme == "wss" else 80
        port = parsed.port or default_port
        use_ssl = ssl_ctx if parsed.scheme == "wss" else None

        if use_ssl is None:
            logger.warning(
                "SC WebSocket connecting WITHOUT TLS to %s:%d — "
                "traffic is unencrypted and unauthenticated. "
                "BACnet/SC requires TLS 1.3 in production (Annex AB.7.4).",
                host,
                port,
            )
        else:
            logger.debug("SC WebSocket connecting (TLS) to %s:%d", host, port)
        reader, writer = await asyncio.open_connection(host, port, ssl=use_ssl)
        _set_nodelay(writer)

        ws_uri = parse_uri(uri)
        protocol = ClientProtocol(
            ws_uri,
            subprotocols=[Subprotocol(subprotocol)],
            max_size=max_size,
        )

        request = protocol.connect()
        protocol.send_request(request)
        outgoing = _drain_to_send(protocol)
        if outgoing:
            writer.write(outgoing)
            await writer.drain()

        # Read HTTP response (with timeout to prevent indefinite hangs)
        try:
            async with asyncio.timeout(handshake_timeout):
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
        except BaseException:
            writer.close()
            raise

        logger.debug("SC WebSocket client connected to %s:%d", host, port)
        return cls(reader, writer, protocol)

    # -- Server factory --

    @classmethod
    async def accept(
        cls,
        reader: StreamReader,
        writer: StreamWriter,
        subprotocol: str,
        *,
        handshake_timeout: float = 10.0,
        max_size: int | None = None,
    ) -> SCWebSocket:
        """Accept an inbound WebSocket connection on existing streams.

        :param reader: asyncio StreamReader from accepted connection.
        :param writer: asyncio StreamWriter from accepted connection.
        :param subprotocol: WebSocket subprotocol to accept.
        :param handshake_timeout: Maximum seconds to wait for the handshake.
        :param max_size: Maximum WebSocket message size.  Passed to the
            protocol layer so oversized frames are rejected early.
        """
        protocol = ServerProtocol(
            subprotocols=[Subprotocol(subprotocol)],
            max_size=max_size,
        )
        _set_nodelay(writer)

        # Read the HTTP upgrade request (with timeout to prevent slow clients)
        async with asyncio.timeout(handshake_timeout):
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

        logger.debug("SC WebSocket server accepted connection")
        return cls(reader, writer, protocol)

    # -- I/O operations --

    async def send(self, data: bytes) -> None:
        """Send a binary WebSocket frame."""
        logger.debug("SC WebSocket send: %d bytes", len(data))
        self._protocol.send_binary(data)
        if _write_pending(self._protocol, self._writer):
            await self._writer.drain()

    send_raw = send  # Alias — same operation, named for semantic clarity

    def write_no_drain(self, data: bytes) -> bool:
        """Buffer a binary WebSocket frame without draining.

        Returns True if data was written to the transport buffer.
        Call :meth:`drain` afterwards to flush.  Used by hub broadcast
        to batch writes across connections before draining concurrently.
        """
        self._protocol.send_binary(data)
        return _write_pending(self._protocol, self._writer)

    async def drain(self) -> None:
        """Drain the write buffer.  Pair with :meth:`write_no_drain`."""
        await self._writer.drain()

    async def recv(self) -> bytes:
        """Receive the next binary WebSocket message.

        :raises ConnectionClosedOK: On graceful close.
        :raises ConnectionClosedError: On abnormal close.
        """
        while True:
            # Drain pending events first (from a previous multi-frame read)
            while self._pending_events:
                event = self._pending_events.pop(0)
                result = await self._process_frame(event)
                if result is not None:
                    return result

            # Fetch new events from the protocol
            events = self._protocol.events_received()
            for i, raw_event in enumerate(events):
                if isinstance(raw_event, Frame):
                    result = await self._process_frame(raw_event)
                    if result is not None:
                        # Stash remaining events for subsequent recv() calls
                        for remaining in events[i + 1 :]:
                            if isinstance(remaining, Frame):
                                self._pending_events.append(remaining)
                        return result

            # Need more data from the network
            data = await self._reader.read(_READ_SIZE)
            if not data:
                logger.warning("SC WebSocket connection closed unexpectedly")
                raise ConnectionClosedError(None, None, rcvd_then_sent=None)
            self._protocol.receive_data(data)

            if self._protocol.handshake_exc is not None:
                raise self._protocol.handshake_exc

            await self._flush_outgoing()

    async def _process_frame(self, event: Frame) -> bytes | None:
        """Process a single WebSocket frame.

        Returns the payload bytes for BINARY frames, None for control frames.
        Raises on CLOSE frames.
        """
        if event.opcode == Opcode.BINARY:
            if self._max_frame_size and len(event.data) > self._max_frame_size:
                logger.warning(
                    "SC WebSocket frame too large: %d bytes (max %d), dropping",
                    len(event.data),
                    self._max_frame_size,
                )
                return None
            logger.debug("SC WebSocket recv: %d bytes", len(event.data))
            return bytes(event.data)
        if event.opcode == Opcode.CLOSE:
            rcvd = Close.parse(event.data) if event.data else None
            await self._flush_outgoing()
            raise ConnectionClosedOK(rcvd, None, rcvd_then_sent=None)
        if event.opcode in (Opcode.PING, Opcode.PONG):
            await self._flush_outgoing()
        return None

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
        if _write_pending(self._protocol, self._writer):
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
        return self._protocol.state is _WSState.OPEN

    @property
    def subprotocol(self) -> str | None:
        """Return the negotiated WebSocket subprotocol."""
        return self._protocol.subprotocol
