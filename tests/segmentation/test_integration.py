"""Integration tests for segmentation with TSMs.

Uses FakeNetworkLayer to simulate the wire and exercises the full
segmented send/receive flow through the TSMs.
"""

import asyncio
import contextlib

import pytest

from bac_py.app.tsm import (
    ClientTSM,
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
from bac_py.segmentation.manager import (
    compute_max_segment_payload,
    split_payload,
)
from bac_py.services.errors import BACnetAbortError
from bac_py.types.enums import AbortReason
from tests.helpers import PEER, FakeNetworkLayer


class TestClientSegmentedRequestSending:
    """Tests for client sending segmented confirmed requests."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ClientTSM(
            network,
            apdu_timeout=1.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=0.5,
            proposed_window_size=4,
        )

    async def test_small_request_not_segmented(self, tsm, network):
        """Requests that fit in a single APDU should not be segmented."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01\x02", PEER))
        await asyncio.sleep(0.01)

        # Should have sent exactly one APDU
        assert len(network.sent) == 1
        apdu_bytes = network.sent[0][0]
        pdu = decode_apdu(apdu_bytes)
        assert isinstance(pdu, ConfirmedRequestPDU)
        assert pdu.segmented is False

        # Complete the request
        invoke_id = pdu.invoke_id
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        result = await task
        assert result == b""

    async def test_large_request_segmented(self, tsm, network):
        """Requests exceeding max segment payload should be segmented."""
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        large_data = bytes(max_payload + 100)

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        # Should have sent multiple segments (window of 4)
        assert len(network.sent) >= 2
        first_pdu = decode_apdu(network.sent[0][0])
        assert isinstance(first_pdu, ConfirmedRequestPDU)
        assert first_pdu.segmented is True
        assert first_pdu.more_follows is True
        assert first_pdu.sequence_number == 0

        # Verify all sent segments are segmented ConfirmedRequests
        invoke_id = first_pdu.invoke_id
        for sent_bytes, _, _ in network.sent:
            seg_pdu = decode_apdu(sent_bytes)
            assert isinstance(seg_pdu, ConfirmedRequestPDU)
            assert seg_pdu.segmented is True
            assert seg_pdu.invoke_id == invoke_id

        # ACK the last segment in the window
        last_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(last_pdu, ConfirmedRequestPDU)
        last_seq = last_pdu.sequence_number

        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=last_seq,
            actual_window_size=4,
        )
        tsm.handle_segment_ack(PEER, ack)
        await asyncio.sleep(0.01)

        # Now the remaining segments should be sent (or we await confirmation)
        # Complete with a simple ACK after all segments sent
        tsm.handle_simple_ack(PEER, invoke_id, 12)
        result = await task
        assert result == b""

    async def test_segmented_request_with_full_flow(self, network):
        """Full segmented request flow: send all windows, receive ACKs, get response."""
        tsm = ClientTSM(
            network,
            apdu_timeout=2.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=1.0,
            proposed_window_size=16,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        # Create data requiring exactly 3 segments
        large_data = bytes(range(256)) * ((max_payload * 3) // 256 + 1)
        large_data = large_data[: max_payload * 2 + 10]

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        # All segments should be sent in first window (window >= total_segments)
        assert len(network.sent) >= 2
        invoke_id = decode_apdu(network.sent[0][0]).invoke_id

        # Find the last segment
        last_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(last_pdu, ConfirmedRequestPDU)
        assert last_pdu.more_follows is False  # Last segment

        # ACK the final segment
        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=last_pdu.sequence_number,
            actual_window_size=16,
        )
        tsm.handle_segment_ack(PEER, ack)
        await asyncio.sleep(0.01)

        # Transaction should now be in AWAIT_CONFIRMATION
        # Send a ComplexACK response
        tsm.handle_complex_ack(PEER, invoke_id, 12, b"\xaa\xbb")
        result = await task
        assert result == b"\xaa\xbb"


class TestClientSegmentedResponseReceiving:
    """Tests for client receiving a segmented ComplexACK response."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ClientTSM(
            network,
            apdu_timeout=1.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=0.5,
            proposed_window_size=16,
        )

    async def test_segmented_complex_ack_reassembly(self, tsm, network):
        """Client should reassemble a segmented ComplexACK response."""
        original_data = bytes(range(256)) * 5  # 1280 bytes
        max_payload = compute_max_segment_payload(480, "complex_ack")
        segments = split_payload(original_data, max_payload)

        task = asyncio.create_task(tsm.send_request(12, b"\x01", PEER))
        await asyncio.sleep(0.01)

        apdu_bytes = network.sent[0][0]
        invoke_id = decode_apdu(apdu_bytes).invoke_id

        # Send segmented ComplexACK segments to the client
        for i, seg_data in enumerate(segments):
            more = i < len(segments) - 1
            pdu = ComplexAckPDU(
                segmented=True,
                more_follows=more,
                invoke_id=invoke_id,
                sequence_number=i,
                proposed_window_size=16,
                service_choice=12,
                service_ack=seg_data,
            )
            tsm.handle_segmented_complex_ack(PEER, pdu)
            await asyncio.sleep(0.01)

        result = await task
        assert result == original_data

    async def test_client_sends_segment_acks(self, tsm, network):
        """Client should send SegmentACK PDUs when receiving segmented response."""
        task = asyncio.create_task(tsm.send_request(12, b"\x01", PEER))
        await asyncio.sleep(0.01)

        apdu_bytes = network.sent[0][0]
        invoke_id = decode_apdu(apdu_bytes).invoke_id
        network.clear()

        # Send first segment
        pdu = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=invoke_id,
            sequence_number=0,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\x01\x02\x03",
        )
        tsm.handle_segmented_complex_ack(PEER, pdu)
        await asyncio.sleep(0.01)

        # Client should have sent a SegmentACK
        seg_ack_found = False
        for sent_bytes, _, _ in network.sent:
            decoded = decode_apdu(sent_bytes)
            if isinstance(decoded, SegmentAckPDU):
                assert decoded.invoke_id == invoke_id
                assert decoded.sent_by_server is False
                seg_ack_found = True

        assert seg_ack_found, "Client should send SegmentACK for first segment"

        # Send remaining segments
        pdu2 = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=invoke_id,
            sequence_number=1,
            proposed_window_size=4,
            service_choice=12,
            service_ack=b"\x04\x05\x06",
        )
        tsm.handle_segmented_complex_ack(PEER, pdu2)

        result = await task
        assert result == b"\x01\x02\x03\x04\x05\x06"


class TestServerSegmentedRequestReceiving:
    """Tests for server receiving segmented confirmed requests."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
        )

    async def test_receive_segmented_request_reassembly(self, tsm, network):
        """Server should reassemble a segmented request."""
        original_data = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a"

        # First segment
        pdu1 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=16,
            service_choice=12,
            service_request=original_data[:5],
        )
        result1 = tsm.receive_confirmed_request(pdu1, PEER)
        assert result1 is not None
        _txn, data = result1
        assert data is None  # More segments expected

        # Server should have sent a SegmentACK
        assert len(network.sent) >= 1
        ack_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(ack_pdu, SegmentAckPDU)
        assert ack_pdu.sent_by_server is True

        # Second (final) segment
        pdu2 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=1,
            proposed_window_size=16,
            service_choice=12,
            service_request=original_data[5:],
        )
        result2 = tsm.receive_confirmed_request(pdu2, PEER)
        assert result2 is not None
        _txn2, data2 = result2
        assert data2 == original_data


