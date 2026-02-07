"""BACnet/IP transport using asyncio UDP per Annex J."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bvll import decode_bvll, encode_bvll
from bac_py.types.enums import BvlcFunction

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class _UDPProtocol(asyncio.DatagramProtocol):
    """Low-level asyncio DatagramProtocol wrapper."""

    def __init__(self, callback: Callable[[bytes, tuple[str, int]], None]) -> None:
        self._callback = callback

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming UDP datagram."""
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        """Handle transport errors."""
        logger.warning("UDP transport error: %s", exc)


class BIPTransport:
    """BACnet/IP transport using asyncio UDP.

    Provides send/receive for BACnet/IP datagrams wrapped in BVLL.
    """

    def __init__(
        self,
        interface: str = "0.0.0.0",
        port: int = 0xBAC0,
    ) -> None:
        self._interface = interface
        self._port = port
        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._receive_callback: Callable[[bytes, BIPAddress], None] | None = None
        self._local_address: BIPAddress | None = None

    async def start(self) -> None:
        """Bind UDP socket and start listening."""
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._on_datagram_received),
            local_addr=(self._interface, self._port),
            allow_broadcast=True,
        )
        self._transport = transport
        self._protocol = protocol

        # Discover actual bound address
        sock = self._transport.get_extra_info("socket")
        addr: tuple[str, int] = sock.getsockname()
        self._local_address = BIPAddress(host=addr[0], port=addr[1])
        logger.info("BIPTransport started on %s:%d", addr[0], addr[1])

    async def stop(self) -> None:
        """Close UDP socket."""
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("BIPTransport stopped")

    def on_receive(self, callback: Callable[[bytes, BIPAddress], None]) -> None:
        """Register callback for received NPDU data.

        Args:
            callback: Called with (npdu_bytes, source_address) for each
                received datagram containing an NPDU.
        """
        self._receive_callback = callback

    def send_unicast(self, npdu: bytes, destination: BIPAddress) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        Args:
            npdu: NPDU bytes to send.
            destination: Target BACnet/IP address.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        self._transport.sendto(bvll, (destination.host, destination.port))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send a local broadcast (Original-Broadcast-NPDU).

        Args:
            npdu: NPDU bytes to broadcast.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        self._transport.sendto(bvll, ("255.255.255.255", self._port))

    @property
    def local_address(self) -> BIPAddress:
        """The local BACnet/IP address of this transport."""
        if self._local_address is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        return self._local_address

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length for BACnet/IP (Table 6-1)."""
        return 1497

    def _on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process incoming UDP datagram."""
        try:
            msg = decode_bvll(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed BVLL from %s:%d", addr[0], addr[1])
            return

        source = BIPAddress(host=addr[0], port=addr[1])

        match msg.function:
            case BvlcFunction.ORIGINAL_UNICAST_NPDU | BvlcFunction.ORIGINAL_BROADCAST_NPDU:
                if self._receive_callback:
                    self._receive_callback(msg.data, source)
            case BvlcFunction.FORWARDED_NPDU:
                if self._receive_callback and msg.originating_address:
                    self._receive_callback(msg.data, msg.originating_address)
            case BvlcFunction.BVLC_RESULT:
                self._handle_bvlc_result(msg.data)
            case _:
                logger.debug("Ignoring BVLC function %s from %s", msg.function, source)

    def _handle_bvlc_result(self, data: bytes) -> None:
        """Handle a BVLC-Result message."""
        if len(data) >= 2:
            result_code = int.from_bytes(data[:2], "big")
            logger.debug("BVLC-Result: %d", result_code)
