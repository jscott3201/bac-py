import asyncio

import pytest

from bac_py.app.tsm import (
    ClientTransaction,
    ClientTSM,
    ServerTransaction,
    ServerTransactionState,
    ServerTSM,
)
from bac_py.encoding.apdu import (
    AbortPDU,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    SegmentAckPDU,
    decode_apdu,
)
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

    async def test_max_apdu_override_constrains_segment_payload(self, network):
        """max_apdu_override should constrain the APDU size in sent PDUs."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=1476)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER, max_apdu_override=480))
        await asyncio.sleep(0.01)

        # The sent APDU should advertise max_apdu_length=480, not 1476
        assert len(network.sent) >= 1
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]

        # Byte 1 of ConfirmedRequestPDU encodes max-segments and
        # max-APDU-length-accepted. Bits 0-3 encode the max APDU index.
        # Index 3 = 480 bytes per Clause 20.1.2.5
        max_apdu_encoding = apdu_bytes[1] & 0x0F
        assert max_apdu_encoding == 3  # 3 = 480 bytes

        tsm.handle_simple_ack(PEER, invoke_id, 12)
        await task


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


# ---------------------------------------------------------------------------
# Segmentation scenario tests
# ---------------------------------------------------------------------------


class TestClientSegmentedResponse:
    """Test receiving a segmented ComplexACK response on the client side."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ClientTSM(network, apdu_timeout=0.1, apdu_retries=1, proposed_window_size=16)

    async def test_first_segment_triggers_segment_ack(self, tsm, network):
        """Receiving the first segment (seq=0, more_follows=True) should send a SegmentACK."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        assert len(network.sent) >= 1
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]

        # Clear to isolate the SegmentACK we expect next
        network.clear()

        # Server sends first segment of a segmented ComplexACK
        first_seg = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, first_seg)

        # Client should have sent a SegmentACK
        assert len(network.sent) == 1
        ack_bytes = network.sent[0][0]
        decoded_ack = decode_apdu(ack_bytes)
        assert isinstance(decoded_ack, SegmentAckPDU)
        assert decoded_ack.invoke_id == invoke_id
        assert decoded_ack.sequence_number == 0
        assert decoded_ack.negative_ack is False
        assert decoded_ack.sent_by_server is False

        # Task should still be pending (more segments expected)
        assert not task.done()

        # Clean up: send final segment
        network.clear()
        final_seg = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xcc\xdd",
        )
        tsm.handle_segmented_complex_ack(PEER, final_seg)
        result = await task
        assert result == b"\xaa\xbb\xcc\xdd"

    async def test_two_segment_reassembly(self, tsm, network):
        """Receiving two segments should reassemble into complete data."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # First segment
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\x01\x02\x03",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)
        network.clear()

        # Second (final) segment
        seg1 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\x04\x05\x06",
        )
        tsm.handle_segmented_complex_ack(PEER, seg1)
        result = await task
        assert result == b"\x01\x02\x03\x04\x05\x06"

    async def test_four_segments_with_window_ack(self, tsm, network):
        """Four segments with window_size=2 should produce an intermediate ACK.

        The SegmentReceiver stores segment 0 at creation, setting
        ``_expected_idx=1`` and ``_window_start_idx=1``.  With
        ``actual_window_size=2`` (min of ours and sender's), the first
        window boundary is at ``_window_start_idx + actual_window_size = 3``.
        So segments 1 and 2 fill that window, triggering a SEND_ACK.
        """
        tsm_ws2 = ClientTSM(network, apdu_timeout=0.1, apdu_retries=1, proposed_window_size=2)
        task = asyncio.create_task(tsm_ws2.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # First segment (seq=0) -- stored by SegmentReceiver.create()
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm_ws2.handle_segmented_complex_ack(PEER, seg0)
        # Initial ACK for seq=0 sent by handle_segmented_complex_ack
        network.clear()

        # Second segment (seq=1) -- CONTINUE, no ACK yet
        seg1 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xbb",
        )
        tsm_ws2.handle_segmented_complex_ack(PEER, seg1)

        # Third segment (seq=2) -- window boundary, triggers SEND_ACK
        seg2 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=2,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xcc",
        )
        tsm_ws2.handle_segmented_complex_ack(PEER, seg2)

        # Should have sent a SegmentACK at the window boundary
        assert len(network.sent) >= 1
        ack_bytes = network.sent[-1][0]
        decoded = decode_apdu(ack_bytes)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.sequence_number == 2
        network.clear()

        # Fourth (final) segment
        seg3 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=3,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xdd",
        )
        tsm_ws2.handle_segmented_complex_ack(PEER, seg3)
        result = await task
        assert result == b"\xaa\xbb\xcc\xdd"

    async def test_segmented_ack_ignored_for_unknown_transaction(self, tsm, network):
        """A segmented ComplexACK for an unknown invoke_id should be silently ignored."""
        seg = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=99,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa",
        )
        # Should not raise
        tsm.handle_segmented_complex_ack(PEER, seg)
        assert len(network.sent) == 0


