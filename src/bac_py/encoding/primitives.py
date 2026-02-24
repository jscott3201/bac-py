"""BACnet primitive type encoding/decoding per ASHRAE 135-2016 Clause 20.2."""

from __future__ import annotations

import enum
import logging
import struct

from bac_py.encoding.tags import TagClass, encode_closing_tag, encode_opening_tag, encode_tag
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import (
    BACnetDate,
    BACnetDouble,
    BACnetTime,
    BitString,
    ObjectIdentifier,
)

logger = logging.getLogger(__name__)

# Application tag numbers for primitive types
_TAG_NULL = 0
_TAG_BOOLEAN = 1
_TAG_UNSIGNED = 2
_TAG_SIGNED = 3
_TAG_REAL = 4
_TAG_DOUBLE = 5
_TAG_OCTET_STRING = 6
_TAG_CHARACTER_STRING = 7
_TAG_BIT_STRING = 8
_TAG_ENUMERATED = 9
_TAG_DATE = 10
_TAG_TIME = 11
_TAG_OBJECT_IDENTIFIER = 12

# Charset decoders for CharacterString (Clause 20.2.9)
_CHARSET_DECODERS: dict[int, str] = {
    0x00: "utf-8",
    0x01: "iso2022_jp",  # JIS X0201 (Clause 20.2.9)
    0x02: "iso2022_jp",
    0x03: "utf-32-be",
    0x04: "utf-16-be",
    0x05: "iso-8859-1",
}


# --- Unsigned Integer (Clause 20.2.4) ---

# Pre-computed single-byte unsigned encodings for values 0-255.
_UNSIGNED_1BYTE: tuple[bytes, ...] = tuple(bytes([i]) for i in range(256))


def encode_unsigned(value: int) -> bytes:
    """Encode an unsigned integer using the minimum number of octets, big-endian.

    BACnet unsigned integers are at most 4 bytes (0..4,294,967,295).

    :param value: Non-negative integer to encode (0--4,294,967,295).
    :returns: Big-endian encoded bytes (1--4 bytes).
    :raises ValueError: If *value* is negative or exceeds the 4-byte maximum.
    """
    if value < 0:
        msg = f"Unsigned integer must be >= 0, got {value}"
        raise ValueError(msg)
    if value <= 0xFF:
        return _UNSIGNED_1BYTE[value]
    if value > 0xFFFFFFFF:
        msg = f"Unsigned integer exceeds 4-byte maximum (4294967295), got {value}"
        raise ValueError(msg)
    n = (value.bit_length() + 7) // 8
    return value.to_bytes(n, "big")


def decode_unsigned(data: memoryview | bytes) -> int:
    """Decode an unsigned integer from big-endian bytes.

    :param data: One or more bytes encoding a big-endian unsigned integer.
    :returns: The decoded non-negative integer.
    """
    return int.from_bytes(data, "big")


# --- Unsigned64 Integer (Clause 20.2.4, extended for Unsigned64 fields) ---


def encode_unsigned64(value: int) -> bytes:
    """Encode an unsigned integer using the minimum number of octets, up to 8 bytes.

    Used for BACnet Unsigned64 fields such as audit log sequence numbers.

    :param value: Non-negative integer to encode (0--18,446,744,073,709,551,615).
    :returns: Big-endian encoded bytes (1--8 bytes).
    :raises ValueError: If *value* is negative or exceeds the 8-byte maximum.
    """
    if value < 0:
        msg = f"Unsigned64 integer must be >= 0, got {value}"
        raise ValueError(msg)
    if value <= 0xFF:
        return _UNSIGNED_1BYTE[value]
    if value > 0xFFFFFFFFFFFFFFFF:
        msg = f"Unsigned64 integer exceeds 8-byte maximum, got {value}"
        raise ValueError(msg)
    n = (value.bit_length() + 7) // 8
    return value.to_bytes(n, "big")


def decode_unsigned64(data: memoryview | bytes) -> int:
    """Decode an unsigned integer from big-endian bytes (up to 8 bytes).

    :param data: One or more bytes encoding a big-endian unsigned integer.
    :returns: The decoded non-negative integer.
    """
    return int.from_bytes(data, "big")


# --- Signed Integer (Clause 20.2.5) ---


def _min_signed_bytes(value: int) -> int:
    """Return the minimum number of bytes needed to encode a signed integer.

    Per Clause 20.2.5, signed integers shall use the minimum number
    of octets in two's-complement representation.

    :param value: Signed integer to measure.
    :returns: Byte count (1--4) required for two's-complement big-endian encoding.
    """
    if value == 0:
        return 1
    if value > 0:
        return (value.bit_length() + 8) // 8  # +1 for sign bit, rounded up
    # For negative values: (-value - 1) gives the magnitude that must
    # be representable.  E.g. -128 -> 127 -> 7 bits -> (7+8)//8 = 1 byte.
    return ((-value - 1).bit_length() + 8) // 8