class TestServerSegmentedResponseSending:
    """Tests for server sending segmented ComplexACK responses."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    @pytest.fixture
    def tsm(self, network):
        return ServerTSM(
            network,
            request_timeout=1.0,
            segment_timeout=0.5,
            max_apdu_length=480,
            proposed_window_size=4,
        )

    async def test_start_segmented_response(self, tsm, network):
        """Server should send segments when response exceeds max APDU."""
        # First, create a transaction via a non-segmented request
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
            service_request=b"\x01",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        network.clear()

        # Generate a large response
        large_response = bytes(range(256)) * 5  # 1280 bytes

        tsm.start_segmented_response(txn, 12, large_response)

        # Should have sent the first window of segments
        assert len(network.sent) >= 1
        first_pdu = decode_apdu(network.sent[0][0])
        assert isinstance(first_pdu, ComplexAckPDU)
        assert first_pdu.segmented is True
        assert first_pdu.more_follows is True
        assert first_pdu.sequence_number == 0
        assert txn.state == ServerTransactionState.SEGMENTED_RESPONSE

    async def test_segmented_response_abort_if_not_accepted(self, tsm, network):
        """Server should abort if client doesn't accept segmentation."""
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=False,  # Client doesn't accept
            max_segments=None,
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
        network.clear()

        large_response = bytes(1000)
        tsm.start_segmented_response(txn, 12, large_response)

        # Should have sent an Abort PDU
        assert len(network.sent) >= 1
        abort_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(abort_pdu, AbortPDU)
        assert abort_pdu.abort_reason == AbortReason.SEGMENTATION_NOT_SUPPORTED
        assert abort_pdu.sent_by_server is True

    async def test_segmented_response_full_flow(self, network):
        """Full segmented response flow: send windows with ACKs until complete."""
        tsm = ServerTSM(
            network,
            request_timeout=2.0,
            segment_timeout=1.0,
            max_apdu_length=480,
            proposed_window_size=4,
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
            service_request=b"\x01",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        txn, _data = result
        network.clear()

        # Generate response requiring multiple windows
        max_payload = compute_max_segment_payload(480, "complex_ack")
        large_response = bytes(max_payload * 6 + 10)

        tsm.start_segmented_response(txn, 12, large_response)

        # First window should be sent (4 segments)
        assert len(network.sent) == 4

        # ACK the last segment in the window
        last_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(last_pdu, ComplexAckPDU)
        network.clear()

        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=1,
            sequence_number=last_pdu.sequence_number,
            actual_window_size=4,
        )
        tsm.handle_segment_ack_for_response(PEER, ack)

        # Next window should be sent
        assert len(network.sent) >= 1

        # Continue ACKing until all segments are sent
        while True:
            last_sent = decode_apdu(network.sent[-1][0])
            if isinstance(last_sent, ComplexAckPDU) and not last_sent.more_follows:
                # Final segment sent, ACK it
                network.clear()
                ack = SegmentAckPDU(
                    negative_ack=False,
                    sent_by_server=False,
                    invoke_id=1,
                    sequence_number=last_sent.sequence_number,
                    actual_window_size=4,
                )
                tsm.handle_segment_ack_for_response(PEER, ack)
                break
            network.clear()
            ack = SegmentAckPDU(
                negative_ack=False,
                sent_by_server=False,
                invoke_id=1,
                sequence_number=last_sent.sequence_number,
                actual_window_size=4,
            )
            tsm.handle_segment_ack_for_response(PEER, ack)

        # Transaction should be complete (IDLE state)
        assert txn.state == ServerTransactionState.IDLE