class TestClientInvokeIdAllocation:
    """Test invoke ID allocation and exhaustion."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_256_requests_exhausts_invoke_ids(self, network):
        """Sending 256 concurrent requests to the same peer should exhaust invoke IDs."""
        tsm = ClientTSM(network, apdu_timeout=5.0, apdu_retries=0)
        tasks = []
        for _ in range(256):
            t = asyncio.create_task(tsm.send_request(12, b"\x01", PEER))
            tasks.append(t)
        await asyncio.sleep(0.01)

        # All 256 invoke IDs are now in use; the next one should raise RuntimeError
        with pytest.raises(RuntimeError, match="No available invoke IDs"):
            tsm._allocate_invoke_id(PEER)

        # Clean up: complete all transactions
        for apdu_bytes, dest, _ in network.sent:
            invoke_id = apdu_bytes[2]
            tsm.handle_simple_ack(dest, invoke_id, 12)
        for t in tasks:
            await t

    async def test_completed_request_frees_invoke_id(self, network):
        """Completing a request should free the invoke ID for reuse."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)

        # Send and complete a request
        task1 = asyncio.create_task(tsm.send_request(12, b"\x01", PEER))
        await asyncio.sleep(0.01)
        invoke_id_1 = network.sent[0][0][2]
        tsm.handle_simple_ack(PEER, invoke_id_1, 12)
        await task1

        # The invoke ID should now be available again; send another request
        network.clear()
        task2 = asyncio.create_task(tsm.send_request(12, b"\x02", PEER))
        await asyncio.sleep(0.01)
        assert len(network.sent) == 1
        invoke_id_2 = network.sent[0][0][2]
        tsm.handle_simple_ack(PEER, invoke_id_2, 12)
        result = await task2
        assert result == b""

    async def test_different_peers_can_coexist(self, network):
        """Concurrent requests to different peers should both succeed."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        peer2 = BACnetAddress(mac_address=b"\xc0\xa8\x01\x02\xba\xc0")

        task1 = asyncio.create_task(tsm.send_request(12, b"\x01", PEER))
        task2 = asyncio.create_task(tsm.send_request(12, b"\x01", peer2))
        await asyncio.sleep(0.01)

        assert len(network.sent) == 2
        invoke_id_1 = network.sent[0][0][2]
        invoke_id_2 = network.sent[1][0][2]

        # Both transactions should be independently completable
        tsm.handle_simple_ack(PEER, invoke_id_1, 12)
        tsm.handle_simple_ack(peer2, invoke_id_2, 12)
        result1 = await task1
        result2 = await task2
        assert result1 == b""
        assert result2 == b""


class TestServerSegmentedResponse:
    """Test server sending segmented ComplexACK responses."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ServerTSM(
            network,
            request_timeout=0.1,
            max_apdu_length=480,
            proposed_window_size=2,
        )

    def _receive_request(self, tsm, *, segmented_response_accepted=True):
        """Receive a confirmed request and return the transaction."""
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=segmented_response_accepted,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, data = result
        assert data == b"\x01\x02"
        return txn

    async def test_segmented_response_sends_segments(self, tsm, network):
        """start_segmented_response should send ComplexACK segments to the network."""
        txn = self._receive_request(tsm)
        network.clear()

        # Create response data larger than one segment
        # max_apdu_length=480, ComplexACK overhead=5, so max payload = 475 bytes/segment
        response_data = bytes(range(256)) * 2  # 512 bytes -> needs 2 segments

        tsm.start_segmented_response(txn, 12, response_data)

        # Should have sent segments (window_size=2 means up to 2 segments sent)
        assert len(network.sent) >= 1
        # Decode the first sent APDU to verify it is a segmented ComplexACK
        first_apdu = decode_apdu(network.sent[0][0])
        assert isinstance(first_apdu, ComplexAckPDU)
        assert first_apdu.segmented is True
        assert first_apdu.invoke_id == 1
        assert first_apdu.sequence_number == 0
        assert first_apdu.service_choice == 12

    async def test_segment_ack_advances_window(self, tsm, network):
        """After receiving SegmentACK, the server should send the next window."""
        txn = self._receive_request(tsm)
        network.clear()

        # 3-segment response: 475*2 + remainder
        response_data = b"\xab" * (475 * 2 + 100)  # 1050 bytes -> 3 segments

        tsm.start_segmented_response(txn, 12, response_data)

        # With window_size=2, the first window sends segments 0 and 1
        initial_sent_count = len(network.sent)
        assert initial_sent_count >= 2

        # Verify segment 0 and 1 were sent
        seg0 = decode_apdu(network.sent[0][0])
        seg1 = decode_apdu(network.sent[1][0])
        assert isinstance(seg0, ComplexAckPDU)
        assert isinstance(seg1, ComplexAckPDU)
        assert seg0.sequence_number == 0
        assert seg1.sequence_number == 1
        assert seg0.more_follows is True
        assert seg1.more_follows is True

        network.clear()

        # Client sends SegmentACK acknowledging through sequence 1
        seg_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=1,
            actual_window_size=2,
        )
        tsm.handle_segment_ack_for_response(PEER, seg_ack)

        # Server should now send the next window (segment 2, the final one)
        assert len(network.sent) >= 1
        seg2 = decode_apdu(network.sent[0][0])
        assert isinstance(seg2, ComplexAckPDU)
        assert seg2.sequence_number == 2
        assert seg2.more_follows is False

    async def test_final_segment_ack_completes_transaction(self, tsm, network):
        """SegmentACK for the final segment should complete the segmented response."""
        txn = self._receive_request(tsm)
        network.clear()

        # 2-segment response
        response_data = b"\xab" * 500  # 500 bytes -> 2 segments (475 + 25)

        tsm.start_segmented_response(txn, 12, response_data)

        # With window_size=2, both segments sent in one window
        assert len(network.sent) == 2
        seg1 = decode_apdu(network.sent[1][0])
        assert isinstance(seg1, ComplexAckPDU)
        assert seg1.more_follows is False  # last segment

        network.clear()

        # Client ACKs the final segment
        seg_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=1,
            actual_window_size=2,
        )
        tsm.handle_segment_ack_for_response(PEER, seg_ack)

        # Transaction should transition to IDLE (complete)
        assert txn.state == ServerTransactionState.IDLE
        assert txn.segment_sender is None

    async def test_segmented_response_rejected_when_not_accepted(self, tsm, network):
        """If client does not accept segmented responses, server should abort."""
        txn = self._receive_request(tsm, segmented_response_accepted=False)
        network.clear()

        response_data = b"\xab" * 500
        tsm.start_segmented_response(txn, 12, response_data)

        # Should have sent an Abort PDU
        assert len(network.sent) == 1
        abort = decode_apdu(network.sent[0][0])
        assert isinstance(abort, AbortPDU)
        assert abort.sent_by_server is True
        assert abort.abort_reason == AbortReason.SEGMENTATION_NOT_SUPPORTED


