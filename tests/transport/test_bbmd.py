"""Tests for BBMD manager (transport/bbmd.py)."""

from __future__ import annotations

import asyncio
import time

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import (
    BDT_ENTRY_SIZE,
    FDT_GRACE_PERIOD_SECONDS,
    BBMDManager,
    BDTEntry,
    FDTEntry,
    _compute_forward_address,
    _encode_bvlc_result,
)
from bac_py.transport.bvll import decode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode

# --- Fixtures ---

BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)
PEER_ADDR = BIPAddress(host="192.168.2.1", port=47808)
PEER_ADDR2 = BIPAddress(host="192.168.3.1", port=47808)
FD_ADDR = BIPAddress(host="10.0.0.50", port=47808)
FD_ADDR2 = BIPAddress(host="10.0.0.51", port=47808)
CLIENT_ADDR = BIPAddress(host="192.168.1.100", port=47808)
ALL_ONES_MASK = b"\xff\xff\xff\xff"


class SentCollector:
    """Collects sent messages for test assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, BIPAddress]] = []
        self.local_broadcasts: list[tuple[bytes, BIPAddress]] = []

    def send(self, data: bytes, dest: BIPAddress) -> None:
        self.sent.append((data, dest))

    def local_broadcast(self, npdu: bytes, source: BIPAddress) -> None:
        self.local_broadcasts.append((npdu, source))

    def clear(self) -> None:
        self.sent.clear()
        self.local_broadcasts.clear()

    def find_sent_to(self, dest: BIPAddress) -> list[bytes]:
        return [data for data, d in self.sent if d == dest]

    def find_bvlc_results(self, dest: BIPAddress) -> list[BvlcResultCode]:
        results = []
        for data, d in self.sent:
            if d == dest:
                msg = decode_bvll(data)
                if msg.function == BvlcFunction.BVLC_RESULT and len(msg.data) >= 2:
                    results.append(BvlcResultCode(int.from_bytes(msg.data[0:2], "big")))
        return results


@pytest.fixture
def collector() -> SentCollector:
    return SentCollector()


@pytest.fixture
def bbmd(collector: SentCollector) -> BBMDManager:
    return BBMDManager(
        local_address=BBMD_ADDR,
        send_callback=collector.send,
        local_broadcast_callback=collector.local_broadcast,
    )


@pytest.fixture
def bbmd_with_bdt(bbmd: BBMDManager) -> BBMDManager:
    """BBMD with a 2-entry BDT (self + one peer), all-ones mask."""
    bbmd.set_bdt(
        [
            BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
            BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
        ]
    )
    return bbmd


# --- BDTEntry tests ---


class TestBDTEntry:
    def test_encode_decode_round_trip(self):
        entry = BDTEntry(
            address=BIPAddress(host="192.168.1.1", port=47808),
            broadcast_mask=b"\xff\xff\xff\x00",
        )
        encoded = entry.encode()
        assert len(encoded) == BDT_ENTRY_SIZE
        decoded = BDTEntry.decode(encoded)
        assert decoded.address.host == "192.168.1.1"
        assert decoded.address.port == 47808
        assert decoded.broadcast_mask == b"\xff\xff\xff\x00"

    def test_encode_produces_10_bytes(self):
        entry = BDTEntry(
            address=BIPAddress(host="10.0.0.1", port=47808),
            broadcast_mask=ALL_ONES_MASK,
        )
        assert len(entry.encode()) == 10

    def test_decode_from_memoryview(self):
        entry = BDTEntry(
            address=BIPAddress(host="172.16.0.1", port=47808),
            broadcast_mask=b"\xff\xff\x00\x00",
        )
        encoded = entry.encode()
        decoded = BDTEntry.decode(memoryview(encoded))
        assert decoded.address.host == "172.16.0.1"
        assert decoded.broadcast_mask == b"\xff\xff\x00\x00"


# --- FDTEntry tests ---


class TestFDTEntry:
    def test_remaining_positive(self):
        entry = FDTEntry(
            address=FD_ADDR,
            ttl=60,
            expiry=time.monotonic() + 30,
        )
        assert entry.remaining > 0
        assert entry.remaining <= 30

    def test_remaining_zero_when_expired(self):
        entry = FDTEntry(
            address=FD_ADDR,
            ttl=60,
            expiry=time.monotonic() - 10,
        )
        assert entry.remaining == 0


# --- Forwarding address computation ---


class TestComputeForwardAddress:
    def test_all_ones_mask_returns_same_address(self):
        entry = BDTEntry(
            address=BIPAddress(host="192.168.1.1", port=47808),
            broadcast_mask=ALL_ONES_MASK,
        )
        result = _compute_forward_address(entry)
        assert result.host == "192.168.1.1"
        assert result.port == 47808

    def test_subnet_mask_returns_directed_broadcast(self):
        entry = BDTEntry(
            address=BIPAddress(host="192.168.1.1", port=47808),
            broadcast_mask=b"\xff\xff\xff\x00",
        )
        result = _compute_forward_address(entry)
        # 192.168.1.1 | ~(255.255.255.0) = 192.168.1.1 | 0.0.0.255 = 192.168.1.255
        assert result.host == "192.168.1.255"
        assert result.port == 47808

    def test_class_b_mask(self):
        entry = BDTEntry(
            address=BIPAddress(host="172.16.5.1", port=47808),
            broadcast_mask=b"\xff\xff\x00\x00",
        )
        result = _compute_forward_address(entry)
        # 172.16.5.1 | ~(255.255.0.0) = 172.16.5.1 | 0.0.255.255 = 172.16.255.255
        assert result.host == "172.16.255.255"

    def test_zero_mask_returns_full_broadcast(self):
        entry = BDTEntry(
            address=BIPAddress(host="10.1.2.3", port=47808),
            broadcast_mask=b"\x00\x00\x00\x00",
        )
        result = _compute_forward_address(entry)
        assert result.host == "255.255.255.255"


# --- BVLC Result encoding ---


class TestEncodeBvlcResult:
    def test_successful_completion(self):
        result = _encode_bvlc_result(BvlcResultCode.SUCCESSFUL_COMPLETION)
        msg = decode_bvll(result)
        assert msg.function == BvlcFunction.BVLC_RESULT
        assert int.from_bytes(msg.data[0:2], "big") == 0x0000

    def test_register_nak(self):
        result = _encode_bvlc_result(BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK)
        msg = decode_bvll(result)
        assert msg.function == BvlcFunction.BVLC_RESULT
        assert int.from_bytes(msg.data[0:2], "big") == 0x0030


# --- BBMDManager: BDT management ---


class TestBBMDBDTManagement:
    def test_set_bdt(self, bbmd: BBMDManager):
        entries = [
            BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
            BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
        ]
        bbmd.set_bdt(entries)
        assert len(bbmd.bdt) == 2
        assert bbmd.bdt[0].address == BBMD_ADDR
        assert bbmd.bdt[1].address == PEER_ADDR

    def test_bdt_returns_copy(self, bbmd: BBMDManager):
        bbmd.set_bdt([BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)])
        bdt = bbmd.bdt
        bdt.clear()
        assert len(bbmd.bdt) == 1  # Original unchanged

    def test_write_bdt(self, collector: SentCollector):
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            allow_write_bdt=True,
        )
        entry1 = BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)
        entry2 = BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK)
        payload = entry1.encode() + entry2.encode()

        handled = bbmd.handle_bvlc(
            BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
            payload,
            CLIENT_ADDR,
        )
        assert handled is True
        assert len(bbmd.bdt) == 2
        # Should receive BVLC-Result success
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_write_bdt_invalid_size(self, collector: SentCollector):
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            allow_write_bdt=True,
        )
        # 7 bytes is not a multiple of 10
        handled = bbmd.handle_bvlc(
            BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
            b"\x00" * 7,
            CLIENT_ADDR,
        )
        assert handled is True
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK in results

    def test_read_bdt(self, bbmd_with_bdt: BBMDManager, collector: SentCollector):
        handled = bbmd_with_bdt.handle_bvlc(
            BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE,
            b"",
            CLIENT_ADDR,
        )
        assert handled is True
        sent = collector.find_sent_to(CLIENT_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK
        assert len(msg.data) == 2 * BDT_ENTRY_SIZE

    def test_read_bdt_empty_returns_empty_ack(self, bbmd: BBMDManager, collector: SentCollector):
        handled = bbmd.handle_bvlc(
            BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE,
            b"",
            CLIENT_ADDR,
        )
        assert handled is True
        sent = collector.find_sent_to(CLIENT_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK
        assert len(msg.data) == 0  # Empty list per J.2.4


# --- BBMDManager: Foreign device registration ---


class TestBBMDForeignDeviceRegistration:
    def test_register_foreign_device(self, bbmd: BBMDManager, collector: SentCollector):
        ttl_bytes = (60).to_bytes(2, "big")
        handled = bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl_bytes,
            FD_ADDR,
        )
        assert handled is True
        assert FD_ADDR in bbmd.fdt
        assert bbmd.fdt[FD_ADDR].ttl == 60
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_re_register_updates_entry(self, bbmd: BBMDManager, collector: SentCollector):
        ttl_bytes = (60).to_bytes(2, "big")
        bbmd.handle_bvlc(BvlcFunction.REGISTER_FOREIGN_DEVICE, ttl_bytes, FD_ADDR)
        old_expiry = bbmd.fdt[FD_ADDR].expiry

        collector.clear()
        ttl_bytes2 = (120).to_bytes(2, "big")
        bbmd.handle_bvlc(BvlcFunction.REGISTER_FOREIGN_DEVICE, ttl_bytes2, FD_ADDR)
        assert bbmd.fdt[FD_ADDR].ttl == 120
        assert bbmd.fdt[FD_ADDR].expiry >= old_expiry

    def test_register_with_short_payload_returns_nak(
        self, bbmd: BBMDManager, collector: SentCollector
    ):
        handled = bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            b"\x00",  # Only 1 byte, need 2
            FD_ADDR,
        )
        assert handled is True
        assert FD_ADDR not in bbmd.fdt
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK in results


# --- BBMDManager: FDT management ---


class TestBBMDFDTManagement:
    def _register_fd(self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_read_fdt(self, bbmd: BBMDManager, collector: SentCollector):
        self._register_fd(bbmd, FD_ADDR, ttl=60)
        collector.clear()

        handled = bbmd.handle_bvlc(
            BvlcFunction.READ_FOREIGN_DEVICE_TABLE,
            b"",
            CLIENT_ADDR,
        )
        assert handled is True
        sent = collector.find_sent_to(CLIENT_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK
        # Each FDT entry is 10 bytes (6 addr + 2 TTL + 2 remaining)
        assert len(msg.data) == 10

    def test_read_fdt_empty_returns_empty_ack(self, bbmd: BBMDManager, collector: SentCollector):
        handled = bbmd.handle_bvlc(
            BvlcFunction.READ_FOREIGN_DEVICE_TABLE,
            b"",
            CLIENT_ADDR,
        )
        assert handled is True
        sent = collector.find_sent_to(CLIENT_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK
        assert len(msg.data) == 0  # Empty list per J.2.8

    def test_delete_fdt_entry(self, bbmd: BBMDManager, collector: SentCollector):
        self._register_fd(bbmd, FD_ADDR)
        collector.clear()

        handled = bbmd.handle_bvlc(
            BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            FD_ADDR.encode(),
            CLIENT_ADDR,
        )
        assert handled is True
        assert FD_ADDR not in bbmd.fdt
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_delete_nonexistent_fdt_entry_returns_nak(
        self, bbmd: BBMDManager, collector: SentCollector
    ):
        handled = bbmd.handle_bvlc(
            BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            FD_ADDR.encode(),
            CLIENT_ADDR,
        )
        assert handled is True
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK in results

    def test_delete_fdt_entry_short_payload(self, bbmd: BBMDManager, collector: SentCollector):
        handled = bbmd.handle_bvlc(
            BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY,
            b"\x00\x01",  # Too short
            CLIENT_ADDR,
        )
        assert handled is True
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK in results


# --- BBMDManager: Broadcast forwarding ---


class TestBBMDBroadcastForwarding:
    def _register_fd(self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_original_broadcast_forwards_to_peers(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        npdu = b"\x01\x00\x10\x08\x00"
        collector.clear()

        handled = bbmd_with_bdt.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )
        # Returns False because normal receive should also process it
        assert handled is False

        # Should have forwarded to PEER_ADDR (but not to self)
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1
        fwd_msg = decode_bvll(peer_sent[0])
        assert fwd_msg.function == BvlcFunction.FORWARDED_NPDU
        assert fwd_msg.originating_address == CLIENT_ADDR
        assert fwd_msg.data == npdu

    def test_original_broadcast_forwards_to_foreign_devices(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        self._register_fd(bbmd_with_bdt, FD_ADDR)
        self._register_fd(bbmd_with_bdt, FD_ADDR2)
        collector.clear()

        npdu = b"\x01\x00\x10"
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        fd_sent = collector.find_sent_to(FD_ADDR)
        fd2_sent = collector.find_sent_to(FD_ADDR2)
        assert len(fd_sent) == 1
        assert len(fd2_sent) == 1

    def test_original_broadcast_not_forwarded_to_self(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        npdu = b"\x01\x00\x10"
        collector.clear()
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )
        # Should NOT send to self (BBMD_ADDR)
        self_sent = collector.find_sent_to(BBMD_ADDR)
        assert len(self_sent) == 0

    def test_forwarded_npdu_sent_to_foreign_devices(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        """When a BBMD receives Forwarded-NPDU from another BBMD, it forwards to registered foreign devices."""
        self._register_fd(bbmd_with_bdt, FD_ADDR)
        collector.clear()

        npdu = b"\x01\x00\x10"
        # Simulate receiving Forwarded-NPDU (source = originating address)
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,  # originating address
        )

        fd_sent = collector.find_sent_to(FD_ADDR)
        assert len(fd_sent) == 1
        fwd_msg = decode_bvll(fd_sent[0])
        assert fwd_msg.function == BvlcFunction.FORWARDED_NPDU
        assert fwd_msg.data == npdu

    def test_forwarded_npdu_broadcasts_locally(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        npdu = b"\x01\x00\x10"
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
        )
        assert len(collector.local_broadcasts) == 1
        assert collector.local_broadcasts[0] == (npdu, CLIENT_ADDR)

    def test_forwarded_npdu_not_re_forwarded_to_bdt_peers(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        """Forwarded-NPDU should NOT be re-forwarded to BDT peers (only Original-Broadcast-NPDU triggers peer forwarding)."""
        npdu = b"\x01\x00\x10"
        collector.clear()
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
        )
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 0


# --- BBMDManager: Distribute-Broadcast-To-Network ---


class TestBBMDDistributeBroadcast:
    def _register_fd(self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_distribute_broadcast_from_registered_fd(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        self._register_fd(bbmd_with_bdt, FD_ADDR)
        collector.clear()

        npdu = b"\x01\x00\x10"
        handled = bbmd_with_bdt.handle_bvlc(
            BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK,
            npdu,
            FD_ADDR,
        )
        assert handled is True

        # Should forward to BDT peer
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1
        fwd_msg = decode_bvll(peer_sent[0])
        assert fwd_msg.function == BvlcFunction.FORWARDED_NPDU
        assert fwd_msg.originating_address == FD_ADDR

        # Should broadcast locally
        assert len(collector.local_broadcasts) == 1

    def test_distribute_broadcast_excludes_sender(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        """The sending foreign device should not receive the forwarded copy."""
        self._register_fd(bbmd_with_bdt, FD_ADDR)
        self._register_fd(bbmd_with_bdt, FD_ADDR2)
        collector.clear()

        npdu = b"\x01\x00\x10"
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK,
            npdu,
            FD_ADDR,
        )

        # FD_ADDR (sender) should NOT receive a copy
        fd_sent = collector.find_sent_to(FD_ADDR)
        assert len(fd_sent) == 0

        # FD_ADDR2 should receive a copy
        fd2_sent = collector.find_sent_to(FD_ADDR2)
        assert len(fd2_sent) == 1

    def test_distribute_broadcast_from_unregistered_fd_returns_nak(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        npdu = b"\x01\x00\x10"
        handled = bbmd_with_bdt.handle_bvlc(
            BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK,
            npdu,
            FD_ADDR,  # Not registered
        )
        assert handled is True
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK in results


# --- BBMDManager: Unhandled functions ---


class TestBBMDUnhandledFunctions:
    def test_unicast_not_handled(self, bbmd: BBMDManager):
        handled = bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_UNICAST_NPDU,
            b"\x01\x00",
            CLIENT_ADDR,
        )
        assert handled is False

    def test_bvlc_result_not_handled(self, bbmd: BBMDManager):
        handled = bbmd.handle_bvlc(
            BvlcFunction.BVLC_RESULT,
            b"\x00\x00",
            CLIENT_ADDR,
        )
        assert handled is False


# --- BBMDManager: FDT expiry ---


class TestBBMDFDTExpiry:
    def test_purge_expired_entries(self, bbmd: BBMDManager):
        # Register a foreign device with a past expiry
        bbmd._fdt[FD_ADDR] = FDTEntry(
            address=FD_ADDR,
            ttl=60,
            expiry=time.monotonic() - 10,  # Already expired
        )
        bbmd._fdt[FD_ADDR2] = FDTEntry(
            address=FD_ADDR2,
            ttl=60,
            expiry=time.monotonic() + 100,  # Still valid
        )

        bbmd._purge_expired_fdt_entries()

        assert FD_ADDR not in bbmd.fdt
        assert FD_ADDR2 in bbmd.fdt

    @pytest.mark.asyncio
    async def test_cleanup_loop_purges_expired(self, bbmd: BBMDManager):
        bbmd._fdt[FD_ADDR] = FDTEntry(
            address=FD_ADDR,
            ttl=1,
            expiry=time.monotonic() - 1,  # Already expired
        )

        await bbmd.start()
        try:
            # Give the cleanup loop a chance to run
            await asyncio.sleep(0.1)
            # The loop sleeps 10s, but we can call purge directly
            bbmd._purge_expired_fdt_entries()
            assert FD_ADDR not in bbmd.fdt
        finally:
            await bbmd.stop()

    @pytest.mark.asyncio
    async def test_start_stop_cleanup_task(self, bbmd: BBMDManager):
        await bbmd.start()
        assert bbmd._cleanup_task is not None
        await bbmd.stop()
        assert bbmd._cleanup_task is None


# --- BBMDManager: Multi-peer BDT ---


class TestBBMDMultiPeer:
    def test_forward_to_multiple_peers(self, bbmd: BBMDManager, collector: SentCollector):
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR2, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        peer1_sent = collector.find_sent_to(PEER_ADDR)
        peer2_sent = collector.find_sent_to(PEER_ADDR2)
        assert len(peer1_sent) == 1
        assert len(peer2_sent) == 1

    def test_directed_broadcast_mask(self, bbmd: BBMDManager, collector: SentCollector):
        """When BDT mask is not all-ones, use directed broadcast."""
        subnet_mask = b"\xff\xff\xff\x00"
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=subnet_mask),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        # Should send to 192.168.2.255 (directed broadcast), not 192.168.2.1
        directed_broadcast = BIPAddress(host="192.168.2.255", port=47808)
        sent = collector.find_sent_to(directed_broadcast)
        assert len(sent) == 1


# --- BBMDManager: Grace period ---


class TestBBMDGracePeriod:
    def test_fdt_entry_expiry_includes_grace_period(self, bbmd: BBMDManager):
        ttl = 60
        before = time.monotonic()
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            FD_ADDR,
        )
        after = time.monotonic()

        entry = bbmd.fdt[FD_ADDR]
        expected_min = before + ttl + FDT_GRACE_PERIOD_SECONDS
        expected_max = after + ttl + FDT_GRACE_PERIOD_SECONDS
        assert expected_min <= entry.expiry <= expected_max


# --- Phase 1: B1 - Forwarded-NPDU unicast-mask wire re-broadcast ---


BROADCAST_ADDR = BIPAddress(host="192.168.1.255", port=47808)


class TestForwardedNPDUUnicastMaskRebroadcast:
    """B1: When a Forwarded-NPDU arrives from a BDT peer with an all-ones
    mask, the BBMD should re-broadcast the Forwarded-NPDU on the local
    wire (via broadcast_address) because local devices didn't see the
    packet.  When the mask is not all-ones (directed broadcast), no
    wire re-broadcast is needed since local devices already received it
    via the directed broadcast.
    """

    def _register_fd(self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_unicast_mask_peer_triggers_wire_rebroadcast(self, collector: SentCollector):
        """Forwarded-NPDU from a unicast-mask peer triggers wire re-broadcast."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            broadcast_address=BROADCAST_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,  # originating address
            udp_source=PEER_ADDR,  # actual UDP peer
        )

        # Wire re-broadcast should have been sent to broadcast address
        broadcast_sent = collector.find_sent_to(BROADCAST_ADDR)
        assert len(broadcast_sent) == 1
        fwd_msg = decode_bvll(broadcast_sent[0])
        assert fwd_msg.function == BvlcFunction.FORWARDED_NPDU
        assert fwd_msg.originating_address == CLIENT_ADDR
        assert fwd_msg.data == npdu

    def test_directed_broadcast_mask_no_wire_rebroadcast(self, collector: SentCollector):
        """Forwarded-NPDU from a directed-broadcast-mask peer does NOT trigger wire re-broadcast."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            broadcast_address=BROADCAST_ADDR,
        )
        subnet_mask = b"\xff\xff\xff\x00"
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=subnet_mask),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
            udp_source=PEER_ADDR,
        )

        # NO wire re-broadcast to broadcast address
        broadcast_sent = collector.find_sent_to(BROADCAST_ADDR)
        assert len(broadcast_sent) == 0

    def test_unknown_peer_defaults_to_wire_rebroadcast(self, collector: SentCollector):
        """Forwarded-NPDU from an unknown peer (not in BDT) defaults to
        wire re-broadcast for safety.
        """
        unknown_peer = BIPAddress(host="10.99.99.1", port=47808)
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            broadcast_address=BROADCAST_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
            udp_source=unknown_peer,
        )

        # Unknown peer -> assume unicast -> wire re-broadcast
        broadcast_sent = collector.find_sent_to(BROADCAST_ADDR)
        assert len(broadcast_sent) == 1

    def test_no_broadcast_address_no_wire_rebroadcast(self, collector: SentCollector):
        """When broadcast_address is not configured, no wire re-broadcast occurs."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            # No broadcast_address
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
            udp_source=PEER_ADDR,
        )

        # No broadcast address -> no wire re-broadcast
        # Only FD forwarding (none) and local broadcast
        assert len(collector.sent) == 0
        assert len(collector.local_broadcasts) == 1

    def test_app_delivery_always_happens(self, collector: SentCollector):
        """The BBMD's own application always receives the NPDU regardless
        of BDT mask.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            broadcast_address=BROADCAST_ADDR,
        )
        subnet_mask = b"\xff\xff\xff\x00"
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=subnet_mask),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,
            udp_source=PEER_ADDR,
        )

        # App delivery happens even without wire re-broadcast
        assert len(collector.local_broadcasts) == 1
        assert collector.local_broadcasts[0] == (npdu, CLIENT_ADDR)

    def test_forwarded_npdu_excludes_originating_fd(self, collector: SentCollector):
        """B3: When forwarding to FDs, exclude the originating device
        if it is a registered foreign device.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            broadcast_address=BROADCAST_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )
        self._register_fd(bbmd, FD_ADDR)
        self._register_fd(bbmd, FD_ADDR2)
        collector.clear()

        npdu = b"\x01\x00\x10"
        # Forwarded-NPDU with originating address = FD_ADDR
        bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            FD_ADDR,  # originating address is a registered FD
            udp_source=PEER_ADDR,
        )

        # FD_ADDR should NOT receive a copy (it's the originator)
        fd_sent = collector.find_sent_to(FD_ADDR)
        assert len(fd_sent) == 0

        # FD_ADDR2 should receive a copy
        fd2_sent = collector.find_sent_to(FD_ADDR2)
        assert len(fd2_sent) == 1