def encode_signed(value: int) -> bytes:
    """Encode a signed integer using minimum octets, two's complement, big-endian.

    BACnet signed integers are at most 4 bytes (-2,147,483,648..2,147,483,647).

    :param value: Signed integer to encode (-2,147,483,648..2,147,483,647).
    :returns: Two's-complement big-endian encoded bytes (1--4 bytes).
    :raises ValueError: If *value* is outside the 4-byte signed range.
    """
    if value < -0x80000000 or value > 0x7FFFFFFF:
        msg = f"Signed integer out of 4-byte range (-2147483648..2147483647), got {value}"
        raise ValueError(msg)
    n = _min_signed_bytes(value)
    return value.to_bytes(n, "big", signed=True)


def decode_signed(data: memoryview | bytes) -> int:
    """Decode a signed integer from two's-complement big-endian bytes.

    :param data: One or more bytes encoding a two's-complement big-endian signed integer.
    :returns: The decoded signed integer.
    """
    return int.from_bytes(data, "big", signed=True)


# --- Real (Clause 20.2.6) ---


def encode_real(value: float) -> bytes:
    """Encode an IEEE-754 single-precision (32-bit) float.

    :param value: Floating-point value to encode.
    :returns: 4 bytes in big-endian IEEE-754 single-precision format.
    """
    return struct.pack(">f", value)


def decode_real(data: memoryview | bytes) -> float:
    """Decode an IEEE-754 single-precision (32-bit) float.

    :param data: At least 4 bytes of big-endian IEEE-754 single-precision data.
    :returns: The decoded floating-point value.
    :raises ValueError: If *data* contains fewer than 4 bytes.
    """
    if len(data) < 4:
        msg = f"decode_real requires at least 4 bytes, got {len(data)}"
        raise ValueError(msg)
    result: float = struct.unpack_from(">f", data)[0]
    return result


# --- Double (Clause 20.2.7) ---


def encode_double(value: float) -> bytes:
    """Encode an IEEE-754 double-precision (64-bit) float.

    :param value: Floating-point value to encode.
    :returns: 8 bytes in big-endian IEEE-754 double-precision format.
    """
    return struct.pack(">d", value)


def decode_double(data: memoryview | bytes) -> float:
    """Decode an IEEE-754 double-precision (64-bit) float.

    :param data: At least 8 bytes of big-endian IEEE-754 double-precision data.
    :returns: The decoded floating-point value.
    :raises ValueError: If *data* contains fewer than 8 bytes.
    """
    if len(data) < 8:
        msg = f"decode_double requires at least 8 bytes, got {len(data)}"
        raise ValueError(msg)
    result: float = struct.unpack_from(">d", data)[0]
    return result


# --- Octet String (Clause 20.2.8) ---


def decode_octet_string(data: memoryview | bytes) -> bytes:
    """Decode an octet string by copying the raw bytes.

    :param data: Raw octet-string content bytes.
    :returns: A copy of the input as a ``bytes`` object.
    """
    return bytes(data)


# --- Character String (Clause 20.2.9) ---


def encode_character_string(value: str, charset: int = 0) -> bytes:
    """Encode a character string with a leading charset byte.

    :param value: The string to encode.
    :param charset: Character set identifier (default ``0x00`` = UTF-8).
    :returns: Encoded bytes with leading charset byte.
    :raises ValueError: If *charset* is not a supported BACnet character set.
    """
    encoding = _CHARSET_DECODERS.get(charset)
    if encoding is None:
        msg = f"Unsupported BACnet character set: 0x{charset:02x}"
        raise ValueError(msg)
    encoded = value.encode(encoding)
    buf = bytearray(1 + len(encoded))
    buf[0] = charset
    buf[1:] = encoded
    return bytes(buf)


def decode_character_string(data: memoryview | bytes) -> str:
    """Decode a character string from contents octets.

    The first byte is the character set identifier. Unknown charsets
    fall back to latin-1 decoding with a warning log rather than
    raising, to preserve data from devices using non-standard charsets.

    :param data: Contents octets with leading charset byte.
    :returns: The decoded Python string.
    :raises ValueError: If *data* is empty.
    """
    if len(data) < 1:
        msg = "CharacterString data too short: need at least 1 byte for charset"
        raise ValueError(msg)
    charset = data[0]
    encoding = _CHARSET_DECODERS.get(charset)
    if encoding is None:
        logger.warning(
            "Unknown BACnet character set 0x%02x; falling back to latin-1",
            charset,
        )
        encoding = "iso-8859-1"
    return (
        data[1:].tobytes().decode(encoding)
        if isinstance(data, memoryview)
        else data[1:].decode(encoding)
    )


# --- Enumerated (Clause 20.2.11) ---


def encode_enumerated(value: int) -> bytes:
    """Encode an enumerated value (same encoding as unsigned).

    :param value: Enumerated value to encode.
    :returns: Big-endian encoded bytes.
    """
    return encode_unsigned(value)


def decode_enumerated(data: memoryview | bytes) -> int:
    """Decode an enumerated value (same encoding as unsigned).

    :param data: Big-endian encoded bytes.
    :returns: The decoded enumerated value as an integer.
    """
    return decode_unsigned(data)


# --- Bit String (Clause 20.2.10) ---


def encode_bit_string(value: BitString) -> bytes:
    """Encode a bit string with a leading unused-bits count byte.

    :param value: The :class:`BitString` to encode.
    :returns: Encoded bytes with leading unused-bits count followed by the bit data.
    """
    buf = bytearray(1 + len(value.data))
    buf[0] = value.unused_bits
    buf[1:] = value.data
    return bytes(buf)


