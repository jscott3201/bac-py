from bac_py.encoding.apdu import (
    AbortPDU,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    ErrorPDU,
    RejectPDU,
    SegmentAckPDU,
    SimpleAckPDU,
    UnconfirmedRequestPDU,
    decode_apdu,
    encode_apdu,
)
from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, RejectReason


class TestConfirmedRequestPDU:
    def test_round_trip_non_segmented(self):
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=4,
            max_apdu_length=1476,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_request=b"\x01\x02\x03",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ConfirmedRequestPDU)
        assert decoded.segmented is False
        assert decoded.more_follows is False
        assert decoded.segmented_response_accepted is True
        assert decoded.max_segments == 4
        assert decoded.max_apdu_length == 1476
        assert decoded.invoke_id == 1
        assert decoded.sequence_number is None
        assert decoded.proposed_window_size is None
        assert decoded.service_choice == 12
        assert decoded.service_request == b"\x01\x02\x03"

    def test_round_trip_segmented(self):
        pdu = ConfirmedRequestPDU(
            segmented=True,
            more_follows=True,
            segmented_response_accepted=True,
            max_segments=64,
            max_apdu_length=480,
            invoke_id=55,
            sequence_number=3,
            proposed_window_size=16,
            service_choice=14,
            service_request=b"\xaa\xbb",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ConfirmedRequestPDU)
        assert decoded.segmented is True
        assert decoded.more_follows is True
        assert decoded.segmented_response_accepted is True
        assert decoded.max_segments == 64
        assert decoded.max_apdu_length == 480
        assert decoded.invoke_id == 55
        assert decoded.sequence_number == 3
        assert decoded.proposed_window_size == 16
        assert decoded.service_choice == 14
        assert decoded.service_request == b"\xaa\xbb"

    def test_empty_service_request(self):
        pdu = ConfirmedRequestPDU(
            segmented=False,
            more_follows=False,
            segmented_response_accepted=False,
            max_segments=0,
            max_apdu_length=1476,
            invoke_id=0,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=5,
            service_request=b"",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ConfirmedRequestPDU)
        assert decoded.service_request == b""
        assert decoded.service_choice == 5


class TestUnconfirmedRequestPDU:
    def test_round_trip(self):
        pdu = UnconfirmedRequestPDU(
            service_choice=8,
            service_request=b"\x01\x02",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, UnconfirmedRequestPDU)
        assert decoded.service_choice == 8
        assert decoded.service_request == b"\x01\x02"

    def test_empty_request(self):
        pdu = UnconfirmedRequestPDU(
            service_choice=0,
            service_request=b"",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, UnconfirmedRequestPDU)
        assert decoded.service_choice == 0
        assert decoded.service_request == b""


class TestSimpleAckPDU:
    def test_round_trip(self):
        pdu = SimpleAckPDU(invoke_id=42, service_choice=15)
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, SimpleAckPDU)
        assert decoded.invoke_id == 42
        assert decoded.service_choice == 15

    def test_encoding_length(self):
        pdu = SimpleAckPDU(invoke_id=0, service_choice=0)
        encoded = encode_apdu(pdu)
        assert len(encoded) == 3


class TestComplexAckPDU:
    def test_round_trip_non_segmented(self):
        pdu = ComplexAckPDU(
            segmented=False,
            more_follows=False,
            invoke_id=10,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_ack=b"\xde\xad",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ComplexAckPDU)
        assert decoded.segmented is False
        assert decoded.more_follows is False
        assert decoded.invoke_id == 10
        assert decoded.sequence_number is None
        assert decoded.proposed_window_size is None
        assert decoded.service_choice == 12
        assert decoded.service_ack == b"\xde\xad"

    def test_round_trip_segmented(self):
        pdu = ComplexAckPDU(
            segmented=True,
            more_follows=True,
            invoke_id=99,
            sequence_number=7,
            proposed_window_size=4,
            service_choice=14,
            service_ack=b"\x01\x02\x03\x04",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ComplexAckPDU)
        assert decoded.segmented is True
        assert decoded.more_follows is True
        assert decoded.invoke_id == 99
        assert decoded.sequence_number == 7
        assert decoded.proposed_window_size == 4
        assert decoded.service_choice == 14
        assert decoded.service_ack == b"\x01\x02\x03\x04"

    def test_empty_ack(self):
        pdu = ComplexAckPDU(
            segmented=False,
            more_follows=False,
            invoke_id=1,
            sequence_number=None,
            proposed_window_size=None,
            service_choice=12,
            service_ack=b"",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ComplexAckPDU)
        assert decoded.service_ack == b""