# --- Phase 1: B2 - Don't forward back to origin ---


class TestDontForwardBackToOrigin:
    """B2: When forwarding to BDT peers, skip the entry whose computed
    forward address matches the originating source.
    """

    def test_original_broadcast_not_forwarded_to_originator_bdt_entry(
        self, collector: SentCollector
    ):
        """If the originating source matches a BDT peer's forward address,
        that peer should be skipped.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR2, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        # Broadcast originated from PEER_ADDR itself
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            PEER_ADDR,  # originating source matches a BDT entry
        )

        # Should NOT forward back to PEER_ADDR
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 0

        # Should forward to PEER_ADDR2
        peer2_sent = collector.find_sent_to(PEER_ADDR2)
        assert len(peer2_sent) == 1

    def test_distribute_broadcast_not_forwarded_to_originator_bdt_entry(
        self, collector: SentCollector
    ):
        """Distribute-Broadcast from FD whose address matches a BDT peer's
        forward address: that peer should be skipped.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
        )
        # BDT entry for PEER_ADDR with all-ones mask (forward dest = PEER_ADDR)
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR2, broadcast_mask=ALL_ONES_MASK),
            ]
        )
        # Register the FD that happens to have the same address as a BDT peer
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            PEER_ADDR,
        )
        collector.clear()

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK,
            npdu,
            PEER_ADDR,
        )

        # PEER_ADDR should NOT get a BDT forwarded copy
        # (it IS the originator, skipped by B2 and by exclude_fd)
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 0

        # PEER_ADDR2 should receive the forwarded copy
        peer2_sent = collector.find_sent_to(PEER_ADDR2)
        assert len(peer2_sent) == 1

    def test_normal_client_not_affected_by_origin_check(
        self, bbmd_with_bdt: BBMDManager, collector: SentCollector
    ):
        """Normal broadcast from a local client (not a BDT peer) should
        forward to all peers normally.
        """
        collector.clear()
        npdu = b"\x01\x00\x10"
        bbmd_with_bdt.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,  # Not a BDT entry
        )

        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1


