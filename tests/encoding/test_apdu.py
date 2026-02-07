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