class TestSegmentAckPDU:
    def test_round_trip(self):
        pdu = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=True,
            invoke_id=5,
            sequence_number=12,
            actual_window_size=8,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.negative_ack is False
        assert decoded.sent_by_server is True
        assert decoded.invoke_id == 5
        assert decoded.sequence_number == 12
        assert decoded.actual_window_size == 8

    def test_negative_ack(self):
        pdu = SegmentAckPDU(
            negative_ack=True,
            sent_by_server=False,
            invoke_id=200,
            sequence_number=0,
            actual_window_size=1,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, SegmentAckPDU)
        assert decoded.negative_ack is True
        assert decoded.sent_by_server is False

    def test_encoding_length(self):
        pdu = SegmentAckPDU(
            negative_ack=False,
            sent_by_server=False,
            invoke_id=0,
            sequence_number=0,
            actual_window_size=1,
        )
        encoded = encode_apdu(pdu)
        assert len(encoded) == 4


class TestErrorPDU:
    def test_round_trip(self):
        pdu = ErrorPDU(
            invoke_id=7,
            service_choice=12,
            error_class=ErrorClass.OBJECT,
            error_code=ErrorCode.UNKNOWN_OBJECT,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ErrorPDU)
        assert decoded.invoke_id == 7
        assert decoded.service_choice == 12
        assert decoded.error_class == ErrorClass.OBJECT
        assert decoded.error_code == ErrorCode.UNKNOWN_OBJECT

    def test_device_error(self):
        pdu = ErrorPDU(
            invoke_id=0,
            service_choice=15,
            error_class=ErrorClass.DEVICE,
            error_code=ErrorCode.DEVICE_BUSY,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ErrorPDU)
        assert decoded.error_class == ErrorClass.DEVICE
        assert decoded.error_code == ErrorCode.DEVICE_BUSY

    def test_property_error(self):
        pdu = ErrorPDU(
            invoke_id=100,
            service_choice=12,
            error_class=ErrorClass.PROPERTY,
            error_code=ErrorCode.UNKNOWN_PROPERTY,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ErrorPDU)
        assert decoded.error_class == ErrorClass.PROPERTY
        assert decoded.error_code == ErrorCode.UNKNOWN_PROPERTY


class TestRejectPDU:
    def test_round_trip(self):
        pdu = RejectPDU(
            invoke_id=33,
            reject_reason=RejectReason.INVALID_TAG,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, RejectPDU)
        assert decoded.invoke_id == 33
        assert decoded.reject_reason == RejectReason.INVALID_TAG

    def test_encoding_length(self):
        pdu = RejectPDU(
            invoke_id=0,
            reject_reason=RejectReason.OTHER,
        )
        encoded = encode_apdu(pdu)
        assert len(encoded) == 3

    def test_buffer_overflow(self):
        pdu = RejectPDU(
            invoke_id=255,
            reject_reason=RejectReason.BUFFER_OVERFLOW,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, RejectPDU)
        assert decoded.invoke_id == 255
        assert decoded.reject_reason == RejectReason.BUFFER_OVERFLOW


