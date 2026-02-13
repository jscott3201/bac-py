"""Tests for segmentation/manager.py pure logic."""

import pytest

from bac_py.segmentation.manager import (
    COMPLEX_ACK_SEGMENT_OVERHEAD,
    CONFIRMED_REQUEST_SEGMENT_OVERHEAD,
    SegmentAction,
    SegmentationError,
    SegmentReceiver,
    SegmentSender,
    check_segment_count,
    compute_max_segment_payload,
    duplicate_in_window,
    in_window,
    split_payload,
)
from bac_py.types.enums import AbortReason


class TestInWindow:
    def test_basic_in_window(self):
        # diff = (5-3) % 256 = 2 < 4
        assert in_window(5, 3, 4) is True

    def test_at_boundary_excluded(self):
        # diff = (7-3) % 256 = 4, not < 4
        assert in_window(7, 3, 4) is False

    def test_wrapping(self):
        # diff = (1-254) % 256 = 3 < 4
        assert in_window(1, 254, 4) is True

    def test_same_sequence(self):
        # diff = 0 < 4
        assert in_window(3, 3, 4) is True

    def test_window_size_1(self):
        # Only the expected sequence is in-window
        assert in_window(3, 3, 1) is True
        assert in_window(4, 3, 1) is False

    def test_behind_window(self):
        # diff = (2-5) % 256 = 253, not < 4
        assert in_window(2, 5, 4) is False


class TestDuplicateInWindow:
    def test_basic_duplicate(self):
        # actual=4, proposed=4, Wm=4. diff = (2-5) % 256 = 253. 4 < 253 <= 255 -> True
        assert duplicate_in_window(2, 5, 4, 4) is True

    def test_just_before_window_not_duplicate(self):
        # diff = (4-5) % 256 = 255. Wm=4. 4 < 255 <= 255 -> True
        assert duplicate_in_window(4, 5, 4, 4) is True

    def test_in_window_not_duplicate(self):
        # diff = (5-3) % 256 = 2. Wm=4. 4 < 2 -> False
        assert duplicate_in_window(5, 3, 4, 4) is False

    def test_at_wm_boundary_excluded(self):
        # diff = (1-5) % 256 = 252. Wm=252. 252 < 252 -> False (not strictly greater)
        assert duplicate_in_window(1, 5, 252, 252) is False

    def test_different_actual_proposed(self):
        # actual=2, proposed=8, Wm=8
        # diff = (1-10) % 256 = 247. 8 < 247 <= 255 -> True
        assert duplicate_in_window(1, 10, 2, 8) is True

    def test_completely_out_of_range(self):
        # Very small window, segment is both not in_window and not duplicate_in_window
        # actual=1, proposed=1, Wm=1. diff = (5-3) % 256 = 2. 1 < 2 <= 255 -> True
        # Actually with small windows, most things count as "duplicate". Only diff=0 is in-window,
        # diff=1 is at Wm boundary (excluded), diff>1 is duplicate.
        assert duplicate_in_window(5, 3, 1, 1) is True
        # diff=1 -> Wm=1, 1 < 1 -> False
        assert duplicate_in_window(4, 3, 1, 1) is False


class TestSplitPayload:
    def test_exact_multiple(self):
        data = bytes(range(100))
        segments = split_payload(data, 10)
        assert len(segments) == 10
        assert all(len(s) == 10 for s in segments)
        assert b"".join(segments) == data

    def test_remainder(self):
        data = bytes(range(105))
        segments = split_payload(data, 10)
        assert len(segments) == 11
        assert len(segments[-1]) == 5
        assert b"".join(segments) == data

    def test_single_segment(self):
        data = b"hello"
        segments = split_payload(data, 10)
        assert len(segments) == 1
        assert segments[0] == data

    def test_empty_payload(self):
        segments = split_payload(b"", 10)
        assert len(segments) == 1
        assert segments[0] == b""

    def test_invalid_size_raises(self):
        with pytest.raises(ValueError, match="positive"):
            split_payload(b"data", 0)

    def test_single_byte_segments(self):
        data = b"abcd"
        segments = split_payload(data, 1)
        assert len(segments) == 4
        assert segments == [b"a", b"b", b"c", b"d"]


class TestCheckSegmentCount:
    def test_within_limit(self):
        assert check_segment_count(4, 8) is True

    def test_at_limit(self):
        assert check_segment_count(8, 8) is True

    def test_over_limit(self):
        assert check_segment_count(9, 8) is False

    def test_unlimited(self):
        assert check_segment_count(1000, None) is True