def decode_bit_string(data: memoryview | bytes) -> BitString:
    """Decode a bit string from contents octets.

    :param data: Contents octets with leading unused-bits count byte.
    :returns: The decoded :class:`BitString`.
    :raises ValueError: If *data* is empty.
    """
    if len(data) < 1:
        msg = "BitString data too short: need at least 1 byte for unused-bits count"
        raise ValueError(msg)
    unused_bits = data[0]
    if unused_bits > 7:
        msg = f"BitString unused_bits must be 0-7, got {unused_bits}"
        raise ValueError(msg)
    return BitString(bytes(data[1:]), unused_bits)


# --- Date (Clause 20.2.12) ---


def encode_date(date: BACnetDate) -> bytes:
    """Encode a :class:`BACnetDate` to 4 bytes: year-1900, month, day, day-of-week.

    Valid years are 1900--2155 or ``0xFF`` (unspecified).

    :param date: The :class:`BACnetDate` to encode.
    :returns: 4 bytes representing the encoded date.
    :raises ValueError: If the year is outside the valid range.
    """
    if date.year == 0xFF:
        year_byte = 0xFF
    elif not 1900 <= date.year <= 2155:
        msg = f"BACnetDate year must be 1900-2155 or 0xFF (unspecified), got {date.year}"
        raise ValueError(msg)
    else:
        year_byte = date.year - 1900
    return bytes([year_byte, date.month, date.day, date.day_of_week])


def decode_date(data: memoryview | bytes) -> BACnetDate:
    """Decode a :class:`BACnetDate` from 4 bytes.

    :param data: At least 4 bytes of encoded date data.
    :returns: The decoded :class:`BACnetDate`.
    :raises ValueError: If *data* contains fewer than 4 bytes.
    """
    if len(data) < 4:
        msg = f"Date data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    year = 0xFF if data[0] == 0xFF else data[0] + 1900
    return BACnetDate(year, data[1], data[2], data[3])


# --- Time (Clause 20.2.13) ---


def encode_time(time: BACnetTime) -> bytes:
    """Encode a :class:`BACnetTime` to 4 bytes: hour, minute, second, hundredth.

    :param time: The :class:`BACnetTime` to encode.
    :returns: 4 bytes representing the encoded time.
    """
    return bytes([time.hour, time.minute, time.second, time.hundredth])


def decode_time(data: memoryview | bytes) -> BACnetTime:
    """Decode a :class:`BACnetTime` from 4 bytes.

    :param data: At least 4 bytes of encoded time data.
    :returns: The decoded :class:`BACnetTime`.
    :raises ValueError: If *data* contains fewer than 4 bytes.
    """
    if len(data) < 4:
        msg = f"Time data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    return BACnetTime(data[0], data[1], data[2], data[3])


# --- Object Identifier (Clause 20.2.14) ---


def encode_object_identifier(obj_type: int, instance: int) -> bytes:
    """Encode a BACnet object identifier to 4 bytes.

    Object type is a 10-bit field (0--1023). Instance is a 22-bit field
    (0--4,194,303). Delegates to :class:`ObjectIdentifier` for encoding.

    :param obj_type: Object type number (0--1023).
    :param instance: Instance number (0--4,194,303).
    :returns: 4 bytes encoding the object identifier.
    """
    return ObjectIdentifier(ObjectType(obj_type), instance).encode()


def decode_object_identifier(data: memoryview | bytes) -> tuple[int, int]:
    """Decode a BACnet object identifier from 4 bytes.

    :param data: At least 4 bytes of encoded object identifier data.
    :returns: Tuple of ``(object_type, instance_number)``.
    :raises ValueError: If *data* contains fewer than 4 bytes.
    """
    if len(data) < 4:
        msg = f"ObjectIdentifier data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    value = int.from_bytes(data[:4], "big")
    return (value >> 22, value & 0x3FFFFF)


# --- Null (Clause 20.2.2) ---


# --- Boolean (Clause 20.2.3) ---
# Note: Application-tagged booleans encode the value in the tag's L/V/T bits
# (no contents octet). Context-tagged booleans use 1 contents octet.
# The tag encoding handles this; these functions handle the contents octet form.


_BOOL_TRUE = b"\x01"
_BOOL_FALSE = b"\x00"


def encode_boolean(value: bool) -> bytes:
    """Encode a boolean value as a single contents octet.

    For context-tagged booleans. Application-tagged booleans encode the
    value in the tag itself.

    :param value: The boolean value to encode.
    :returns: A single byte (``0x01`` for ``True``, ``0x00`` for ``False``).
    """
    return _BOOL_TRUE if value else _BOOL_FALSE


def decode_boolean(data: memoryview | bytes) -> bool:
    """Decode a boolean value from a single contents octet.

    :param data: At least 1 byte; the first byte is interpreted as the boolean value.
    :returns: ``True`` if the first byte is non-zero, ``False`` otherwise.
    :raises ValueError: If *data* is empty.
    """
    if len(data) < 1:
        msg = f"decode_boolean requires at least 1 byte, got {len(data)}"
        raise ValueError(msg)
    return bool(data[0])