class TestAbortPDU:
    def test_round_trip_server(self):
        pdu = AbortPDU(
            sent_by_server=True,
            invoke_id=44,
            abort_reason=AbortReason.SEGMENTATION_NOT_SUPPORTED,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, AbortPDU)
        assert decoded.sent_by_server is True
        assert decoded.invoke_id == 44
        assert decoded.abort_reason == AbortReason.SEGMENTATION_NOT_SUPPORTED

    def test_round_trip_non_server(self):
        pdu = AbortPDU(
            sent_by_server=False,
            invoke_id=0,
            abort_reason=AbortReason.OTHER,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, AbortPDU)
        assert decoded.sent_by_server is False
        assert decoded.invoke_id == 0
        assert decoded.abort_reason == AbortReason.OTHER

    def test_encoding_length(self):
        pdu = AbortPDU(
            sent_by_server=False,
            invoke_id=0,
            abort_reason=AbortReason.OTHER,
        )
        encoded = encode_apdu(pdu)
        assert len(encoded) == 3

    def test_buffer_overflow_reason(self):
        pdu = AbortPDU(
            sent_by_server=True,
            invoke_id=128,
            abort_reason=AbortReason.BUFFER_OVERFLOW,
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, AbortPDU)
        assert decoded.abort_reason == AbortReason.BUFFER_OVERFLOW


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestSegmentedTooShort:
    def test_decode_segmented_confirmed_request_too_short(self):
        """Segmented ConfirmedRequest with insufficient bytes raises ValueError."""
        import pytest

        # Build a ConfirmedRequest header with segmented bit set but only 5 bytes
        # (need at least 6 for segmented).
        # Byte 0: PDU type 0 (CONFIRMED_REQUEST) << 4 | 0x08 (segmented)
        byte0 = 0x08  # pdu_type=0, segmented=True
        byte1 = 0x25  # max_segments=2, max_apdu=1476
        invoke_id = 1
        service_choice = 12
        # Only 5 bytes total: byte0, byte1, invoke_id, service_choice, extra
        data = bytes([byte0, byte1, invoke_id, service_choice, 0x00])
        with pytest.raises(ValueError, match="Segmented ConfirmedRequest too short"):
            decode_apdu(data)

    def test_decode_segmented_complex_ack_too_short(self):
        """Segmented ComplexACK with insufficient bytes raises ValueError."""
        import pytest

        # Byte 0: PDU type 3 (COMPLEX_ACK) << 4 | 0x08 (segmented)
        byte0 = (3 << 4) | 0x08  # 0x38
        invoke_id = 5
        # Only 4 bytes: byte0, invoke_id, seq_num, proposed_window - need 5
        data = bytes([byte0, invoke_id, 0x00, 0x01])
        with pytest.raises(ValueError, match="Segmented ComplexACK too short"):
            decode_apdu(data)


class TestErrorPDUTrailingData:
    def test_decode_error_pdu_with_trailing_data(self):
        """ErrorPDU with trailing bytes preserves them in error_data."""
        pdu = ErrorPDU(
            invoke_id=7,
            service_choice=12,
            error_class=ErrorClass.OBJECT,
            error_code=ErrorCode.UNKNOWN_OBJECT,
            error_data=b"\xaa\xbb\xcc",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ErrorPDU)
        assert decoded.error_data == b"\xaa\xbb\xcc"


