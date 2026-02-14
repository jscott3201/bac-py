"""Tests for BACnet/IPv6 BBMD manager (bbmd6.py)."""

import asyncio
import time

from bac_py.network.address import BIP6Address
from bac_py.transport.bbmd6 import (
    FDT6_GRACE_PERIOD_SECONDS,
    BBMD6Manager,
    BDT6Entry,
    FDT6Entry,
)
from bac_py.transport.bvll_ipv6 import decode_bvll6
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode

# Helpers

LOCAL_ADDR = BIP6Address(host="fd00::1", port=47808)
LOCAL_VMAC = b"\xaa\xbb\xcc"
PEER_ADDR = BIP6Address(host="fd00::2", port=47808)
FD_ADDR = BIP6Address(host="fd00::10", port=47808)
FD_VMAC = b"\x11\x22\x33"


class SentCollector:
    """Collects sent BVLL6 datagrams for assertions."""

    def __init__(self):
        self.sent: list[tuple[bytes, BIP6Address]] = []
        self.local_delivered: list[tuple[bytes, bytes]] = []
        self.multicast_sent: list[bytes] = []

    def send(self, data: bytes, dest: BIP6Address) -> None:
        self.sent.append((data, dest))

    def local_deliver(self, npdu: bytes, source_vmac: bytes) -> None:
        self.local_delivered.append((npdu, source_vmac))

    def multicast_send(self, data: bytes) -> None:
        self.multicast_sent.append(data)


def _make_bbmd(
    collector: SentCollector | None = None,
    bdt: list[BDT6Entry] | None = None,
    accept_fd: bool = True,
    max_fdt: int = 128,
) -> tuple[BBMD6Manager, SentCollector]:
    if collector is None:
        collector = SentCollector()
    bbmd = BBMD6Manager(
        local_address=LOCAL_ADDR,
        local_vmac=LOCAL_VMAC,
        send_callback=collector.send,
        local_broadcast_callback=collector.local_deliver,
        multicast_send_callback=collector.multicast_send,
        max_fdt_entries=max_fdt,
        accept_fd_registrations=accept_fd,
    )
    if bdt is not None:
        bbmd.set_bdt(bdt)
    return bbmd, collector


# ---------- BDT6Entry ----------


class TestBDT6Entry:
    def test_encode_decode_roundtrip(self):
        entry = BDT6Entry(address=BIP6Address(host="fd00::1", port=47808))
        encoded = entry.encode()
        assert len(encoded) == 18
        decoded = BDT6Entry.decode(encoded)
        assert decoded.address.host == entry.address.host
        assert decoded.address.port == entry.address.port

    def test_decode_from_memoryview(self):
        entry = BDT6Entry(address=PEER_ADDR)
        decoded = BDT6Entry.decode(memoryview(entry.encode()))
        assert decoded.address.port == PEER_ADDR.port


# ---------- FDT6Entry ----------


class TestFDT6Entry:
    def test_remaining_positive(self):
        entry = FDT6Entry(address=FD_ADDR, vmac=FD_VMAC, ttl=60, expiry=time.monotonic() + 30)
        assert entry.remaining > 0
        assert entry.remaining <= 30

    def test_remaining_zero_when_expired(self):
        entry = FDT6Entry(address=FD_ADDR, vmac=FD_VMAC, ttl=60, expiry=time.monotonic() - 1)
        assert entry.remaining == 0

    def test_remaining_capped_at_65535(self):
        entry = FDT6Entry(address=FD_ADDR, vmac=FD_VMAC, ttl=60, expiry=time.monotonic() + 100000)
        assert entry.remaining == 65535


# ---------- Registration ----------


