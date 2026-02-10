"""APDU encoding and decoding per ASHRAE 135-2016 Clause 20.1."""

from __future__ import annotations

from dataclasses import dataclass

from bac_py.encoding.primitives import decode_enumerated, encode_application_enumerated
from bac_py.encoding.tags import decode_tag
from bac_py.types.enums import AbortReason, ErrorClass, ErrorCode, PduType, RejectReason

# Max-segments encoding table (Clause 20.1.2.4)
# B'000' = unspecified, B'001' = 2, ... B'110' = 64, B'111' = >64
_MAX_SEGMENTS_ENCODE: dict[int, int] = {
    2: 1,
    4: 2,
    8: 3,
    16: 4,
    32: 5,
    64: 6,
}
_MAX_SEGMENTS_UNSPECIFIED = 0  # B'000'
_MAX_SEGMENTS_OVER_64 = 7  # B'111'

_MAX_SEGMENTS_DECODE: dict[int, int | None] = {
    0: None,  # Unspecified
    1: 2,
    2: 4,
    3: 8,
    4: 16,
    5: 32,
    6: 64,
    7: None,  # Greater than 64 (also treated as unlimited)
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
    """Encode a max-segments value to a 3-bit field per Clause 20.1.2.4.

    :param value: Maximum number of segments (2, 4, 8, 16, 32, 64) or
        ``None`` for unspecified.
    :returns: 3-bit encoded field value (0-7).
    """
    if value is None:
        return _MAX_SEGMENTS_UNSPECIFIED
    return _MAX_SEGMENTS_ENCODE.get(value, _MAX_SEGMENTS_OVER_64)


def _decode_max_segments(value: int) -> int | None:
    """Decode a 3-bit max-segments field per Clause 20.1.2.4.

    :param value: 3-bit field value from the PDU header.
    :returns: Segment count, or ``None`` if unspecified or >64.
    """
    return _MAX_SEGMENTS_DECODE.get(value)


def _encode_max_apdu(value: int) -> int:
    """Encode a max-APDU-length to a 4-bit field per Clause 20.1.2.5.

    :param value: Maximum APDU length in bytes (50, 128, 206, 480, 1024, 1476).
    :returns: 4-bit encoded field value (0-5), defaults to 5 (1476).
    """
    return _MAX_APDU_ENCODE.get(value, 5)


def _decode_max_apdu(value: int) -> int:
    """Decode a 4-bit max-APDU-length field per Clause 20.1.2.5.

    :param value: 4-bit field value from the PDU header.
    :returns: Maximum APDU length in bytes, defaults to 1476.
    """
    return _MAX_APDU_DECODE.get(value, 1476)


# --- PDU Dataclasses ---


@dataclass(frozen=True, slots=True)
class ConfirmedRequestPDU:
    """BACnet Confirmed-Request PDU (Clause 20.1.2)."""

    segmented: bool
    """Whether this PDU is a segment of a larger message."""

    more_follows: bool
    """Whether more segments follow this one."""

    segmented_response_accepted: bool
    """Whether the sender can accept a segmented response."""

    max_segments: int | None
    """Maximum number of segments the sender can accept, or ``None`` for unspecified."""

    max_apdu_length: int
    """Maximum APDU length in bytes the sender can accept."""

    invoke_id: int
    """Invoke ID for matching requests to responses (0-255)."""

    sequence_number: int | None
    """Segment sequence number, or ``None`` if not segmented."""

    proposed_window_size: int | None
    """Proposed window size for segmentation, or ``None`` if not segmented."""

    service_choice: int
    """Confirmed service choice number."""

    service_request: bytes
    """Encoded service request parameters."""


@dataclass(frozen=True, slots=True)
class UnconfirmedRequestPDU:
    """BACnet Unconfirmed-Request PDU (Clause 20.1.3)."""

    service_choice: int
    """Unconfirmed service choice number."""

    service_request: bytes
    """Encoded service request parameters."""


@dataclass(frozen=True, slots=True)
class SimpleAckPDU:
    """BACnet SimpleACK PDU (Clause 20.1.4)."""

    invoke_id: int
    """Invoke ID of the confirmed request being acknowledged."""

    service_choice: int
    """Service choice of the confirmed request being acknowledged."""


@dataclass(frozen=True, slots=True)
class ComplexAckPDU:
    """BACnet ComplexACK PDU (Clause 20.1.5)."""

    segmented: bool
    """Whether this PDU is a segment of a larger response."""

    more_follows: bool
    """Whether more segments follow this one."""

    invoke_id: int
    """Invoke ID of the confirmed request being acknowledged."""

    sequence_number: int | None
    """Segment sequence number, or ``None`` if not segmented."""

    proposed_window_size: int | None
    """Proposed window size for segmentation, or ``None`` if not segmented."""

    service_choice: int
    """Service choice of the confirmed request being acknowledged."""

    service_ack: bytes
    """Encoded service response parameters."""


@dataclass(frozen=True, slots=True)
class SegmentAckPDU:
    """BACnet SegmentACK PDU (Clause 20.1.6)."""

    negative_ack: bool
    """Whether this is a negative acknowledgement (requesting retransmission)."""

    sent_by_server: bool
    """Whether the server (not the client) sent this SegmentACK."""

    invoke_id: int
    """Invoke ID of the segmented transaction."""

    sequence_number: int
    """Sequence number of the last segment received."""

    actual_window_size: int
    """Actual window size the sender can accept."""


@dataclass(frozen=True, slots=True)
class ErrorPDU:
    """BACnet Error PDU (Clause 20.1.7).

    Represents the error response with error-class, error-code, and
    optional trailing error data for extended error types (e.g.
    ChangeList-Error, CreateObject-Error).
    """

    invoke_id: int
    """Invoke ID of the confirmed request that caused the error."""

    service_choice: int
    """Service choice of the confirmed request that caused the error."""

    error_class: ErrorClass
    """Error class categorising the error (e.g. object, property, resource)."""

    error_code: ErrorCode
    """Specific error code within the error class."""

    error_data: bytes = b""
    """Optional trailing bytes for extended error types."""


@dataclass(frozen=True, slots=True)
class RejectPDU:
    """BACnet Reject PDU (Clause 20.1.8)."""

    invoke_id: int
    """Invoke ID of the confirmed request being rejected."""

    reject_reason: RejectReason
    """Reason the request was rejected."""


@dataclass(frozen=True, slots=True)
class AbortPDU:
    """BACnet Abort PDU (Clause 20.1.9)."""

    sent_by_server: bool
    """Whether the server (not the client) initiated the abort."""

    invoke_id: int
    """Invoke ID of the transaction being aborted."""

    abort_reason: AbortReason
    """Reason the transaction was aborted."""


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


# --- Segmentation field helpers ---


def _encode_segmentation_fields(
    buf: bytearray,
    segmented: bool,
    sequence_number: int | None,
    proposed_window_size: int | None,
) -> None:
    """Append segmentation fields to *buf* if the PDU is segmented.

    :param buf: Mutable byte buffer to append to.
    :param segmented: Whether the PDU is segmented.
    :param sequence_number: Segment sequence number.
    :param proposed_window_size: Proposed window size.
    """
    if segmented:
        buf.append(sequence_number if sequence_number is not None else 0)
        buf.append(proposed_window_size if proposed_window_size is not None else 1)


def _decode_segmentation_fields(
    data: memoryview,
    offset: int,
    segmented: bool,
    min_len: int,
    pdu_name: str,
) -> tuple[int | None, int | None, int]:
    """Decode segmentation fields if the PDU is segmented.

    :param data: Buffer containing the raw PDU bytes.
    :param offset: Current position in the buffer.
    :param segmented: Whether the PDU is segmented.
    :param min_len: Minimum buffer length required for segmented PDUs.
    :param pdu_name: PDU type name for error messages.
    :returns: Tuple of (sequence_number, proposed_window_size, new_offset).
    :raises ValueError: If the buffer is too short for segmented fields.
    """
    if not segmented:
        return None, None, offset
    if len(data) < min_len:
        msg = f"Segmented {pdu_name} too short: need at least {min_len} bytes, got {len(data)}"
        raise ValueError(msg)
    return data[offset], data[offset + 1], offset + 2


# --- Encoding ---


def encode_apdu(pdu: APDU) -> bytes:
    """Encode an APDU dataclass to wire-format bytes.

    Dispatches to the appropriate encoder based on the PDU type.

    :param pdu: The PDU dataclass instance to encode.
    :returns: Encoded APDU bytes ready for transmission.
    :raises TypeError: If *pdu* is not a recognised PDU type.
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
        case _:
            msg = f"Unknown PDU type: {type(pdu).__name__}"
            raise TypeError(msg)


def _encode_confirmed_request(pdu: ConfirmedRequestPDU) -> bytes:
    """Encode a :class:`ConfirmedRequestPDU` to bytes per Clause 20.1.2.

    :param pdu: Confirmed request to encode.
    :returns: Encoded PDU bytes.
    """
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
    buf.append(pdu.invoke_id)
    _encode_segmentation_fields(buf, pdu.segmented, pdu.sequence_number, pdu.proposed_window_size)
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_request)
    return bytes(buf)


def _encode_unconfirmed_request(pdu: UnconfirmedRequestPDU) -> bytes:
    """Encode an :class:`UnconfirmedRequestPDU` to bytes per Clause 20.1.3.

    :param pdu: Unconfirmed request to encode.
    :returns: Encoded PDU bytes.
    """
    buf = bytearray()
    buf.append(PduType.UNCONFIRMED_REQUEST << 4)
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_request)
    return bytes(buf)


def _encode_simple_ack(pdu: SimpleAckPDU) -> bytes:
    """Encode a :class:`SimpleAckPDU` to bytes per Clause 20.1.4.

    :param pdu: Simple ACK to encode.
    :returns: Encoded PDU bytes (3 bytes).
    """
    return bytes([PduType.SIMPLE_ACK << 4, pdu.invoke_id, pdu.service_choice])


def _encode_complex_ack(pdu: ComplexAckPDU) -> bytes:
    """Encode a :class:`ComplexAckPDU` to bytes per Clause 20.1.5.

    :param pdu: Complex ACK to encode.
    :returns: Encoded PDU bytes.
    """
    buf = bytearray()
    byte0 = PduType.COMPLEX_ACK << 4
    if pdu.segmented:
        byte0 |= 0x08
    if pdu.more_follows:
        byte0 |= 0x04
    buf.append(byte0)
    buf.append(pdu.invoke_id)
    _encode_segmentation_fields(buf, pdu.segmented, pdu.sequence_number, pdu.proposed_window_size)
    buf.append(pdu.service_choice)
    buf.extend(pdu.service_ack)
    return bytes(buf)


def _encode_segment_ack(pdu: SegmentAckPDU) -> bytes:
    """Encode a :class:`SegmentAckPDU` to bytes per Clause 20.1.6.

    :param pdu: Segment ACK to encode.
    :returns: Encoded PDU bytes (4 bytes).
    """
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
    """Encode an :class:`ErrorPDU` to bytes per Clause 20.1.7.

    :param pdu: Error PDU to encode.
    :returns: Encoded PDU bytes including error class, code, and optional data.
    """
    buf = bytearray()
    buf.append(PduType.ERROR << 4)
    buf.append(pdu.invoke_id)
    buf.append(pdu.service_choice)
    buf.extend(encode_application_enumerated(pdu.error_class))
    buf.extend(encode_application_enumerated(pdu.error_code))
    if pdu.error_data:
        buf.extend(pdu.error_data)
    return bytes(buf)


def _encode_reject(pdu: RejectPDU) -> bytes:
    """Encode a :class:`RejectPDU` to bytes per Clause 20.1.8.

    :param pdu: Reject PDU to encode.
    :returns: Encoded PDU bytes (3 bytes).
    """
    return bytes([PduType.REJECT << 4, pdu.invoke_id, pdu.reject_reason])


def _encode_abort(pdu: AbortPDU) -> bytes:
    """Encode an :class:`AbortPDU` to bytes per Clause 20.1.9.

    :param pdu: Abort PDU to encode.
    :returns: Encoded PDU bytes (3 bytes).
    """
    byte0 = PduType.ABORT << 4
    if pdu.sent_by_server:
        byte0 |= 0x01
    return bytes([byte0, pdu.invoke_id, pdu.abort_reason])


# --- Decoding ---


def decode_apdu(data: memoryview | bytes) -> APDU:
    """Decode an APDU from raw bytes.

    Inspects the PDU type nibble in the first byte and dispatches
    to the appropriate decoder.

    :param data: Raw APDU bytes.
    :returns: Decoded PDU dataclass instance.
    :raises ValueError: If *data* is too short to decode.
    :raises TypeError: If the PDU type is not recognised.
    """
    if len(data) < 1:
        msg = "APDU data too short: need at least 1 byte"
        raise ValueError(msg)

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
        case _:
            msg = f"Unknown PDU type: {pdu_type!r}"
            raise TypeError(msg)


def _decode_confirmed_request(data: memoryview) -> ConfirmedRequestPDU:
    """Decode a :class:`ConfirmedRequestPDU` from raw bytes per Clause 20.1.2.

    :param data: Raw PDU bytes (at least 4 bytes).
    :returns: Decoded :class:`ConfirmedRequestPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 4:
        msg = f"ConfirmedRequest too short: need at least 4 bytes, got {len(data)}"
        raise ValueError(msg)
    byte0 = data[0]
    segmented = bool(byte0 & 0x08)
    more_follows = bool(byte0 & 0x04)
    segmented_response_accepted = bool(byte0 & 0x02)

    byte1 = data[1]
    max_segments = _decode_max_segments((byte1 >> 4) & 0x07)
    max_apdu_length = _decode_max_apdu(byte1 & 0x0F)

    invoke_id = data[2]
    offset = 3

    sequence_number, proposed_window_size, offset = _decode_segmentation_fields(
        data, offset, segmented, 6, "ConfirmedRequest"
    )

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
    """Decode an :class:`UnconfirmedRequestPDU` from raw bytes per Clause 20.1.3.

    :param data: Raw PDU bytes (at least 2 bytes).
    :returns: Decoded :class:`UnconfirmedRequestPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 2:
        msg = f"UnconfirmedRequest too short: need at least 2 bytes, got {len(data)}"
        raise ValueError(msg)
    service_choice = data[1]
    service_request = bytes(data[2:])
    return UnconfirmedRequestPDU(
        service_choice=service_choice,
        service_request=service_request,
    )


def _decode_simple_ack(data: memoryview) -> SimpleAckPDU:
    """Decode a :class:`SimpleAckPDU` from raw bytes per Clause 20.1.4.

    :param data: Raw PDU bytes (at least 3 bytes).
    :returns: Decoded :class:`SimpleAckPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 3:
        msg = f"SimpleACK too short: need at least 3 bytes, got {len(data)}"
        raise ValueError(msg)
    return SimpleAckPDU(invoke_id=data[1], service_choice=data[2])


def _decode_complex_ack(data: memoryview) -> ComplexAckPDU:
    """Decode a :class:`ComplexAckPDU` from raw bytes per Clause 20.1.5.

    :param data: Raw PDU bytes (at least 3 bytes).
    :returns: Decoded :class:`ComplexAckPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 3:
        msg = f"ComplexACK too short: need at least 3 bytes, got {len(data)}"
        raise ValueError(msg)
    byte0 = data[0]
    segmented = bool(byte0 & 0x08)
    more_follows = bool(byte0 & 0x04)

    invoke_id = data[1]
    offset = 2

    sequence_number, proposed_window_size, offset = _decode_segmentation_fields(
        data, offset, segmented, 5, "ComplexACK"
    )

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
    """Decode a :class:`SegmentAckPDU` from raw bytes per Clause 20.1.6.

    :param data: Raw PDU bytes (at least 4 bytes).
    :returns: Decoded :class:`SegmentAckPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 4:
        msg = f"SegmentACK too short: need at least 4 bytes, got {len(data)}"
        raise ValueError(msg)
    byte0 = data[0]
    return SegmentAckPDU(
        negative_ack=bool(byte0 & 0x02),
        sent_by_server=bool(byte0 & 0x01),
        invoke_id=data[1],
        sequence_number=data[2],
        actual_window_size=data[3],
    )


def _decode_error(data: memoryview) -> ErrorPDU:
    """Decode an :class:`ErrorPDU` from raw bytes per Clause 20.1.7.

    Decodes the error class and error code as application-tagged enumerated
    values, and preserves any trailing bytes as extended error data.

    :param data: Raw PDU bytes (at least 5 bytes).
    :returns: Decoded :class:`ErrorPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 5:
        msg = f"ErrorPDU too short: need at least 5 bytes, got {len(data)}"
        raise ValueError(msg)

    invoke_id = data[1]
    service_choice = data[2]

    # Error class and code are application-tagged enumerated values
    offset = 3
    tag, offset = decode_tag(data, offset)
    error_class = ErrorClass(decode_enumerated(data[offset : offset + tag.length]))
    offset += tag.length

    tag, offset = decode_tag(data, offset)
    error_code = ErrorCode(decode_enumerated(data[offset : offset + tag.length]))
    offset += tag.length

    # Preserve any trailing error data (extended error types)
    error_data = bytes(data[offset:]) if offset < len(data) else b""

    return ErrorPDU(
        invoke_id=invoke_id,
        service_choice=service_choice,
        error_class=error_class,
        error_code=error_code,
        error_data=error_data,
    )


def _decode_reject(data: memoryview) -> RejectPDU:
    """Decode a :class:`RejectPDU` from raw bytes per Clause 20.1.8.

    :param data: Raw PDU bytes (at least 3 bytes).
    :returns: Decoded :class:`RejectPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 3:
        msg = f"RejectPDU too short: need at least 3 bytes, got {len(data)}"
        raise ValueError(msg)
    return RejectPDU(
        invoke_id=data[1],
        reject_reason=RejectReason(data[2]),
    )


def _decode_abort(data: memoryview) -> AbortPDU:
    """Decode an :class:`AbortPDU` from raw bytes per Clause 20.1.9.

    :param data: Raw PDU bytes (at least 3 bytes).
    :returns: Decoded :class:`AbortPDU`.
    :raises ValueError: If *data* is too short.
    """
    if len(data) < 3:
        msg = f"AbortPDU too short: need at least 3 bytes, got {len(data)}"
        raise ValueError(msg)
    byte0 = data[0]
    return AbortPDU(
        sent_by_server=bool(byte0 & 0x01),
        invoke_id=data[1],
        abort_reason=AbortReason(data[2]),
    )
