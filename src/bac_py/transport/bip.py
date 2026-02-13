"""BACnet/IP transport using asyncio UDP per Annex J."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import BDT_ENTRY_SIZE, FDT_ENTRY_SIZE, BBMDManager, BDTEntry, FDTEntry
from bac_py.transport.bvll import decode_bvll, encode_bvll
from bac_py.transport.foreign_device import ForeignDeviceManager
from bac_py.types.enums import BvlcFunction, BvlcResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class BvlcNakError(Exception):
    """Raised when a BVLC-Result NAK is received for a pending request."""

    def __init__(self, result_code: int, source: BIPAddress) -> None:
        self.result_code = result_code
        self.source = source
        super().__init__(f"BVLC NAK code {result_code:#06x} from {source}")


# F3: Mapping from BVLC management functions to their NAK result codes.
# Non-BBMD devices respond with NAK when receiving these messages.
_BVLC_NAK_MAP: dict[BvlcFunction, BvlcResultCode] = {
    BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE: BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK,
    BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE: BvlcResultCode.READ_BROADCAST_DISTRIBUTION_TABLE_NAK,
    BvlcFunction.REGISTER_FOREIGN_DEVICE: BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK,
    BvlcFunction.READ_FOREIGN_DEVICE_TABLE: BvlcResultCode.READ_FOREIGN_DEVICE_TABLE_NAK,
    BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY: BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK,
    BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK: BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK,
}

# Reverse map: NAK result code -> the ACK function that a pending _bvlc_request
# would be waiting for.  Used to immediately fail pending futures on NAK instead
# of waiting for the full timeout.
_NAK_TO_PENDING_ACK: dict[int, BvlcFunction] = {
    BvlcResultCode.READ_BROADCAST_DISTRIBUTION_TABLE_NAK: BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK,
    BvlcResultCode.READ_FOREIGN_DEVICE_TABLE_NAK: BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK,
    BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK: BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
    BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK: BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
}


def _is_confirmed_request_npdu(npdu: bytes) -> bool:
    """Check if NPDU data contains a BACnet-Confirmed-Request-PDU.

    Parses just enough of the NPDU header to reach the APDU type byte.
    Returns ``False`` for network messages, malformed data, or any
    APDU type other than Confirmed-Request (type 0).
    """
    if len(npdu) < 3:
        return False
    control = npdu[1]
    if control & 0x80:
        return False  # Network message, not APDU
    offset = 2
    if control & 0x20:  # DNET present
        if offset + 3 > len(npdu):
            return False
        dlen = npdu[offset + 2]
        offset += 3 + dlen
    if control & 0x08:  # SNET present
        if offset + 3 > len(npdu):
            return False
        slen = npdu[offset + 2]
        offset += 3 + slen
    if control & 0x20:  # Hop count (present when DNET is present)
        offset += 1
    if offset >= len(npdu):
        return False
    apdu_type = (npdu[offset] >> 4) & 0x0F
    return apdu_type == 0  # 0 = BACnet-Confirmed-Request-PDU


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
    """Low-level :class:`~asyncio.DatagramProtocol` wrapper for BACnet/IP UDP communication."""

    def __init__(
        self,
        callback: Callable[[bytes, tuple[str, int]], None],
        connection_lost_callback: Callable[[Exception | None], None] | None = None,
    ) -> None:
        self._callback = callback
        self._connection_lost_callback = connection_lost_callback

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Forward an incoming UDP datagram to the registered callback."""
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
        *,
        multicast_enabled: bool = False,
        multicast_address: str = "239.255.186.192",
        multicast_ttl: int = 32,
    ) -> None:
        """Initialize the BACnet/IP transport.

        :param interface: Local IP address to bind. ``"0.0.0.0"`` binds all
            interfaces.
        :param port: UDP port number. Defaults to ``0xBAC0`` (47808).
        :param broadcast_address: Directed broadcast address for this subnet.
        :param multicast_enabled: Enable IPv4 multicast per Annex J.8.
        :param multicast_address: Multicast group address (default ``239.255.186.192``).
        :param multicast_ttl: Multicast TTL (hop limit). Defaults to 32.
        """
        self._interface = interface
        self._port = port
        self._broadcast_address = broadcast_address
        self._multicast_enabled = multicast_enabled
        self._multicast_address = multicast_address
        self._multicast_ttl = multicast_ttl
        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._receive_callback: Callable[[bytes, bytes], None] | None = None
        self._local_address: BIPAddress | None = None
        self._bbmd: BBMDManager | None = None
        self._foreign_device: ForeignDeviceManager | None = None
        # F5: Pending BVLC client request futures, keyed by
        # (expected_response_function, source_address).
        self._pending_bvlc: dict[tuple[BvlcFunction, BIPAddress], asyncio.Future[bytes]] = {}

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

        # Join IPv4 multicast group if enabled (Annex J.8)
        if self._multicast_enabled:
            try:
                group = socket.inet_aton(self._multicast_address)
                iface = socket.inet_aton(self._interface if self._interface != "0.0.0.0" else host)
                mreq = group + iface
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self._multicast_ttl)
                logger.info("Joined multicast group %s", self._multicast_address)
            except OSError:
                logger.warning("Failed to join multicast group %s", self._multicast_address)

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
            # Leave multicast group if joined
            if self._multicast_enabled:
                try:
                    sock = self._transport.get_extra_info("socket")
                    host = self._local_address.host if self._local_address else "0.0.0.0"
                    group = socket.inet_aton(self._multicast_address)
                    iface = socket.inet_aton(host)
                    mreq = group + iface
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
                except OSError:
                    pass
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("BIPTransport stopped")

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register a callback for received NPDU data.

        :param callback: Called with ``(npdu_bytes, source_mac)`` for each
            received datagram containing an NPDU.  *source_mac* is
            the 6-byte BACnet/IP MAC (4-byte IP + 2-byte port).
        """
        self._receive_callback = callback

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        :param npdu: NPDU bytes to send.
        :param mac_address: 6-byte destination MAC (4-byte IP + 2-byte port).
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        destination = BIPAddress.decode(mac_address)
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        self._transport.sendto(bvll, (destination.host, destination.port))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send a local broadcast (Original-Broadcast-NPDU).

        If registered as a foreign device, uses
        Distribute-Broadcast-To-Network instead per Annex J.5.6.
        If a BBMD is attached, also forwards to BDT peers and
        registered foreign devices per Annex J.4.5.

        :param npdu: NPDU bytes to broadcast.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        # Foreign devices must use Distribute-Broadcast-To-Network
        # instead of Original-Broadcast-NPDU per Annex J.5.6
        if self._foreign_device is not None and self._foreign_device.is_registered:
            self._foreign_device.send_distribute_broadcast(npdu)
            return

        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        if self._multicast_enabled:
            # Send to multicast group per Annex J.8
            self._transport.sendto(bvll, (self._multicast_address, self._port))
        # Also send to directed broadcast (mixed mode interop with legacy devices)
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

        :param bdt_entries: Optional initial BDT entries.  If ``None``,
            the BBMD starts with an empty BDT.
        :returns: The attached :class:`BBMDManager` instance.
        :raises RuntimeError: If transport not started or BBMD already attached.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        if self._bbmd is not None:
            msg = "BBMD already attached"
            raise RuntimeError(msg)

        self._bbmd = BBMDManager(
            local_address=self.local_address,
            send_callback=self._send_raw,
            local_broadcast_callback=self._bbmd_local_deliver,
            broadcast_address=BIPAddress(host=self._broadcast_address, port=self._port),
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

        :param bbmd_address: Address of the BBMD to register with.
        :param ttl: Time-to-Live for the registration in seconds.
        :returns: The attached :class:`ForeignDeviceManager` instance.
        :raises RuntimeError: If transport not started or foreign device
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
            send_callback=self._send_raw,
            local_address=self.local_address,
        )
        await self._foreign_device.start()
        logger.info(
            "Foreign device manager attached, registering with BBMD %s:%d",
            bbmd_address.host,
            bbmd_address.port,
        )
        return self._foreign_device

    # ------------------------------------------------------------------
    # F5: BBMD client functions
    # ------------------------------------------------------------------

    async def read_bdt(self, bbmd_address: BIPAddress, *, timeout: float = 5.0) -> list[BDTEntry]:
        """Read the Broadcast Distribution Table from a remote BBMD.

        Sends a Read-Broadcast-Distribution-Table request and waits for
        the Read-BDT-Ack response.

        :param bbmd_address: Address of the BBMD to query.
        :param timeout: Seconds to wait for a response.
        :returns: List of :class:`BDTEntry` instances from the remote BBMD.
        :raises RuntimeError: If transport not started.
        :raises BvlcNakError: If the target is not a BBMD.
        :raises TimeoutError: If no response within *timeout*.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        bvll = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE, b"")
        data = await self._bvlc_request(
            bvll,
            bbmd_address,
            BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK,
            timeout=timeout,
        )
        entries: list[BDTEntry] = []
        for i in range(0, len(data), BDT_ENTRY_SIZE):
            if i + BDT_ENTRY_SIZE > len(data):
                break
            entries.append(BDTEntry.decode(data[i : i + BDT_ENTRY_SIZE]))
        return entries

    async def write_bdt(
        self,
        bbmd_address: BIPAddress,
        entries: list[BDTEntry],
        *,
        timeout: float = 5.0,
    ) -> BvlcResultCode:
        """Write a Broadcast Distribution Table to a remote BBMD.

        Sends a Write-Broadcast-Distribution-Table request and waits for
        the BVLC-Result response.

        :param bbmd_address: Address of the BBMD to configure.
        :param entries: :class:`BDTEntry` instances to write.
        :param timeout: Seconds to wait for a response.
        :returns: The :class:`BvlcResultCode` from the BBMD.
        :raises RuntimeError: If transport not started.
        :raises TimeoutError: If no response within *timeout*.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        payload = b"".join(entry.encode() for entry in entries)
        bvll = encode_bvll(BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE, payload)
        data = await self._bvlc_request(
            bvll,
            bbmd_address,
            BvlcFunction.BVLC_RESULT,
            timeout=timeout,
        )
        if len(data) >= 2:
            return BvlcResultCode(int.from_bytes(data[:2], "big"))
        return BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK

    async def read_fdt(self, bbmd_address: BIPAddress, *, timeout: float = 5.0) -> list[FDTEntry]:
        """Read the Foreign Device Table from a remote BBMD.

        Sends a Read-Foreign-Device-Table request and waits for
        the Read-FDT-Ack response.

        :param bbmd_address: Address of the BBMD to query.
        :param timeout: Seconds to wait for a response.
        :returns: List of :class:`FDTEntry` instances from the remote BBMD.
            The ``expiry`` field is set to ``0.0`` since it is not meaningful
            for remote entries; use the ``remaining`` property instead.
        :raises RuntimeError: If transport not started.
        :raises BvlcNakError: If the target is not a BBMD.
        :raises TimeoutError: If no response within *timeout*.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        bvll = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE, b"")
        data = await self._bvlc_request(
            bvll,
            bbmd_address,
            BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK,
            timeout=timeout,
        )
        entries: list[FDTEntry] = []
        for i in range(0, len(data), FDT_ENTRY_SIZE):
            if i + FDT_ENTRY_SIZE > len(data):
                break
            addr = BIPAddress.decode(data[i : i + 6])
            ttl = int.from_bytes(data[i + 6 : i + 8], "big")
            # Wire bytes i+8:i+10 contain remaining-time, not retained for
            # remote entries since it is only meaningful on the local BBMD.
            entries.append(FDTEntry(address=addr, ttl=ttl, expiry=0.0))
        return entries

    async def delete_fdt_entry(
        self,
        bbmd_address: BIPAddress,
        entry_address: BIPAddress,
        *,
        timeout: float = 5.0,
    ) -> BvlcResultCode:
        """Delete a Foreign Device Table entry on a remote BBMD.

        Sends a Delete-Foreign-Device-Table-Entry request and waits for
        the BVLC-Result response.

        :param bbmd_address: Address of the BBMD.
        :param entry_address: Address of the FDT entry to delete.
        :param timeout: Seconds to wait for a response.
        :returns: The :class:`BvlcResultCode` from the BBMD.
        :raises RuntimeError: If transport not started.
        :raises TimeoutError: If no response within *timeout*.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        bvll = encode_bvll(
            BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            entry_address.encode(),
        )
        data = await self._bvlc_request(
            bvll,
            bbmd_address,
            BvlcFunction.BVLC_RESULT,
            timeout=timeout,
        )
        if len(data) >= 2:
            return BvlcResultCode(int.from_bytes(data[:2], "big"))
        return BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK

    async def _bvlc_request(
        self,
        bvll_data: bytes,
        destination: BIPAddress,
        expected_response: BvlcFunction,
        *,
        timeout: float = 5.0,
    ) -> bytes:
        """Send a BVLC request and wait for the expected response.

        :param bvll_data: Complete BVLL message to send.
        :param destination: Target BBMD address.
        :param expected_response: The :class:`BvlcFunction` code expected in reply.
        :param timeout: Seconds to wait.
        :returns: The payload data from the response message.
        :raises TimeoutError: If no response within *timeout*.
        """
        key = (expected_response, destination)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes] = loop.create_future()
        self._pending_bvlc[key] = future

        try:
            if self._transport is not None:
                self._transport.sendto(bvll_data, (destination.host, destination.port))
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_bvlc.pop(key, None)

    # ------------------------------------------------------------------
    # BBMD / foreign device integration helpers
    # ------------------------------------------------------------------

    def _send_raw(self, data: bytes, destination: BIPAddress) -> None:
        """Send raw BVLL data to a destination.

        Used as the send callback for :class:`BBMDManager` and
        :class:`ForeignDeviceManager`.
        """
        if self._transport is not None:
            self._transport.sendto(data, (destination.host, destination.port))

    def _bbmd_local_deliver(self, npdu: bytes, source: BIPAddress) -> None:
        """Deliver an NPDU to the local receive callback (BBMD callback).

        Called by :class:`BBMDManager` when a Forwarded-NPDU or
        Distribute-Broadcast-To-Network message needs to be delivered
        to the application/router layer.
        """
        # F7: Drop confirmed requests received via broadcast.
        if _is_confirmed_request_npdu(npdu):
            logger.debug(
                "Dropped confirmed request via BBMD broadcast from %s:%d",
                source.host,
                source.port,
            )
            return
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

        # F6: Drop datagrams from our own address.  This prevents
        # processing our own broadcasts echoed back by the OS or
        # wire re-broadcasts from the BBMD.
        if self._local_address is not None and source == self._local_address:
            return

        # --- BBMD intercept ---
        if self._bbmd is not None:
            # For Forwarded-NPDU the BBMD expects the originating
            # address as 'source', not the UDP peer address.
            if msg.function == BvlcFunction.FORWARDED_NPDU and msg.originating_address:
                bbmd_source = msg.originating_address
            else:
                bbmd_source = source

            handled = self._bbmd.handle_bvlc(
                msg.function, msg.data, bbmd_source, udp_source=source
            )

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

        # --- F3: Non-BBMD NAK responses ---
        # When no BBMD is attached, respond with NAK to BVLC management
        # messages so the sender knows this device is not a BBMD.
        if self._bbmd is None:
            nak_code = _BVLC_NAK_MAP.get(msg.function)
            if nak_code is not None:
                self._send_bvlc_nak(nak_code, source)
                return

        # --- Normal receive path ---
        match msg.function:
            case BvlcFunction.ORIGINAL_UNICAST_NPDU:
                if self._receive_callback:
                    self._receive_callback(msg.data, source.encode())
            case BvlcFunction.ORIGINAL_BROADCAST_NPDU:
                # F7: Drop confirmed requests received via broadcast.
                if _is_confirmed_request_npdu(msg.data):
                    logger.debug(
                        "Dropped confirmed request via broadcast from %s:%d",
                        source.host,
                        source.port,
                    )
                    return
                if self._receive_callback:
                    self._receive_callback(msg.data, source.encode())
            case BvlcFunction.FORWARDED_NPDU:
                # F7: Drop confirmed requests received via broadcast.
                if _is_confirmed_request_npdu(msg.data):
                    logger.debug(
                        "Dropped confirmed request via forwarded broadcast from %s",
                        msg.originating_address or source,
                    )
                    return
                if self._receive_callback and msg.originating_address:
                    self._receive_callback(msg.data, msg.originating_address.encode())
            case BvlcFunction.BVLC_RESULT:
                # F5: Route to pending client request futures first.
                if not self._resolve_pending_bvlc(msg.function, msg.data, source):
                    self._handle_bvlc_result(msg.data, source)
            case (
                BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK
                | BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK
            ):
                # F5: Route ACK responses to pending client requests.
                if not self._resolve_pending_bvlc(msg.function, msg.data, source):
                    logger.debug("Ignoring unsolicited %s from %s", msg.function, source)
            case _:
                logger.debug("Ignoring BVLC function %s from %s", msg.function, source)

    def _resolve_pending_bvlc(
        self, function: BvlcFunction, data: bytes, source: BIPAddress
    ) -> bool:
        """Try to resolve a pending BVLC client request future.

        :param function: BVLC function code of the received message.
        :param data: Payload data of the received message.
        :param source: Source address of the received message.
        :returns: ``True`` if a pending future was resolved, ``False`` otherwise.
        """
        key = (function, source)
        future = self._pending_bvlc.get(key)
        if future is not None and not future.done():
            future.set_result(data)
            return True
        return False

    def _send_bvlc_nak(self, result_code: BvlcResultCode, destination: BIPAddress) -> None:
        """Send a BVLC-Result NAK to the given destination.

        Used to reject BVLC management messages when no BBMD is attached.
        """
        if self._transport is None:
            return
        payload = result_code.to_bytes(2, "big")
        bvll = encode_bvll(BvlcFunction.BVLC_RESULT, payload)
        self._transport.sendto(bvll, (destination.host, destination.port))

    def _handle_bvlc_result(self, data: bytes, source: BIPAddress) -> None:
        """Handle a BVLC-Result message.

        Routes the result to the attached :class:`ForeignDeviceManager`
        (if any) so it can track registration state.  Non-zero result
        codes are logged at warning level.

        When a NAK maps to a pending ``_bvlc_request`` future (e.g. a
        Read-BDT-NAK for a pending Read-BDT-ACK), the future is failed
        immediately with :class:`BvlcNakError` instead of waiting for
        the full timeout.

        S3: Only routes to the ForeignDeviceManager if the sender
        matches the expected BBMD address, preventing rogue devices
        from spoofing registration confirmations.
        """
        if self._foreign_device is not None and source == self._foreign_device.bbmd_address:
            # S3: Only accept BVLC-Results from the BBMD we registered with.
            self._foreign_device.handle_bvlc_result(data)
        if len(data) >= 2:
            result_code = int.from_bytes(data[:2], "big")
            if result_code != 0:
                logger.debug("BVLC-Result NAK: code %d from %s", result_code, source)
                # Fail any pending _bvlc_request future immediately.
                ack_func = _NAK_TO_PENDING_ACK.get(result_code)
                if ack_func is not None:
                    key = (ack_func, source)
                    future = self._pending_bvlc.get(key)
                    if future is not None and not future.done():
                        future.set_exception(BvlcNakError(result_code, source))
            else:
                logger.debug("BVLC-Result: %d", result_code)
