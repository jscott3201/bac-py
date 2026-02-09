"""BACnet primitive type encoding/decoding per ASHRAE 135-2016 Clause 20.2."""

from __future__ import annotations

import enum
import struct

from bac_py.encoding.tags import TagClass, encode_tag
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier

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
    0x02: "iso2022_jp",
    0x03: "utf-32-be",
    0x04: "utf-16-be",
    0x05: "iso-8859-1",
}


def _min_unsigned_bytes(value: int) -> int:
    """Return minimum number of bytes to encode an unsigned integer."""
    if value == 0:
        return 1
    return (value.bit_length() + 7) // 8


# --- Unsigned Integer (Clause 20.2.4) ---


def encode_unsigned(value: int) -> bytes:
    """Encode an unsigned integer using minimum octets, big-endian."""
    if value < 0:
        msg = f"Unsigned integer must be >= 0, got {value}"
        raise ValueError(msg)
    n = _min_unsigned_bytes(value)
    return value.to_bytes(n, "big")


def decode_unsigned(data: memoryview | bytes) -> int:
    """Decode an unsigned integer from big-endian bytes."""
    return int.from_bytes(data, "big")


# --- Signed Integer (Clause 20.2.5) ---


def encode_signed(value: int) -> bytes:
    """Encode a signed integer using minimum octets, 2's complement, big-endian."""
    if value == 0:
        return b"\x00"
    n = (value.bit_length() + 8) // 8  # +1 for sign bit, rounded up
    return value.to_bytes(n, "big", signed=True)


def decode_signed(data: memoryview | bytes) -> int:
    """Decode a signed integer from 2's complement big-endian bytes."""
    return int.from_bytes(data, "big", signed=True)


# --- Real (Clause 20.2.6) ---


def encode_real(value: float) -> bytes:
    """Encode an IEEE-754 single precision float."""
    return struct.pack(">f", value)


def decode_real(data: memoryview | bytes) -> float:
    """Decode an IEEE-754 single precision float."""
    result: float = struct.unpack(">f", data[:4])[0]
    return result


# --- Double (Clause 20.2.7) ---


def encode_double(value: float) -> bytes:
    """Encode an IEEE-754 double precision float."""
    return struct.pack(">d", value)


def decode_double(data: memoryview | bytes) -> float:
    """Decode an IEEE-754 double precision float."""
    result: float = struct.unpack(">d", data[:8])[0]
    return result


# --- Octet String (Clause 20.2.8) ---


def encode_octet_string(value: bytes) -> bytes:
    """Encode an octet string (identity operation)."""
    return value


def decode_octet_string(data: memoryview | bytes) -> bytes:
    """Decode an octet string."""
    return bytes(data)


# --- Character String (Clause 20.2.9) ---


def encode_character_string(value: str, charset: int = 0) -> bytes:
    """Encode a character string with leading charset byte.

    Args:
        value: The string to encode.
        charset: Character set identifier (default 0x00 = UTF-8).

    Returns:
        Encoded bytes with leading charset byte.
    """
    encoding = _CHARSET_DECODERS.get(charset)
    if encoding is None:
        msg = f"Unsupported BACnet character set: 0x{charset:02x}"
        raise ValueError(msg)
    return bytes([charset]) + value.encode(encoding)


def decode_character_string(data: memoryview | bytes) -> str:
    """Decode a character string from contents octets.

    The first byte is the character set identifier.
    """
    if len(data) < 1:
        msg = "CharacterString data too short: need at least 1 byte for charset"
        raise ValueError(msg)
    charset = data[0]
    encoding = _CHARSET_DECODERS.get(charset)
    if encoding is None:
        msg = f"Unsupported BACnet character set: 0x{charset:02x}"
        raise ValueError(msg)
    return bytes(data[1:]).decode(encoding)


# --- Enumerated (Clause 20.2.11) ---


def encode_enumerated(value: int) -> bytes:
    """Encode an enumerated value (same encoding as unsigned)."""
    return encode_unsigned(value)


def decode_enumerated(data: memoryview | bytes) -> int:
    """Decode an enumerated value (same encoding as unsigned)."""
    return decode_unsigned(data)


# --- Bit String (Clause 20.2.10) ---


def encode_bit_string(value: BitString) -> bytes:
    """Encode a bit string with leading unused-bits count byte."""
    return bytes([value.unused_bits]) + value.data


def decode_bit_string(data: memoryview | bytes) -> BitString:
    """Decode a bit string from contents octets."""
    if len(data) < 1:
        msg = "BitString data too short: need at least 1 byte for unused-bits count"
        raise ValueError(msg)
    unused_bits = data[0]
    return BitString(bytes(data[1:]), unused_bits)


