"""BACnet/IP transport using asyncio UDP per Annex J."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import BBMDManager, BDTEntry
from bac_py.transport.bvll import decode_bvll, encode_bvll
from bac_py.transport.foreign_device import ForeignDeviceManager
from bac_py.types.enums import BvlcFunction

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _resolve_local_ip() -> str:
    """Resolve the local machine's IP address.

    Uses a UDP connect to a public address to determine the outgoing
    interface IP.  Falls back to ``127.0.0.1`` if resolution fails.
    No actual traffic is sent.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip: str = s.getsockname()[0]
            return ip
    except OSError:
        return "127.0.0.1"


class _UDPProtocol(asyncio.DatagramProtocol):
    """Low-level asyncio DatagramProtocol wrapper."""

    def __init__(
        self,
        callback: Callable[[bytes, tuple[str, int]], None],
        connection_lost_callback: Callable[[Exception | None], None] | None = None,
    ) -> None:
        self._callback = callback
        self._connection_lost_callback = connection_lost_callback

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming UDP datagram."""
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        """Handle transport errors."""
        logger.warning("UDP transport error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        """Handle transport connection loss (interface down, socket closed)."""
        if exc is not None:
            logger.warning("UDP connection lost: %s", exc)
        else:
            logger.debug("UDP connection closed")
        if self._connection_lost_callback is not None:
            self._connection_lost_callback(exc)


class BIPTransport:
    """BACnet/IP transport using asyncio UDP.

    Provides send/receive for BACnet/IP datagrams wrapped in BVLL.
    """

    def __init__(
        self,
        interface: str = "0.0.0.0",
        port: int = 0xBAC0,
        broadcast_address: str = "255.255.255.255",
    ) -> None:
        self._interface = interface
        self._port = port
        self._broadcast_address = broadcast_address
        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._receive_callback: Callable[[bytes, bytes], None] | None = None
        self._local_address: BIPAddress | None = None
        self._bbmd: BBMDManager | None = None
        self._foreign_device: ForeignDeviceManager | None = None

    async def start(self) -> None:
        """Bind UDP socket and start listening."""
        if self._transport is not None:
            return  # Already started
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._on_datagram_received, self._on_connection_lost),
            local_addr=(self._interface, self._port),
            allow_broadcast=True,
        )
        self._transport = transport
        self._protocol = protocol

        # Discover actual bound address
        sock = self._transport.get_extra_info("socket")
        addr: tuple[str, int] = sock.getsockname()
        host = addr[0]
        # Resolve wildcard to actual interface IP so that BBMD BDT
        # self-comparison and Forwarded-NPDU originating addresses work.
        if host == "0.0.0.0":
            host = _resolve_local_ip()
        self._local_address = BIPAddress(host=host, port=addr[1])
        logger.info("BIPTransport started on %s:%d", host, addr[1])

    async def stop(self) -> None:
        """Close UDP socket and stop BBMD/foreign device if attached."""
        if self._foreign_device is not None:
            await self._foreign_device.stop()
            self._foreign_device = None
        if self._bbmd is not None:
            await self._bbmd.stop()
            self._bbmd = None
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("BIPTransport stopped")

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register callback for received NPDU data.

        Args:
            callback: Called with (npdu_bytes, source_mac) for each
                received datagram containing an NPDU.  *source_mac* is
                the 6-byte BACnet/IP MAC (4-byte IP + 2-byte port).
        """
        self._receive_callback = callback

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        Args:
            npdu: NPDU bytes to send.
            mac_address: 6-byte destination MAC (4-byte IP + 2-byte port).
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        destination = BIPAddress.decode(mac_address)
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
        self._transport.sendto(bvll, (self._broadcast_address, self._port))

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

    async def attach_bbmd(self, bdt_entries: list[BDTEntry] | None = None) -> BBMDManager:
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

    @property
    def foreign_device(self) -> ForeignDeviceManager | None:
        """The attached foreign device manager, or ``None``."""
        return self._foreign_device

    async def attach_foreign_device(
        self,
        bbmd_address: BIPAddress,
        ttl: int,
    ) -> ForeignDeviceManager:
        """Attach a foreign device manager to this transport.

        Creates and starts a :class:`ForeignDeviceManager` that will
        register with the specified BBMD and periodically re-register
        to maintain the registration.

        Incoming BVLC-Result messages will be routed to the manager
        to track registration status.

        Args:
            bbmd_address: Address of the BBMD to register with.
            ttl: Time-to-Live for the registration in seconds.

        Returns:
            The attached :class:`ForeignDeviceManager` instance.

        Raises:
            RuntimeError: If transport not started or foreign device
                already attached.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        if self._foreign_device is not None:
            msg = "Foreign device manager already attached"
            raise RuntimeError(msg)

        self._foreign_device = ForeignDeviceManager(
            bbmd_address=bbmd_address,
            ttl=ttl,
            send_callback=self._fd_send_raw,
        )
        await self._foreign_device.start()
        logger.info(
            "Foreign device manager attached, registering with BBMD %s:%d",
            bbmd_address.host,
            bbmd_address.port,
        )
        return self._foreign_device

    # ------------------------------------------------------------------
    # BBMD / foreign device integration helpers
    # ------------------------------------------------------------------

    def _bbmd_send_raw(self, data: bytes, destination: BIPAddress) -> None:
        """Send raw BVLL data to a destination (BBMD send callback).

        Used by :class:`BBMDManager` to send Forwarded-NPDUs to BDT
        peers and foreign devices.
        """
        if self._transport is not None:
            self._transport.sendto(data, (destination.host, destination.port))

    def _fd_send_raw(self, data: bytes, destination: BIPAddress) -> None:
        """Send raw BVLL data to a destination (foreign device send callback).

        Used by :class:`ForeignDeviceManager` to send registration
        and distribute-broadcast messages to the BBMD.
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
            self._receive_callback(npdu, source.encode())

    def _on_connection_lost(self, exc: Exception | None) -> None:
        """Handle UDP connection loss."""
        self._transport = None
        self._protocol = None

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
                    self._receive_callback(msg.data, source.encode())
            case BvlcFunction.FORWARDED_NPDU:
                if self._receive_callback and msg.originating_address:
                    self._receive_callback(msg.data, msg.originating_address.encode())
            case BvlcFunction.BVLC_RESULT:
                self._handle_bvlc_result(msg.data)
            case _:
                logger.debug("Ignoring BVLC function %s from %s", msg.function, source)

    def _handle_bvlc_result(self, data: bytes) -> None:
        """Handle a BVLC-Result message.

        Routes the result to the attached :class:`ForeignDeviceManager`
        (if any) so it can track registration state.  Non-zero result
        codes are logged at warning level.
        """
        if self._foreign_device is not None:
            self._foreign_device.handle_bvlc_result(data)
        if len(data) >= 2:
            result_code = int.from_bytes(data[:2], "big")
            if result_code != 0:
                logger.warning("BVLC-Result NAK: code %d", result_code)
            else:
                logger.debug("BVLC-Result: %d", result_code)