class TestWindowManagement:
    """Tests for window size negotiation and negative ACKs."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_window_size_negotiation(self, network):
        """Receiver can negotiate window size down."""
        tsm = ClientTSM(
            network,
            apdu_timeout=2.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=1.0,
            proposed_window_size=16,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        large_data = bytes(max_payload * 8 + 10)

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = decode_apdu(network.sent[0][0]).invoke_id

        last_pdu = decode_apdu(network.sent[-1][0])
        assert isinstance(last_pdu, ConfirmedRequestPDU)
        network.clear()

        # Server negotiates window down to 2
        ack = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=last_pdu.sequence_number,
            actual_window_size=2,
        )
        tsm.handle_segment_ack(PEER, ack)
        await asyncio.sleep(0.01)

        # Next window should have at most 2 segments
        assert len(network.sent) <= 2

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_negative_ack_retransmission(self, network):
        """Negative ACK should trigger retransmission."""
        tsm = ClientTSM(
            network,
            apdu_timeout=2.0,
            apdu_retries=3,
            max_apdu_length=480,
            segment_timeout=1.0,
            proposed_window_size=4,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        large_data = bytes(max_payload * 6 + 10)

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        invoke_id = decode_apdu(network.sent[0][0]).invoke_id

        # ACK only the first segment with a negative ACK (request retransmit from seq 1)
        first_pdu = decode_apdu(network.sent[0][0])
        assert isinstance(first_pdu, ConfirmedRequestPDU)
        network.clear()

        ack = SegmentAckPDU(
            negative_ack=True,
            sent_by_server=True,
            invoke_id=invoke_id,
            sequence_number=0,
            actual_window_size=4,
        )
        tsm.handle_segment_ack(PEER, ack)
        await asyncio.sleep(0.01)

        # Should have retransmitted from sequence 1
        assert len(network.sent) >= 1
        retransmitted = decode_apdu(network.sent[0][0])
        assert isinstance(retransmitted, ConfirmedRequestPDU)
        assert retransmitted.sequence_number == 1

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestTimeoutRecovery:
    """Tests for segment timeout handling."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_client_segment_timeout_retransmits(self, network):
        """Client should retransmit segments after segment timeout."""
        tsm = ClientTSM(
            network,
            apdu_timeout=2.0,
            apdu_retries=3,
            max_apdu_length=480,
            segment_timeout=0.05,
            proposed_window_size=4,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        large_data = bytes(max_payload * 3 + 10)

        task = asyncio.create_task(tsm.send_request(12, large_data, PEER))
        await asyncio.sleep(0.01)

        initial_count = len(network.sent)

        # Wait for segment timeout (4 * T_seg = 0.2s for wait_for_seg)
        await asyncio.sleep(0.25)

        # Should have retransmitted
        assert len(network.sent) > initial_count

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_client_segment_timeout_exhaustion_aborts(self, network):
        """Client should abort after exhausting segment retries."""
        tsm = ClientTSM(
            network,
            apdu_timeout=5.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=0.02,
            proposed_window_size=4,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        large_data = bytes(max_payload * 3 + 10)

        with pytest.raises(BACnetAbortError) as exc_info:
            await tsm.send_request(12, large_data, PEER)
        assert exc_info.value.reason == AbortReason.TSM_TIMEOUT

    async def test_server_segment_timeout_sends_negative_ack(self, network):
        """Server should send negative SegmentACK on segment timeout."""
        tsm = ServerTSM(
            network,
            request_timeout=2.0,
            segment_timeout=0.05,
            max_apdu_length=480,
        )

        # Send first segment of a segmented request
        pdu = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=16,
            service_choice=12,
            service_request=b"\x01\x02\x03",
        )
        result = tsm.receive_confirmed_request(pdu, PEER)
        assert result is not None
        network.clear()

        # Wait for segment timeout
        await asyncio.sleep(0.1)

        # Server should have sent a negative SegmentACK
        found_nack = False
        for sent_bytes, _, _ in network.sent:
            decoded = decode_apdu(sent_bytes)
            if isinstance(decoded, SegmentAckPDU) and decoded.negative_ack:
                found_nack = True
                assert decoded.sent_by_server is True

        assert found_nack, "Server should send negative SegmentACK on timeout"


class TestDataIntegrity:
    """Tests verifying end-to-end data integrity through segmentation."""

    @pytest.fixture
    def network(self):
        return FakeNetworkLayer()

    async def test_client_segments_reassembled_correctly(self, network):
        """Verify that segmented request data is correct on the wire."""
        tsm = ClientTSM(
            network,
            apdu_timeout=2.0,
            apdu_retries=1,
            max_apdu_length=480,
            segment_timeout=1.0,
            proposed_window_size=64,
        )
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        original_data = bytes(range(256)) * ((max_payload * 5) // 256 + 1)
        original_data = original_data[: max_payload * 4 + 100]

        task = asyncio.create_task(tsm.send_request(12, original_data, PEER))
        await asyncio.sleep(0.01)

        # Collect all segment data
        reassembled = b""
        for sent_bytes, _, _ in network.sent:
            pdu = decode_apdu(sent_bytes)
            assert isinstance(pdu, ConfirmedRequestPDU)
            reassembled += pdu.service_request

        assert reassembled == original_data

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_server_segments_reassemble_to_original(self, network):
        """Server-side reassembly should produce the original request data."""
        tsm = ServerTSM(
            network,
            request_timeout=2.0,
            segment_timeout=1.0,
            max_apdu_length=480,
        )
        original_data = bytes(range(256)) * 3  # 768 bytes
        segments = split_payload(original_data, 200)

        # Send first segment
        pdu1 = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=0,
            proposed_window_size=16,
            service_choice=12,
            service_request=segments[0],
        )
        result = tsm.receive_confirmed_request(pdu1, PEER)
        assert result is not None

        # Send middle segments
        for i in range(1, len(segments) - 1):
            pdu = ConfirmedRequestPDU(
                segmented=True,
                more_follows=True,
                segmented_response_accepted=True,
                max_segments=None,
                max_apdu_length=480,
                invoke_id=1,
                sequence_number=i,
                proposed_window_size=16,
                service_choice=12,
                service_request=segments[i],
            )
            result = tsm.receive_confirmed_request(pdu, PEER)

        # Send final segment
        pdu_last = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=None,
            max_apdu_length=480,
            invoke_id=1,
            sequence_number=len(segments) - 1,
            proposed_window_size=16,
            service_choice=12,
            service_request=segments[-1],
        )
        result = tsm.receive_confirmed_request(pdu_last, PEER)
        assert result is not None
        _txn, reassembled_data = result
        assert reassembled_data == original_data