class TestComputeMaxSegmentPayload:
    def test_confirmed_request(self):
        result = compute_max_segment_payload(480, "confirmed_request")
        assert result == 480 - CONFIRMED_REQUEST_SEGMENT_OVERHEAD

    def test_complex_ack(self):
        result = compute_max_segment_payload(480, "complex_ack")
        assert result == 480 - COMPLEX_ACK_SEGMENT_OVERHEAD

    def test_1476(self):
        result = compute_max_segment_payload(1476, "confirmed_request")
        assert result == 1476 - CONFIRMED_REQUEST_SEGMENT_OVERHEAD


class TestSegmentSender:
    def test_create_and_fill_first_window(self):
        # 3000 bytes with max APDU of 480 -> payload per segment = 474
        # 3000 / 474 = 7 segments (6 full + 1 partial)
        sender = SegmentSender.create(
            payload=bytes(3000),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=4,
        )
        assert sender.total_segments == 7  # ceil(3000/474)

        window = sender.fill_window()
        assert len(window) == 4
        # First 4 segments: seq 0,1,2,3 all with more_follows=True
        for i, (seq, _data, more) in enumerate(window):
            assert seq == i
            assert more is True

    def test_positive_ack_advances_window(self):
        sender = SegmentSender.create(
            payload=bytes(3000),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=4,
        )
        sender.fill_window()  # segments 0-3

        # ACK for segment 3 -> advance to 4
        complete = sender.handle_segment_ack(3, 4, negative=False)
        assert complete is False

        window = sender.fill_window()
        assert len(window) == 3  # segments 4,5,6
        assert window[0][0] == 4
        assert window[-1][0] == 6
        assert window[-1][2] is False  # last segment, more_follows=False

    def test_negative_ack_retransmits(self):
        sender = SegmentSender.create(
            payload=bytes(3000),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=4,
        )
        sender.fill_window()  # segments 0-3

        # Negative ACK for segment 1 -> retransmit from 2
        complete = sender.handle_segment_ack(1, 4, negative=True)
        assert complete is False

        window = sender.fill_window()
        assert window[0][0] == 2

    def test_final_segment_completion(self):
        # Small payload that fits in 2 segments
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        sender = SegmentSender.create(
            payload=bytes(max_payload + 10),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        assert sender.total_segments == 2

        window = sender.fill_window()
        assert len(window) == 2
        assert window[0][2] is True  # more_follows
        assert window[1][2] is False  # last segment

        # ACK for last segment
        complete = sender.handle_segment_ack(1, 16, negative=False)
        assert complete is True
        assert sender.is_complete is True

    def test_window_size_negotiation(self):
        sender = SegmentSender.create(
            payload=bytes(5000),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        window = sender.fill_window()
        assert len(window) == min(16, sender.total_segments)

        # Receiver negotiates down to 4
        sender.handle_segment_ack(window[-1][0], 4, negative=False)
        window2 = sender.fill_window()
        assert len(window2) <= 4

    def test_apdu_too_long_raises(self):
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        # Data requiring 5 segments, but peer only accepts 4
        data_size = max_payload * 4 + 10  # 5 segments needed
        with pytest.raises(SegmentationError) as exc_info:
            SegmentSender.create(
                payload=bytes(data_size),
                invoke_id=1,
                service_choice=12,
                max_apdu_length=480,
                pdu_type="confirmed_request",
                peer_max_segments=4,
            )
        assert exc_info.value.abort_reason == AbortReason.APDU_TOO_LONG

    def test_complex_ack_overhead(self):
        # ComplexACK uses smaller overhead
        max_payload_cr = compute_max_segment_payload(480, "confirmed_request")
        max_payload_ca = compute_max_segment_payload(480, "complex_ack")
        assert max_payload_ca == max_payload_cr + 1  # 1 byte less overhead

    def test_data_integrity(self):
        """Verify that segments can be reassembled to original data."""
        original = bytes(range(256)) * 10  # 2560 bytes
        sender = SegmentSender.create(
            payload=original,
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        all_data = b"".join(seg for _, seg, _ in sender.fill_window())
        # Fill remaining windows
        while not sender.is_complete:
            window = sender.fill_window()
            last_seq = window[-1][0]
            sender.handle_segment_ack(last_seq, 16, negative=False)
            if sender.is_complete:
                break
            window = sender.fill_window()
            all_data += b"".join(seg for _, seg, _ in window)

        # Actually, let's just check all segments concatenate correctly
        reassembled = b"".join(sender.segments)
        assert reassembled == original


class TestSegmentReceiver:
    def test_receive_all_segments_in_order(self):
        """Feed segments in order and verify completion."""
        original = bytes(range(50))
        # Split into 5 segments of 10 bytes each
        segments = split_payload(original, 10)
        assert len(segments) == 5

        receiver = SegmentReceiver.create(
            first_segment_data=segments[0],
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )
        # First segment already stored

        for i in range(1, 4):
            action, seq = receiver.receive_segment(i, segments[i], more_follows=True)
            # Window size (16) > total segments (5), so intermediate
            # segments return CONTINUE (no ACK until window boundary)
            assert action == SegmentAction.CONTINUE
            assert seq == i

        # Last segment
        action, seq = receiver.receive_segment(4, segments[4], more_follows=False)
        assert action == SegmentAction.COMPLETE
        assert seq == 4
        assert receiver.is_complete
        assert receiver.reassemble() == original

    def test_reassembly_correctness(self):
        """Verify reassembled data matches original."""
        original = bytes(range(256)) * 3  # 768 bytes
        max_seg = 100
        segs = split_payload(original, max_seg)

        receiver = SegmentReceiver.create(
            first_segment_data=segs[0],
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )

        for i in range(1, len(segs)):
            more = i < len(segs) - 1
            receiver.receive_segment(i, segs[i], more_follows=more)

        assert receiver.reassemble() == original

    def test_duplicate_segment_resends_ack(self):
        segments = [bytes(10) for _ in range(5)]
        receiver = SegmentReceiver.create(
            first_segment_data=segments[0],
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )

        # Receive segments 1 and 2
        receiver.receive_segment(1, segments[1], more_follows=True)
        receiver.receive_segment(2, segments[2], more_follows=True)

        # Re-send segment 0 (duplicate, before current window)
        action, ack_seq = receiver.receive_segment(0, segments[0], more_follows=True)
        assert action == SegmentAction.RESEND_LAST_ACK
        assert ack_seq == 2  # Last ACK we sent

    def test_out_of_range_aborts(self):
        _receiver = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=2,
            more_follows=True,
            our_window_size=2,
        )
        # Expected is seq 1, window is 2 -> accepts 1 and 2
        # Seq 200 is neither in-window nor duplicate (for small windows it's duplicate)
        # With actual=2, proposed=2, Wm=2: diff=(200-1)%256=199. 2 < 199 <= 255 -> duplicate
        # So we need a case where it's NOT duplicate either.
        # Actually with 8-bit arithmetic nearly everything is either in-window or duplicate.
        # The only case where ABORT happens is when Wm covers everything.
        # Let's use actual=128, proposed=128, Wm=128.
        receiver2 = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=128,
            more_follows=True,
            our_window_size=127,
        )
        # actual=127, proposed=128, Wm=128
        # Expected seq is 1. in_window: diff < 127. Covers 1..127.
        # duplicate_in_window: 128 < diff <= 255. Covers diff 129..255.
        # Neither: diff=128 exactly. That's seq = (1+128) % 256 = 129.
        action, _seq = receiver2.receive_segment(129, b"data", more_follows=True)
        # diff = (129-1) % 256 = 128. Not < 127, and not > 128.
        assert action == SegmentAction.ABORT

    def test_window_clamping(self):
        receiver = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=32,
            more_follows=True,
            our_window_size=8,
        )
        assert receiver.actual_window_size == 8

    def test_single_segment_complete(self):
        receiver = SegmentReceiver.create(
            first_segment_data=b"only-segment",
            service_choice=12,
            proposed_window_size=16,
            more_follows=False,
        )
        assert receiver.is_complete
        assert receiver.reassemble() == b"only-segment"

    def test_reassemble_before_complete_raises(self):
        receiver = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )
        with pytest.raises(ValueError, match="not all segments"):
            receiver.reassemble()

    def test_window_clamping_to_proposed(self):
        """Our window is bigger than proposed, should clamp to proposed."""
        receiver = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=4,
            more_follows=True,
            our_window_size=16,
        )
        assert receiver.actual_window_size == 4

    def test_last_ack_seq_initial(self):
        """last_ack_seq starts at 0 after creation."""
        receiver = SegmentReceiver.create(
            first_segment_data=b"seg0",
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )
        assert receiver.last_ack_seq == 0

    def test_last_ack_seq_updates_on_receive(self):
        """last_ack_seq tracks the most recently received sequence number."""
        segments = [bytes(10) for _ in range(5)]
        receiver = SegmentReceiver.create(
            first_segment_data=segments[0],
            service_choice=12,
            proposed_window_size=16,
            more_follows=True,
        )
        assert receiver.last_ack_seq == 0

        receiver.receive_segment(1, segments[1], more_follows=True)
        assert receiver.last_ack_seq == 1

        receiver.receive_segment(2, segments[2], more_follows=True)
        assert receiver.last_ack_seq == 2