# --- Application-Tagged Convenience Functions ---


def encode_application_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with an application tag.

    :param tag_number: Application tag number identifying the data type.
    :param data: Encoded content bytes to wrap with the tag.
    :returns: Application-tagged encoded bytes.
    """
    return encode_tag(tag_number, TagClass.APPLICATION, len(data)) + data


def encode_context_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with a context-specific tag.

    :param tag_number: Context tag number.
    :param data: Encoded content bytes to wrap with the tag.
    :returns: Context-tagged encoded bytes.
    """
    return encode_tag(tag_number, TagClass.CONTEXT, len(data)) + data


def encode_application_null() -> bytes:
    """Encode an application-tagged Null.

    :returns: Application-tagged Null encoding (tag only, no content).
    """
    return encode_application_tagged(_TAG_NULL, b"")


def encode_application_boolean(value: bool) -> bytes:
    """Encode an application-tagged Boolean.

    Per Clause 20.2.3, the value is encoded in the L/V/T bits of the tag
    with no contents octet.

    :param value: The boolean value to encode.
    :returns: Application-tagged Boolean encoding.
    """
    return encode_tag(_TAG_BOOLEAN, TagClass.APPLICATION, 1 if value else 0)


def encode_application_unsigned(value: int) -> bytes:
    """Encode an application-tagged Unsigned Integer.

    :param value: Non-negative integer to encode.
    :returns: Application-tagged Unsigned Integer encoding.
    """
    data = encode_unsigned(value)
    return encode_application_tagged(_TAG_UNSIGNED, data)


def encode_application_signed(value: int) -> bytes:
    """Encode an application-tagged Signed Integer.

    :param value: Signed integer to encode.
    :returns: Application-tagged Signed Integer encoding.
    """
    data = encode_signed(value)
    return encode_application_tagged(_TAG_SIGNED, data)


def encode_application_real(value: float) -> bytes:
    """Encode an application-tagged Real.

    :param value: Floating-point value to encode.
    :returns: Application-tagged Real encoding.
    """
    data = encode_real(value)
    return encode_application_tagged(_TAG_REAL, data)


def encode_application_double(value: float) -> bytes:
    """Encode an application-tagged Double.

    :param value: Floating-point value to encode.
    :returns: Application-tagged Double encoding.
    """
    data = encode_double(value)
    return encode_application_tagged(_TAG_DOUBLE, data)


def encode_application_octet_string(value: bytes) -> bytes:
    """Encode an application-tagged Octet String.

    :param value: Raw bytes to encode.
    :returns: Application-tagged Octet String encoding.
    """
    return encode_application_tagged(_TAG_OCTET_STRING, value)


def encode_application_character_string(value: str) -> bytes:
    """Encode an application-tagged Character String.

    :param value: String to encode (UTF-8 by default).
    :returns: Application-tagged Character String encoding.
    """
    data = encode_character_string(value)
    return encode_application_tagged(_TAG_CHARACTER_STRING, data)


def encode_application_enumerated(value: int) -> bytes:
    """Encode an application-tagged Enumerated.

    :param value: Enumerated value to encode.
    :returns: Application-tagged Enumerated encoding.
    """
    data = encode_enumerated(value)
    return encode_application_tagged(_TAG_ENUMERATED, data)


def encode_application_date(date: BACnetDate) -> bytes:
    """Encode an application-tagged Date.

    :param date: The :class:`BACnetDate` to encode.
    :returns: Application-tagged Date encoding.
    """
    data = encode_date(date)
    return encode_application_tagged(_TAG_DATE, data)


def encode_application_time(time: BACnetTime) -> bytes:
    """Encode an application-tagged Time.

    :param time: The :class:`BACnetTime` to encode.
    :returns: Application-tagged Time encoding.
    """
    data = encode_time(time)
    return encode_application_tagged(_TAG_TIME, data)


def encode_application_object_id(obj_type: int, instance: int) -> bytes:
    """Encode an application-tagged Object Identifier.

    :param obj_type: Object type number.
    :param instance: Instance number.
    :returns: Application-tagged Object Identifier encoding.
    """
    data = encode_object_identifier(obj_type, instance)
    return encode_application_tagged(_TAG_OBJECT_IDENTIFIER, data)


def encode_context_object_id(tag_number: int, obj_id: ObjectIdentifier) -> bytes:
    """Encode an :class:`ObjectIdentifier` with a context-specific tag.

    :param tag_number: Context tag number.
    :param obj_id: The :class:`ObjectIdentifier` to encode.
    :returns: Context-tagged Object Identifier encoding.
    """
    return encode_context_tagged(tag_number, obj_id.encode())


def encode_context_unsigned(tag_number: int, value: int) -> bytes:
    """Encode an unsigned integer with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: Non-negative integer to encode.
    :returns: Context-tagged unsigned integer encoding.
    """
    return encode_context_tagged(tag_number, encode_unsigned(value))


def encode_context_signed(tag_number: int, value: int) -> bytes:
    """Encode a signed integer with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: Signed integer to encode.
    :returns: Context-tagged signed integer encoding.
    """
    return encode_context_tagged(tag_number, encode_signed(value))


