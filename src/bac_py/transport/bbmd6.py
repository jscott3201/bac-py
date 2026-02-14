"""BACnet/IPv6 Broadcast Management Device (BBMD) per Annex U.

Provides BBMD6Manager for BDT/FDT management, broadcast forwarding
between BACnet/IPv6 subnets, and foreign device registration handling.
IPv6 BBMDs use multicast instead of directed broadcast and all BVLL6
messages include a 3-byte source VMAC.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bac_py.network.address import BIP6Address
from bac_py.transport.bvll_ipv6 import BIP6_ADDRESS_LENGTH, encode_bvll6
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Per Annex U, the BBMD adds a 30-second grace period to the TTL
# before purging expired foreign device entries.
FDT6_GRACE_PERIOD_SECONDS = 30

# FDT6 entry wire size: 18-octet B/IPv6 address + 2-octet TTL + 2-octet remaining
FDT6_ENTRY_SIZE = 22


@dataclass(frozen=True, slots=True)
class BDT6Entry:
    """Broadcast Distribution Table entry for BACnet/IPv6 per Annex U.

    IPv6 BBMDs do not use broadcast masks (IPv6 uses multicast).
    Each entry contains only the B/IPv6 address of a peer BBMD.
    """

    address: BIP6Address

    def encode(self) -> bytes:
        """Encode to 18-byte wire format."""
        return self.address.encode()

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BDT6Entry:
        """Decode from 18-byte wire format."""
        address = BIP6Address.decode(data[0:BIP6_ADDRESS_LENGTH])
        return cls(address=address)


@dataclass(frozen=True, slots=True)
class FDT6Entry:
    """Foreign Device Table entry for BACnet/IPv6 per Annex U.

    Tracks a registered foreign device with its TTL and
    the absolute time at which the entry expires.
    """

    address: BIP6Address
    vmac: bytes  # 3-byte VMAC of the foreign device
    ttl: int  # Time-to-Live supplied at registration (seconds)
    expiry: float  # Absolute time (time.monotonic) when entry expires

    @property
    def remaining(self) -> int:
        """Seconds remaining before this entry expires.

        Capped at 65535 per wire encoding (2-octet field).
        """
        return min(65535, max(0, int(self.expiry - time.monotonic())))


def _encode_bvlc6_result(result_code: Bvlc6ResultCode, source_vmac: bytes) -> bytes:
    """Encode a BVLC6-Result message with source VMAC."""
    return encode_bvll6(
        Bvlc6Function.BVLC_RESULT, result_code.to_bytes(2, "big"), source_vmac=source_vmac
    )


class BBMD6Manager:
    """BACnet/IPv6 Broadcast Management Device per Annex U.

    Manages BDT (Broadcast Distribution Table) and FDT (Foreign Device
    Table), handles broadcast forwarding between BACnet/IPv6 subnets,
    and processes foreign device registration requests.

    Key differences from IPv4 BBMD:
    - No broadcast mask -- all BDT peer forwarding is unicast
    - All BVLL6 messages include ``source_vmac`` parameter
    - ``Forwarded-NPDU`` includes 18-byte ``originating_address``
    - Uses multicast for local re-broadcast of Forwarded-NPDUs
    - FDT keyed on ``BIP6Address`` (18 bytes)
    """

    def __init__(
        self,
        local_address: BIP6Address,
        local_vmac: bytes,
        send_callback: Callable[[bytes, BIP6Address], None],
        local_broadcast_callback: Callable[[bytes, bytes], None] | None = None,
        multicast_send_callback: Callable[[bytes], None] | None = None,
        max_fdt_entries: int = 128,
        accept_fd_registrations: bool = True,
        fdt_cleanup_interval: float = 10.0,
    ) -> None:
        """Initialize IPv6 BBMD manager.

        :param local_address: This BBMD's B/IPv6 address.
        :param local_vmac: 3-byte VMAC for all outgoing BVLL6 messages.
        :param send_callback: Called with ``(raw_bytes, destination)`` to send
            a UDP datagram to a specific address.
        :param local_broadcast_callback: Called with ``(npdu_bytes, source_vmac)``
            to deliver an NPDU to the BBMD's own application layer.
        :param multicast_send_callback: Called with ``(raw_bytes,)`` to
            re-broadcast a Forwarded-NPDU to the local multicast group.
        :param max_fdt_entries: Maximum number of foreign device table entries.
        :param accept_fd_registrations: Whether to accept foreign device
            registrations.
        :param fdt_cleanup_interval: How often (in seconds) the FDT cleanup
            loop runs to purge expired foreign device entries.
        """
        self._local_address = local_address
        self._local_vmac = local_vmac
        self._send = send_callback
        self._local_broadcast = local_broadcast_callback
        self._multicast_send = multicast_send_callback
        self._max_fdt_entries = max_fdt_entries
        self._accept_fd_registrations = accept_fd_registrations
        self._fdt_cleanup_interval = fdt_cleanup_interval
        self._bdt: list[BDT6Entry] = []
        self._fdt: dict[BIP6Address, FDT6Entry] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def bdt(self) -> list[BDT6Entry]:
        """Current Broadcast Distribution Table."""
        return list(self._bdt)

    @property
    def fdt(self) -> dict[BIP6Address, FDT6Entry]:
        """Current Foreign Device Table."""
        return dict(self._fdt)

    @property
    def accept_fd_registrations(self) -> bool:
        """Whether foreign device registrations are accepted."""
        return self._accept_fd_registrations

    @accept_fd_registrations.setter
    def accept_fd_registrations(self, value: bool) -> None:
        self._accept_fd_registrations = value

    def set_bdt(self, entries: list[BDT6Entry]) -> None:
        """Set the Broadcast Distribution Table.

        :param entries: New BDT entries. Should include this BBMD's own entry.
        """
        self._bdt = list(entries)
        logger.info("BDT6 updated with %d entries", len(self._bdt))

    async def start(self) -> None:
        """Start the FDT cleanup background task."""
        self._cleanup_task = asyncio.create_task(self._fdt_cleanup_loop())
        logger.info(
            "BBMD6Manager started on [%s]:%d (BDT=%d entries, FD registration=%s)",
            self._local_address.host,
            self._local_address.port,
            len(self._bdt),
            "enabled" if self._accept_fd_registrations else "disabled",
        )

    async def stop(self) -> None:
        """Stop the FDT cleanup background task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
        logger.info("BBMD6Manager stopped")

    def handle_bvlc(
        self,
        function: Bvlc6Function,
        data: bytes,
        source: BIP6Address,
        source_vmac: bytes | None = None,
    ) -> bool:
        """Process a BVLC6 message directed at the BBMD.

        :param function: BVLC6 function code.
        :param data: Payload after BVLL6 header fields.
        :param source: UDP source address.
        :param source_vmac: 3-byte VMAC of the sender.
        :returns: ``True`` if the message was fully consumed by the BBMD and
            should *not* be delivered locally. ``False`` if the NPDU
            should also be processed by the normal receive path.
        """
        # Drop Forwarded-NPDUs whose originating address is our own (loop prevention)
        if function == Bvlc6Function.FORWARDED_NPDU:
            # originating_address is parsed by the caller; check source
            pass

        match function:
            case Bvlc6Function.ORIGINAL_BROADCAST_NPDU:
                self._handle_original_broadcast(data, source, source_vmac or b"")
                return False  # Also deliver locally

            case Bvlc6Function.FORWARDED_NPDU:
                self._handle_forwarded_npdu(data, source, source_vmac or b"")
                return False  # BBMD delivers via local_broadcast callback

            case Bvlc6Function.REGISTER_FOREIGN_DEVICE:
                self._handle_register_foreign_device(data, source, source_vmac or b"")
                return True

            case Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY:
                self._handle_delete_fdt_entry(data, source)
                return True

            case Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU:
                self._handle_distribute_broadcast(data, source, source_vmac or b"")
                return True

            case Bvlc6Function.ADDRESS_RESOLUTION:
                self._handle_address_resolution(data, source, source_vmac or b"")
                return True

            case _:
                return False

    # --- Broadcast forwarding ---

    def _handle_original_broadcast(
        self, npdu: bytes, source: BIP6Address, source_vmac: bytes
    ) -> None:
        """Handle Original-Broadcast-NPDU per Annex U.

        Forward to BDT peers and FDT entries as Forwarded-NPDU.
        """
        logger.debug(
            "Original-Broadcast from [%s]:%d, forwarding %d bytes",
            source.host,
            source.port,
            len(npdu),
        )
        self._forward_to_peers_and_fds(npdu, source, source_vmac)

    def _handle_forwarded_npdu(
        self,
        npdu: bytes,
        originating_source: BIP6Address,
        source_vmac: bytes,
    ) -> None:
        """Handle Forwarded-NPDU per Annex U.

        Re-broadcast locally via multicast, forward to FDT entries.
        Does NOT forward to BDT peers to prevent infinite loops.
        """
        # Drop self-originated Forwarded-NPDUs (loop prevention)
        if originating_source == self._local_address:
            logger.debug("Dropped self-originated Forwarded-NPDU")
            return

        forwarded = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            npdu,
            source_vmac=self._local_vmac,
            originating_address=originating_source,
        )

        # Forward to all FDs except the originating device
        for fd in self._fdt.values():
            if fd.address == originating_source:
                continue
            self._send(forwarded, fd.address)

        # Re-broadcast on the local multicast group
        if self._multicast_send is not None:
            self._multicast_send(forwarded)

        # Deliver to the BBMD's own application layer
        if self._local_broadcast is not None:
            self._local_broadcast(npdu, source_vmac)

    def _handle_distribute_broadcast(
        self, npdu: bytes, source: BIP6Address, source_vmac: bytes
    ) -> None:
        """Handle Distribute-Broadcast-NPDU per Annex U.

        Verify FD registered, then forward to BDT + other FDT + local multicast.
        """
        logger.debug("Distribute-Broadcast-NPDU from [%s]:%d", source.host, source.port)
        if source not in self._fdt:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        # Forward to BDT peers and other foreign devices (not the sender)
        self._forward_to_peers_and_fds(npdu, source, source_vmac, exclude_fd=source)

        # Broadcast locally via multicast
        forwarded = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            npdu,
            source_vmac=self._local_vmac,
            originating_address=source,
        )
        if self._multicast_send is not None:
            self._multicast_send(forwarded)

        # Deliver to the BBMD's own application layer
        if self._local_broadcast is not None:
            self._local_broadcast(npdu, source_vmac)

    def _forward_to_peers_and_fds(
        self,
        npdu: bytes,
        originating_source: BIP6Address,
        source_vmac: bytes,
        *,
        exclude_fd: BIP6Address | None = None,
    ) -> None:
        """Forward NPDU to all BDT peers and foreign devices.

        Wraps the NPDU in a Forwarded-NPDU and sends to:
        - All BDT peers (except this BBMD and the originating source)
        - All registered foreign devices (optionally excluding one)

        :param npdu: Raw NPDU bytes to forward.
        :param originating_source: Original source B/IPv6 address.
        :param source_vmac: VMAC of the originating device.
        :param exclude_fd: Optional foreign device to exclude (the sender).
        """
        forwarded = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            npdu,
            source_vmac=self._local_vmac,
            originating_address=originating_source,
        )

        # Forward to BDT peers (except self and the originating source)
        for entry in self._bdt:
            if entry.address == self._local_address:
                continue
            if entry.address == originating_source:
                continue
            self._send(forwarded, entry.address)

        # Forward to registered foreign devices
        for fd in self._fdt.values():
            if exclude_fd is not None and fd.address == exclude_fd:
                continue
            self._send(forwarded, fd.address)

    # --- Address resolution forwarding ---

    def _handle_address_resolution(
        self, data: bytes, source: BIP6Address, source_vmac: bytes
    ) -> None:
        """Forward Address-Resolution as Forwarded-Address-Resolution to BDT + FDT."""
        forwarded = encode_bvll6(
            Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
            data,
            source_vmac=source_vmac,
            originating_address=source,
        )
        for entry in self._bdt:
            if entry.address == self._local_address:
                continue
            self._send(forwarded, entry.address)
        for fd in self._fdt.values():
            if fd.address == source:
                continue
            self._send(forwarded, fd.address)

    # --- Foreign device registration ---

    def _handle_register_foreign_device(
        self, data: bytes, source: BIP6Address, source_vmac: bytes
    ) -> None:
        """Handle Register-Foreign-Device per Annex U.

        Payload is a 2-octet TTL (seconds). The BBMD adds the device
        to the FDT with an expiry of TTL + 30s grace period.
        """
        if not self._accept_fd_registrations:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        if len(data) < 2:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        ttl = int.from_bytes(data[0:2], "big")
        if ttl < 1:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        # Reject new registrations when FDT is full (re-registrations OK)
        if source not in self._fdt and len(self._fdt) >= self._max_fdt_entries:
            logger.warning(
                "FDT6 full (%d entries), rejecting registration from [%s]:%d",
                self._max_fdt_entries,
                source.host,
                source.port,
            )
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        expiry = time.monotonic() + ttl + FDT6_GRACE_PERIOD_SECONDS
        self._fdt[source] = FDT6Entry(address=source, vmac=source_vmac, ttl=ttl, expiry=expiry)
        logger.info(
            "Registered IPv6 foreign device [%s]:%d with TTL=%ds",
            source.host,
            source.port,
            ttl,
        )

        result = _encode_bvlc6_result(Bvlc6ResultCode.SUCCESSFUL_COMPLETION, self._local_vmac)
        self._send(result, source)

    # --- FDT management ---

    def _handle_delete_fdt_entry(self, data: bytes, source: BIP6Address) -> None:
        """Handle Delete-Foreign-Device-Table-Entry per Annex U.

        Payload is an 18-octet B/IPv6 address of the entry to delete.
        """
        if len(data) < BIP6_ADDRESS_LENGTH:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK, self._local_vmac
            )
            self._send(result, source)
            return

        addr = BIP6Address.decode(data[0:BIP6_ADDRESS_LENGTH])
        if addr in self._fdt:
            del self._fdt[addr]
            logger.info("Deleted FDT6 entry for [%s]:%d", addr.host, addr.port)
            result = _encode_bvlc6_result(Bvlc6ResultCode.SUCCESSFUL_COMPLETION, self._local_vmac)
        else:
            result = _encode_bvlc6_result(
                Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK, self._local_vmac
            )
        self._send(result, source)

    def read_bdt(self) -> list[BDT6Entry]:
        """Return a copy of the current BDT."""
        return list(self._bdt)

    def read_fdt(self) -> dict[BIP6Address, FDT6Entry]:
        """Return a copy of the current FDT."""
        return dict(self._fdt)

    # --- FDT cleanup ---

    async def _fdt_cleanup_loop(self) -> None:
        """Periodically purge expired FDT entries."""
        while True:
            await asyncio.sleep(self._fdt_cleanup_interval)
            try:
                self._purge_expired_fdt_entries()
            except Exception:
                logger.warning("Error in FDT6 cleanup loop", exc_info=True)

    def _purge_expired_fdt_entries(self) -> None:
        """Remove FDT entries whose TTL + grace period has elapsed."""
        now = time.monotonic()
        expired = [addr for addr, fd in self._fdt.items() if fd.expiry <= now]
        for addr in expired:
            del self._fdt[addr]
            logger.info("Purged expired FDT6 entry for [%s]:%d", addr.host, addr.port)
