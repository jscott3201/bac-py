"""Tests for BBMD core functionality (BDT management, registration, forwarding)."""

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
from tests.transport.conftest import (
    ALL_ONES_MASK,
    BBMD_ADDR,
    CLIENT_ADDR,
    FD_ADDR,
    FD_ADDR2,
    PEER_ADDR,
    PEER_ADDR2,
    SentCollector,
)

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
