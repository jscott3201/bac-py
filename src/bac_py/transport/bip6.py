"""BACnet/IPv6 transport using asyncio UDP per Annex U."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bac_py.network.address import BIP6Address
from bac_py.transport.bvll_ipv6 import decode_bvll6, encode_bvll6
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Default BACnet/IPv6 multicast addresses (Annex U)
MULTICAST_LINK_LOCAL = "ff02::bac0"
MULTICAST_SITE_LOCAL = "ff05::bac0"


@dataclass(slots=True)
class VMACEntry:
    """A cached mapping from VMAC to IPv6 address."""

    address: BIP6Address
    last_seen: float  # monotonic timestamp


class VMACCache:
    """VMAC-to-IPv6 address resolution cache with TTL-based eviction."""

    def __init__(self, ttl: float = 300.0) -> None:
        self._entries: dict[bytes, VMACEntry] = {}
        self._ttl = ttl

    def put(self, vmac: bytes, address: BIP6Address) -> None:
        """Add or update a VMAC-to-address mapping."""
        self._entries[vmac] = VMACEntry(address=address, last_seen=time.monotonic())

    def get(self, vmac: bytes) -> BIP6Address | None:
        """Look up an address by VMAC, returning ``None`` if not cached or stale."""
        entry = self._entries.get(vmac)
        if entry is None:
            return None
        if time.monotonic() - entry.last_seen > self._ttl:
            del self._entries[vmac]
            return None
        return entry.address

    def evict_stale(self) -> None:
        """Remove all entries older than the TTL."""
        now = time.monotonic()
        stale = [k for k, v in self._entries.items() if now - v.last_seen > self._ttl]
        for k in stale:
            del self._entries[k]

    def all_entries(self) -> dict[bytes, VMACEntry]:
        """Return all current entries (for diagnostics)."""
        return dict(self._entries)


@dataclass(slots=True)
class _PendingResolution:
    """An NPDU queued while waiting for VMAC address resolution."""

    npdu: bytes
    created: float = field(default_factory=time.monotonic)


class _UDP6Protocol(asyncio.DatagramProtocol):
    """Low-level :class:`~asyncio.DatagramProtocol` for BACnet/IPv6 UDP."""

    def __init__(
        self,
        callback: Callable[[bytes, tuple[str, int, int, int]], None],
        connection_lost_callback: Callable[[Exception | None], None] | None = None,
    ) -> None:
        self._callback = callback
        self._connection_lost_callback = connection_lost_callback

    def datagram_received(self, data: bytes, addr: tuple[str, int, int, int]) -> None:  # type: ignore[override]
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("UDP6 transport error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None:
            logger.warning("UDP6 connection lost: %s", exc)
        else:
            logger.debug("UDP6 connection closed")
        if self._connection_lost_callback is not None:
            self._connection_lost_callback(exc)


class BIP6Transport:
    """BACnet/IPv6 transport using asyncio UDP.

    Provides send/receive for BACnet/IPv6 datagrams wrapped in BVLL6.
    Uses 3-byte VMACs for network-layer addressing and IPv6 multicast
    for broadcasts per Annex U.
    """

    def __init__(
        self,
        interface: str = "::",
        port: int = 0xBAC0,
        multicast_address: str = MULTICAST_LINK_LOCAL,
        *,
        vmac: bytes | None = None,
        vmac_ttl: float = 300.0,
    ) -> None:
        """Initialize the BACnet/IPv6 transport.

        :param interface: Local IPv6 address to bind. ``"::"`` binds all interfaces.
        :param port: UDP port number. Defaults to ``0xBAC0`` (47808).
        :param multicast_address: IPv6 multicast group for broadcasts.
        :param vmac: Explicit 3-byte VMAC. If ``None``, auto-generated on start.
        :param vmac_ttl: TTL in seconds for VMAC resolution cache entries.
        """
        self._interface = interface
        self._port = port
        self._multicast_address = multicast_address
        self._explicit_vmac = vmac
        self._vmac: bytes = b""
        self._vmac_cache = VMACCache(ttl=vmac_ttl)
        self._protocol: _UDP6Protocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._receive_callback: Callable[[bytes, bytes], None] | None = None
        self._local_address: BIP6Address | None = None
        self._pending_resolutions: dict[bytes, list[_PendingResolution]] = {}
        self._pending_bvlc: dict[tuple[Bvlc6Function, BIP6Address], asyncio.Future[bytes]] = {}

    async def start(self) -> None:
        """Bind UDP6 socket, generate VMAC, and join multicast group."""
        if self._transport is not None:
            return

        # Generate or use explicit VMAC
        if self._explicit_vmac is not None:
            if len(self._explicit_vmac) != 3:
                msg = "VMAC must be exactly 3 bytes"
                raise ValueError(msg)
            self._vmac = self._explicit_vmac
        else:
            self._vmac = os.urandom(3)

        loop = asyncio.get_running_loop()

        # Create IPv6 UDP endpoint
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UDP6Protocol(self._on_datagram_received, self._on_connection_lost),
            local_addr=(self._interface, self._port),
            family=socket.AF_INET6,
        )
        self._transport = transport
        self._protocol = protocol

        # Discover actual bound address
        sock: socket.socket = self._transport.get_extra_info("socket")
        addr = sock.getsockname()
        host = addr[0]
        if host == "::":
            host = "::1"
        self._local_address = BIP6Address(host=host, port=addr[1])

        # Join multicast group
        try:
            group_bin = socket.inet_pton(socket.AF_INET6, self._multicast_address)
            # struct: 16-byte group + 4-byte interface index (0 = default)
            mreq = group_bin + struct.pack("@I", 0)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)
        except OSError:
            logger.warning("Failed to join IPv6 multicast group %s", self._multicast_address)

        logger.info(
            "BIP6Transport started on [%s]:%d, VMAC=%s",
            host,
            addr[1],
            self._vmac.hex(),
        )

    async def stop(self) -> None:
        """Leave multicast group and close UDP socket."""
        if self._transport is not None:
            # Try to leave multicast group
            try:
                sock: socket.socket = self._transport.get_extra_info("socket")
                group_bin = socket.inet_pton(socket.AF_INET6, self._multicast_address)
                mreq = group_bin + struct.pack("@I", 0)
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_LEAVE_GROUP, mreq)
            except OSError:
                pass
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("BIP6Transport stopped")

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register a callback for received NPDU data.

        :param callback: Called with ``(npdu_bytes, source_vmac)`` for each
            received datagram containing an NPDU.  *source_vmac* is the
            3-byte VMAC of the sender.
        """
        self._receive_callback = callback

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send a directed message (Original-Unicast-NPDU).

        :param npdu: NPDU bytes to send.
        :param mac_address: 3-byte destination VMAC.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        dest_addr = self._vmac_cache.get(mac_address)
        if dest_addr is None:
            # Queue for address resolution
            pending = self._pending_resolutions.setdefault(mac_address, [])
            pending.append(_PendingResolution(npdu=npdu))
            self._send_address_resolution(mac_address)
            return

        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_UNICAST_NPDU,
            npdu,
            source_vmac=self._vmac,
            dest_vmac=mac_address,
        )
        self._transport.sendto(bvll, (dest_addr.host, dest_addr.port))

    def send_broadcast(self, npdu: bytes) -> None:
        """Send a local broadcast (Original-Broadcast-NPDU) to the multicast group.

        :param npdu: NPDU bytes to broadcast.
        """
        if self._transport is None:
            msg = "Transport not started"
            raise RuntimeError(msg)

        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            npdu,
            source_vmac=self._vmac,
        )
        self._transport.sendto(bvll, (self._multicast_address, self._port))

    @property
    def local_address(self) -> BIP6Address:
        """The local BACnet/IPv6 address of this transport."""
        if self._local_address is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        return self._local_address

    @property
    def local_mac(self) -> bytes:
        """The 3-byte VMAC address of this port."""
        if not self._vmac:
            msg = "Transport not started"
            raise RuntimeError(msg)
        return self._vmac

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length for BACnet/IPv6 (Table 6-1)."""
        return 1497

    @property
    def vmac_cache(self) -> VMACCache:
        """The VMAC resolution cache (for diagnostics)."""
        return self._vmac_cache

    # ------------------------------------------------------------------
    # Address resolution
    # ------------------------------------------------------------------

    def _send_address_resolution(self, target_vmac: bytes) -> None:
        """Send an Address-Resolution broadcast for a VMAC."""
        if self._transport is None:
            return
        bvll = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=self._vmac,
        )
        self._transport.sendto(bvll, (self._multicast_address, self._port))

    def _handle_address_resolution(
        self,
        source_vmac: bytes,
        payload: bytes,
        sender: BIP6Address,
    ) -> None:
        """Respond to an Address-Resolution request if the target VMAC matches ours."""
        if len(payload) < 3:
            return
        target_vmac = payload[:3]
        # Update cache with sender's VMAC
        self._vmac_cache.put(source_vmac, sender)
        if target_vmac == self._vmac:
            self._send_address_resolution_ack(source_vmac, sender)

    def _send_address_resolution_ack(
        self,
        target_vmac: bytes,
        destination: BIP6Address,
    ) -> None:
        """Send an Address-Resolution-ACK to the requester."""
        if self._transport is None:
            return
        bvll = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=self._vmac,
            dest_vmac=target_vmac,
        )
        self._transport.sendto(bvll, (destination.host, destination.port))

    def _handle_address_resolution_ack(
        self,
        source_vmac: bytes,
        sender: BIP6Address,
    ) -> None:
        """Process an Address-Resolution-ACK: update cache and flush pending NPDUs."""
        self._vmac_cache.put(source_vmac, sender)
        self._flush_pending(source_vmac, sender)

    def _handle_virtual_address_resolution(
        self,
        source_vmac: bytes,
        sender: BIP6Address,
    ) -> None:
        """Respond to a Virtual-Address-Resolution request."""
        self._vmac_cache.put(source_vmac, sender)
        if self._transport is None:
            return
        bvll = encode_bvll6(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=self._vmac,
            dest_vmac=source_vmac,
        )
        self._transport.sendto(bvll, (sender.host, sender.port))

    def _flush_pending(self, vmac: bytes, address: BIP6Address) -> None:
        """Send any NPDUs queued while waiting for address resolution."""
        pending = self._pending_resolutions.pop(vmac, [])
        for item in pending:
            bvll = encode_bvll6(
                Bvlc6Function.ORIGINAL_UNICAST_NPDU,
                item.npdu,
                source_vmac=self._vmac,
                dest_vmac=vmac,
            )
            if self._transport is not None:
                self._transport.sendto(bvll, (address.host, address.port))

    # ------------------------------------------------------------------
    # Datagram receive
    # ------------------------------------------------------------------

    def _on_connection_lost(self, exc: Exception | None) -> None:
        self._transport = None
        self._protocol = None

    def _on_datagram_received(self, data: bytes, addr: tuple[str, int, int, int]) -> None:
        """Process incoming UDP6 datagram."""
        try:
            msg = decode_bvll6(memoryview(data))
        except (ValueError, IndexError):
            logger.warning("Dropped malformed BVLL6 from [%s]:%d", addr[0], addr[1])
            return

        sender = BIP6Address(host=addr[0], port=addr[1])

        # Update resolution cache for any message with a source VMAC
        if msg.source_vmac:
            self._vmac_cache.put(msg.source_vmac, sender)

        match msg.function:
            case Bvlc6Function.ORIGINAL_UNICAST_NPDU:
                if self._receive_callback and msg.source_vmac:
                    self._receive_callback(msg.data, msg.source_vmac)

            case Bvlc6Function.ORIGINAL_BROADCAST_NPDU:
                if self._receive_callback and msg.source_vmac:
                    self._receive_callback(msg.data, msg.source_vmac)

            case Bvlc6Function.FORWARDED_NPDU:
                if self._receive_callback and msg.source_vmac:
                    self._receive_callback(msg.data, msg.source_vmac)

            case Bvlc6Function.ADDRESS_RESOLUTION:
                if msg.source_vmac:
                    self._handle_address_resolution(msg.source_vmac, msg.data, sender)

            case Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION:
                if msg.source_vmac:
                    self._handle_address_resolution(msg.source_vmac, msg.data, sender)

            case Bvlc6Function.ADDRESS_RESOLUTION_ACK:
                if msg.source_vmac:
                    self._handle_address_resolution_ack(msg.source_vmac, sender)

            case Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION:
                if msg.source_vmac:
                    self._handle_virtual_address_resolution(msg.source_vmac, sender)

            case Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK:
                if msg.source_vmac:
                    self._vmac_cache.put(msg.source_vmac, sender)

            case Bvlc6Function.BVLC_RESULT:
                self._resolve_pending_bvlc(msg.function, msg.data, sender)

            case Bvlc6Function.REGISTER_FOREIGN_DEVICE:
                self._send_bvlc6_nak(Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, sender)

            case Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY:
                self._send_bvlc6_nak(Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK, sender)

            case Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU:
                self._send_bvlc6_nak(Bvlc6ResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK, sender)

            case _:
                logger.debug(
                    "Ignoring BVLC6 function %s from [%s]:%d", msg.function, addr[0], addr[1]
                )

    def _resolve_pending_bvlc(
        self, function: Bvlc6Function, data: bytes, source: BIP6Address
    ) -> bool:
        key = (function, source)
        future = self._pending_bvlc.get(key)
        if future is not None and not future.done():
            future.set_result(data)
            return True
        return False

    def _send_bvlc6_nak(self, result_code: Bvlc6ResultCode, destination: BIP6Address) -> None:
        """Send a BVLC6-Result NAK."""
        if self._transport is None:
            return
        payload = result_code.to_bytes(2, "big")
        bvll = encode_bvll6(Bvlc6Function.BVLC_RESULT, payload)
        self._transport.sendto(bvll, (destination.host, destination.port))