# --- Date (Clause 20.2.12) ---


def encode_date(date: BACnetDate) -> bytes:
    """Encode a BACnet date to 4 bytes: year-1900, month, day, day-of-week."""
    year_byte = 0xFF if date.year == 0xFF else date.year - 1900
    return bytes([year_byte, date.month, date.day, date.day_of_week])


def decode_date(data: memoryview | bytes) -> BACnetDate:
    """Decode a BACnet date from 4 bytes."""
    if len(data) < 4:
        msg = f"Date data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    year = 0xFF if data[0] == 0xFF else data[0] + 1900
    return BACnetDate(year, data[1], data[2], data[3])


# --- Time (Clause 20.2.13) ---


def encode_time(time: BACnetTime) -> bytes:
    """Encode a BACnet time to 4 bytes: hour, minute, second, hundredth."""
    return bytes([time.hour, time.minute, time.second, time.hundredth])


def decode_time(data: memoryview | bytes) -> BACnetTime:
    """Decode a BACnet time from 4 bytes."""
    if len(data) < 4:
        msg = f"Time data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    return BACnetTime(data[0], data[1], data[2], data[3])


# --- Object Identifier (Clause 20.2.14) ---


def encode_object_identifier(obj_type: int, instance: int) -> bytes:
    """Encode a BACnet object identifier to 4 bytes.

    Object type is a 10-bit field (0-1023). Instance is a 22-bit field
    (0-4194303). Delegates to ObjectIdentifier.encode().
    """
    return ObjectIdentifier(ObjectType(obj_type), instance).encode()


def decode_object_identifier(data: memoryview | bytes) -> tuple[int, int]:
    """Decode a BACnet object identifier from 4 bytes.

    Returns:
        Tuple of (object_type, instance_number).
    """
    if len(data) < 4:
        msg = f"ObjectIdentifier data too short: need 4 bytes, got {len(data)}"
        raise ValueError(msg)
    value = int.from_bytes(data[:4], "big")
    return (value >> 22, value & 0x3FFFFF)


# --- Null (Clause 20.2.2) ---


def encode_null() -> bytes:
    """Encode a Null value (empty contents)."""
    return b""


# --- Boolean (Clause 20.2.3) ---
# Note: Application-tagged booleans encode the value in the tag's L/V/T bits
# (no contents octet). Context-tagged booleans use 1 contents octet.
# The tag encoding handles this; these functions handle the contents octet form.


def encode_boolean(value: bool) -> bytes:
    """Encode a boolean value as a single contents octet.

    For context-tagged booleans. Application-tagged booleans encode the
    value in the tag itself.
    """
    return bytes([1 if value else 0])


def decode_boolean(data: memoryview | bytes) -> bool:
    """Decode a boolean value from a single contents octet."""
    return bool(data[0])


# --- Application-Tagged Convenience Functions ---