def encode_context_enumerated(tag_number: int, value: int) -> bytes:
    """Encode an enumerated value with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: Enumerated value to encode.
    :returns: Context-tagged enumerated encoding.
    """
    return encode_context_tagged(tag_number, encode_enumerated(value))


def encode_context_boolean(tag_number: int, value: bool) -> bytes:
    """Encode a boolean with a context-specific tag.

    Context-tagged booleans use a 1-byte contents octet, unlike
    application-tagged booleans which encode the value in the tag LVT.

    :param tag_number: Context tag number.
    :param value: The boolean value to encode.
    :returns: Context-tagged boolean encoding.
    """
    return encode_context_tagged(tag_number, encode_boolean(value))


def encode_context_real(tag_number: int, value: float) -> bytes:
    """Encode a Real with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: Floating-point value to encode.
    :returns: Context-tagged Real encoding.
    """
    return encode_context_tagged(tag_number, encode_real(value))


def encode_context_octet_string(tag_number: int, value: bytes) -> bytes:
    """Encode an octet string with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: Raw bytes to encode.
    :returns: Context-tagged octet string encoding.
    """
    return encode_context_tagged(tag_number, value)


def encode_context_bit_string(tag_number: int, value: BitString) -> bytes:
    """Encode a bit string with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: The :class:`BitString` to encode.
    :returns: Context-tagged bit string encoding.
    """
    return encode_context_tagged(tag_number, encode_bit_string(value))


def encode_context_date(tag_number: int, value: BACnetDate) -> bytes:
    """Encode a date with a context-specific tag.

    :param tag_number: Context tag number.
    :param value: The :class:`BACnetDate` to encode.
    :returns: Context-tagged date encoding.
    """
    return encode_context_tagged(tag_number, encode_date(value))


def encode_application_bit_string(value: BitString) -> bytes:
    """Encode an application-tagged Bit String.

    :param value: The :class:`BitString` to encode.
    :returns: Application-tagged Bit String encoding.
    """
    data = encode_bit_string(value)
    return encode_application_tagged(_TAG_BIT_STRING, data)


def decode_application_value(data: bytes | memoryview) -> object:
    """Decode application-tagged bytes to a native Python value.

    Inspects the application tag number and dispatches to the
    appropriate decoder. Returns native Python types:

        Tag 0  (Null)             -> ``None``
        Tag 1  (Boolean)          -> ``bool``
        Tag 2  (Unsigned)         -> ``int``
        Tag 3  (Signed)           -> ``int``
        Tag 4  (Real)             -> ``float``
        Tag 5  (Double)           -> ``float``
        Tag 6  (Octet String)     -> ``bytes``
        Tag 7  (Character String) -> ``str``
        Tag 8  (Bit String)       -> :class:`BitString`
        Tag 9  (Enumerated)       -> ``int``
        Tag 10 (Date)             -> :class:`BACnetDate`
        Tag 11 (Time)             -> :class:`BACnetTime`
        Tag 12 (Object Id)        -> :class:`ObjectIdentifier`

    :param data: Application-tagged encoded bytes.
    :returns: Decoded Python value.
    :raises ValueError: If the tag is not application-class or is unrecognised.

    Example::

        from bac_py.encoding.primitives import (
            decode_application_value,
            encode_application_real,
        )

        encoded = encode_application_real(72.5)
        value = decode_application_value(encoded)  # -> 72.5
    """
    from bac_py.encoding.tags import decode_tag

    tag, offset = decode_tag(data, 0)
    if tag.cls != TagClass.APPLICATION:
        msg = f"Expected application tag, got context tag {tag.number}"
        raise ValueError(msg)

    match tag.number:
        case 0:  # Null
            return None
        case 1:  # Boolean - value is in the tag L/V/T field (Clause 20.2.3)
            return tag.is_boolean_true

    # Bounds check (after Boolean/Null which don't use content bytes)
    if offset + tag.length > len(data):
        msg = (
            f"Application tag content truncated: tag claims {tag.length} bytes "
            f"at offset {offset}, but only {len(data) - offset} bytes remain"
        )
        logger.warning(msg)
        raise ValueError(msg)
    content = data[offset : offset + tag.length]

    match tag.number:
        case 2:  # Unsigned
            return decode_unsigned(content)
        case 3:  # Signed
            return decode_signed(content)
        case 4:  # Real
            return decode_real(content)
        case 5:  # Double
            return decode_double(content)
        case 6:  # Octet String
            return decode_octet_string(content)
        case 7:  # Character String
            return decode_character_string(content)
        case 8:  # Bit String
            return decode_bit_string(content)
        case 9:  # Enumerated
            return decode_enumerated(content)
        case 10:  # Date
            return decode_date(content)
        case 11:  # Time
            return decode_time(content)
        case 12:  # Object Identifier
            obj_type, instance = decode_object_identifier(content)
            return ObjectIdentifier(ObjectType(obj_type), instance)
        case _:
            msg = f"Unknown application tag number: {tag.number}"
            raise ValueError(msg)


_MAX_DECODED_VALUES = 10_000
"""Maximum number of decoded application-tagged values to prevent memory exhaustion."""


