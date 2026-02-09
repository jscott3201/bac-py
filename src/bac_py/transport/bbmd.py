"""BACnet/IP Broadcast Management Device (BBMD) per Annex J.4-J.5.

Provides BBMDManager for BDT/FDT management, broadcast forwarding
between BACnet/IP subnets, and foreign device registration handling.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bac_py.network.address import BIPAddress
from bac_py.transport.bvll import encode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


@dataclass(frozen=True, slots=True)
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
    dest_ip = bytes(a | b for a, b in zip(ip_bytes, inv_mask, strict=True))
    host = ".".join(str(b) for b in dest_ip)
    return BIPAddress(host=host, port=entry.address.port)


_ALL_ONES_MASK = b"\xff\xff\xff\xff"


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
        broadcast_address: BIPAddress | None = None,
        max_fdt_entries: int = 128,
        accept_fd_registrations: bool = True,
        allow_write_bdt: bool = False,
        global_address: BIPAddress | None = None,
        bdt_backup_path: Path | None = None,
        fdt_cleanup_interval: float = 10.0,
    ) -> None:
        """Initialize BBMD manager.

        Args:
            local_address: This BBMD's B/IP address.
            send_callback: Called with (raw_bytes, destination) to send
                a UDP datagram. Typically BIPTransport._transport.sendto
                wrapped to accept BIPAddress.
            local_broadcast_callback: Called with (npdu_bytes, source_address)
                to deliver an NPDU to the BBMD's own application/router
                layer.
            broadcast_address: The local subnet broadcast address. When
                set, Forwarded-NPDUs arriving via unicast (BDT all-ones
                mask) are re-broadcast on the local wire so other
                devices on the subnet can receive them.
            max_fdt_entries: Maximum number of foreign device table
                entries. New registrations are NAKed when the limit
                is reached. Re-registrations of existing entries are
                always accepted regardless of the limit.
            accept_fd_registrations: Whether to accept foreign device
                registrations. When ``False``, all registration
                requests are NAKed. Defaults to ``True``.
            allow_write_bdt: Whether to accept Write-BDT requests.
                Defaults to ``False`` per protocol revision >= 17.
                Set to ``True`` to allow remote BDT configuration.
            global_address: Optional public/NAT address per Annex J.7.8.
                When set, outgoing Forwarded-NPDUs for locally originated
                broadcasts use this address as the originating source
                instead of the actual sender's local address.  BDT
                entries whose computed forward address matches this
                address are skipped to prevent NAT loops.
            bdt_backup_path: Optional path to persist the BDT as JSON.
                When set, the BDT is saved to this file whenever it
                changes (via ``set_bdt`` or Write-BDT).  On ``start()``,
                the BDT is restored from this file if it exists and
                is valid.
            fdt_cleanup_interval: How often (in seconds) the FDT cleanup
                loop runs to purge expired foreign device entries.
                Defaults to 10 seconds.
        """
        self._local_address = local_address
        self._send = send_callback
        self._local_broadcast = local_broadcast_callback
        self._broadcast_address = broadcast_address
        self._max_fdt_entries = max_fdt_entries
        self._accept_fd_registrations = accept_fd_registrations
        self._allow_write_bdt = allow_write_bdt
        self._global_address = global_address
        self._bdt_backup_path = bdt_backup_path
        self._fdt_cleanup_interval = fdt_cleanup_interval
        self._bdt: list[BDTEntry] = []
        self._bdt_forward_cache: list[BIPAddress] = []
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

    @property
    def accept_fd_registrations(self) -> bool:
        """Whether foreign device registrations are accepted."""
        return self._accept_fd_registrations

    @accept_fd_registrations.setter
    def accept_fd_registrations(self, value: bool) -> None:
        self._accept_fd_registrations = value

    @property
    def global_address(self) -> BIPAddress | None:
        """Optional public/NAT address per Annex J.7.8."""
        return self._global_address

    @global_address.setter
    def global_address(self, value: BIPAddress | None) -> None:
        self._global_address = value

    def set_bdt(self, entries: list[BDTEntry]) -> None:
        """Set the Broadcast Distribution Table.

        Args:
            entries: New BDT entries. Should include this BBMD's own entry.
        """
        self._bdt = list(entries)
        self._rebuild_forward_cache()
        logger.info("BDT updated with %d entries", len(self._bdt))
        self._save_bdt_backup()

    def _rebuild_forward_cache(self) -> None:
        """Rebuild the pre-computed forward address cache from the current BDT.

        Called whenever the BDT changes to avoid recomputing
        ``_compute_forward_address`` on every broadcast forward.
        """
        self._bdt_forward_cache = [_compute_forward_address(entry) for entry in self._bdt]

    async def start(self) -> None:
        """Start the FDT cleanup background task.

        If a ``bdt_backup_path`` was configured and the file exists,
        the BDT is restored from it before starting.
        """
        await asyncio.to_thread(self._load_bdt_backup)
        self._cleanup_task = asyncio.create_task(self._fdt_cleanup_loop())

    async def stop(self) -> None:
        """Stop the FDT cleanup background task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    def _is_unicast_bdt_mask(self, addr: BIPAddress) -> bool:
        """Check whether a BDT peer uses a unicast mask (all-ones).

        When the mask is all-ones, Forwarded-NPDUs are sent as unicast
        directly to the peer BBMD.  With any other mask, the packet is
        sent to a directed-broadcast address and is already visible to
        all devices on the peer's subnet.

        Returns ``True`` (assume unicast) if the address is not found
        in the BDT so that local re-broadcast is performed defensively.
        """
        for entry in self._bdt:
            if entry.address == addr:
                return entry.broadcast_mask == _ALL_ONES_MASK
        return True  # Unknown peer -- assume unicast for safety

    def handle_bvlc(
        self,
        function: BvlcFunction,
        data: bytes,
        source: BIPAddress,
        *,
        udp_source: BIPAddress | None = None,
    ) -> bool:
        """Process a BVLC message directed at the BBMD.

        Args:
            function: BVLC function code.
            data: Payload after BVLL header (for most functions) or
                full payload including originating address (for Forwarded-NPDU,
                which is pre-parsed by decode_bvll).
            source: For most functions this is the UDP source address.
                For ``FORWARDED_NPDU`` this is the **originating**
                address extracted from the BVLL header.
            udp_source: The actual UDP peer address.  Only needed for
                ``FORWARDED_NPDU`` where *source* is the originating
                address.  Used for BDT mask lookup to decide whether
                to re-broadcast the NPDU on the local wire.

        Returns:
            ``True`` if the message was fully consumed by the BBMD and
            should *not* be delivered locally.  ``False`` if the NPDU
            should also be processed by the normal receive path (this
            is the case for Original-Broadcast-NPDU and Forwarded-NPDU,
            which are forwarded *and* delivered locally).
        """
        # S2: Drop Forwarded-NPDUs whose originating address is our own.
        # This prevents loops where our broadcast comes back through a
        # peer BBMD.  Original-Broadcast and Original-Unicast echoes are
        # already caught by the transport-level self-message check in
        # BIPTransport._on_datagram_received (F6).
        # F1: Also drop if originating address matches our global/NAT address.
        if function == BvlcFunction.FORWARDED_NPDU and (
            source == self._local_address
            or (self._global_address is not None and source == self._global_address)
        ):
            logger.debug("Dropped self-originated Forwarded-NPDU")
            return True

        match function:
            case BvlcFunction.ORIGINAL_BROADCAST_NPDU:
                self._handle_original_broadcast(data, source)
                return False  # Also deliver locally via normal path

            case BvlcFunction.FORWARDED_NPDU:
                self._handle_forwarded_npdu(data, source, udp_source=udp_source or source)
                return False  # BBMD delivers via _local_broadcast callback

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

    def _handle_forwarded_npdu(
        self,
        npdu: bytes,
        originating_source: BIPAddress,
        *,
        udp_source: BIPAddress,
    ) -> None:
        """Handle Forwarded-NPDU per Annex J.4.5.

        When a BBMD receives a Forwarded-NPDU from another BBMD,
        it forwards to all registered foreign devices (excluding the
        originating device if it is a registered FD) and delivers the
        NPDU to the local application.

        If the sending BBMD has a unicast BDT mask (all-ones), the
        Forwarded-NPDU arrived via unicast and other devices on the
        local subnet have not yet seen it.  In this case the BBMD
        re-broadcasts the Forwarded-NPDU frame on the local wire so
        that local devices can receive it.  When the BDT mask is not
        all-ones, the packet arrived via directed broadcast and local
        devices already received it -- no wire re-broadcast is needed.

        The BBMD does NOT forward to BDT peers (other BBMDs) to prevent
        infinite forwarding loops.
        """
        forwarded = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=originating_source,
        )

        # B3: Forward to all FDs except the originating device.
        for fd in self._fdt.values():
            if fd.address == originating_source:
                continue
            self._send(forwarded, fd.address)

        # B1: Re-broadcast on the local wire when the Forwarded-NPDU
        # arrived via unicast (BDT all-ones mask for this peer).
        # When it arrived via directed broadcast, all local devices
        # already received the packet from the directed broadcast.
        if self._broadcast_address is not None and self._is_unicast_bdt_mask(udp_source):
            self._send(forwarded, self._broadcast_address)

        # Always deliver to the BBMD's own application/router layer.
        if self._local_broadcast is not None:
            self._local_broadcast(npdu, originating_source)

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
        - All BDT peers (except this BBMD and the originating source)
        - All registered foreign devices (optionally excluding one)

        F1: When a ``global_address`` is configured (NAT traversal),
        it is used as the originating address in outgoing Forwarded-NPDUs
        instead of the actual sender's local address.  BDT entries whose
        computed forward address matches the global address are also
        skipped to prevent NAT loops.

        Args:
            npdu: Raw NPDU bytes to forward.
            originating_source: Original source B/IP address.
            exclude_fd: Optional foreign device to exclude (the sender).
        """
        # F1: Use global address as originating source when configured
        forwarded_source = (
            self._global_address if self._global_address is not None else originating_source
        )
        forwarded = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=forwarded_source,
        )

        # Forward to BDT peers (except self and the originating source)
        for entry, dest in zip(self._bdt, self._bdt_forward_cache, strict=True):
            if entry.address == self._local_address:
                continue
            # B2: Don't forward back to the originating source.
            if dest == originating_source:
                continue
            # F1: Don't forward to our own global/NAT address (loop prevention).
            if self._global_address is not None and dest == self._global_address:
                continue
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
        # F4: Reject registration when FD acceptance is disabled.
        if not self._accept_fd_registrations:
            result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
            self._send(result, source)
            return

        if len(data) < 2:
            result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
            self._send(result, source)
            return

        ttl = int.from_bytes(data[0:2], "big")
        if ttl < 1:
            result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
            self._send(result, source)
            return

        # S1: Reject new registrations when FDT is full.
        # Re-registrations (same address) are always accepted.
        if source not in self._fdt and len(self._fdt) >= self._max_fdt_entries:
            logger.warning(
                "FDT full (%d entries), rejecting registration from %s:%d",
                self._max_fdt_entries,
                source.host,
                source.port,
            )
            result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
            self._send(result, source)
            return

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
        # F8: Reject Write-BDT when not allowed (default per revision >= 17).
        if not self._allow_write_bdt:
            result = _encode_bvlc_result(BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK)
            self._send(result, source)
            return

        if len(data) % BDT_ENTRY_SIZE != 0:
            result = _encode_bvlc_result(BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK)
            self._send(result, source)
            return

        entries = []
        for i in range(0, len(data), BDT_ENTRY_SIZE):
            entries.append(BDTEntry.decode(data[i : i + BDT_ENTRY_SIZE]))

        self._bdt = entries
        self._rebuild_forward_cache()
        logger.info("BDT written with %d entries from %s", len(entries), source)
        self._save_bdt_backup()

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
            await asyncio.sleep(self._fdt_cleanup_interval)
            try:
                self._purge_expired_fdt_entries()
            except Exception:
                logger.exception("Error in FDT cleanup loop")

    def _purge_expired_fdt_entries(self) -> None:
        """Remove FDT entries whose TTL + grace period has elapsed."""
        now = time.monotonic()
        expired = [addr for addr, fd in self._fdt.items() if fd.expiry <= now]
        for addr in expired:
            del self._fdt[addr]
            logger.info("Purged expired FDT entry for %s:%d", addr.host, addr.port)

    # --- BDT persistence ---

    def _save_bdt_backup(self) -> None:
        """Persist BDT entries to a JSON file if a backup path is configured.

        Writes atomically by writing to a temporary file first, then
        renaming.  Errors are logged but do not propagate.
        """
        if self._bdt_backup_path is None:
            return
        try:
            entries = [
                {
                    "host": entry.address.host,
                    "port": entry.address.port,
                    "mask": list(entry.broadcast_mask),
                }
                for entry in self._bdt
            ]
            tmp_path = self._bdt_backup_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(entries, indent=2))
            tmp_path.replace(self._bdt_backup_path)
            logger.debug("BDT backup saved to %s", self._bdt_backup_path)
        except Exception:
            logger.exception("Failed to save BDT backup to %s", self._bdt_backup_path)

    def _load_bdt_backup(self) -> None:
        """Load BDT entries from a JSON backup file if it exists.

        Called during ``start()`` to restore the BDT from a previous
        session.  Only loads if no BDT entries are already configured
        (i.e., ``set_bdt()`` was not called before ``start()``).
        Errors are logged but do not propagate.
        """
        if self._bdt_backup_path is None:
            return
        if self._bdt:
            # BDT was already set programmatically -- don't overwrite.
            return
        if not self._bdt_backup_path.exists():
            return
        try:
            raw = json.loads(self._bdt_backup_path.read_text())
            entries = [
                BDTEntry(
                    address=BIPAddress(host=e["host"], port=e["port"]),
                    broadcast_mask=bytes(e["mask"]),
                )
                for e in raw
            ]
            self._bdt = entries
            self._rebuild_forward_cache()
            logger.info("BDT restored from backup with %d entries", len(entries))
        except Exception:
            logger.exception("Failed to load BDT backup from %s", self._bdt_backup_path)