class TestSegmentAckWindowSize:
    """Test window size validation in SegmentACK handling."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_client_aborts_on_zero_window_size(self, network):
        """Client should abort when receiving SegmentACK with window_size=0."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)

        # Create a request large enough to require segmentation
        # max_apdu=50, confirmed_request overhead=6, so max_payload=44
        large_data = b"\xab" * 100  # 100 bytes -> 3 segments

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        assert len(network.sent) >= 1
        invoke_id = network.sent[0][0][2]
        network.clear()

        # Send SegmentACK with invalid window_size=0
        bad_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=0,
        )
        tsm.handle_segment_ack(PEER, bad_ack)

        # Client should have sent an Abort PDU
        assert len(network.sent) >= 1
        abort = decode_apdu(network.sent[-1][0])
        assert isinstance(abort, AbortPDU)
        assert abort.abort_reason == AbortReason.WINDOW_SIZE_OUT_OF_RANGE

        with pytest.raises(BACnetAbortError) as exc_info:
            await task
        assert exc_info.value.reason == AbortReason.WINDOW_SIZE_OUT_OF_RANGE

    async def test_client_aborts_on_window_size_128(self, network):
        """Client should abort when receiving SegmentACK with window_size=128."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        bad_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=128,
        )
        tsm.handle_segment_ack(PEER, bad_ack)

        assert len(network.sent) >= 1
        abort = decode_apdu(network.sent[-1][0])
        assert isinstance(abort, AbortPDU)
        assert abort.abort_reason == AbortReason.WINDOW_SIZE_OUT_OF_RANGE

        with pytest.raises(BACnetAbortError):
            await task

    async def test_server_aborts_on_zero_window_size(self, network):
        """Server should abort when receiving SegmentACK with window_size=0."""
        tsm = ServerTSM(
            network,
            request_timeout=0.1,
            max_apdu_length=480,
            proposed_window_size=2,
        )
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        network.clear()

        response_data = b"\xab" * 500
        tsm.start_segmented_response(txn, 12, response_data)
        network.clear()

        bad_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=0,
            actual_window_size=0,
        )
        tsm.handle_segment_ack_for_response(PEER, bad_ack)

        # Should have sent an Abort PDU
        assert len(network.sent) >= 1
        abort = decode_apdu(network.sent[-1][0])
        assert isinstance(abort, AbortPDU)
        assert abort.sent_by_server is True
        assert abort.abort_reason == AbortReason.WINDOW_SIZE_OUT_OF_RANGE

    async def test_server_aborts_on_window_size_255(self, network):
        """Server should abort when receiving SegmentACK with window_size=255."""
        tsm = ServerTSM(
            network,
            request_timeout=0.1,
            max_apdu_length=480,
            proposed_window_size=2,
        )
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        network.clear()

        response_data = b"\xab" * 500
        tsm.start_segmented_response(txn, 12, response_data)
        network.clear()

        bad_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=0,
            actual_window_size=255,
        )
        tsm.handle_segment_ack_for_response(PEER, bad_ack)

        assert len(network.sent) >= 1
        abort = decode_apdu(network.sent[-1][0])
        assert isinstance(abort, AbortPDU)
        assert abort.abort_reason == AbortReason.WINDOW_SIZE_OUT_OF_RANGE

    async def test_valid_window_size_127_is_accepted(self, network):
        """Window size 127 (the maximum valid value) should be accepted."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Send a valid SegmentACK with window_size=127 for the last segment
        # First, figure out what segments were sent
        # max_payload = 50 - 6 = 44 bytes; 100 bytes -> ceil(100/44) = 3 segments
        # Acknowledge through the last segment (seq=2)
        good_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=2,
            actual_window_size=127,
        )
        tsm.handle_segment_ack(PEER, good_ack)

        # Should NOT have sent an abort; transaction moves to AWAIT_CONFIRMATION
        aborts = [
            s
            for s in network.sent
            if len(s[0]) >= 1 and (s[0][0] >> 4) == 7  # PduType.ABORT = 7
        ]
        assert len(aborts) == 0

        # Complete the transaction to clean up
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        result = await task
        assert result == b""