def decode_all_application_values(data: bytes | memoryview) -> list[object]:
    """Decode all application-tagged values from concatenated bytes.

    Iterates through the buffer, decoding each application-tagged
    element and collecting them into a list.

    :param data: Concatenated application-tagged encoded bytes.
    :returns: List of decoded Python values.
    :raises ValueError: If a non-application tag is encountered or the
        number of decoded values exceeds :data:`_MAX_DECODED_VALUES`.
    """
    from bac_py.encoding.tags import decode_tag

    if isinstance(data, bytes):
        data = memoryview(data)

    results: list[object] = []
    offset = 0
    while offset < len(data):
        if len(results) >= _MAX_DECODED_VALUES:
            msg = (
                f"Decoded value count exceeds maximum ({_MAX_DECODED_VALUES}): "
                f"possible malformed or malicious payload"
            )
            logger.warning(msg)
            raise ValueError(msg)

        tag, tag_end = decode_tag(data, offset)
        if tag.cls != TagClass.APPLICATION:
            msg = f"Expected application tag at offset {offset}, got context tag {tag.number}"
            raise ValueError(msg)

        # For booleans, the value is in the tag length field (no content bytes)
        element_end = tag_end if tag.number == _TAG_BOOLEAN else tag_end + tag.length

        element_bytes = data[offset:element_end]
        results.append(decode_application_value(element_bytes))
        offset = element_end

    return results


def decode_and_unwrap(data: bytes | memoryview) -> object:
    """Decode application-tagged bytes and unwrap single-element lists.

    Convenience wrapper around :func:`decode_all_application_values` that
    returns a single value directly when the data contains exactly one
    application-tagged element, ``None`` for empty data, or the full
    list for multiple elements.

    :param data: Concatenated application-tagged encoded bytes.
    :returns: ``None`` if *data* decodes to zero elements, the single decoded
        value if exactly one element, or a ``list`` of decoded values if
        multiple elements.
    """
    values = decode_all_application_values(data)
    if len(values) == 1:
        return values[0]
    if len(values) == 0:
        return None
    return values


_CONSTRUCTED_ENCODERS: dict[type, object] | None = None


