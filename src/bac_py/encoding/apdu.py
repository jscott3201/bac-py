"""APDU encoding and decoding per ASHRAE 135-2016 Clause 20.1."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, PduType, RejectReason

# Max-segments encoding table (Clause 20.1.2.4)
_MAX_SEGMENTS_ENCODE: dict[int, int] = {
    0: 0,
    2: 1,
    4: 2,
    8: 3,
    16: 4,
    32: 5,
    64: 6,
}
_MAX_SEGMENTS_UNSPECIFIED = 7

_MAX_SEGMENTS_DECODE: dict[int, int | None] = {
    0: 0,
    1: 2,
    2: 4,
    3: 8,
    4: 16,
    5: 32,
    6: 64,
    7: None,  # Unspecified / greater than 64
}

# Max-APDU-length encoding table (Clause 20.1.2.5)
_MAX_APDU_ENCODE: dict[int, int] = {
    50: 0,
    128: 1,
    206: 2,
    480: 3,
    1024: 4,
    1476: 5,
}

_MAX_APDU_DECODE: dict[int, int] = {
    0: 50,
    1: 128,
    2: 206,
    3: 480,
    4: 1024,
    5: 1476,
}


def _encode_max_segments(value: int | None) -> int:
    """Encode max-segments value to 3-bit field."""
    if value is None:
        return _MAX_SEGMENTS_UNSPECIFIED
    return _MAX_SEGMENTS_ENCODE.get(value, _MAX_SEGMENTS_UNSPECIFIED)


def _decode_max_segments(value: int) -> int | None:
    """Decode 3-bit max-segments field."""
    return _MAX_SEGMENTS_DECODE.get(value)


def _encode_max_apdu(value: int) -> int:
    """Encode max-APDU-length to 4-bit field."""
    return _MAX_APDU_ENCODE.get(value, 5)


def _decode_max_apdu(value: int) -> int:
    """Decode 4-bit max-APDU-length field."""
    return _MAX_APDU_DECODE.get(value, 1476)


# --- PDU Dataclasses ---


@dataclass(frozen=True, slots=True)
class ConfirmedRequestPDU:
    """BACnet Confirmed-Request PDU (Clause 20.1.2)."""

    segmented: bool
    more_follows: bool
    segmented_response_accepted: bool
    max_segments: int | None
    max_apdu_length: int
    invoke_id: int
    sequence_number: int | None
    proposed_window_size: int | None
    service_choice: int
    service_request: bytes


@dataclass(frozen=True, slots=True)
class UnconfirmedRequestPDU:
    """BACnet Unconfirmed-Request PDU (Clause 20.1.3)."""

    service_choice: int
    service_request: bytes


@dataclass(frozen=True, slots=True)
class SimpleAckPDU:
    """BACnet SimpleACK PDU (Clause 20.1.4)."""

    invoke_id: int
    service_choice: int


@dataclass(frozen=True, slots=True)
class ComplexAckPDU:
    """BACnet ComplexACK PDU (Clause 20.1.5)."""

    segmented: bool
    more_follows: bool
    invoke_id: int
    sequence_number: int | None
    proposed_window_size: int | None
    service_choice: int
    service_ack: bytes


@dataclass(frozen=True, slots=True)
class SegmentAckPDU:
    """BACnet SegmentACK PDU (Clause 20.1.6)."""

    negative_ack: bool
    sent_by_server: bool
    invoke_id: int
    sequence_number: int
    actual_window_size: int


@dataclass(frozen=True, slots=True)
class ErrorPDU:
    """BACnet Error PDU (Clause 20.1.7)."""

    invoke_id: int
    service_choice: int
    error_class: ErrorClass
    error_code: ErrorCode


@dataclass(frozen=True, slots=True)
class RejectPDU:
    """BACnet Reject PDU (Clause 20.1.8)."""

    invoke_id: int
    reject_reason: RejectReason


@dataclass(frozen=True, slots=True)
class AbortPDU:
    """BACnet Abort PDU (Clause 20.1.9)."""

    sent_by_server: bool
    invoke_id: int
    abort_reason: AbortReason


# Union of all PDU types
APDU = (
    ConfirmedRequestPDU
    | UnconfirmedRequestPDU
    | SimpleAckPDU
    | ComplexAckPDU
    | SegmentAckPDU
    | ErrorPDU
    | RejectPDU
    | AbortPDU
)


# --- Encoding ---


def encode_apdu(pdu: APDU) -> bytes:
    """Encode an APDU to bytes.

    Args:
        pdu: The PDU dataclass to encode.

    Returns:
        Encoded APDU bytes.
    """
    match pdu:
        case ConfirmedRequestPDU():
            return _encode_confirmed_request(pdu)
        case UnconfirmedRequestPDU():
            return _encode_unconfirmed_request(pdu)
        case SimpleAckPDU():
            return _encode_simple_ack(pdu)
        case ComplexAckPDU():
            return _encode_complex_ack(pdu)
        case SegmentAckPDU():
            return _encode_segment_ack(pdu)
        case ErrorPDU():
            return _encode_error(pdu)
        case RejectPDU():
            return _encode_reject(pdu)
        case AbortPDU():
            return _encode_abort(pdu)


def _encode_confirmed_request(pdu: ConfirmedRequestPDU) -> bytes:
    buf = bytearray()
    # Byte 0: PDU type + flags
    byte0 = PduType.CONFIRMED_REQUEST << 4
    if pdu.segmented:
        byte0 |= 0x08
    if pdu.more_follows:
        byte0 |= 0x04
    if pdu.segmented_response_accepted:
        byte0 |= 0x02
    buf.append(byte0)
    # Byte 1: max-segments + max-APDU-length
    byte1 = (_encode_max_segments(pdu.max_segments) << 4) | _encode_max_apdu(pdu.max_apdu_length)
    buf.append(byte1)
    # Byte 2: invoke-id
    buf.append(pdu.invoke_id)
    # Segmentation fields (if segmented)
    if pdu.segmented:
        buf.append(pdu.sequence_number or 0)
        buf.append(pdu.proposed_window_size or 1)
    # Service choice + data
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_request)
    return bytes(buf)


def _encode_unconfirmed_request(pdu: UnconfirmedRequestPDU) -> bytes:
    buf = bytearray()
    buf.append(PduType.UNCONFIRMED_REQUEST << 4)
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_request)
    return bytes(buf)


def _encode_simple_ack(pdu: SimpleAckPDU) -> bytes:
    return bytes([PduType.SIMPLE_ACK << 4, pdu.invoke_id, pdu.service_choice])


def _encode_complex_ack(pdu: ComplexAckPDU) -> bytes:
    buf = bytearray()
    byte0 = PduType.COMPLEX_ACK << 4
    if pdu.segmented:
        byte0 |= 0x08
    if pdu.more_follows:
        byte0 |= 0x04
    buf.append(byte0)
    buf.append(pdu.invoke_id)
    if pdu.segmented:
        buf.append(pdu.sequence_number or 0)
        buf.append(pdu.proposed_window_size or 1)
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_ack)
    return bytes(buf)


def _encode_segment_ack(pdu: SegmentAckPDU) -> bytes:
    byte0 = PduType.SEGMENT_ACK << 4
    if pdu.negative_ack:
        byte0 |= 0x02
    if pdu.sent_by_server:
        byte0 |= 0x01
    return bytes(
        [
            byte0,
            pdu.invoke_id,
            pdu.sequence_number,
            pdu.actual_window_size,
        ]
    )


def _encode_error(pdu: ErrorPDU) -> bytes:
    from bac_py.encoding.primitives import (
        encode_application_enumerated,
    )

    buf = bytearray()
    buf.append(PduType.ERROR << 4)
    buf.append(pdu.invoke_id)
    buf.append(pdu.service_choice)
    buf.extend(encode_application_enumerated(pdu.error_class))
    buf.extend(encode_application_enumerated(pdu.error_code))
    return bytes(buf)


def _encode_reject(pdu: RejectPDU) -> bytes:
    return bytes([PduType.REJECT << 4, pdu.invoke_id, pdu.reject_reason])


def _encode_abort(pdu: AbortPDU) -> bytes:
    byte0 = PduType.ABORT << 4
    if pdu.sent_by_server:
        byte0 |= 0x01
    return bytes([byte0, pdu.invoke_id, pdu.abort_reason])


# --- Decoding ---


def decode_apdu(data: memoryview | bytes) -> APDU:
    """Decode an APDU from raw bytes.

    Args:
        data: Raw APDU bytes.

    Returns:
        Decoded PDU dataclass.
    """
    if isinstance(data, bytes):
        data = memoryview(data)

    pdu_type = PduType((data[0] >> 4) & 0x0F)

    match pdu_type:
        case PduType.CONFIRMED_REQUEST:
            return _decode_confirmed_request(data)
        case PduType.UNCONFIRMED_REQUEST:
            return _decode_unconfirmed_request(data)
        case PduType.SIMPLE_ACK:
            return _decode_simple_ack(data)
        case PduType.COMPLEX_ACK:
            return _decode_complex_ack(data)
        case PduType.SEGMENT_ACK:
            return _decode_segment_ack(data)
        case PduType.ERROR:
            return _decode_error(data)
        case PduType.REJECT:
            return _decode_reject(data)
        case PduType.ABORT:
            return _decode_abort(data)


def _decode_confirmed_request(data: memoryview) -> ConfirmedRequestPDU:
    byte0 = data[0]
    segmented = bool(byte0 & 0x08)
    more_follows = bool(byte0 & 0x04)
    segmented_response_accepted = bool(byte0 & 0x02)

    byte1 = data[1]
    max_segments = _decode_max_segments((byte1 >> 4) & 0x07)
    max_apdu_length = _decode_max_apdu(byte1 & 0x0F)

    invoke_id = data[2]
    offset = 3

    sequence_number = None
    proposed_window_size = None
    if segmented:
        sequence_number = data[offset]
        offset += 1
        proposed_window_size = data[offset]
        offset += 1

    service_choice = data[offset]
    offset += 1
    service_request = bytes(data[offset:])

    return ConfirmedRequestPDU(
        segmented=segmented,
        more_follows=more_follows,
        segmented_response_accepted=segmented_response_accepted,
        max_segments=max_segments,
        max_apdu_length=max_apdu_length,
        invoke_id=invoke_id,
        sequence_number=sequence_number,
        proposed_window_size=proposed_window_size,
        service_choice=service_choice,
        service_request=service_request,
    )


def _decode_unconfirmed_request(data: memoryview) -> UnconfirmedRequestPDU:
    service_choice = data[1]
    service_request = bytes(data[2:])
    return UnconfirmedRequestPDU(
        service_choice=service_choice,
        service_request=service_request,
    )


def _decode_simple_ack(data: memoryview) -> SimpleAckPDU:
    return SimpleAckPDU(invoke_id=data[1], service_choice=data[2])


def _decode_complex_ack(data: memoryview) -> ComplexAckPDU:
    byte0 = data[0]
    segmented = bool(byte0 & 0x08)
    more_follows = bool(byte0 & 0x04)

    invoke_id = data[1]
    offset = 2

    sequence_number = None
    proposed_window_size = None
    if segmented:
        sequence_number = data[offset]
        offset += 1
        proposed_window_size = data[offset]
        offset += 1

    service_choice = data[offset]
    offset += 1
    service_ack = bytes(data[offset:])

    return ComplexAckPDU(
        segmented=segmented,
        more_follows=more_follows,
        invoke_id=invoke_id,
        sequence_number=sequence_number,
        proposed_window_size=proposed_window_size,
        service_choice=service_choice,
        service_ack=service_ack,
    )


def _decode_segment_ack(data: memoryview) -> SegmentAckPDU:
    byte0 = data[0]
    return SegmentAckPDU(
        negative_ack=bool(byte0 & 0x02),
        sent_by_server=bool(byte0 & 0x01),
        invoke_id=data[1],
        sequence_number=data[2],
        actual_window_size=data[3],
    )


def _decode_error(data: memoryview) -> ErrorPDU:
    from bac_py.encoding.primitives import decode_enumerated
    from bac_py.encoding.tags import decode_tag

    invoke_id = data[1]
    service_choice = data[2]

    # Error class and code are application-tagged enumerated values
    offset = 3
    tag, offset = decode_tag(data, offset)
    error_class = ErrorClass(decode_enumerated(data[offset : offset + tag.length]))
    offset += tag.length

    tag, offset = decode_tag(data, offset)
    error_code = ErrorCode(decode_enumerated(data[offset : offset + tag.length]))

    return ErrorPDU(
        invoke_id=invoke_id,
        service_choice=service_choice,
        error_class=error_class,
        error_code=error_code,
    )


def _decode_reject(data: memoryview) -> RejectPDU:
    return RejectPDU(
        invoke_id=data[1],
        reject_reason=RejectReason(data[2]),
    )


def _decode_abort(data: memoryview) -> AbortPDU:
    byte0 = data[0]
    return AbortPDU(
        sent_by_server=bool(byte0 & 0x01),
        invoke_id=data[1],
        abort_reason=AbortReason(data[2]),
    )