class TestDuplicateSegments:
    """Test duplicate segment handling during segmented reception."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ClientTSM(network, apdu_timeout=0.1, apdu_retries=1, proposed_window_size=4)

    async def test_duplicate_segment_resends_ack(self, tsm, network):
        """Receiving a duplicate segment should trigger a resend of the last ACK."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Server sends first segment
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)

        # Client sent a SegmentACK for the first segment (initial ACK)
        initial_ack_count = len(network.sent)
        assert initial_ack_count == 1
        network.clear()

        # Server resends the first segment (seq=0) -- this is a duplicate
        # since the receiver has already advanced past it
        tsm.handle_segmented_complex_ack(PEER, seg0)

        # The duplicate should trigger a RESEND_LAST_ACK action,
        # sending another SegmentACK
        assert len(network.sent) >= 1
        ack_bytes = network.sent[-1][0]
        decoded = decode_apdu(ack_bytes)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.negative_ack is False

        # Task still pending
        assert not task.done()

        # Clean up: send final segment
        network.clear()
        seg1 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, seg1)
        result = await task
        assert result == b"\xaa\xbb"

    async def test_duplicate_does_not_corrupt_reassembly(self, tsm, network):
        """Receiving a duplicate segment should not corrupt the reassembled data."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Segment 0
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\x11\x22",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)
        network.clear()

        # Segment 1
        seg1 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\x33\x44",
        )
        tsm.handle_segmented_complex_ack(PEER, seg1)
        network.clear()

        # Duplicate of segment 0 (should be ignored or cause ACK resend)
        tsm.handle_segmented_complex_ack(PEER, seg0)
        network.clear()

        # Duplicate of segment 1
        tsm.handle_segmented_complex_ack(PEER, seg1)
        network.clear()

        # Final segment
        seg2 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=2,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\x55\x66",
        )
        tsm.handle_segmented_complex_ack(PEER, seg2)
        result = await task
        assert result == b"\x11\x22\x33\x44\x55\x66"

    async def test_server_duplicate_request_segment_handling(self, network):
        """Server should handle duplicate request segments gracefully."""
        tsm = ServerTSM(
            network,
            request_timeout=0.1,
            proposed_window_size=4,
        )

        # First segment of a segmented request
        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(seg0, PEER)
        assert result is not None
        _txn, data = result
        assert data is None  # More segments expected

        ack_count_after_first = len(network.sent)
        assert ack_count_after_first >= 1  # SegmentACK for seq=0

        # Duplicate of segment 0
        tsm.receive_confirmed_request(seg0, PEER)
        # Duplicate goes through handle_request_segment; should return (txn, None)
        # and resend the last ACK
        ack_count_after_dup = len(network.sent)
        assert ack_count_after_dup > ack_count_after_first

        # Send final segment to complete the request
        seg1 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        result3 = tsm.receive_confirmed_request(seg1, PEER)
        assert result3 is not None
        _txn3, complete_data = result3
        assert complete_data == b"\x01\x02\x03\x04"


# ---------------------------------------------------------------------------
# Additional coverage tests for TSM
# ---------------------------------------------------------------------------


class TestClientSegmentTimeoutRetry:
    """Test segment timeout handling with retries.

    Covers SEGMENTED_REQUEST and SEGMENTED_CONFIRMATION states.
    """

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segment_timeout_retry_segmented_request(self, network):
        """In SEGMENTED_REQUEST state, segment timeout should refill the window."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=2,
            max_apdu_length=50,
            segment_timeout=0.05,
        )
        large_data = b"\xab" * 100  # Forces segmented request

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        initial_sent = len(network.sent)
        assert initial_sent >= 1

        # Wait for the segment timeout to fire (4 * 0.05 = 0.2s for wait_for_seg)
        await asyncio.sleep(0.25)

        # Should have retried (resent the window)
        assert len(network.sent) > initial_sent

        # Cancel to clean up
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_segment_timeout_exhaustion_segmented_request(self, network):
        """In SEGMENTED_REQUEST state, exhausting retries should abort."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=0,
            max_apdu_length=50,
            segment_timeout=0.05,
        )
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        # Wait for the segment timeout to exhaust retries (0 retries -> immediate abort)
        await asyncio.sleep(0.3)

        with pytest.raises(BACnetAbortError) as exc_info:
            await task
        assert exc_info.value.reason == AbortReason.TSM_TIMEOUT

    async def test_segment_timeout_retry_segmented_confirmation(self, network):
        """In SEGMENTED_CONFIRMATION state, segment timeout sends negative SegmentACK."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=2,
            segment_timeout=0.05,
            proposed_window_size=4,
        )
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Receive first segment to enter SEGMENTED_CONFIRMATION
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)
        network.clear()

        # Wait for segment timeout to fire
        await asyncio.sleep(0.1)

        # Should have sent a negative SegmentACK
        assert len(network.sent) >= 1
        ack_bytes = network.sent[-1][0]
        decoded = decode_apdu(ack_bytes)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.negative_ack is True

        # Clean up
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_segment_timeout_exhaustion_segmented_confirmation(self, network):
        """In SEGMENTED_CONFIRMATION state, exhausting retries should abort."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=0,
            segment_timeout=0.05,
            proposed_window_size=4,
        )
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Receive first segment to enter SEGMENTED_CONFIRMATION
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)

        # Wait for segment timeout to fire and exhaust retries
        await asyncio.sleep(0.15)

        with pytest.raises(BACnetAbortError) as exc_info:
            await task
        assert exc_info.value.reason == AbortReason.TSM_TIMEOUT


class TestClientSegmentedRequest:
    """Test sending segmented requests (large payloads)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segmented_request_segment_ack_advances(self, network):
        """Valid SegmentACK after partial window should advance sending."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=1,
            max_apdu_length=50,
            proposed_window_size=2,
        )
        large_data = b"\xab" * 100  # 100 bytes, needs ~3 segments

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        assert len(network.sent) >= 1
        invoke_id = network.sent[0][0][2]
        network.clear()

        # Server sends SegmentACK for the first window
        seg_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=1,
            actual_window_size=2,
        )
        tsm.handle_segment_ack(PEER, seg_ack)

        # Should have sent next window of segments
        assert len(network.sent) >= 1

        # Send final SegmentACK indicating all received, then SimpleACK
        # to complete
        final_ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=2,
            actual_window_size=2,
        )
        tsm.handle_segment_ack(PEER, final_ack)

        # Now in AWAIT_CONFIRMATION, send SimpleACK
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        result = await task
        assert result == b""

    async def test_simple_ack_wrong_state_ignored(self, network):
        """SimpleACK received in wrong state should be silently ignored."""
        tsm = ClientTSM(
            network,
            apdu_timeout=0.1,
            apdu_retries=0,
            max_apdu_length=50,
        )
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]

        # In SEGMENTED_REQUEST state, SimpleACK should be ignored
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        # Task should still be pending
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_complex_ack_wrong_state_ignored(self, network):
        """ComplexACK in wrong state should be silently ignored."""
        tsm = ClientTSM(
            network,
            apdu_timeout=0.1,
            apdu_retries=0,
            max_apdu_length=50,
        )
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]

        # In SEGMENTED_REQUEST state, ComplexACK should be ignored
        tsm.handle_complex_ack(PEER, invoke_id, 12, b"\xaa")
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestServerSegmentTimeout:
    """Test server-side segment timeout handling."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_server_segment_timeout_retry_segmented_request(self, network):
        """Server segment timeout in SEGMENTED_REQUEST sends negative SegmentACK."""
        tsm = ServerTSM(
            network,
            request_timeout=5.0,
            segment_timeout=0.05,
            apdu_retries=2,
            proposed_window_size=4,
        )

        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(seg0, PEER)
        assert result is not None
        network.clear()

        # Wait for segment timeout
        await asyncio.sleep(0.1)

        # Should have sent a negative SegmentACK
        assert len(network.sent) >= 1
        ack_bytes = network.sent[-1][0]
        decoded = decode_apdu(ack_bytes)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.negative_ack is True

    async def test_server_segment_timeout_exhaustion_aborts(self, network):
        """Server segment timeout exhaustion sends Abort PDU."""
        tsm = ServerTSM(
            network,
            request_timeout=5.0,
            segment_timeout=0.03,
            apdu_retries=0,
            proposed_window_size=4,
        )

        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        tsm.receive_confirmed_request(seg0, PEER)
        network.clear()

        # Wait for segment timeout to exhaust retries
        await asyncio.sleep(0.1)

        # Should have sent an Abort PDU
        assert len(network.sent) >= 1
        abort = decode_apdu(network.sent[-1][0])
        assert isinstance(abort, AbortPDU)
        assert abort.abort_reason == AbortReason.TSM_TIMEOUT

    async def test_server_segment_timeout_retry_segmented_response(self, network):
        """Server segment timeout in SEGMENTED_RESPONSE retries sending window."""
        tsm = ServerTSM(
            network,
            request_timeout=5.0,
            segment_timeout=0.05,
            apdu_retries=2,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        network.clear()

        response_data = b"\xab" * 500
        tsm.start_segmented_response(txn, 12, response_data)
        network.clear()

        # Wait for segment timeout (4 * 0.05 = 0.2s)
        await asyncio.sleep(0.25)

        # Should have retried sending the window
        assert len(network.sent) >= 1

    async def test_server_segment_timeout_exhaustion_response_aborts(self, network):
        """Server segment timeout exhaustion in SEGMENTED_RESPONSE sends Abort."""
        tsm = ServerTSM(
            network,
            request_timeout=5.0,
            segment_timeout=0.03,
            apdu_retries=0,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        network.clear()

        response_data = b"\xab" * 500
        tsm.start_segmented_response(txn, 12, response_data)
        network.clear()

        # Wait for timeout exhaustion
        await asyncio.sleep(0.2)

        # Should have sent an Abort PDU
        abort_pdus = [s for s in network.sent if len(s[0]) >= 1 and (s[0][0] >> 4) == 7]
        assert len(abort_pdus) >= 1

    async def test_server_on_segment_timeout_no_txn(self, network):
        """Server _on_server_segment_timeout with missing txn should be no-op."""
        tsm = ServerTSM(network, request_timeout=5.0)
        # Call with a key that doesn't exist -- should not raise
        tsm._on_server_segment_timeout((PEER, 255))
        assert len(network.sent) == 0

    async def test_client_on_segment_timeout_no_txn(self, network):
        """Client _on_segment_timeout with missing txn should be no-op."""
        tsm = ClientTSM(network, apdu_timeout=5.0)
        # Call with a key that doesn't exist -- should not raise
        tsm._on_segment_timeout((PEER, 255))
        assert len(network.sent) == 0

    async def test_client_on_timeout_no_txn(self, network):
        """Client _on_timeout with missing txn should be no-op."""
        tsm = ClientTSM(network, apdu_timeout=5.0)
        tsm._on_timeout((PEER, 255))
        assert len(network.sent) == 0


# ---------------------------------------------------------------------------
# Additional coverage tests for TSM
# ---------------------------------------------------------------------------


class TestClientSegmentAckEdgeCases:
    """Test edge cases in client handle_segment_ack."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segment_ack_done_future_ignored(self, network):
        """handle_segment_ack ignores transactions with done future (line 260)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        # Cancel the future so it's done
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Now call handle_segment_ack with a done future -- should be no-op
        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=2,
        )
        network.clear()
        tsm.handle_segment_ack(PEER, ack)
        assert len(network.sent) == 0

    async def test_segment_ack_wrong_state_ignored(self, network):
        """handle_segment_ack ignores when state is not SEGMENTED_REQUEST (line 263)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # State is AWAIT_CONFIRMATION (not SEGMENTED_REQUEST)
        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=2,
        )
        tsm.handle_segment_ack(PEER, ack)
        # Should be ignored, no abort sent
        assert len(network.sent) == 0

        # Clean up
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        await task

    async def test_segment_ack_no_sender_ignored(self, network):
        """handle_segment_ack ignores when segment_sender is None (line 267)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        # Force-clear the segment_sender
        key = (PEER, invoke_id)
        txn = tsm._transactions[key]
        txn.segment_sender = None
        network.clear()

        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=2,
        )
        tsm.handle_segment_ack(PEER, ack)
        assert len(network.sent) == 0

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestClientSegmentedComplexAckEdgeCases:
    """Test edge cases in handle_segmented_complex_ack."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_single_segment_segmented_response(self, network):
        """Single-segment 'segmented' response completes immediately (lines 311-312)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Single segment with more_follows=False
        seg = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, seg)
        result = await task
        assert result == b"\xaa\xbb"

    async def test_wrong_state_for_subsequent_segment(self, network):
        """Subsequent segment in wrong state is ignored (line 319)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Send a non-zero segment without first transitioning to
        # SEGMENTED_CONFIRMATION state
        seg = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, seg)
        # Should be ignored, task still pending
        assert not task.done()

        tsm.handle_simple_ack(PEER, invoke_id, 12)
        await task

    async def test_no_receiver_for_subsequent_segment(self, network):
        """Subsequent segment with receiver=None is ignored (line 323)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, proposed_window_size=4)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # First segment to enter SEGMENTED_CONFIRMATION
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)

        # Force remove the receiver
        key = (PEER, invoke_id)
        txn = tsm._transactions[key]
        txn.segment_receiver = None
        network.clear()

        # Now send another segment -- should be ignored
        seg1 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, seg1)
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_no_sequence_number_for_subsequent_segment(self, network):
        """Subsequent segment with sequence_number=None is ignored (line 326)."""
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, proposed_window_size=4)
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # First segment
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)
        network.clear()

        # Send segment with sequence_number=None
        seg_bad = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=None,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, seg_bad)
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestClientSegmentationError:
    """Test SegmentationError during _send_segmented_request."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segmentation_error_aborts_future(self, network):
        """SegmentationError during segmented request sets exception (lines 394-396)."""
        from unittest.mock import patch

        from bac_py.segmentation.manager import SegmentationError

        # Use max_apdu_length=50 and a payload that triggers segmentation
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0, max_apdu_length=50)

        # Patch SegmentSender.create to raise
        with patch(
            "bac_py.app.tsm.SegmentSender.create",
            side_effect=SegmentationError(AbortReason.APDU_TOO_LONG),
        ):
            with pytest.raises(BACnetAbortError) as exc_info:
                await tsm.send_request(12, b"\xab" * 100, PEER)
            assert exc_info.value.reason == AbortReason.APDU_TOO_LONG


class TestClientFillWindowNoSender:
    """Test _fill_and_send_request_window with no sender."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_fill_window_no_sender_is_noop(self, network):
        """_fill_and_send_request_window returns early if sender is None (line 406)."""
        from bac_py.app.tsm import ClientTransaction

        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        txn = ClientTransaction(
            invoke_id=1,
            destination=PEER,
            service_choice=12,
            request_data=b"\x01",
            future=asyncio.get_event_loop().create_future(),
        )
        txn.segment_sender = None
        network.clear()
        tsm._fill_and_send_request_window(txn)
        assert len(network.sent) == 0