def _build_constructed_encoders() -> dict[type, object]:
    """Build a type-to-encoder dispatch table for constructed BACnet types.

    Built lazily on first call to :func:`encode_property_value` to avoid
    circular imports between ``encoding.primitives`` and ``types.constructed``.
    Each encoder is a callable ``(value, int_as_real) -> bytes``.
    """
    # Local import to break circular dependency with types.constructed
    from typing import Any

    from bac_py.types.constructed import (
        BACnetAddress,
        BACnetCalendarEntry,
        BACnetCOVSubscription,
        BACnetDateRange,
        BACnetDateTime,
        BACnetDestination,
        BACnetDeviceObjectPropertyReference,
        BACnetDeviceObjectReference,
        BACnetLogRecord,
        BACnetObjectPropertyReference,
        BACnetPrescale,
        BACnetPriorityArray,
        BACnetPriorityValue,
        BACnetRecipient,
        BACnetRecipientProcess,
        BACnetScale,
        BACnetSpecialEvent,
        BACnetTimeValue,
        BACnetValueSource,
        BACnetWeekNDay,
        StatusFlags,
    )

    def _enc_status_flags(v: Any, _iar: bool) -> bytes:
        return encode_application_bit_string(v.to_bit_string())

    def _enc_datetime(v: Any, _iar: bool) -> bytes:
        return encode_application_date(v.date) + encode_application_time(v.time)

    def _enc_date_range(v: Any, _iar: bool) -> bytes:
        return encode_application_date(v.start_date) + encode_application_date(v.end_date)

    def _enc_week_n_day(v: Any, _iar: bool) -> bytes:
        return encode_application_octet_string(bytes([v.month, v.week_of_month, v.day_of_week]))

    def _enc_calendar_entry(v: Any, _iar: bool) -> bytes:
        return _encode_calendar_entry(v)

    def _enc_time_value(v: Any, iar: bool) -> bytes:
        return encode_application_time(v.time) + encode_property_value(v.value, int_as_real=iar)

    def _enc_special_event(v: Any, iar: bool) -> bytes:
        return _encode_special_event(v, int_as_real=iar)

    def _enc_dev_obj_prop_ref(v: Any, _iar: bool) -> bytes:
        parts = [
            encode_context_object_id(0, v.object_identifier),
            encode_context_enumerated(1, v.property_identifier),
        ]
        if v.property_array_index is not None:
            parts.append(encode_context_unsigned(2, v.property_array_index))
        if v.device_identifier is not None:
            parts.append(encode_context_object_id(3, v.device_identifier))
        return b"".join(parts)

    def _enc_obj_prop_ref(v: Any, _iar: bool) -> bytes:
        parts = [
            encode_context_object_id(0, v.object_identifier),
            encode_context_enumerated(1, v.property_identifier),
        ]
        if v.property_array_index is not None:
            parts.append(encode_context_unsigned(2, v.property_array_index))
        return b"".join(parts)

    def _enc_address(v: Any, _iar: bool) -> bytes:
        return encode_context_unsigned(0, v.network_number) + encode_context_octet_string(
            1, v.mac_address
        )

    def _enc_recipient(v: Any, _iar: bool) -> bytes:
        return _encode_recipient(v)

    def _enc_recipient_process(v: Any, _iar: bool) -> bytes:
        return b"".join(
            [
                encode_opening_tag(0),
                _encode_recipient(v.recipient),
                encode_closing_tag(0),
                encode_context_unsigned(1, v.process_identifier),
            ]
        )

    def _enc_destination(v: Any, _iar: bool) -> bytes:
        return b"".join(
            [
                encode_application_bit_string(v.valid_days),
                encode_application_time(v.from_time),
                encode_application_time(v.to_time),
                _encode_recipient(v.recipient),
                encode_application_unsigned(v.process_identifier),
                encode_application_boolean(v.issue_confirmed_notifications),
                encode_application_bit_string(v.transitions),
            ]
        )

    def _enc_scale(v: Any, _iar: bool) -> bytes:
        if v.float_scale is not None:
            return encode_context_real(0, v.float_scale)
        if v.integer_scale is not None:
            return encode_context_signed(1, v.integer_scale)
        return encode_context_real(0, 0.0)

    def _enc_prescale(v: Any, _iar: bool) -> bytes:
        return encode_context_unsigned(0, v.multiplier) + encode_context_unsigned(
            1, v.modulo_divide
        )

    def _enc_log_record(v: Any, iar: bool) -> bytes:
        parts = [
            encode_application_date(v.timestamp.date),
            encode_application_time(v.timestamp.time),
            encode_property_value(v.log_datum, int_as_real=iar),
        ]
        if v.status_flags is not None:
            parts.append(encode_context_bit_string(1, v.status_flags.to_bit_string()))
        return b"".join(parts)

    def _enc_cov_subscription(v: Any, _iar: bool) -> bytes:
        return _encode_cov_subscription(v)

    def _enc_value_source(v: Any, _iar: bool) -> bytes:
        result: bytes = v.encode()
        return result

    def _enc_dev_obj_ref(v: Any, _iar: bool) -> bytes:
        result: bytes = v.encode()
        return result

    def _enc_priority_value(v: Any, iar: bool) -> bytes:
        if v.value is None:
            return encode_application_null()
        return encode_property_value(v.value, int_as_real=iar)

    def _enc_priority_array(v: Any, iar: bool) -> bytes:
        parts: list[bytes] = []
        for slot in v.slots:
            if slot.value is None:
                parts.append(encode_application_null())
            else:
                parts.append(encode_property_value(slot.value, int_as_real=iar))
        return b"".join(parts)

    return {
        StatusFlags: _enc_status_flags,
        BACnetDateTime: _enc_datetime,
        BACnetDateRange: _enc_date_range,
        BACnetWeekNDay: _enc_week_n_day,
        BACnetCalendarEntry: _enc_calendar_entry,
        BACnetTimeValue: _enc_time_value,
        BACnetSpecialEvent: _enc_special_event,
        BACnetDeviceObjectPropertyReference: _enc_dev_obj_prop_ref,
        BACnetObjectPropertyReference: _enc_obj_prop_ref,
        BACnetAddress: _enc_address,
        BACnetRecipient: _enc_recipient,
        BACnetRecipientProcess: _enc_recipient_process,
        BACnetDestination: _enc_destination,
        BACnetScale: _enc_scale,
        BACnetPrescale: _enc_prescale,
        BACnetLogRecord: _enc_log_record,
        BACnetCOVSubscription: _enc_cov_subscription,
        BACnetValueSource: _enc_value_source,
        BACnetDeviceObjectReference: _enc_dev_obj_ref,
        BACnetPriorityValue: _enc_priority_value,
        BACnetPriorityArray: _enc_priority_array,
    }


def encode_property_value(value: object, *, int_as_real: bool = False) -> bytes:
    """Encode a Python value to application-tagged bytes.

    Handles the common types stored in BACnet object properties,
    including both primitive and constructed BACnet types.

    :param value: The value to encode.
    :param int_as_real: If ``True``, encode plain ``int`` values as Real instead
        of Unsigned (used for analog object types where Present_Value is Real).
    :returns: Application-tagged encoded bytes.
    :raises TypeError: If the value type is not supported.
    """
    global _CONSTRUCTED_ENCODERS
    if _CONSTRUCTED_ENCODERS is None:
        _CONSTRUCTED_ENCODERS = _build_constructed_encoders()

    if value is None:
        return encode_application_null()
    if isinstance(value, ObjectIdentifier):
        return encode_application_object_id(value.object_type, value.instance_number)

    # --- Constructed types: O(1) dispatch table lookup ---
    encoder = _CONSTRUCTED_ENCODERS.get(type(value))
    if encoder is not None:
        result: bytes = encoder(value, int_as_real)  # type: ignore[operator]
        return result

    # --- Primitive types (order matters due to subclass relationships) ---

    if isinstance(value, BitString):
        return encode_application_bit_string(value)
    if isinstance(value, BACnetDate):
        return encode_application_date(value)
    if isinstance(value, BACnetTime):
        return encode_application_time(value)
    if isinstance(value, str):
        return encode_application_character_string(value)
    if isinstance(value, bool):
        # Must check bool before int since bool is a subclass of int
        return encode_application_boolean(value)
    if isinstance(value, enum.IntEnum):
        # Must check IntEnum before int since IntEnum is a subclass of int
        return encode_application_enumerated(value)
    if isinstance(value, BACnetDouble):
        # Must check BACnetDouble before float since BACnetDouble is a subclass of float
        return encode_application_double(value)
    if isinstance(value, float):
        return encode_application_real(value)
    if isinstance(value, int):
        if int_as_real:
            return encode_application_real(float(value))
        return encode_application_unsigned(value)
    if isinstance(value, bytes):
        # Already-encoded application-tagged bytes (pass-through)
        return value
    if isinstance(value, list):
        return b"".join(encode_property_value(item, int_as_real=int_as_real) for item in value)

    msg = f"Cannot encode value of type {type(value).__name__}"
    raise TypeError(msg)


