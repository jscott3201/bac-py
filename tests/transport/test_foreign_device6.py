"""Tests for IPv6 Foreign Device manager (transport/foreign_device6.py)."""

from __future__ import annotations

import asyncio

import pytest

from bac_py.network.address import BIP6Address
from bac_py.transport.bvll_ipv6 import decode_bvll6
from bac_py.transport.foreign_device6 import ForeignDevice6Manager
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode

# --- Helpers ---

BBMD_ADDR = BIP6Address(host="fd00::1", port=47808)
LOCAL_ADDR = BIP6Address(host="fd00::50", port=47808)
LOCAL_VMAC = b"\xaa\xbb\xcc"


class Sent6Collector:
    """Collects sent BVLL6 datagrams for assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, BIP6Address]] = []

    def send(self, data: bytes, dest: BIP6Address) -> None:
        self.sent.append((data, dest))

    def clear(self) -> None:
        self.sent.clear()

    def find_sent_to(self, dest: BIP6Address) -> list[bytes]:
        return [data for data, d in self.sent if d == dest]


@pytest.fixture
def collector() -> Sent6Collector:
    return Sent6Collector()


@pytest.fixture
def fd_mgr(collector: Sent6Collector) -> ForeignDevice6Manager:
    return ForeignDevice6Manager(
        bbmd_address=BBMD_ADDR,
        ttl=60,
        send_callback=collector.send,
        local_vmac=LOCAL_VMAC,
        local_address=LOCAL_ADDR,
    )


# --- Properties ---


class TestProperties:
    def test_bbmd_address(self, fd_mgr: ForeignDevice6Manager):
        assert fd_mgr.bbmd_address == BBMD_ADDR

    def test_ttl(self, fd_mgr: ForeignDevice6Manager):
        assert fd_mgr.ttl == 60

    def test_not_registered_initially(self, fd_mgr: ForeignDevice6Manager):
        assert fd_mgr.is_registered is False

    def test_no_last_result_initially(self, fd_mgr: ForeignDevice6Manager):
        assert fd_mgr.last_result is None


# --- Registration ---


class TestRegistration:
    def test_send_registration(self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector):
        fd_mgr._send_registration()

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll6(sent[0])
        assert msg.function == Bvlc6Function.REGISTER_FOREIGN_DEVICE
        assert msg.source_vmac == LOCAL_VMAC
        # Payload should be 2-byte TTL
        assert len(msg.data) == 2
        assert int.from_bytes(msg.data, "big") == 60

    def test_handle_successful_result(self, fd_mgr: ForeignDevice6Manager):
        result_data = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(result_data)
        assert fd_mgr.is_registered is True
        assert fd_mgr.last_result == Bvlc6ResultCode.SUCCESSFUL_COMPLETION

    def test_handle_nak_result(self, fd_mgr: ForeignDevice6Manager):
        result_data = Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(result_data)
        assert fd_mgr.is_registered is False
        assert fd_mgr.last_result == Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK

    def test_handle_short_result_ignored(self, fd_mgr: ForeignDevice6Manager):
        fd_mgr.handle_bvlc_result(b"\x00")  # Only 1 byte
        assert fd_mgr.is_registered is False
        assert fd_mgr.last_result is None

    def test_successful_then_nak_clears_registration(self, fd_mgr: ForeignDevice6Manager):
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        nak = Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(nak)
        assert fd_mgr.is_registered is False

    def test_re_registration_no_duplicate_log(self, fd_mgr: ForeignDevice6Manager):
        """Second successful result should not log again (already registered)."""
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True
        # Second success — takes the already-registered branch
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True


# --- Registration loop ---


class TestRegistrationLoop:
    async def test_start_sends_registration(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        await fd_mgr.start()
        try:
            await asyncio.sleep(0.05)
            sent = collector.find_sent_to(BBMD_ADDR)
            assert len(sent) >= 1
            msg = decode_bvll6(sent[0])
            assert msg.function == Bvlc6Function.REGISTER_FOREIGN_DEVICE
            assert msg.source_vmac == LOCAL_VMAC
        finally:
            await fd_mgr.stop()

    async def test_stop_clears_registration(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        await fd_mgr.start()
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        await fd_mgr.stop()
        assert fd_mgr.is_registered is False

    async def test_start_idempotent(self, fd_mgr: ForeignDevice6Manager):
        await fd_mgr.start()
        task1 = fd_mgr._task
        await fd_mgr.start()
        task2 = fd_mgr._task
        assert task1 is task2
        await fd_mgr.stop()

    async def test_stop_when_not_started(self, fd_mgr: ForeignDevice6Manager):
        await fd_mgr.stop()  # Should not raise


# --- Distribute broadcast ---


class TestDistributeBroadcast:
    def test_send_distribute_broadcast(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)

        npdu = b"\x01\x00\x10\x08\x00"
        fd_mgr.send_distribute_broadcast(npdu)

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll6(sent[0])
        assert msg.function == Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU
        assert msg.source_vmac == LOCAL_VMAC
        assert msg.data == npdu

    def test_distribute_broadcast_not_registered_raises(self, fd_mgr: ForeignDevice6Manager):
        with pytest.raises(RuntimeError, match="Not registered"):
            fd_mgr.send_distribute_broadcast(b"\x01\x00")


# --- TTL encoding ---


class TestTTLEncoding:
    def test_ttl_60_encoding(self, collector: Sent6Collector):
        fd_mgr = ForeignDevice6Manager(
            bbmd_address=BBMD_ADDR,
            ttl=60,
            send_callback=collector.send,
            local_vmac=LOCAL_VMAC,
        )
        fd_mgr._send_registration()
        sent = collector.find_sent_to(BBMD_ADDR)
        msg = decode_bvll6(sent[0])
        assert msg.data == b"\x00\x3c"  # 60 in big-endian

    def test_ttl_300_encoding(self, collector: Sent6Collector):
        fd_mgr = ForeignDevice6Manager(
            bbmd_address=BBMD_ADDR,
            ttl=300,
            send_callback=collector.send,
            local_vmac=LOCAL_VMAC,
        )
        fd_mgr._send_registration()
        sent = collector.find_sent_to(BBMD_ADDR)
        msg = decode_bvll6(sent[0])
        assert msg.data == b"\x01\x2c"  # 300 in big-endian

    def test_ttl_0_raises(self, collector: Sent6Collector):
        with pytest.raises(ValueError, match="TTL must be >= 1"):
            ForeignDevice6Manager(
                bbmd_address=BBMD_ADDR,
                ttl=0,
                send_callback=collector.send,
                local_vmac=LOCAL_VMAC,
            )


# --- Deregistration on stop ---


class TestDeregistrationOnStop:
    async def test_stop_sends_deregistration_when_registered(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        await fd_mgr.start()
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        collector.clear()
        await fd_mgr.stop()

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll6(sent[0])
        assert msg.function == Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY
        assert msg.source_vmac == LOCAL_VMAC
        assert msg.data == LOCAL_ADDR.encode()

    async def test_stop_no_deregistration_when_not_registered(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        await fd_mgr.start()
        await asyncio.sleep(0.05)
        collector.clear()
        await fd_mgr.stop()

        sent = collector.find_sent_to(BBMD_ADDR)
        deregistrations = [
            s
            for s in sent
            if decode_bvll6(s).function == Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY
        ]
        assert len(deregistrations) == 0

    async def test_stop_no_deregistration_without_local_address(self, collector: Sent6Collector):
        fd_mgr = ForeignDevice6Manager(
            bbmd_address=BBMD_ADDR,
            ttl=60,
            send_callback=collector.send,
            local_vmac=LOCAL_VMAC,
            # No local_address
        )
        await fd_mgr.start()
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        collector.clear()
        await fd_mgr.stop()

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 0
        assert fd_mgr.is_registered is False

    async def test_stop_clears_registered_after_deregistration(
        self, fd_mgr: ForeignDevice6Manager, collector: Sent6Collector
    ):
        await fd_mgr.start()
        ok = Bvlc6ResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        await fd_mgr.stop()
        assert fd_mgr.is_registered is False


# --- Registration loop edge cases ---


class TestRegistrationLoopEdgeCases:
    async def test_registration_transport_error(self, collector: Sent6Collector):
        """Transport error during registration loop is caught and logged."""
        call_count = 0

        def failing_send(data: bytes, dest: BIP6Address) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise OSError("Network unreachable")
            collector.send(data, dest)

        fd_mgr = ForeignDevice6Manager(
            bbmd_address=BBMD_ADDR,
            ttl=2,  # Short TTL so re-registration happens at 1s
            send_callback=failing_send,
            local_vmac=LOCAL_VMAC,
            local_address=LOCAL_ADDR,
        )
        await fd_mgr.start()
        try:
            await asyncio.sleep(1.5)
            assert call_count >= 2
        finally:
            await fd_mgr.stop()