class TestClientSegmentAckNoReceiver:
    """Test _send_client_segment_ack with no receiver."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_send_segment_ack_no_receiver_is_noop(self, network):
        """_send_client_segment_ack returns early if receiver is None (line 435)."""
        from bac_py.app.tsm import ClientTransaction

        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        txn = ClientTransaction(
            invoke_id=1,
            destination=PEER,
            service_choice=12,
            request_data=b"\x01",
            future=asyncio.get_event_loop().create_future(),
        )
        txn.segment_receiver = None
        tsm._send_client_segment_ack(txn, seq=0, negative=False)
        assert len(network.sent) == 0


class TestClientAbortTransactionAlreadyDone:
    """Test _abort_transaction when future is already done."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_abort_done_future_only_sends_pdu(self, network):
        """_abort_transaction with done future still sends abort but does not set exception (line 453)."""
        from bac_py.app.tsm import ClientTransaction

        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=0)
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result(b"")  # Mark as done
        txn = ClientTransaction(
            invoke_id=1,
            destination=PEER,
            service_choice=12,
            request_data=b"\x01",
            future=future,
        )
        tsm._abort_transaction(txn, AbortReason.OTHER)
        # Should still send the abort PDU
        assert len(network.sent) == 1
        decoded = decode_apdu(network.sent[0][0])
        assert isinstance(decoded, AbortPDU)
        # Future should still have its original result
        assert future.result() == b""