class TestRegistration:
    def test_register_success(self):
        bbmd, col = _make_bbmd()
        ttl_payload = (60).to_bytes(2, "big")
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )

        # Should send success result
        assert len(col.sent) == 1
        data, dest = col.sent[0]
        assert dest == FD_ADDR
        decoded = decode_bvll6(data)
        assert decoded.function == Bvlc6Function.BVLC_RESULT
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.SUCCESSFUL_COMPLETION

        # FDT should have the entry
        assert FD_ADDR in bbmd.fdt
        entry = bbmd.fdt[FD_ADDR]
        assert entry.ttl == 60
        assert entry.vmac == FD_VMAC

    def test_register_nak_when_disabled(self):
        bbmd, col = _make_bbmd(accept_fd=False)
        ttl_payload = (60).to_bytes(2, "big")
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )

        assert len(col.sent) == 1
        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK
        assert FD_ADDR not in bbmd.fdt

    def test_register_nak_short_data(self):
        bbmd, col = _make_bbmd()
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, b"\x00", FD_ADDR, source_vmac=FD_VMAC
        )

        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK

    def test_register_nak_zero_ttl(self):
        bbmd, col = _make_bbmd()
        ttl_payload = (0).to_bytes(2, "big")
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )

        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK

    def test_register_nak_fdt_full(self):
        bbmd, col = _make_bbmd(max_fdt=1)
        # Register first FD
        ttl_payload = (60).to_bytes(2, "big")
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )
        col.sent.clear()

        # Try to register second FD
        fd2 = BIP6Address(host="fd00::11", port=47808)
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, fd2, source_vmac=b"\xdd\xee\xff"
        )

        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK
        assert fd2 not in bbmd.fdt

    def test_re_registration_always_accepted(self):
        bbmd, col = _make_bbmd(max_fdt=1)
        ttl_payload = (60).to_bytes(2, "big")
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )
        col.sent.clear()

        # Re-register same FD (should succeed despite FDT being full)
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE, ttl_payload, FD_ADDR, source_vmac=FD_VMAC
        )
        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.SUCCESSFUL_COMPLETION

    def test_expiry_includes_grace_period(self):
        bbmd, _ = _make_bbmd()
        ttl = 60
        before = time.monotonic()
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        after = time.monotonic()
        entry = bbmd.fdt[FD_ADDR]
        assert entry.expiry >= before + ttl + FDT6_GRACE_PERIOD_SECONDS
        assert entry.expiry <= after + ttl + FDT6_GRACE_PERIOD_SECONDS


# ---------- Delete FDT entry ----------


