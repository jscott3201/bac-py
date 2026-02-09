"""Tests for Foreign Device manager (transport/foreign_device.py)."""

from __future__ import annotations

import asyncio

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bvll import decode_bvll
from bac_py.transport.foreign_device import ForeignDeviceManager
from bac_py.types.enums import BvlcFunction, BvlcResultCode

# --- Fixtures ---

BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)
LOCAL_ADDR = BIPAddress(host="10.0.0.50", port=47808)


class SentCollector:
    """Collects sent messages for test assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, BIPAddress]] = []

    def send(self, data: bytes, dest: BIPAddress) -> None:
        self.sent.append((data, dest))

    def clear(self) -> None:
        self.sent.clear()

    def find_sent_to(self, dest: BIPAddress) -> list[bytes]:
        return [data for data, d in self.sent if d == dest]


@pytest.fixture
def collector() -> SentCollector:
    return SentCollector()


@pytest.fixture
def fd_mgr(collector: SentCollector) -> ForeignDeviceManager:
    return ForeignDeviceManager(
        bbmd_address=BBMD_ADDR,
        ttl=60,
        send_callback=collector.send,
        local_address=LOCAL_ADDR,
    )


# --- Properties ---


class TestProperties:
    def test_bbmd_address(self, fd_mgr: ForeignDeviceManager):
        assert fd_mgr.bbmd_address == BBMD_ADDR

    def test_ttl(self, fd_mgr: ForeignDeviceManager):
        assert fd_mgr.ttl == 60

    def test_not_registered_initially(self, fd_mgr: ForeignDeviceManager):
        assert fd_mgr.is_registered is False

    def test_no_last_result_initially(self, fd_mgr: ForeignDeviceManager):
        assert fd_mgr.last_result is None


# --- Registration ---


class TestRegistration:
    def test_send_registration(self, fd_mgr: ForeignDeviceManager, collector: SentCollector):
        fd_mgr._send_registration()

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.REGISTER_FOREIGN_DEVICE
        # Payload should be 2-byte TTL
        assert len(msg.data) == 2
        assert int.from_bytes(msg.data, "big") == 60

    def test_handle_successful_result(self, fd_mgr: ForeignDeviceManager):
        result_data = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(result_data)
        assert fd_mgr.is_registered is True
        assert fd_mgr.last_result == BvlcResultCode.SUCCESSFUL_COMPLETION

    def test_handle_nak_result(self, fd_mgr: ForeignDeviceManager):
        result_data = BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(result_data)
        assert fd_mgr.is_registered is False
        assert fd_mgr.last_result == BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK

    def test_handle_short_result_ignored(self, fd_mgr: ForeignDeviceManager):
        fd_mgr.handle_bvlc_result(b"\x00")  # Only 1 byte
        assert fd_mgr.is_registered is False
        assert fd_mgr.last_result is None

    def test_successful_then_nak_clears_registration(self, fd_mgr: ForeignDeviceManager):
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        nak = BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(nak)
        assert fd_mgr.is_registered is False


# --- Registration loop ---


class TestRegistrationLoop:
    @pytest.mark.asyncio
    async def test_start_sends_registration(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        await fd_mgr.start()
        try:
            # Give the task a chance to run
            await asyncio.sleep(0.05)
            sent = collector.find_sent_to(BBMD_ADDR)
            assert len(sent) >= 1
            msg = decode_bvll(sent[0])
            assert msg.function == BvlcFunction.REGISTER_FOREIGN_DEVICE
        finally:
            await fd_mgr.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_registration(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        await fd_mgr.start()
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        await fd_mgr.stop()
        assert fd_mgr.is_registered is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self, fd_mgr: ForeignDeviceManager):
        await fd_mgr.start()
        task1 = fd_mgr._task
        await fd_mgr.start()
        task2 = fd_mgr._task
        assert task1 is task2
        await fd_mgr.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self, fd_mgr: ForeignDeviceManager):
        # Should not raise
        await fd_mgr.stop()


# --- Distribute broadcast ---


class TestDistributeBroadcast:
    def test_send_distribute_broadcast(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        # Must be registered first
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)

        npdu = b"\x01\x00\x10\x08\x00"
        fd_mgr.send_distribute_broadcast(npdu)

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK
        assert msg.data == npdu

    def test_distribute_broadcast_not_registered_raises(self, fd_mgr: ForeignDeviceManager):
        with pytest.raises(RuntimeError, match="Not registered"):
            fd_mgr.send_distribute_broadcast(b"\x01\x00")


# --- TTL encoding ---


class TestTTLEncoding:
    def test_ttl_60_encoding(self, collector: SentCollector):
        fd_mgr = ForeignDeviceManager(
            bbmd_address=BBMD_ADDR,
            ttl=60,
            send_callback=collector.send,
        )
        fd_mgr._send_registration()
        sent = collector.find_sent_to(BBMD_ADDR)
        msg = decode_bvll(sent[0])
        assert msg.data == b"\x00\x3c"  # 60 in big-endian

    def test_ttl_300_encoding(self, collector: SentCollector):
        fd_mgr = ForeignDeviceManager(
            bbmd_address=BBMD_ADDR,
            ttl=300,
            send_callback=collector.send,
        )
        fd_mgr._send_registration()
        sent = collector.find_sent_to(BBMD_ADDR)
        msg = decode_bvll(sent[0])
        assert msg.data == b"\x01\x2c"  # 300 in big-endian

    def test_ttl_0_raises(self, collector: SentCollector):
        with pytest.raises(ValueError, match="TTL must be >= 1"):
            ForeignDeviceManager(
                bbmd_address=BBMD_ADDR,
                ttl=0,
                send_callback=collector.send,
            )


# --- Deregistration on stop (F2) ---


class TestDeregistrationOnStop:
    @pytest.mark.asyncio
    async def test_stop_sends_deregistration_when_registered(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        """F2: stop() sends Delete-Foreign-Device-Table-Entry when registered."""
        await fd_mgr.start()
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        collector.clear()
        await fd_mgr.stop()

        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 1
        msg = decode_bvll(sent[0])
        assert msg.function == BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY
        # Payload should be our own 6-byte address
        assert msg.data == LOCAL_ADDR.encode()

    @pytest.mark.asyncio
    async def test_stop_no_deregistration_when_not_registered(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        """F2: stop() does not send deregistration when not registered."""
        await fd_mgr.start()
        await asyncio.sleep(0.05)
        collector.clear()
        await fd_mgr.stop()

        # No deregistration should be sent since we never got
        # a successful registration result
        sent = collector.find_sent_to(BBMD_ADDR)
        deregistrations = [
            s
            for s in sent
            if decode_bvll(s).function == BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY
        ]
        assert len(deregistrations) == 0

    @pytest.mark.asyncio
    async def test_stop_no_deregistration_without_local_address(
        self, collector: SentCollector
    ):
        """F2: stop() skips deregistration when no local_address is set."""
        fd_mgr = ForeignDeviceManager(
            bbmd_address=BBMD_ADDR,
            ttl=60,
            send_callback=collector.send,
            # No local_address
        )
        await fd_mgr.start()
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        assert fd_mgr.is_registered is True

        collector.clear()
        await fd_mgr.stop()

        # No delete message sent (no local address to send)
        sent = collector.find_sent_to(BBMD_ADDR)
        assert len(sent) == 0
        assert fd_mgr.is_registered is False

    @pytest.mark.asyncio
    async def test_stop_clears_registered_after_deregistration(
        self, fd_mgr: ForeignDeviceManager, collector: SentCollector
    ):
        """F2: stop() clears is_registered after sending deregistration."""
        await fd_mgr.start()
        ok = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
        fd_mgr.handle_bvlc_result(ok)
        await fd_mgr.stop()
        assert fd_mgr.is_registered is False