class TestUnknownPDUType:
    def test_encode_apdu_unknown_type(self):
        """Passing a non-PDU object to encode_apdu raises TypeError."""
        import pytest

        with pytest.raises(TypeError, match="Unknown PDU type"):
            encode_apdu("not a pdu")  # type: ignore[arg-type]

    def test_decode_apdu_empty(self):
        """Passing empty bytes to decode_apdu raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="APDU data too short"):
            decode_apdu(b"")


class TestSegmentedRoundTrips:
    def test_encode_confirmed_request_segmented_round_trip(self):
        """Segmented ConfirmedRequest encodes and decodes with correct fields."""
        pdu = ConfirmedRequestPDU(
            segmented=True,
            more_follows=False,
            segmented_response_accepted=True,
            max_segments=8,
            max_apdu_length=1476,
            invoke_id=42,
            sequence_number=5,
            proposed_window_size=4,
            service_choice=15,
            service_request=b"\x01\x02\x03",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ConfirmedRequestPDU)
        assert decoded.segmented is True
        assert decoded.more_follows is False
        assert decoded.sequence_number == 5
        assert decoded.proposed_window_size == 4
        assert decoded.service_choice == 15
        assert decoded.service_request == b"\x01\x02\x03"

    def test_encode_complex_ack_segmented_round_trip(self):
        """Segmented ComplexACK encodes and decodes with correct fields."""
        pdu = ComplexAckPDU(
            segmented=True,
            more_follows=False,
            invoke_id=77,
            sequence_number=10,
            proposed_window_size=8,
            service_choice=12,
            service_ack=b"\xde\xad\xbe\xef",
        )
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(encoded)
        assert isinstance(decoded, ComplexAckPDU)
        assert decoded.segmented is True
        assert decoded.more_follows is False
        assert decoded.sequence_number == 10
        assert decoded.proposed_window_size == 8
        assert decoded.service_choice == 12
        assert decoded.service_ack == b"\xde\xad\xbe\xef"


# ---------------------------------------------------------------------------
# Coverage: "too short" validation branches and unknown PDU type
# ---------------------------------------------------------------------------


class TestDecodeAPDUTooShortBranches:
    """Cover all 'too short' error branches in each PDU decoder function."""

    def test_decode_apdu_with_memoryview_input(self):
        """Lines 488-491: decode_apdu converts bytes to memoryview."""
        pdu = SimpleAckPDU(invoke_id=1, service_choice=2)
        encoded = encode_apdu(pdu)
        decoded = decode_apdu(memoryview(encoded))
        assert isinstance(decoded, SimpleAckPDU)
        assert decoded.invoke_id == 1

    def test_decode_apdu_unknown_pdu_type(self):
        """Lines 510-512: unknown PDU type raises TypeError.

        Note: PduType is an IntEnum with values 0-7 and no _missing_ handler,
        so PduType(8) raises ValueError before reaching the match/case default.
        """
        import pytest

        # PDU types 8-15 are unused; place type 8 in the high nibble
        data = bytes([0x80, 0x00, 0x00])
        with pytest.raises((TypeError, ValueError)):
            decode_apdu(data)

    def test_decode_apdu_unknown_pdu_type_monkeypatched(self):
        """Unknown PDU type nibble (>7) raises ValueError via tuple lookup."""
        import pytest

        # PDU type 9 in high nibble -> 0x90 (not in _PDU_TYPES lookup)
        data = bytes([0x90, 0x00, 0x00])
        with pytest.raises(ValueError, match="Unknown PDU type"):
            decode_apdu(data)

    def test_confirmed_request_too_short(self):
        """Lines 523-524: ConfirmedRequest with < 4 bytes raises ValueError."""
        import pytest

        # PDU type 0 (CONFIRMED_REQUEST) in high nibble, only 3 bytes total
        data = bytes([0x00, 0x25, 0x01])
        with pytest.raises(ValueError, match="ConfirmedRequest too short"):
            decode_apdu(data)

    def test_unconfirmed_request_too_short(self):
        """Lines 567-568: UnconfirmedRequest with < 2 bytes raises ValueError."""
        import pytest

        # PDU type 1 (UNCONFIRMED_REQUEST) in high nibble, only 1 byte
        data = bytes([0x10])
        with pytest.raises(ValueError, match="UnconfirmedRequest too short"):
            decode_apdu(data)

    def test_simple_ack_too_short(self):
        """Lines 585-586: SimpleACK with < 3 bytes raises ValueError."""
        import pytest

        # PDU type 2 (SIMPLE_ACK) in high nibble, only 2 bytes
        data = bytes([0x20, 0x01])
        with pytest.raises(ValueError, match="SimpleACK too short"):
            decode_apdu(data)

    def test_complex_ack_too_short(self):
        """Lines 598-599: ComplexACK with < 3 bytes raises ValueError."""
        import pytest

        # PDU type 3 (COMPLEX_ACK) in high nibble, only 2 bytes
        data = bytes([0x30, 0x01])
        with pytest.raises(ValueError, match="ComplexACK too short"):
            decode_apdu(data)

    def test_segment_ack_too_short(self):
        """Lines 634-635: SegmentACK with < 4 bytes raises ValueError."""
        import pytest

        # PDU type 4 (SEGMENT_ACK) in high nibble, only 3 bytes
        data = bytes([0x40, 0x01, 0x02])
        with pytest.raises(ValueError, match="SegmentACK too short"):
            decode_apdu(data)

    def test_error_pdu_too_short(self):
        """Lines 657-658: ErrorPDU with < 5 bytes raises ValueError."""
        import pytest

        # PDU type 5 (ERROR) in high nibble, only 4 bytes
        data = bytes([0x50, 0x01, 0x02, 0x03])
        with pytest.raises(ValueError, match="ErrorPDU too short"):
            decode_apdu(data)

    def test_reject_pdu_too_short(self):
        """Lines 693-694: RejectPDU with < 3 bytes raises ValueError."""
        import pytest

        # PDU type 6 (REJECT) in high nibble, only 2 bytes
        data = bytes([0x60, 0x01])
        with pytest.raises(ValueError, match="RejectPDU too short"):
            decode_apdu(data)

    def test_abort_pdu_too_short(self):
        """Lines 709-710: AbortPDU with < 3 bytes raises ValueError."""
        import pytest

        # PDU type 7 (ABORT) in high nibble, only 2 bytes
        data = bytes([0x70, 0x01])
        with pytest.raises(ValueError, match="AbortPDU too short"):
            decode_apdu(data)
