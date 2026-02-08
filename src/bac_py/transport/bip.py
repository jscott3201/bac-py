"""BACnet/IP transport using asyncio UDP per Annex J."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import BBMDManager, BDTEntry
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
        self._bbmd: BBMDManager | None = None

    async def start(self) -> None:
        """Bind UDP socket and start listening."""
        if self._transport is not None:
            return  # Already started
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
        """Close UDP socket and stop BBMD if attached."""
        if self._bbmd is not None:
            await self._bbmd.stop()
            self._bbmd = None
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

    def send_unicast(self, npdu: bytes, destination: BIPAddress | bytes) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        Args:
            npdu: NPDU bytes to send.
            destination: Target BACnet/IP address, either as a
                :class:`BIPAddress` or 6-byte raw MAC (IP + port).
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        if isinstance(destination, (bytes, memoryview)):
            destination = BIPAddress.decode(destination)
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        self._transport.sendto(bvll, (destination.host, destination.port))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send a local broadcast (Original-Broadcast-NPDU).

        If a BBMD is attached, also forwards to BDT peers and
        registered foreign devices per Annex J.4.5.

        Args:
            npdu: NPDU bytes to broadcast.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        self._transport.sendto(bvll, ("255.255.255.255", self._port))

        # If BBMD attached, also forward to peers and foreign devices
        if self._bbmd is not None:
            self._bbmd.handle_bvlc(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu, self.local_address)

    @property
    def local_address(self) -> BIPAddress:
        """The local BACnet/IP address of this transport."""
        if self._local_address is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        return self._local_address

    @property
    def local_mac(self) -> bytes:
        """The 6-byte MAC address of this port (4-byte IP + 2-byte port)."""
        return self.local_address.encode()

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length for BACnet/IP (Table 6-1)."""
        return 1497

    @property
    def bbmd(self) -> BBMDManager | None:
        """The attached BBMD manager, or ``None`` if not configured."""
        return self._bbmd

    async def attach_bbmd(
        self, bdt_entries: list[BDTEntry] | None = None
    ) -> BBMDManager:
        """Attach a BBMD manager to this transport.

        Creates and starts a :class:`BBMDManager` integrated with this
        transport.  The BBMD intercepts incoming BVLC messages before
        they reach the normal receive path, and outgoing broadcasts are
        also forwarded to BDT peers and foreign devices.

        Per Annex J.7.1 this allows a single device to combine BBMD
        and router functionality.

        Args:
            bdt_entries: Optional initial BDT entries.  If ``None``,
                the BBMD starts with an empty BDT.

        Returns:
            The attached :class:`BBMDManager` instance.

        Raises:
            RuntimeError: If transport not started or BBMD already attached.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        if self._bbmd is not None:
            msg = "BBMD already attached"
            raise RuntimeError(msg)

        self._bbmd = BBMDManager(
            local_address=self.local_address,
            send_callback=self._bbmd_send_raw,
            local_broadcast_callback=self._bbmd_local_deliver,
        )
        if bdt_entries:
            self._bbmd.set_bdt(bdt_entries)
        await self._bbmd.start()
        logger.info(
            "BBMD attached to transport %s:%d",
            self.local_address.host,
            self.local_address.port,
        )
        return self._bbmd

    # ------------------------------------------------------------------
    # BBMD integration helpers
    # ------------------------------------------------------------------

    def _bbmd_send_raw(self, data: bytes, destination: BIPAddress) -> None:
        """Send raw BVLL data to a destination (BBMD send callback).

        Used by :class:`BBMDManager` to send Forwarded-NPDUs to BDT
        peers and foreign devices.
        """
        if self._transport is not None:
            self._transport.sendto(data, (destination.host, destination.port))

    def _bbmd_local_deliver(self, npdu: bytes, source: BIPAddress) -> None:
        """Deliver an NPDU to the local receive callback (BBMD callback).

        Called by :class:`BBMDManager` when a Forwarded-NPDU or
        Distribute-Broadcast-To-Network message needs to be delivered
        to the application/router layer.
        """
        if self._receive_callback is not None:
            self._receive_callback(npdu, source)

    def _on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process incoming UDP datagram.

        When a BBMD is attached, BVLC messages are first passed through
        :meth:`BBMDManager.handle_bvlc` before reaching the normal
        receive path.  This ensures BVLC management messages
        (Register-Foreign-Device, Read/Write-BDT, etc.) are handled
        exclusively by the BBMD while broadcast NPDUs are still
        delivered to the application/router layer.
        """
        try:
            msg = decode_bvll(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed BVLL from %s:%d", addr[0], addr[1])
            return

        source = BIPAddress(host=addr[0], port=addr[1])

        # --- BBMD intercept ---
        if self._bbmd is not None:
            # For Forwarded-NPDU the BBMD expects the originating
            # address as 'source', not the UDP peer address.
            if msg.function == BvlcFunction.FORWARDED_NPDU and msg.originating_address:
                bbmd_source = msg.originating_address
            else:
                bbmd_source = source

            handled = self._bbmd.handle_bvlc(msg.function, msg.data, bbmd_source)

            if handled:
                # Exclusively handled by BBMD (BVLC management messages
                # or Distribute-Broadcast which already called
                # _bbmd_local_deliver).
                return

            # BBMD returned False -- the message also needs normal
            # delivery.  For Forwarded-NPDU the BBMD already delivered
            # via local_broadcast_callback so we skip the normal path
            # to prevent double delivery.
            if msg.function == BvlcFunction.FORWARDED_NPDU:
                return

        # --- Normal receive path ---
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