def encode_application_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with an application tag."""
    return encode_tag(tag_number, TagClass.APPLICATION, len(data)) + data


def encode_context_tagged(tag_number: int, data: bytes) -> bytes:
    """Encode data with a context-specific tag."""
    return encode_tag(tag_number, TagClass.CONTEXT, len(data)) + data


def encode_application_null() -> bytes:
    """Encode an application-tagged Null."""
    return encode_application_tagged(_TAG_NULL, b"")


def encode_application_boolean(value: bool) -> bytes:
    """Encode an application-tagged Boolean.

    Per Clause 20.2.3, the value is encoded in the L/V/T bits of the tag
    with no contents octet.
    """
    return encode_tag(_TAG_BOOLEAN, TagClass.APPLICATION, 1 if value else 0)


def encode_application_unsigned(value: int) -> bytes:
    """Encode an application-tagged Unsigned Integer."""
    data = encode_unsigned(value)
    return encode_application_tagged(_TAG_UNSIGNED, data)


def encode_application_signed(value: int) -> bytes:
    """Encode an application-tagged Signed Integer."""
    data = encode_signed(value)
    return encode_application_tagged(_TAG_SIGNED, data)


def encode_application_real(value: float) -> bytes:
    """Encode an application-tagged Real."""
    data = encode_real(value)
    return encode_application_tagged(_TAG_REAL, data)


def encode_application_double(value: float) -> bytes:
    """Encode an application-tagged Double."""
    data = encode_double(value)
    return encode_application_tagged(_TAG_DOUBLE, data)


def encode_application_octet_string(value: bytes) -> bytes:
    """Encode an application-tagged Octet String."""
    return encode_application_tagged(_TAG_OCTET_STRING, value)


def encode_application_character_string(value: str) -> bytes:
    """Encode an application-tagged Character String."""
    data = encode_character_string(value)
    return encode_application_tagged(_TAG_CHARACTER_STRING, data)


def encode_application_enumerated(value: int) -> bytes:
    """Encode an application-tagged Enumerated."""
    data = encode_enumerated(value)
    return encode_application_tagged(_TAG_ENUMERATED, data)


def encode_application_date(date: BACnetDate) -> bytes:
    """Encode an application-tagged Date."""
    data = encode_date(date)
    return encode_application_tagged(_TAG_DATE, data)


def encode_application_time(time: BACnetTime) -> bytes:
    """Encode an application-tagged Time."""
    data = encode_time(time)
    return encode_application_tagged(_TAG_TIME, data)


def encode_application_object_id(obj_type: int, instance: int) -> bytes:
    """Encode an application-tagged Object Identifier."""
    data = encode_object_identifier(obj_type, instance)
    return encode_application_tagged(_TAG_OBJECT_IDENTIFIER, data)


def encode_context_object_id(tag_number: int, obj_id: ObjectIdentifier) -> bytes:
    """Encode an ObjectIdentifier with a context-specific tag."""
    return encode_context_tagged(tag_number, obj_id.encode())


def encode_application_bit_string(value: BitString) -> bytes:
    """Encode an application-tagged Bit String."""
    data = encode_bit_string(value)
    return encode_application_tagged(_TAG_BIT_STRING, data)


def decode_application_value(data: bytes | memoryview) -> object:
    """Decode application-tagged bytes to a native Python value.

    Inspects the application tag number and dispatches to the
    appropriate decoder. Returns native Python types:

        Tag 0  (Null)             -> None
        Tag 1  (Boolean)          -> bool
        Tag 2  (Unsigned)         -> int
        Tag 3  (Signed)           -> int
        Tag 4  (Real)             -> float
        Tag 5  (Double)           -> float
        Tag 6  (Octet String)     -> bytes
        Tag 7  (Character String) -> str
        Tag 8  (Bit String)       -> BitString
        Tag 9  (Enumerated)       -> int
        Tag 10 (Date)             -> BACnetDate
        Tag 11 (Time)             -> BACnetTime
        Tag 12 (Object Id)        -> ObjectIdentifier

    Args:
        data: Application-tagged encoded bytes.

    Returns:
        Decoded Python value.

    Raises:
        ValueError: If the tag is not application-class or is unrecognised.

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

    content = data[offset : offset + tag.length]

    match tag.number:
        case 0:  # Null
            return None
        case 1:  # Boolean - value is in the tag length field
            return tag.length != 0
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


def decode_all_application_values(data: bytes | memoryview) -> list[object]:
    """Decode all application-tagged values from concatenated bytes.

    Iterates through the buffer, decoding each application-tagged
    element and collecting them into a list.

    Args:
        data: Concatenated application-tagged encoded bytes.

    Returns:
        List of decoded Python values.
    """
    from bac_py.encoding.tags import decode_tag

    if isinstance(data, bytes):
        data = memoryview(data)

    results: list[object] = []
    offset = 0
    while offset < len(data):
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


def encode_property_value(value: object, *, int_as_real: bool = False) -> bytes:
    """Encode a Python value to application-tagged bytes.

    Handles the common types stored in BACnet object properties.

    Args:
        value: The value to encode.
        int_as_real: If True, encode plain ints as Real instead of Unsigned
            (used for analog object types where Present_Value is Real).

    Returns:
        Application-tagged encoded bytes.

    Raises:
        TypeError: If the value type is not supported.
    """
    if isinstance(value, ObjectIdentifier):
        return encode_application_object_id(value.object_type, value.instance_number)
    if isinstance(value, BitString):
        return encode_application_bit_string(value)
    if isinstance(value, str):
        return encode_application_character_string(value)
    if isinstance(value, bool):
        # Must check bool before int since bool is a subclass of int
        return encode_application_enumerated(int(value))
    if isinstance(value, enum.IntEnum):
        # Must check IntEnum before int since IntEnum is a subclass of int
        return encode_application_enumerated(value)
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
        buf = bytearray()
        for item in value:
            buf.extend(encode_property_value(item, int_as_real=int_as_real))
        return bytes(buf)

    msg = f"Cannot encode value of type {type(value).__name__}"
    raise TypeError(msg)