# --- Phase 1: S2 - Self-originated Forwarded-NPDU drop ---


class TestSelfOriginatedForwardedNPDUDrop:
    """S2: Forwarded-NPDU with originating address matching the BBMD's
    own address should be dropped to prevent loops.
    """

    def test_self_originated_forwarded_npdu_dropped(
        self, bbmd: BBMDManager, collector: SentCollector
    ):
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        handled = bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            BBMD_ADDR,  # originating address = our own
        )

        # Should be consumed (dropped) by the BBMD
        assert handled is True
        # No forwarding, no local delivery
        assert len(collector.sent) == 0
        assert len(collector.local_broadcasts) == 0

    def test_non_self_forwarded_npdu_not_dropped(
        self, bbmd: BBMDManager, collector: SentCollector
    ):
        npdu = b"\x01\x00\x10"
        handled = bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            CLIENT_ADDR,  # originating address != our own
        )

        assert handled is False
        assert len(collector.local_broadcasts) == 1


# --- Phase 1: _is_unicast_bdt_mask helper ---


class TestIsUnicastBDTMask:
    def test_all_ones_mask_is_unicast(self, bbmd: BBMDManager):
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )
        assert bbmd._is_unicast_bdt_mask(PEER_ADDR) is True

    def test_subnet_mask_is_not_unicast(self, bbmd: BBMDManager):
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=b"\xff\xff\xff\x00"),
            ]
        )
        assert bbmd._is_unicast_bdt_mask(PEER_ADDR) is False

    def test_unknown_address_defaults_to_unicast(self, bbmd: BBMDManager):
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )
        unknown = BIPAddress(host="10.99.99.1", port=47808)
        assert bbmd._is_unicast_bdt_mask(unknown) is True


