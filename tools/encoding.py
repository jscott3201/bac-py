"""Smart value encoding and decoding for the BACnet CLI.

Handles the inference of BACnet application tag types from object type,
property identifier, and raw user input.
"""

from __future__ import annotations

from bac_py.encoding.primitives import (
    decode_character_string,
    decode_double,
    decode_object_identifier,
    decode_real,
    decode_signed,
    decode_unsigned,
    encode_application_boolean,
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_null,
    encode_application_real,
    encode_application_signed,
    encode_application_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.types.enums import EngineeringUnits, ObjectType, PropertyIdentifier

# Properties that are always a specific type
_STRING_PROPERTIES = frozenset(
    {
        PropertyIdentifier.OBJECT_NAME,
        PropertyIdentifier.DESCRIPTION,
        PropertyIdentifier.LOCATION,
        PropertyIdentifier.DEVICE_TYPE,
        PropertyIdentifier.PROFILE_NAME,
    }
)

_BOOLEAN_PROPERTIES = frozenset(
    {
        PropertyIdentifier.OUT_OF_SERVICE,
        PropertyIdentifier.EVENT_DETECTION_ENABLE,
        PropertyIdentifier.EVENT_ALGORITHM_INHIBIT,
        PropertyIdentifier.RELIABILITY_EVALUATION_INHIBIT,
    }
)

_REAL_PROPERTIES = frozenset(
    {
        PropertyIdentifier.COV_INCREMENT,
        PropertyIdentifier.HIGH_LIMIT,
        PropertyIdentifier.LOW_LIMIT,
        PropertyIdentifier.DEADBAND,
        PropertyIdentifier.RESOLUTION,
        PropertyIdentifier.MAX_PRES_VALUE,
        PropertyIdentifier.MIN_PRES_VALUE,
        PropertyIdentifier.RELINQUISH_DEFAULT,
    }
)

_ENUMERATED_PROPERTIES = frozenset(
    {
        PropertyIdentifier.UNITS,
        PropertyIdentifier.POLARITY,
        PropertyIdentifier.EVENT_STATE,
        PropertyIdentifier.RELIABILITY,
        PropertyIdentifier.SEGMENTATION_SUPPORTED,
    }
)

# Object types whose PRESENT_VALUE is analog (REAL)
_ANALOG_TYPES = frozenset(
    {
        ObjectType.ANALOG_INPUT,
        ObjectType.ANALOG_OUTPUT,
        ObjectType.ANALOG_VALUE,
        ObjectType.LARGE_ANALOG_VALUE,
        ObjectType.PULSE_CONVERTER,
    }
)

# Object types whose PRESENT_VALUE is binary (ENUMERATED)
_BINARY_TYPES = frozenset(
    {
        ObjectType.BINARY_INPUT,
        ObjectType.BINARY_OUTPUT,
        ObjectType.BINARY_VALUE,
    }
)

# Object types whose PRESENT_VALUE is multi-state (UNSIGNED)
_MULTISTATE_TYPES = frozenset(
    {
        ObjectType.MULTI_STATE_INPUT,
        ObjectType.MULTI_STATE_OUTPUT,
        ObjectType.MULTI_STATE_VALUE,
    }
)


def encode_value(
    value_str: str,
    obj_type: ObjectType,
    prop: PropertyIdentifier,
    type_override: str | None = None,
) -> bytes:
    """Encode a user-supplied value string to application-tagged bytes.

    Decision order:
    1. ``type_override`` forces a specific type
    2. Special keywords (null, active, inactive, true, false)
    3. PRESENT_VALUE type inferred from object type
    4. Known property type tables
    5. Heuristic fallback (contains '.' -> REAL, integer -> UNSIGNED, else STRING)
    """
    lower = value_str.strip().lower()

    # 1. Explicit type override
    if type_override:
        return _encode_by_type(value_str, type_override)

    # 2. Special keywords
    if lower == "null":
        return encode_application_null()
    if lower in ("active", "inactive"):
        return encode_application_enumerated(1 if lower == "active" else 0)
    if lower == "true":
        return encode_application_boolean(True)
    if lower == "false":
        return encode_application_boolean(False)

    # 3. PRESENT_VALUE inferred from object type
    if prop == PropertyIdentifier.PRESENT_VALUE:
        if obj_type in _ANALOG_TYPES:
            return encode_application_real(float(value_str))
        if obj_type in _BINARY_TYPES:
            return encode_application_enumerated(int(value_str))
        if obj_type in _MULTISTATE_TYPES:
            return encode_application_unsigned(int(value_str))

    # 4. Known property types
    if prop in _STRING_PROPERTIES:
        return encode_application_character_string(value_str)
    if prop in _BOOLEAN_PROPERTIES:
        return encode_application_boolean(lower in ("1", "true", "yes"))
    if prop in _REAL_PROPERTIES:
        return encode_application_real(float(value_str))
    if prop in _ENUMERATED_PROPERTIES:
        return encode_application_enumerated(int(value_str))

    # 5. Heuristic fallback
    if "." in value_str:
        try:
            return encode_application_real(float(value_str))
        except ValueError:
            pass
    try:
        v = int(value_str)
        if v < 0:
            return encode_application_signed(v)
        return encode_application_unsigned(v)
    except ValueError:
        pass

    return encode_application_character_string(value_str)


def _encode_by_type(value_str: str, type_name: str) -> bytes:
    """Encode a value with an explicit type name."""
    t = type_name.lower().replace("-", "_")
    match t:
        case "null":
            return encode_application_null()
        case "bool" | "boolean":
            return encode_application_boolean(value_str.lower() in ("1", "true", "yes", "active"))
        case "real" | "float":
            return encode_application_real(float(value_str))
        case "unsigned" | "uint":
            return encode_application_unsigned(int(value_str))
        case "signed" | "int":
            return encode_application_signed(int(value_str))
        case "enumerated" | "enum":
            return encode_application_enumerated(int(value_str))
        case "string" | "characterstring" | "char":
            return encode_application_character_string(value_str)
        case _:
            msg = f"Unknown type: {type_name!r}"
            raise ValueError(msg)


def _object_type_name(obj_type: int) -> str:
    """Return the ObjectType enum name, or the raw int as a string."""
    try:
        return ObjectType(obj_type).name
    except ValueError:
        return str(obj_type)


def decode_application_value(raw: bytes) -> str | float | int | bool | None:
    """Decode a single application-tagged value to a Python type."""
    if not raw:
        return None

    tag, offset = decode_tag(raw, 0)
    if tag.cls != TagClass.APPLICATION:
        return raw.hex()

    data = raw[offset : offset + tag.length]

    match tag.number:
        case 0:  # Null
            return None
        case 1:  # Boolean
            return tag.length != 0
        case 2:  # Unsigned Integer
            return decode_unsigned(data)
        case 3:  # Signed Integer
            return decode_signed(data)
        case 4:  # Real
            return round(decode_real(data), 4)
        case 5:  # Double
            return round(decode_double(data), 6)
        case 6:  # Octet String
            return bytes(data).hex()
        case 7:  # Character String
            return decode_character_string(data)
        case 8:  # Bit String
            return bytes(data).hex()
        case 9:  # Enumerated
            return decode_unsigned(data)
        case 10:  # Date
            if len(data) >= 4:
                year = data[0] + 1900 if data[0] != 0xFF else 0
                return f"{year}-{data[1]:02d}-{data[2]:02d}"
            return bytes(data).hex()
        case 11:  # Time
            if len(data) >= 4:
                return f"{data[0]:02d}:{data[1]:02d}:{data[2]:02d}"
            return bytes(data).hex()
        case 12:  # Object Identifier
            obj_type, instance = decode_object_identifier(data)
            return f"{_object_type_name(obj_type)}:{instance}"
        case _:
            return bytes(data).hex()


def decode_object_list(raw: bytes) -> list[tuple[int, int]]:
    """Decode a sequence of application-tagged object identifiers."""
    results: list[tuple[int, int]] = []
    offset = 0
    mv = memoryview(raw)
    while offset < len(mv):
        tag, new_offset = decode_tag(mv, offset)
        if tag.cls == TagClass.APPLICATION and tag.number == 12:
            obj_type, instance = decode_object_identifier(mv[new_offset : new_offset + tag.length])
            results.append((obj_type, instance))
        offset = new_offset + tag.length
    return results


def format_property_value(
    prop: PropertyIdentifier,
    value: int | str | float | bool | None,
) -> str | float | int | bool | None:
    """Resolve known enumerated property values to readable names."""
    if not isinstance(value, int):
        return value
    if prop == PropertyIdentifier.UNITS:
        try:
            return EngineeringUnits(value).name
        except ValueError:
            return value
    if prop == PropertyIdentifier.OBJECT_TYPE:
        return _object_type_name(value)
    return value