def _encode_calendar_entry(entry: object) -> bytes:
    """Encode a ``BACnetCalendarEntry`` CHOICE with context tags.

    :param entry: A ``BACnetCalendarEntry`` instance containing a
        :class:`BACnetDate`, ``BACnetDateRange``, or ``BACnetWeekNDay``.
    :returns: Context-tagged encoded bytes for the calendar entry.
    """
    from bac_py.types.constructed import BACnetCalendarEntry, BACnetDateRange, BACnetWeekNDay

    assert isinstance(entry, BACnetCalendarEntry)
    val = entry.value
    if isinstance(val, BACnetDate):
        # date [0]
        return encode_context_date(0, val)
    if isinstance(val, BACnetDateRange):
        # dateRange [1] - constructed
        return b"".join(
            [
                encode_opening_tag(1),
                encode_application_date(val.start_date),
                encode_application_date(val.end_date),
                encode_closing_tag(1),
            ]
        )
    # weekNDay [2]
    assert isinstance(val, BACnetWeekNDay)
    return encode_context_octet_string(
        2,
        bytes([val.month, val.week_of_month, val.day_of_week]),
    )


def _encode_special_event(event: object, *, int_as_real: bool = False) -> bytes:
    """Encode a ``BACnetSpecialEvent`` SEQUENCE.

    :param event: A ``BACnetSpecialEvent`` instance.
    :param int_as_real: If ``True``, encode integer time-values as Real.
    :returns: Encoded bytes for the special event.
    """
    from bac_py.types.constructed import BACnetCalendarEntry, BACnetSpecialEvent

    assert isinstance(event, BACnetSpecialEvent)
    parts: list[bytes] = []
    if isinstance(event.period, BACnetCalendarEntry):
        parts.append(encode_opening_tag(0))
        parts.append(_encode_calendar_entry(event.period))
        parts.append(encode_closing_tag(0))
    else:
        # Calendar object reference
        parts.append(encode_context_object_id(1, event.period))
    parts.append(encode_opening_tag(2))  # listOfTimeValues
    for tv in event.list_of_time_values:
        parts.append(encode_application_time(tv.time))
        parts.append(encode_property_value(tv.value, int_as_real=int_as_real))
    parts.append(encode_closing_tag(2))
    parts.append(encode_context_unsigned(3, event.event_priority))
    return b"".join(parts)


def _encode_recipient(recipient: object) -> bytes:
    """Encode a ``BACnetRecipient`` CHOICE.

    :param recipient: A ``BACnetRecipient`` instance with either a device
        or address field populated.
    :returns: Context-tagged encoded bytes for the recipient.
    """
    from bac_py.types.constructed import BACnetRecipient

    assert isinstance(recipient, BACnetRecipient)
    if recipient.device is not None:
        # device [0] ObjectIdentifier
        return encode_context_object_id(0, recipient.device)
    if recipient.address is not None:
        # address [1] BACnetAddress - constructed
        return b"".join(
            [
                encode_opening_tag(1),
                encode_context_unsigned(0, recipient.address.network_number),
                encode_context_octet_string(1, recipient.address.mac_address),
                encode_closing_tag(1),
            ]
        )
    # Empty recipient defaults to device context tag with zero-length
    return encode_context_object_id(0, ObjectIdentifier(ObjectType(0), 0))


def _encode_cov_subscription(sub: object) -> bytes:
    """Encode a ``BACnetCOVSubscription`` SEQUENCE.

    :param sub: A ``BACnetCOVSubscription`` instance.
    :returns: Encoded bytes for the COV subscription.
    """
    from bac_py.types.constructed import BACnetCOVSubscription

    assert isinstance(sub, BACnetCOVSubscription)
    parts = [
        # recipient [0] BACnetRecipientProcess
        encode_opening_tag(0),
        encode_opening_tag(0),  # recipient.recipient
        _encode_recipient(sub.recipient.recipient),
        encode_closing_tag(0),
        encode_context_unsigned(1, sub.recipient.process_identifier),
        encode_closing_tag(0),
        # monitoredPropertyReference [1]
        encode_opening_tag(1),
        encode_context_object_id(0, sub.monitored_object),
        encode_closing_tag(1),
        # issueConfirmedNotifications [2]
        encode_context_boolean(2, sub.issue_confirmed_notifications),
        # timeRemaining [3]
        encode_context_unsigned(3, sub.time_remaining),
    ]
    # covIncrement [4] OPTIONAL
    if sub.cov_increment is not None:
        parts.append(encode_context_real(4, sub.cov_increment))
    return b"".join(parts)