class TestClientTimeoutRetrySegmented:
    """Test _on_timeout retry for segmented requests (line 501)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_timeout_retry_segmented_request(self, network):
        """Timeout retry path re-sends segmented request (line 500-501)."""
        tsm = ClientTSM(
            network,
            apdu_timeout=0.05,
            apdu_retries=1,
            max_apdu_length=50,
        )
        large_data = b"\xab" * 100

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        initial_sent = len(network.sent)
        invoke_id = network.sent[0][0][2]

        # Acknowledge the first request segments so we enter AWAIT_CONFIRMATION
        key = (PEER, invoke_id)
        txn = tsm._transactions.get(key)
        if txn and txn.segment_sender:
            # Simulate all segments sent: acknowledge through last segment
            total = txn.segment_sender.total_segments
            final_ack = SegmentAckPDU(
                negative_ack=False,
                sent_by_server=True,
                invoke_id=invoke_id,
                sequence_number=total - 1,
                actual_window_size=16,
            )
            tsm.handle_segment_ack(PEER, final_ack)

        # Now in AWAIT_CONFIRMATION -- wait for APDU timeout to fire
        await asyncio.sleep(0.15)

        # Should have retried, which sends more PDUs
        assert len(network.sent) > initial_sent

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestClientSegmentTimeoutReceiverNone:
    """Test _on_segment_timeout SEGMENTED_CONFIRMATION with receiver=None (lines 529-535)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segment_timeout_no_receiver_does_not_crash(self, network):
        """Segment timeout with no receiver just does not send ACK."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=2,
            segment_timeout=0.05,
            proposed_window_size=4,
        )
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        invoke_id = network.sent[0][0][2]
        network.clear()

        # Enter SEGMENTED_CONFIRMATION state
        seg0 = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, seg0)

        # Remove the receiver
        key = (PEER, invoke_id)
        txn = tsm._transactions[key]
        txn.segment_receiver = None
        network.clear()

        # Wait for segment timeout
        await asyncio.sleep(0.1)

        # No negative ACK should be sent since receiver is None
        seg_acks = [
            s
            for s in network.sent
            if len(s[0]) >= 1 and (s[0][0] >> 4) == 4  # SegmentACK type
        ]
        assert len(seg_acks) == 0

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestServerSingleSegmentRequest:
    """Test server single-segment 'segmented' request (lines 666-668)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_single_segment_segmented_request(self, network):
        """Single-segment segmented request returns data immediately."""
        tsm = ServerTSM(network, request_timeout=0.1, proposed_window_size=4)

        pdu = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, data = result
        assert data == b"\x01\x02"
        assert txn.state == ServerTransactionState.AWAIT_RESPONSE