class TestDeleteFDTEntry:
    def test_delete_existing_entry(self):
        bbmd, col = _make_bbmd()
        # Register FD
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        # Delete entry
        bbmd.handle_bvlc(
            Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            FD_ADDR.encode(),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        assert FD_ADDR not in bbmd.fdt
        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.SUCCESSFUL_COMPLETION

    def test_delete_nonexistent_entry_nak(self):
        bbmd, col = _make_bbmd()
        bbmd.handle_bvlc(
            Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            FD_ADDR.encode(),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK

    def test_delete_short_data_nak(self):
        bbmd, col = _make_bbmd()
        bbmd.handle_bvlc(
            Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            b"\x00",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK


# ---------- Broadcast forwarding ----------


class TestBroadcastForwarding:
    def test_original_broadcast_forwards_to_peers_and_fds(self):
        bdt = [
            BDT6Entry(address=LOCAL_ADDR),
            BDT6Entry(address=PEER_ADDR),
        ]
        bbmd, col = _make_bbmd(bdt=bdt)
        # Register an FD
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        # Receive Original-Broadcast
        src = BIP6Address(host="fd00::5", port=47808)
        result = bbmd.handle_bvlc(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            b"\x01\x00\x10",
            src,
            source_vmac=b"\x55\x66\x77",
        )

        # Should NOT consume (returns False so caller also delivers locally)
        assert result is False

        # Should forward to PEER_ADDR and FD_ADDR (2 sends)
        assert len(col.sent) == 2
        destinations = {dest for _, dest in col.sent}
        assert PEER_ADDR in destinations
        assert FD_ADDR in destinations

        # Verify Forwarded-NPDU format
        for data, _ in col.sent:
            decoded = decode_bvll6(data)
            assert decoded.function == Bvlc6Function.FORWARDED_NPDU
            assert decoded.source_vmac == LOCAL_VMAC
            assert decoded.originating_address == src

    def test_original_broadcast_not_sent_to_self(self):
        bdt = [BDT6Entry(address=LOCAL_ADDR)]
        bbmd, col = _make_bbmd(bdt=bdt)

        src = BIP6Address(host="fd00::5", port=47808)
        bbmd.handle_bvlc(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU, b"\x01", src, source_vmac=b"\x55\x66\x77"
        )

        # Should not forward to self
        assert len(col.sent) == 0

    def test_original_broadcast_not_sent_to_originator(self):
        bdt = [
            BDT6Entry(address=LOCAL_ADDR),
            BDT6Entry(address=PEER_ADDR),
        ]
        bbmd, col = _make_bbmd(bdt=bdt)

        # Source is the peer itself
        bbmd.handle_bvlc(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            b"\x01",
            PEER_ADDR,
            source_vmac=b"\x55\x66\x77",
        )

        # Should not forward back to the originating peer
        assert len(col.sent) == 0


# ---------- Forwarded-NPDU ----------


class TestForwardedNPDU:
    def test_forwarded_npdu_to_fds_and_multicast(self):
        bbmd, col = _make_bbmd()
        # Register an FD
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        orig = BIP6Address(host="fd00::20", port=47808)
        result = bbmd.handle_bvlc(
            Bvlc6Function.FORWARDED_NPDU, b"\x01\x00", orig, source_vmac=b"\x44\x55\x66"
        )
        assert result is False

        # Should forward to FD and multicast
        assert len(col.sent) == 1  # FD
        assert col.sent[0][1] == FD_ADDR
        assert len(col.multicast_sent) == 1
        assert len(col.local_delivered) == 1

    def test_forwarded_npdu_excludes_originator_from_fds(self):
        bbmd, col = _make_bbmd()
        # Register FD_ADDR as an FD
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        # Forwarded-NPDU originates from FD_ADDR
        bbmd.handle_bvlc(Bvlc6Function.FORWARDED_NPDU, b"\x01\x00", FD_ADDR, source_vmac=FD_VMAC)

        # Should NOT forward back to FD_ADDR
        for _data, dest in col.sent:
            assert dest != FD_ADDR

    def test_self_originated_forwarded_npdu_dropped(self):
        bbmd, col = _make_bbmd()

        # Forwarded-NPDU from our own address
        bbmd.handle_bvlc(
            Bvlc6Function.FORWARDED_NPDU, b"\x01\x00", LOCAL_ADDR, source_vmac=LOCAL_VMAC
        )

        assert len(col.sent) == 0
        assert len(col.multicast_sent) == 0
        assert len(col.local_delivered) == 0

    def test_forwarded_npdu_no_multicast_callback(self):
        """BBMD without multicast callback should still forward to FDs."""
        col = SentCollector()
        bbmd = BBMD6Manager(
            local_address=LOCAL_ADDR,
            local_vmac=LOCAL_VMAC,
            send_callback=col.send,
            local_broadcast_callback=col.local_deliver,
            multicast_send_callback=None,  # No multicast
        )
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        orig = BIP6Address(host="fd00::20", port=47808)
        bbmd.handle_bvlc(
            Bvlc6Function.FORWARDED_NPDU, b"\x01\x00", orig, source_vmac=b"\x44\x55\x66"
        )
        assert len(col.sent) == 1
        assert len(col.multicast_sent) == 0


# ---------- Distribute-Broadcast ----------


class TestDistributeBroadcast:
    def test_distribute_from_registered_fd(self):
        bdt = [BDT6Entry(address=LOCAL_ADDR), BDT6Entry(address=PEER_ADDR)]
        bbmd, col = _make_bbmd(bdt=bdt)
        # Register FD
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()
        col.multicast_sent.clear()
        col.local_delivered.clear()

        result = bbmd.handle_bvlc(
            Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU,
            b"\x01\x00\x10",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        assert result is True

        # Should forward to BDT peer and multicast + local deliver
        peer_sends = [d for d, dest in col.sent if dest == PEER_ADDR]
        assert len(peer_sends) == 1
        assert len(col.multicast_sent) == 1
        assert len(col.local_delivered) == 1

    def test_distribute_from_unregistered_fd_nak(self):
        bbmd, col = _make_bbmd()
        result = bbmd.handle_bvlc(
            Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU,
            b"\x01\x00",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        assert result is True

        decoded = decode_bvll6(col.sent[0][0])
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK

    def test_distribute_excludes_sending_fd(self):
        """Distribute-Broadcast should not forward back to the sending FD."""
        bbmd, col = _make_bbmd()
        # Register two FDs
        fd2 = BIP6Address(host="fd00::11", port=47808)
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            fd2,
            source_vmac=b"\xdd\xee\xff",
        )
        col.sent.clear()

        bbmd.handle_bvlc(
            Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU,
            b"\x01\x00",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )

        # Should NOT have forwarded back to FD_ADDR
        destinations = {dest for _, dest in col.sent}
        assert FD_ADDR not in destinations
        assert fd2 in destinations


# ---------- Address resolution forwarding ----------


class TestAddressResolutionForwarding:
    def test_address_resolution_forwarded(self):
        bdt = [BDT6Entry(address=LOCAL_ADDR), BDT6Entry(address=PEER_ADDR)]
        bbmd, col = _make_bbmd(bdt=bdt)
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()

        src = BIP6Address(host="fd00::5", port=47808)
        result = bbmd.handle_bvlc(
            Bvlc6Function.ADDRESS_RESOLUTION,
            b"\xdd\xee\xff",
            src,
            source_vmac=b"\x55\x66\x77",
        )
        assert result is True

        # Should forward to PEER_ADDR and FD_ADDR
        assert len(col.sent) == 2
        destinations = {dest for _, dest in col.sent}
        assert PEER_ADDR in destinations
        assert FD_ADDR in destinations

        # Verify Forwarded-Address-Resolution format
        for data, _ in col.sent:
            decoded = decode_bvll6(data)
            assert decoded.function == Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION


# ---------- BDT/FDT read ----------


class TestReadBDTFDT:
    def test_read_bdt(self):
        bdt = [BDT6Entry(address=LOCAL_ADDR), BDT6Entry(address=PEER_ADDR)]
        bbmd, _ = _make_bbmd(bdt=bdt)
        result = bbmd.read_bdt()
        assert len(result) == 2
        assert result[0].address == LOCAL_ADDR

    def test_read_fdt(self):
        bbmd, _ = _make_bbmd()
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        result = bbmd.read_fdt()
        assert FD_ADDR in result
        assert result[FD_ADDR].ttl == 60


# ---------- Start / Stop ----------


class TestStartStop:
    async def test_start_and_stop(self):
        bbmd, _ = _make_bbmd()
        await bbmd.start()
        assert bbmd._cleanup_task is not None
        await bbmd.stop()
        assert bbmd._cleanup_task is None

    async def test_stop_when_not_started(self):
        bbmd, _ = _make_bbmd()
        await bbmd.stop()  # Should not raise


# ---------- FDT cleanup ----------


class TestFDTCleanup:
    def test_purge_expired(self):
        bbmd, _ = _make_bbmd()
        # Manually add an expired entry
        bbmd._fdt[FD_ADDR] = FDT6Entry(
            address=FD_ADDR, vmac=FD_VMAC, ttl=1, expiry=time.monotonic() - 1
        )
        assert FD_ADDR in bbmd._fdt
        bbmd._purge_expired_fdt_entries()
        assert FD_ADDR not in bbmd._fdt

    def test_purge_keeps_fresh(self):
        bbmd, _ = _make_bbmd()
        bbmd._fdt[FD_ADDR] = FDT6Entry(
            address=FD_ADDR, vmac=FD_VMAC, ttl=60, expiry=time.monotonic() + 60
        )
        bbmd._purge_expired_fdt_entries()
        assert FD_ADDR in bbmd._fdt

    async def test_cleanup_loop_runs(self):
        bbmd, _ = _make_bbmd()
        bbmd._fdt_cleanup_interval = 0.05  # Very fast for testing
        bbmd._fdt[FD_ADDR] = FDT6Entry(
            address=FD_ADDR, vmac=FD_VMAC, ttl=1, expiry=time.monotonic() - 1
        )
        await bbmd.start()
        await asyncio.sleep(0.15)  # Let cleanup run
        await bbmd.stop()
        assert FD_ADDR not in bbmd._fdt


# ---------- Properties ----------


class TestProperties:
    def test_bdt_property(self):
        bdt = [BDT6Entry(address=LOCAL_ADDR)]
        bbmd, _ = _make_bbmd(bdt=bdt)
        assert len(bbmd.bdt) == 1

    def test_fdt_property(self):
        bbmd, _ = _make_bbmd()
        assert len(bbmd.fdt) == 0

    def test_accept_fd_setter(self):
        bbmd, _ = _make_bbmd(accept_fd=True)
        assert bbmd.accept_fd_registrations is True
        bbmd.accept_fd_registrations = False
        assert bbmd.accept_fd_registrations is False


# ---------- Unknown function passthrough ----------


class TestUnknownFunction:
    def test_unknown_function_returns_false(self):
        bbmd, _ = _make_bbmd()
        result = bbmd.handle_bvlc(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION,
            b"",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        assert result is False


# ---------- No local_broadcast callback ----------


class TestNoLocalBroadcastCallback:
    def test_forwarded_npdu_without_callback(self):
        col = SentCollector()
        bbmd = BBMD6Manager(
            local_address=LOCAL_ADDR,
            local_vmac=LOCAL_VMAC,
            send_callback=col.send,
            local_broadcast_callback=None,
            multicast_send_callback=col.multicast_send,
        )
        orig = BIP6Address(host="fd00::20", port=47808)
        bbmd.handle_bvlc(
            Bvlc6Function.FORWARDED_NPDU, b"\x01\x00", orig, source_vmac=b"\x44\x55\x66"
        )
        # Should not crash; multicast still sent
        assert len(col.multicast_sent) == 1

    def test_distribute_broadcast_without_callback(self):
        col = SentCollector()
        bbmd = BBMD6Manager(
            local_address=LOCAL_ADDR,
            local_vmac=LOCAL_VMAC,
            send_callback=col.send,
            local_broadcast_callback=None,
            multicast_send_callback=col.multicast_send,
        )
        bbmd.handle_bvlc(
            Bvlc6Function.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        col.sent.clear()
        bbmd.handle_bvlc(
            Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU,
            b"\x01\x00",
            FD_ADDR,
            source_vmac=FD_VMAC,
        )
        # Should not crash
        assert len(col.multicast_sent) == 1