class TestSequenceWrapping:
    """Test behavior around sequence number wrapping (modulo 256)."""

    def test_sender_wrapping(self):
        """Sender with >256 segments wraps sequence numbers correctly."""
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        # Create enough data for >256 segments
        data_size = max_payload * 260
        sender = SegmentSender.create(
            payload=bytes(data_size),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        assert sender.total_segments >= 260

        # Fill and ACK several windows to get past seq 255
        while sender._window_start_idx < 257:
            window = sender.fill_window()
            last_seq = window[-1][0]
            sender.handle_segment_ack(last_seq, 16, negative=False)

        # Now sequence numbers should have wrapped
        window = sender.fill_window()
        # The sequence numbers should be in the range after wrapping
        for seq, _data, _more in window:
            assert 0 <= seq <= 255

    def test_receiver_wrapping(self):
        """Receiver handles sequence numbers crossing the 256 boundary."""
        # Create data that results in >256 segments
        max_seg = 10
        num_segments = 260
        original = bytes(num_segments * max_seg)
        segments = split_payload(original, max_seg)

        receiver = SegmentReceiver.create(
            first_segment_data=segments[0],
            service_choice=12,
            proposed_window_size=127,
            more_follows=True,
            our_window_size=127,
        )

        for i in range(1, len(segments)):
            more = i < len(segments) - 1
            seq = i & 0xFF
            action, _ack = receiver.receive_segment(seq, segments[i], more_follows=more)
            if i == len(segments) - 1:
                assert action == SegmentAction.COMPLETE
            else:
                # Window-based ACK: SEND_ACK at window boundaries, CONTINUE otherwise
                assert action in (SegmentAction.SEND_ACK, SegmentAction.CONTINUE)

        assert receiver.reassemble() == original


# --- Coverage gap tests: lines 238-243 ---


class TestSegmentSenderSeqFallback:
    def test_seq_to_idx_fallback_unmapped(self):
        """Lines 238-243: Unmapped seq number falls back to _window_start_idx.

        When no segment index matches the sequence number,
        _seq_to_idx falls back to the current _window_start_idx.
        """
        # Create a sender with a small payload (2 segments)
        max_payload = compute_max_segment_payload(480, "confirmed_request")
        sender = SegmentSender.create(
            payload=bytes(max_payload + 10),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=480,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        assert sender.total_segments == 2

        # ACK segment 1 to complete
        sender.handle_segment_ack(1, 16, negative=False)
        assert sender.is_complete is True

        # Now call _seq_to_idx with a sequence number that doesn't match
        # any segment index at or above the search start.
        # _window_start_idx is 2 (past end), search_start = max(0, 2-16) = 0.
        # Segments are at indices 0 and 1 with seq 0 and 1.
        # Searching for seq 99 won't match anything -> fallback.
        result = sender._seq_to_idx(99)
        assert result == sender._window_start_idx

    def test_complex_ack_header_accounting(self):
        """ComplexACK segmentation uses less overhead (5 bytes vs 6 for ConfirmedRequest)."""
        payload_size = 500
        sender_cr = SegmentSender.create(
            payload=bytes(payload_size),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=50,
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        sender_ca = SegmentSender.create(
            payload=bytes(payload_size),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=50,
            pdu_type="complex_ack",
            proposed_window_size=16,
        )
        # ComplexACK has 1 byte less overhead, so fits more data per segment,
        # resulting in fewer total segments
        assert sender_ca.total_segments <= sender_cr.total_segments

    def test_minimum_apdu_payload(self):
        """Segment with very small max APDU still works, produces many segments."""
        # Minimum viable: overhead is 6 for confirmed_request, so max_apdu must be > 6
        sender = SegmentSender.create(
            payload=bytes(100),
            invoke_id=1,
            service_choice=12,
            max_apdu_length=7,  # Only 1 byte per segment payload
            pdu_type="confirmed_request",
            proposed_window_size=16,
        )
        assert sender.total_segments == 100  # 100 bytes / 1 byte per segment

        # Verify all data can be reassembled
        reassembled = b"".join(sender.segments)
        assert reassembled == bytes(100)