class TestServerHandleRequestSegmentEdgeCases:
    """Test server handle_request_segment edge cases."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_no_txn_returns_none(self, network):
        """handle_request_segment with no matching txn returns None (line 690)."""
        tsm = ServerTSM(network, request_timeout=0.1)
        pdu = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=99,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        result = tsm.handle_request_segment(pdu, PEER)
        assert result is None

    async def test_no_receiver_returns_none(self, network):
        """handle_request_segment with no receiver returns None (line 694)."""
        tsm = ServerTSM(network, request_timeout=0.1, proposed_window_size=4)

        # Create a segmented request to register the txn
        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        tsm.receive_confirmed_request(seg0, PEER)

        # Remove the receiver
        key = (PEER, 1)
        txn = tsm._transactions[key]
        txn.segment_receiver = None

        seg1 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        result = tsm.handle_request_segment(seg1, PEER)
        assert result is None

    async def test_no_sequence_number_returns_none(self, network):
        """handle_request_segment with sequence_number=None returns None (line 697)."""
        tsm = ServerTSM(network, request_timeout=0.1, proposed_window_size=4)

        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        tsm.receive_confirmed_request(seg0, PEER)

        seg_bad = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        result = tsm.handle_request_segment(seg_bad, PEER)
        assert result is None


class TestServerSegmentationError:
    """Test SegmentationError in start_segmented_response (lines 752-754)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_segmentation_error_aborts(self, network):
        """SegmentationError during start_segmented_response sends abort."""
        from unittest.mock import patch

        from bac_py.segmentation.manager import SegmentationError

        tsm = ServerTSM(network, request_timeout=0.1, max_apdu_length=480, proposed_window_size=2)
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        network.clear()

        with patch(
            "bac_py.app.tsm.SegmentSender.create",
            side_effect=SegmentationError(AbortReason.APDU_TOO_LONG),
        ):
            tsm.start_segmented_response(txn, 12, b"\xab" * 500)

        # Should have sent an Abort PDU
        assert len(network.sent) == 1
        decoded = decode_apdu(network.sent[0][0])
        assert isinstance(decoded, AbortPDU)
        assert decoded.abort_reason == AbortReason.APDU_TOO_LONG


class TestServerSegmentAckForResponseEdgeCases:
    """Test edge cases in handle_segment_ack_for_response."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_no_txn_is_noop(self, network):
        """handle_segment_ack_for_response with no txn is noop (line 782)."""
        tsm = ServerTSM(network, request_timeout=0.1)
        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=99,
            sequence_number=0,
            actual_window_size=2,
        )
        tsm.handle_segment_ack_for_response(PEER, ack)
        assert len(network.sent) == 0

    async def test_no_sender_is_noop(self, network):
        """handle_segment_ack_for_response with no sender is noop (line 786)."""
        tsm = ServerTSM(network, request_timeout=0.1, max_apdu_length=480, proposed_window_size=2)
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result

        # Start segmented response
        tsm.start_segmented_response(txn, 12, b"\xab" * 500)

        # Remove the sender
        txn.segment_sender = None
        network.clear()

        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=0,
            actual_window_size=2,
        )
        tsm.handle_segment_ack_for_response(PEER, ack)
        assert len(network.sent) == 0


class TestServerFillWindowNoSender:
    """Test _fill_and_send_response_window with no sender (line 818)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    def test_fill_window_no_sender_is_noop(self, network):
        """_fill_and_send_response_window returns early if sender is None."""
        from bac_py.app.tsm import ServerTransaction

        tsm = ServerTSM(network, request_timeout=0.1)
        txn = ServerTransaction(
            invoke_id=1,
            source=PEER,
            service_choice=12,
        )
        txn.segment_sender = None
        tsm._fill_and_send_response_window(txn)
        assert len(network.sent) == 0


