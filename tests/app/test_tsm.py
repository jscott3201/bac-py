import asyncio

import pytest

from bac_py.app.tsm import ClientTransaction, ClientTSM, ServerTransaction, ServerTSM
from bac_py.encoding.apdu import ConfirmedRequestPDU
from bac_py.network.address import BACnetAddress
from bac_py.services.errors import (
    BACnetAbortError,
    BACnetError,
    BACnetRejectError,
    BACnetTimeoutError,
)
from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, RejectReason
from tests.helpers import PEER, FakeNetworkLayer


def _make_non_segmented_pdu(
    invoke_id: int = 1,
    service_choice: int = 12,
    service_request: bytes = b"\x01\x02",
) -> ConfirmedRequestPDU:
    """Create a non-segmented ConfirmedRequestPDU for testing."""
    return ConfirmedRequestPDU(
        segmented=False,
        more_follows=False,
        segmented_response_accepted=True,
        max_segments=None,
        max_apdu_length=1476,
        invoke_id=invoke_id,
        sequence_number=None,
        proposed_window_size=None,
        service_choice=service_choice,
        service_request=service_request,
    )


class TestClientTSM:
    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ClientTSM(network, apdu_timeout=0.1, apdu_retries=1)

    async def test_send_request_and_simple_ack(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        # Extract invoke_id from the sent APDU
        assert len(network.sent) >= 1
        apdu_bytes = network.sent[0][0]
        # ConfirmedRequest APDU: byte 0 is PDU type + flags, byte 2 is invoke_id
        invoke_id = apdu_bytes[2]
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        result = await task
        assert result == b""

    async def test_send_request_and_complex_ack(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]
        tsm.handle_complex_ack(PEER, invoke_id, 12, b"\xaa\xbb")
        result = await task
        assert result == b"\xaa\xbb"

    async def test_send_request_error_raises(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]
        tsm.handle_error(PEER, invoke_id, ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        with pytest.raises(BACnetError) as exc_info:
            await task
        assert exc_info.value.error_class == ErrorClass.OBJECT
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_send_request_reject_raises(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]
        tsm.handle_reject(PEER, invoke_id, RejectReason.UNRECOGNIZED_SERVICE)
        with pytest.raises(BACnetRejectError) as exc_info:
            await task
        assert exc_info.value.reason == RejectReason.UNRECOGNIZED_SERVICE

    async def test_send_request_abort_raises(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]
        tsm.handle_abort(PEER, invoke_id, AbortReason.OTHER)
        with pytest.raises(BACnetAbortError) as exc_info:
            await task
        assert exc_info.value.reason == AbortReason.OTHER

    async def test_timeout_raises(self, network):
        tsm = ClientTSM(network, apdu_timeout=0.05, apdu_retries=0)
        with pytest.raises(BACnetTimeoutError):
            await tsm.send_request(12, b"\x01\x02", PEER)

    async def test_timeout_with_retry(self, network):
        tsm = ClientTSM(network, apdu_timeout=0.05, apdu_retries=1)
        with pytest.raises(BACnetTimeoutError):
            await tsm.send_request(12, b"\x01\x02", PEER)
        # Should have sent original + 1 retry = 2 sends
        assert len(network.sent) == 2

    async def test_active_transactions(self, tsm, network):
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        active = tsm.active_transactions()
        assert len(active) == 1
        assert isinstance(active[0], ClientTransaction)

        # Complete it
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        await task
        # Transaction should be cleaned up after await
        assert len(tsm.active_transactions()) == 0

    def test_ignore_ack_for_unknown_transaction(self, tsm, network):
        # Should not raise
        tsm.handle_simple_ack(PEER, 99, 12)
        tsm.handle_complex_ack(PEER, 99, 12, b"data")
        tsm.handle_error(PEER, 99, ErrorClass.OBJECT, ErrorCode.UNKNOWN_OBJECT)
        tsm.handle_reject(PEER, 99, RejectReason.UNRECOGNIZED_SERVICE)
        tsm.handle_abort(PEER, 99, AbortReason.OTHER)


class TestServerTSM:
    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ServerTSM(network, request_timeout=0.1)

    async def test_receive_new_request(self, tsm):
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, data = result
        assert isinstance(txn, ServerTransaction)
        assert txn.invoke_id == 1
        assert txn.source == PEER
        assert txn.service_choice == 12
        assert data == b"\x01\x02"

    async def test_duplicate_request_returns_none(self, tsm, network):
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        # Complete the transaction so it has a cached response
        tsm.complete_transaction(txn, b"\x20\x01\x0c")
        # Now send a duplicate
        result2 = tsm.receive_confirmed_request(pdu, PEER)
        assert result2 is None
        # Should have resent the cached response
        assert len(network.sent) == 1
        assert network.sent[0][0] == b"\x20\x01\x0c"

    async def test_duplicate_before_completion_returns_none_no_resend(self, tsm, network):
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        # Duplicate without completing
        result2 = tsm.receive_confirmed_request(pdu, PEER)
        assert result2 is None
        # No cached response to resend
        assert len(network.sent) == 0

    async def test_complete_caches_response(self, tsm):
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        tsm.complete_transaction(txn, b"\x20\x01\x0c")
        assert txn.cached_response == b"\x20\x01\x0c"

    async def test_transaction_cleanup_after_timeout(self, network):
        tsm = ServerTSM(network, request_timeout=0.05)
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        tsm.complete_transaction(txn, b"\x20\x01\x0c")
        await asyncio.sleep(0.1)
        # After timeout, a new request with same invoke_id should succeed
        result2 = tsm.receive_confirmed_request(pdu, PEER)
        assert result2 is not None
        txn2, _data2 = result2
        assert txn2 is not None

    async def test_different_peers_same_invoke_id(self, tsm):
        pdu = _make_non_segmented_pdu(invoke_id=1)
        peer2 = BACnetAddress(mac_address=b"\xc0\xa8\x01\x02\xba\xc0")
        result1 = tsm.receive_confirmed_request(pdu, PEER)
        result2 = tsm.receive_confirmed_request(pdu, peer2)
        assert result1 is not None
        assert result2 is not None
        txn1, _data1 = result1
        txn2, _data2 = result2
        assert txn1.source != txn2.source

    async def test_client_capabilities_stored(self, tsm):
        """Verify client max_apdu_length and segmentation prefs are stored."""
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=64,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        assert txn.client_max_apdu_length == 480
        assert txn.client_max_segments == 64
        assert txn.segmented_response_accepted is True