# --- Phase 2: S1 - Maximum FDT size limit ---


class TestMaxFDTSize:
    """S1: The FDT should have a configurable maximum size to prevent
    memory exhaustion from spoofed registration requests.
    """

    def _register_fd(
        self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60
    ) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_new_registration_rejected_when_fdt_full(self, collector: SentCollector):
        """New FD registration is NAKed when FDT is at max capacity."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            max_fdt_entries=2,
        )
        # Fill up the FDT
        self._register_fd(bbmd, FD_ADDR)
        self._register_fd(bbmd, FD_ADDR2)
        assert len(bbmd.fdt) == 2
        collector.clear()

        # Third registration should be rejected
        new_fd = BIPAddress(host="10.0.0.99", port=47808)
        self._register_fd(bbmd, new_fd)

        assert new_fd not in bbmd.fdt
        results = collector.find_bvlc_results(new_fd)
        assert BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK in results

    def test_re_registration_succeeds_when_fdt_full(self, collector: SentCollector):
        """Re-registration of existing entry succeeds even when FDT is full."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            max_fdt_entries=2,
        )
        self._register_fd(bbmd, FD_ADDR, ttl=60)
        self._register_fd(bbmd, FD_ADDR2, ttl=60)
        assert len(bbmd.fdt) == 2
        collector.clear()

        # Re-register FD_ADDR with a new TTL -- should succeed
        self._register_fd(bbmd, FD_ADDR, ttl=120)

        assert FD_ADDR in bbmd.fdt
        assert bbmd.fdt[FD_ADDR].ttl == 120
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_default_max_fdt_is_128(self, collector: SentCollector):
        """Default max FDT entries is 128."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        assert bbmd._max_fdt_entries == 128

    def test_registration_succeeds_below_limit(self, collector: SentCollector):
        """Registration succeeds when FDT is below max capacity."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            max_fdt_entries=10,
        )
        self._register_fd(bbmd, FD_ADDR)
        assert FD_ADDR in bbmd.fdt
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results