class TestServerCompleteTransaction:
    """Test complete_transaction caching (line 812)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_complete_transaction_caches_response(self, network):
        """complete_transaction stores response and sets state to IDLE."""
        tsm = ServerTSM(network, request_timeout=0.1)
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result

        tsm.complete_transaction(txn, b"\x20\x01\x0c")
        assert txn.cached_response == b"\x20\x01\x0c"
        assert txn.state == ServerTransactionState.IDLE


class TestServerTimeoutHandlerCancelGuards:
    """Test timeout handlers cancel guards (lines 872-896)."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_restart_timeout_cancels_existing(self, network):
        """_restart_timeout cancels existing handle before starting new one."""
        tsm = ServerTSM(network, request_timeout=0.1)
        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result

        # There should be a timeout handle already
        assert txn.timeout_handle is not None
        old_handle = txn.timeout_handle

        # Call _restart_timeout -- should cancel old and set new
        tsm._restart_timeout(txn)
        assert txn.timeout_handle is not None
        assert txn.timeout_handle is not old_handle

    async def test_start_segment_timeout_cancels_existing(self, network):
        """_start_segment_timeout cancels existing handle before starting new one."""
        tsm = ServerTSM(network, request_timeout=0.1, segment_timeout=0.05)

        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(seg0, PEER)
        assert result is not None
        txn = result[0]

        # Should have a timeout handle from _start_segment_timeout
        assert txn.timeout_handle is not None
        old_handle = txn.timeout_handle

        # Restart it
        tsm._restart_segment_timeout(txn)
        assert txn.timeout_handle is not None
        assert txn.timeout_handle is not old_handle

    async def test_start_server_segment_timeout_cancels_existing(self, network):
        """_start_server_segment_timeout cancels existing handle."""
        tsm = ServerTSM(
            network,
            request_timeout=0.1,
            segment_timeout=0.05,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result

        # Start a segmented response
        tsm.start_segmented_response(txn, 12, b"\xab" * 500)
        assert txn.timeout_handle is not None
        old_handle = txn.timeout_handle

        # Restart the server segment timeout
        tsm._start_server_segment_timeout(txn)
        assert txn.timeout_handle is not None
        assert txn.timeout_handle is not old_handle


# ==================== Coverage gap tests: uncovered lines/branches ====================


class TestClientTSMAbortAction:
    """Test ABORT action in client segment dispatch (lines 345-346)."""

    async def test_segmented_complex_ack_abort_on_out_of_window(self):
        """SegmentReceiver returns ABORT for out-of-window sequence (lines 345-346)."""
        network = FakeNetworkLayer()
        tsm = ClientTSM(network, apdu_timeout=1.0, apdu_retries=1)

        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        assert len(network.sent) >= 1
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]

        # Send first segmented complex ack to enter SEGMENTED_CONFIRMATION state
        first_seg = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xaa",
        )
        tsm.handle_segmented_complex_ack(PEER, first_seg)

        # Now send a segment with a sequence number far out of window to trigger ABORT
        bad_seg = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=200,  # Far out of window
            proposed_window_size=2,
            service_choice=12,
            service_ack=b"\xbb",
        )
        tsm.handle_segmented_complex_ack(PEER, bad_seg)

        # The future should have been set with a BACnetAbortError
        with pytest.raises(BACnetAbortError):
            await task


class TestServerTSMAbortAction:
    """Test ABORT action in server segment dispatch (lines 710-712, 720-722)."""

    async def test_server_handle_request_segment_abort(self):
        """handle_request_segment returns None on ABORT for out-of-window segment."""
        network = FakeNetworkLayer()
        tsm = ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        # Create a segmented request to start
        first_seg = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(first_seg, PEER)
        assert result is not None
        _txn, data = result
        assert data is None  # Still waiting for more segments

        # Send a segment that fails both in_window and duplicate_in_window checks.
        # After first seg (seq 0, window size 2), expected=1, actual_window=2,
        # proposed_window=2. Seq 3: (3-1)%256=2, in_window: 2<2=false,
        # duplicate: wm=2, 2<2<=255=false => ABORT.
        bad_seg = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=3,  # Exactly at boundary to trigger ABORT
            proposed_window_size=2,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        abort_result = tsm.handle_request_segment(bad_seg, PEER)
        assert abort_result is None  # ABORT returns None

    async def test_server_handle_request_segment_send_ack(self):
        """handle_request_segment sends ACK at window boundary (lines 709-712)."""
        network = FakeNetworkLayer()
        tsm = ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        # Create a segmented request (more follows, window size 2)
        first_seg = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=2,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(first_seg, PEER)
        assert result is not None

        # Send next segment to fill window
        seg1 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=1,
            proposed_window_size=2,
            service_choice=12,
            service_request=b"\x03\x04",
        )
        result = tsm.handle_request_segment(seg1, PEER)
        # Should return (txn, None) since window boundary was hit -> SEND_ACK
        assert result is not None
        assert result[1] is None


class TestClientTSMCancelTimeout:
    """Test _cancel_timeout with no handle (branch 354->exit)."""

    async def test_cancel_timeout_no_handle(self):
        """_cancel_timeout is a no-op when timeout_handle is None (branch 354->exit)."""
        network = FakeNetworkLayer()
        tsm = ClientTSM(network, apdu_timeout=0.1, apdu_retries=1)

        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)
        assert len(network.sent) >= 1
        apdu_bytes = network.sent[0][0]
        invoke_id = apdu_bytes[2]

        key = (PEER, invoke_id)
        txn = tsm._transactions.get(key)
        assert txn is not None

        # Clear the timeout handle
        txn.timeout_handle = None
        # Should not raise
        tsm._cancel_timeout(txn)

        # Clean up
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        await task


class TestServerTSMTimeoutBranches:
    """Test server TSM timeout branches (872->874, 878->880, 888->890, 894->896, etc.)."""

    async def test_restart_timeout_cancels_existing(self):
        """_restart_timeout cancels existing handle (branch 872->874)."""
        network = FakeNetworkLayer()
        tsm = ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        pdu = _make_non_segmented_pdu(invoke_id=1)
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _ = result
        assert txn.timeout_handle is not None

        old_handle = txn.timeout_handle
        tsm._restart_timeout(txn)
        assert txn.timeout_handle is not None
        assert txn.timeout_handle is not old_handle

    async def test_restart_segment_timeout_cancels_existing(self):
        """_restart_segment_timeout cancels existing handle (branch 888->890)."""
        network = FakeNetworkLayer()
        tsm = ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
            proposed_window_size=2,
        )

        seg0 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_request=b"\x01\x02",
        )
        result = tsm.receive_confirmed_request(seg0, PEER)
        assert result is not None
        txn = result[0]
        assert txn.timeout_handle is not None

        old_handle = txn.timeout_handle
        tsm._restart_segment_timeout(txn)
        assert txn.timeout_handle is not None
        assert txn.timeout_handle is not old_handle
