"""BACnet/IP Broadcast Management Device (BBMD) per Annex J.4-J.5.

Provides BBMDManager for BDT/FDT management, broadcast forwarding
between BACnet/IP subnets, and foreign device registration handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bvll import encode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Per Annex J.5.2.3, the BBMD adds a 30-second grace period to the TTL
# before purging expired foreign device entries.
FDT_GRACE_PERIOD_SECONDS = 30

# BDT entry wire size: 6-octet B/IP address + 4-octet broadcast mask
BDT_ENTRY_SIZE = 10

# FDT entry wire size: 6-octet B/IP address + 2-octet TTL + 2-octet remaining
FDT_ENTRY_SIZE = 10


@dataclass(frozen=True, slots=True)
class BDTEntry:
    """Broadcast Distribution Table entry per Annex J.4.

    Each entry contains the B/IP address of a BBMD peer and a
    4-octet broadcast distribution mask used to compute the
    forwarding address.
    """

    address: BIPAddress
    broadcast_mask: bytes  # 4 octets

    def encode(self) -> bytes:
        """Encode to 10-byte wire format."""
        return self.address.encode() + self.broadcast_mask

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BDTEntry:
        """Decode from 10-byte wire format."""
        address = BIPAddress.decode(data[0:6])
        broadcast_mask = bytes(data[6:10])
        return cls(address=address, broadcast_mask=broadcast_mask)


@dataclass(slots=True)
class FDTEntry:
    """Foreign Device Table entry per Annex J.5.2.

    Tracks a registered foreign device with its TTL and
    the absolute time at which the entry expires.
    """

    address: BIPAddress
    ttl: int  # Time-to-Live supplied at registration (seconds)
    expiry: float  # Absolute time (time.monotonic) when entry expires

    @property
    def remaining(self) -> int:
        """Seconds remaining before this entry expires.

        Capped at 65535 per J.5.2.1 (2-octet wire encoding).
        """
        return min(65535, max(0, int(self.expiry - time.monotonic())))


def _encode_bvlc_result(result_code: BvlcResultCode) -> bytes:
    """Encode a BVLC-Result message."""
    return encode_bvll(BvlcFunction.BVLC_RESULT, result_code.to_bytes(2, "big"))


def _compute_forward_address(entry: BDTEntry) -> BIPAddress:
    """Compute forwarding address from BDT entry and mask per Annex J.4.5.

    If mask is all 1s (255.255.255.255), the result is the BBMD's
    own address (unicast / two-hop forwarding). Otherwise, the result
    is a directed broadcast address (one-hop forwarding):

        dest_ip = entry_ip | ~mask

    Args:
        entry: BDT entry with address and broadcast mask.

    Returns:
        Computed forwarding BIPAddress.
    """
    ip_bytes = bytes(int(x) for x in entry.address.host.split("."))
    mask = entry.broadcast_mask
    inv_mask = bytes(~b & 0xFF for b in mask)
    dest_ip = bytes(a | b for a, b in zip(ip_bytes, inv_mask))
    host = ".".join(str(b) for b in dest_ip)
    return BIPAddress(host=host, port=entry.address.port)


class BBMDManager:
    """BACnet/IP Broadcast Management Device per Annex J.4-J.5.

    Manages BDT (Broadcast Distribution Table) and FDT (Foreign Device
    Table), handles broadcast forwarding between BACnet/IP subnets,
    and processes foreign device registration requests.

    The BBMD must be wired into a BIPTransport to intercept and process
    BVLC messages before they reach the application layer.
    """

    def __init__(
        self,
        local_address: BIPAddress,
        send_callback: Callable[[bytes, BIPAddress], None],
        local_broadcast_callback: Callable[[bytes, BIPAddress], None] | None = None,
    ) -> None:
        """Initialize BBMD manager.

        Args:
            local_address: This BBMD's B/IP address.
            send_callback: Called with (raw_bytes, destination) to send
                a UDP datagram. Typically BIPTransport._transport.sendto
                wrapped to accept BIPAddress.
            local_broadcast_callback: Called with (npdu_bytes, source_address)
                to deliver an NPDU to the local network as if it were a
                local broadcast. Used when forwarding Forwarded-NPDU and
                Distribute-Broadcast-To-Network to the local subnet.
        """
        self._local_address = local_address
        self._send = send_callback
        self._local_broadcast = local_broadcast_callback
        self._bdt: list[BDTEntry] = []
        self._fdt: dict[BIPAddress, FDTEntry] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def bdt(self) -> list[BDTEntry]:
        """Current Broadcast Distribution Table."""
        return list(self._bdt)

    @property
    def fdt(self) -> dict[BIPAddress, FDTEntry]:
        """Current Foreign Device Table."""
        return dict(self._fdt)

    def set_bdt(self, entries: list[BDTEntry]) -> None:
        """Set the Broadcast Distribution Table.

        Args:
            entries: New BDT entries. Should include this BBMD's own entry.
        """
        self._bdt = list(entries)
        logger.info("BDT updated with %d entries", len(self._bdt))

    async def start(self) -> None:
        """Start the FDT cleanup background task."""
        self._cleanup_task = asyncio.create_task(self._fdt_cleanup_loop())

    async def stop(self) -> None:
        """Stop the FDT cleanup background task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    def handle_bvlc(self, function: BvlcFunction, data: bytes, source: BIPAddress) -> bool:
        """Process a BVLC message directed at the BBMD.

        Args:
            function: BVLC function code.
            data: Payload after BVLL header (for most functions) or
                full payload including originating address (for Forwarded-NPDU,
                which is pre-parsed by decode_bvll).
            source: UDP source address of the sender.

        Returns:
            True if the message was handled by the BBMD, False if it
            should be processed by the normal receive path.
        """
        match function:
            case BvlcFunction.ORIGINAL_BROADCAST_NPDU:
                self._handle_original_broadcast(data, source)
                return False  # Also deliver locally via normal path

            case BvlcFunction.FORWARDED_NPDU:
                self._handle_forwarded_npdu(data, source)
                return False  # Also deliver locally via normal path

            case BvlcFunction.REGISTER_FOREIGN_DEVICE:
                self._handle_register_foreign_device(data, source)
                return True

            case BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE:
                self._handle_read_bdt(source)
                return True

            case BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE:
                self._handle_write_bdt(data, source)
                return True

            case BvlcFunction.READ_FOREIGN_DEVICE_TABLE:
                self._handle_read_fdt(source)
                return True

            case BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY:
                self._handle_delete_fdt_entry(data, source)
                return True

            case BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK:
                self._handle_distribute_broadcast(data, source)
                return True

            case _:
                return False

    # --- Broadcast forwarding ---

    def _handle_original_broadcast(self, npdu: bytes, source: BIPAddress) -> None:
        """Handle Original-Broadcast-NPDU per Annex J.4.5.

        When a BBMD receives an Original-Broadcast-NPDU from a device
        on its local subnet, it wraps the NPDU in a Forwarded-NPDU and
        sends it to all BDT peers (except itself) and all registered
        foreign devices.
        """
        self._forward_to_peers_and_fds(npdu, source)

    def _handle_forwarded_npdu(self, npdu: bytes, source: BIPAddress) -> None:
        """Handle Forwarded-NPDU per Annex J.4.5.

        When a BBMD receives a Forwarded-NPDU from another BBMD,
        it broadcasts the NPDU on its local subnet and forwards to
        all registered foreign devices. It does NOT forward to
        other BDT peers (to prevent infinite loops).

        Note: The originating_address and npdu data have already been
        parsed by decode_bvll. The 'source' parameter here is the
        originating address, and 'npdu' is the raw NPDU data.
        """
        # Forward to all registered foreign devices
        forwarded = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=source,
        )
        for fd in self._fdt.values():
            self._send(forwarded, fd.address)

        # Broadcast locally (if callback configured)
        if self._local_broadcast is not None:
            self._local_broadcast(npdu, source)

    def _handle_distribute_broadcast(self, npdu: bytes, source: BIPAddress) -> None:
        """Handle Distribute-Broadcast-To-Network per Annex J.4.5.

        When a BBMD receives a Distribute-Broadcast-To-Network from a
        registered foreign device, it treats it like an Original-Broadcast-NPDU
        from that foreign device: forwards to all BDT peers and all
        registered foreign devices (except the sender), and broadcasts locally.
        """
        # Verify the source is a registered foreign device
        if source not in self._fdt:
            result = _encode_bvlc_result(BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK)
            self._send(result, source)
            return

        # Forward to BDT peers and other foreign devices (not the sender)
        self._forward_to_peers_and_fds(npdu, source, exclude_fd=source)

        # Broadcast locally (if callback configured)
        if self._local_broadcast is not None:
            self._local_broadcast(npdu, source)

    def _forward_to_peers_and_fds(
        self,
        npdu: bytes,
        originating_source: BIPAddress,
        *,
        exclude_fd: BIPAddress | None = None,
    ) -> None:
        """Forward NPDU to all BDT peers and foreign devices.

        Wraps the NPDU in a Forwarded-NPDU and sends to:
        - All BDT peers (except this BBMD)
        - All registered foreign devices (optionally excluding one)

        Args:
            npdu: Raw NPDU bytes to forward.
            originating_source: Original source B/IP address.
            exclude_fd: Optional foreign device to exclude (the sender).
        """
        forwarded = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=originating_source,
        )

        # Forward to BDT peers (except self)
        for entry in self._bdt:
            if entry.address == self._local_address:
                continue
            dest = _compute_forward_address(entry)
            self._send(forwarded, dest)

        # Forward to registered foreign devices
        for fd in self._fdt.values():
            if exclude_fd is not None and fd.address == exclude_fd:
                continue
            self._send(forwarded, fd.address)

    # --- Foreign device registration ---

    def _handle_register_foreign_device(self, data: bytes, source: BIPAddress) -> None:
        """Handle Register-Foreign-Device per Annex J.5.2.3.

        Payload is a 2-octet TTL (seconds). The BBMD adds the device
        to the FDT with an expiry of TTL + 30s grace period.
        """
        if len(data) < 2:
            result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
            self._send(result, source)
            return

        ttl = int.from_bytes(data[0:2], "big")
        expiry = time.monotonic() + ttl + FDT_GRACE_PERIOD_SECONDS

        self._fdt[source] = FDTEntry(address=source, ttl=ttl, expiry=expiry)
        logger.info(
            "Registered foreign device %s:%d with TTL=%ds",
            source.host,
            source.port,
            ttl,
        )

        result = _encode_bvlc_result(BvlcResultCode.SUCCESSFUL_COMPLETION)
        self._send(result, source)

    # --- BDT management ---

    def _handle_read_bdt(self, source: BIPAddress) -> None:
        """Handle Read-Broadcast-Distribution-Table per Annex J.4.4.1.

        Responds with Read-BDT-Ack containing all BDT entries.
        Per J.2.4, an empty BDT is signified by a list of length zero.
        """
        payload = bytearray()
        for entry in self._bdt:
            payload.extend(entry.encode())
        ack = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK, bytes(payload))
        self._send(ack, source)

    def _handle_write_bdt(self, data: bytes, source: BIPAddress) -> None:
        """Handle Write-Broadcast-Distribution-Table per Annex J.4.1.

        Replaces the BDT with the entries in the payload.
        Each entry is 10 octets: 6-octet B/IP address + 4-octet mask.
        """
        if len(data) % BDT_ENTRY_SIZE != 0:
            result = _encode_bvlc_result(BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK)
            self._send(result, source)
            return

        entries = []
        for i in range(0, len(data), BDT_ENTRY_SIZE):
            entries.append(BDTEntry.decode(data[i : i + BDT_ENTRY_SIZE]))

        self._bdt = entries
        logger.info("BDT written with %d entries from %s", len(entries), source)

        result = _encode_bvlc_result(BvlcResultCode.SUCCESSFUL_COMPLETION)
        self._send(result, source)

    # --- FDT management ---

    def _handle_read_fdt(self, source: BIPAddress) -> None:
        """Handle Read-Foreign-Device-Table per Annex J.5.2.1.1.

        Responds with Read-FDT-Ack containing all FDT entries.
        Per J.2.8, an empty FDT is signified by a list of length zero.
        """
        payload = bytearray()
        for fd in self._fdt.values():
            payload.extend(fd.address.encode())
            payload.extend(fd.ttl.to_bytes(2, "big"))
            payload.extend(fd.remaining.to_bytes(2, "big"))
        ack = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK, bytes(payload))
        self._send(ack, source)

    def _handle_delete_fdt_entry(self, data: bytes, source: BIPAddress) -> None:
        """Handle Delete-Foreign-Device-Table-Entry per Annex J.5.4.

        Payload is a 6-octet B/IP address of the entry to delete.
        """
        if len(data) < 6:
            result = _encode_bvlc_result(BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK)
            self._send(result, source)
            return

        addr = BIPAddress.decode(data[0:6])
        if addr in self._fdt:
            del self._fdt[addr]
            logger.info("Deleted FDT entry for %s:%d", addr.host, addr.port)
            result = _encode_bvlc_result(BvlcResultCode.SUCCESSFUL_COMPLETION)
        else:
            result = _encode_bvlc_result(BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK)
        self._send(result, source)

    # --- FDT cleanup ---

    async def _fdt_cleanup_loop(self) -> None:
        """Periodically purge expired FDT entries."""
        while True:
            await asyncio.sleep(10)  # Check every 10 seconds
            self._purge_expired_fdt_entries()

    def _purge_expired_fdt_entries(self) -> None:
        """Remove FDT entries whose TTL + grace period has elapsed."""
        now = time.monotonic()
        expired = [addr for addr, fd in self._fdt.items() if fd.expiry <= now]
        for addr in expired:
            del self._fdt[addr]
            logger.info("Purged expired FDT entry for %s:%d", addr.host, addr.port)