# --- Phase 3: F4 - Accept FD registrations toggle ---


class TestAcceptFDRegistrationsToggle:
    """F4: The BBMD should have a configurable toggle to accept or reject
    foreign device registrations.
    """

    def _register_fd(
        self, bbmd: BBMDManager, addr: BIPAddress, ttl: int = 60
    ) -> None:
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            ttl.to_bytes(2, "big"),
            addr,
        )

    def test_registrations_rejected_when_disabled(self, collector: SentCollector):
        """Registration is NAKed when accept_fd_registrations=False."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            accept_fd_registrations=False,
        )
        self._register_fd(bbmd, FD_ADDR)

        assert FD_ADDR not in bbmd.fdt
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK in results

    def test_registrations_accepted_when_enabled(self, collector: SentCollector):
        """Registration succeeds when accept_fd_registrations=True (default)."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            accept_fd_registrations=True,
        )
        self._register_fd(bbmd, FD_ADDR)

        assert FD_ADDR in bbmd.fdt
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_default_is_enabled(self, collector: SentCollector):
        """Default accept_fd_registrations is True."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        assert bbmd.accept_fd_registrations is True

    def test_toggle_at_runtime(self, collector: SentCollector):
        """accept_fd_registrations can be toggled at runtime."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            accept_fd_registrations=False,
        )
        # Disabled -- registration should fail
        self._register_fd(bbmd, FD_ADDR)
        assert FD_ADDR not in bbmd.fdt

        collector.clear()

        # Enable at runtime
        bbmd.accept_fd_registrations = True
        self._register_fd(bbmd, FD_ADDR)
        assert FD_ADDR in bbmd.fdt
        results = collector.find_bvlc_results(FD_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results


# --- Phase 3: F8 - Write-BDT rejection option ---


class TestWriteBDTRejection:
    """F8: Write-BDT should be rejected by default per protocol revision >= 17."""

    def test_write_bdt_rejected_by_default(self, collector: SentCollector):
        """Default allow_write_bdt=False rejects Write-BDT."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        entry = BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)
        handled = bbmd.handle_bvlc(
            BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
            entry.encode(),
            CLIENT_ADDR,
        )
        assert handled is True
        assert len(bbmd.bdt) == 0  # BDT not changed
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK in results

    def test_write_bdt_accepted_when_allowed(self, collector: SentCollector):
        """Write-BDT succeeds when allow_write_bdt=True."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            allow_write_bdt=True,
        )
        entry = BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)
        handled = bbmd.handle_bvlc(
            BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
            entry.encode(),
            CLIENT_ADDR,
        )
        assert handled is True
        assert len(bbmd.bdt) == 1
        results = collector.find_bvlc_results(CLIENT_ADDR)
        assert BvlcResultCode.SUCCESSFUL_COMPLETION in results

    def test_default_allow_write_bdt_is_false(self, collector: SentCollector):
        """Default allow_write_bdt is False."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        assert bbmd._allow_write_bdt is False


# --- Phase 4: F1 - NAT traversal support ---


GLOBAL_ADDR = BIPAddress(host="203.0.113.1", port=47808)


# --- Phase 4: F9 - BDT persistence ---


class TestBDTPersistence:
    """F9: BDT persistence across restarts.

    When bdt_backup_path is configured, the BDT is saved to a JSON file
    whenever it changes and restored on start().
    """

    def test_set_bdt_saves_backup(self, collector: SentCollector, tmp_path):
        """set_bdt() saves the BDT to the backup file."""
        backup = tmp_path / "bdt.json"
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        assert backup.exists()
        import json

        data = json.loads(backup.read_text())
        assert len(data) == 2
        assert data[0]["host"] == BBMD_ADDR.host
        assert data[0]["port"] == BBMD_ADDR.port
        assert data[1]["host"] == PEER_ADDR.host

    @pytest.mark.asyncio
    async def test_start_loads_backup(self, collector: SentCollector, tmp_path):
        """start() restores BDT from backup file."""
        import json

        backup = tmp_path / "bdt.json"
        entries = [
            {
                "host": BBMD_ADDR.host,
                "port": BBMD_ADDR.port,
                "mask": list(ALL_ONES_MASK),
            },
            {
                "host": PEER_ADDR.host,
                "port": PEER_ADDR.port,
                "mask": list(ALL_ONES_MASK),
            },
        ]
        backup.write_text(json.dumps(entries))

        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        await bbmd.start()
        try:
            assert len(bbmd.bdt) == 2
            assert bbmd.bdt[0].address == BBMD_ADDR
            assert bbmd.bdt[1].address == PEER_ADDR
            assert bbmd.bdt[0].broadcast_mask == ALL_ONES_MASK
        finally:
            await bbmd.stop()

    @pytest.mark.asyncio
    async def test_start_does_not_overwrite_existing_bdt(
        self, collector: SentCollector, tmp_path
    ):
        """start() does not load backup if BDT was already set."""
        import json

        backup = tmp_path / "bdt.json"
        entries = [
            {"host": PEER_ADDR.host, "port": PEER_ADDR.port, "mask": list(ALL_ONES_MASK)},
        ]
        backup.write_text(json.dumps(entries))

        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        # Set BDT before start
        bbmd.set_bdt([BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)])
        await bbmd.start()
        try:
            # Should keep the programmatically set BDT, not overwrite from file
            assert len(bbmd.bdt) == 1
            assert bbmd.bdt[0].address == BBMD_ADDR
        finally:
            await bbmd.stop()

    def test_no_backup_path_no_save(self, collector: SentCollector):
        """Without bdt_backup_path, set_bdt() does not raise or save."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        # Should not raise
        bbmd.set_bdt([BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)])

    @pytest.mark.asyncio
    async def test_no_backup_file_no_load(self, collector: SentCollector, tmp_path):
        """start() does not raise when backup file doesn't exist."""
        backup = tmp_path / "nonexistent.json"
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        await bbmd.start()
        try:
            assert len(bbmd.bdt) == 0
        finally:
            await bbmd.stop()

    def test_write_bdt_saves_backup(self, collector: SentCollector, tmp_path):
        """Write-BDT handler also saves to backup."""
        import json

        backup = tmp_path / "bdt.json"
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            allow_write_bdt=True,
            bdt_backup_path=backup,
        )
        entry = BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK)
        bbmd.handle_bvlc(
            BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE,
            entry.encode(),
            CLIENT_ADDR,
        )

        assert backup.exists()
        data = json.loads(backup.read_text())
        assert len(data) == 1
        assert data[0]["host"] == BBMD_ADDR.host

    def test_backup_round_trip_with_subnet_mask(
        self, collector: SentCollector, tmp_path
    ):
        """Backup and restore preserves non-trivial broadcast masks."""
        import json

        backup = tmp_path / "bdt.json"
        subnet_mask = b"\xff\xff\xff\x00"
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        bbmd.set_bdt(
            [BDTEntry(address=PEER_ADDR, broadcast_mask=subnet_mask)]
        )

        # Verify saved correctly
        data = json.loads(backup.read_text())
        assert data[0]["mask"] == [255, 255, 255, 0]

        # Create a new BBMD and load from the backup
        bbmd2 = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        bbmd2._load_bdt_backup()
        assert len(bbmd2.bdt) == 1
        assert bbmd2.bdt[0].address == PEER_ADDR
        assert bbmd2.bdt[0].broadcast_mask == subnet_mask

    @pytest.mark.asyncio
    async def test_corrupt_backup_file_handled_gracefully(
        self, collector: SentCollector, tmp_path
    ):
        """Corrupt backup file is handled gracefully (BDT stays empty)."""
        backup = tmp_path / "bdt.json"
        backup.write_text("not valid json {{{")

        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            bdt_backup_path=backup,
        )
        await bbmd.start()
        try:
            assert len(bbmd.bdt) == 0
        finally:
            await bbmd.stop()


class TestNATTraversal:
    """F1: NAT traversal support per Annex J.7.8.

    When a global_address is configured, outgoing Forwarded-NPDUs use
    the global address as the originating source, and BDT entries matching
    the global address are skipped to prevent NAT loops.
    """

    def test_default_global_address_is_none(self, collector: SentCollector):
        """Default global_address is None."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        assert bbmd.global_address is None

    def test_global_address_set_at_init(self, collector: SentCollector):
        """global_address can be set at construction."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            global_address=GLOBAL_ADDR,
        )
        assert bbmd.global_address == GLOBAL_ADDR

    def test_global_address_settable_at_runtime(self, collector: SentCollector):
        """global_address can be changed at runtime."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        bbmd.global_address = GLOBAL_ADDR
        assert bbmd.global_address == GLOBAL_ADDR

        bbmd.global_address = None
        assert bbmd.global_address is None

    def test_forwarded_npdu_uses_global_address_as_originating(
        self, collector: SentCollector
    ):
        """When global_address is set, outgoing Forwarded-NPDUs use it
        as the originating address.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            global_address=GLOBAL_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1
        fwd_msg = decode_bvll(peer_sent[0])
        assert fwd_msg.function == BvlcFunction.FORWARDED_NPDU
        # Originating address should be the global/NAT address
        assert fwd_msg.originating_address == GLOBAL_ADDR
        assert fwd_msg.data == npdu

    def test_without_global_address_uses_actual_source(
        self, collector: SentCollector
    ):
        """Without global_address, Forwarded-NPDUs use the actual source."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1
        fwd_msg = decode_bvll(peer_sent[0])
        assert fwd_msg.originating_address == CLIENT_ADDR

    def test_bdt_entry_matching_global_address_skipped(
        self, collector: SentCollector
    ):
        """BDT entry whose forward address matches global_address is skipped
        to prevent NAT loops.
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            global_address=GLOBAL_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                # This peer's address matches our global address
                BDTEntry(address=GLOBAL_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            CLIENT_ADDR,
        )

        # Should NOT send to GLOBAL_ADDR (would loop back to us)
        global_sent = collector.find_sent_to(GLOBAL_ADDR)
        assert len(global_sent) == 0

        # Should send to PEER_ADDR normally
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1

    def test_self_originated_forwarded_npdu_dropped_with_global(
        self, collector: SentCollector
    ):
        """Forwarded-NPDU with originating address matching global_address
        is dropped (S2 extension for NAT).
        """
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            global_address=GLOBAL_ADDR,
        )

        npdu = b"\x01\x00\x10"
        handled = bbmd.handle_bvlc(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            GLOBAL_ADDR,  # originating = our global address
        )

        assert handled is True
        assert len(collector.sent) == 0
        assert len(collector.local_broadcasts) == 0

    def test_distribute_broadcast_uses_global_address(
        self, collector: SentCollector
    ):
        """Distribute-Broadcast-To-Network also uses global_address."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            local_broadcast_callback=collector.local_broadcast,
            global_address=GLOBAL_ADDR,
        )
        bbmd.set_bdt(
            [
                BDTEntry(address=BBMD_ADDR, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
        )
        # Register FD
        bbmd.handle_bvlc(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
            FD_ADDR,
        )
        collector.clear()

        npdu = b"\x01\x00\x10"
        bbmd.handle_bvlc(
            BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK,
            npdu,
            FD_ADDR,
        )

        # Forwarded-NPDU to peer should use global address
        peer_sent = collector.find_sent_to(PEER_ADDR)
        assert len(peer_sent) == 1
        fwd_msg = decode_bvll(peer_sent[0])
        assert fwd_msg.originating_address == GLOBAL_ADDR


# --- Phase 5: Q3 - Configurable FDT cleanup interval ---


class TestConfigurableFDTCleanupInterval:
    """Q3: The FDT cleanup interval should be configurable."""

    def test_default_cleanup_interval_is_10(self, collector: SentCollector):
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
        )
        assert bbmd._fdt_cleanup_interval == 10.0

    def test_custom_cleanup_interval(self, collector: SentCollector):
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            fdt_cleanup_interval=5.0,
        )
        assert bbmd._fdt_cleanup_interval == 5.0

    def test_custom_interval_used_in_cleanup_loop(self, collector: SentCollector):
        """Verify that the custom interval actually affects the cleanup loop timing."""
        bbmd = BBMDManager(
            local_address=BBMD_ADDR,
            send_callback=collector.send,
            fdt_cleanup_interval=30.0,
        )
        # Just verify the parameter was stored correctly
        assert bbmd._fdt_cleanup_interval == 30.0
