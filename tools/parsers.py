"""Input parsing utilities for the BACnet CLI.

Handles object type shorthands, property name resolution,
and address parsing.
"""

from __future__ import annotations

from bac_py.network.address import BACnetAddress
from bac_py.types.enums import ObjectType, PropertyIdentifier

# Object type shorthand mappings
_OBJECT_TYPE_SHORTHANDS: dict[str, ObjectType] = {
    "ai": ObjectType.ANALOG_INPUT,
    "ao": ObjectType.ANALOG_OUTPUT,
    "av": ObjectType.ANALOG_VALUE,
    "bi": ObjectType.BINARY_INPUT,
    "bo": ObjectType.BINARY_OUTPUT,
    "bv": ObjectType.BINARY_VALUE,
    "mi": ObjectType.MULTI_STATE_INPUT,
    "mo": ObjectType.MULTI_STATE_OUTPUT,
    "mv": ObjectType.MULTI_STATE_VALUE,
    "dev": ObjectType.DEVICE,
    "device": ObjectType.DEVICE,
    "cal": ObjectType.CALENDAR,
    "cmd": ObjectType.COMMAND,
    "file": ObjectType.FILE,
    "loop": ObjectType.LOOP,
    "sch": ObjectType.SCHEDULE,
    "nc": ObjectType.NOTIFICATION_CLASS,
    "tl": ObjectType.TREND_LOG,
    "acc": ObjectType.ACCUMULATOR,
    "np": ObjectType.NETWORK_PORT,
}

# Build full-name mappings from enum (e.g. "analog-input" -> ANALOG_INPUT)
_OBJECT_TYPE_NAMES: dict[str, ObjectType] = {}
for _ot in ObjectType:
    _OBJECT_TYPE_NAMES[_ot.name.lower()] = _ot
    _OBJECT_TYPE_NAMES[_ot.name.lower().replace("_", "-")] = _ot

# Build property identifier mappings
_PROPERTY_NAMES: dict[str, PropertyIdentifier] = {}
for _pi in PropertyIdentifier:
    _PROPERTY_NAMES[_pi.name.lower()] = _pi
    _PROPERTY_NAMES[_pi.name.lower().replace("_", "-")] = _pi


def parse_object_type(text: str) -> ObjectType:
    """Parse an object type from user input.

    Accepts shorthands (``ai``, ``bo``), full names with hyphens or
    underscores (``analog-input``, ``analog_input``), or numeric values.

    Raises:
        ValueError: If the text cannot be resolved.
    """
    key = text.strip().lower()

    # Shorthand
    if key in _OBJECT_TYPE_SHORTHANDS:
        return _OBJECT_TYPE_SHORTHANDS[key]

    # Full name
    if key in _OBJECT_TYPE_NAMES:
        return _OBJECT_TYPE_NAMES[key]

    # Numeric
    try:
        return ObjectType(int(key))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown object type: {text!r}"
    raise ValueError(msg)


def parse_object_id(text: str) -> tuple[ObjectType, int]:
    """Parse an object identifier like ``ai:1`` or ``analog-input:1``.

    Returns:
        Tuple of (ObjectType, instance_number).

    Raises:
        ValueError: If the format is invalid.
    """
    if ":" not in text:
        msg = f"Object identifier must be TYPE:INSTANCE (e.g. ai:1), got {text!r}"
        raise ValueError(msg)

    type_str, instance_str = text.rsplit(":", 1)
    obj_type = parse_object_type(type_str)
    try:
        instance = int(instance_str)
    except ValueError:
        msg = f"Instance must be an integer, got {instance_str!r}"
        raise ValueError(msg) from None

    return obj_type, instance


def parse_property(text: str) -> PropertyIdentifier:
    """Parse a property identifier from user input.

    Accepts kebab-case (``present-value``), snake_case
    (``present_value``), or numeric values (``85``).

    Raises:
        ValueError: If the text cannot be resolved.
    """
    key = text.strip().lower().replace("-", "_")

    # Try underscore form first
    if key in _PROPERTY_NAMES:
        return _PROPERTY_NAMES[key]

    # Try with hyphens (already in map)
    key_hyphen = text.strip().lower()
    if key_hyphen in _PROPERTY_NAMES:
        return _PROPERTY_NAMES[key_hyphen]

    # Numeric
    try:
        return PropertyIdentifier(int(text))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown property: {text!r}"
    raise ValueError(msg)


def parse_address(text: str) -> BACnetAddress:
    """Parse a BACnet/IP address from ``IP`` or ``IP:port``.

    Default port is 47808 (0xBAC0).
    """
    if ":" in text:
        ip_str, port_str = text.rsplit(":", 1)
        port = int(port_str)
    else:
        ip_str = text
        port = 0xBAC0

    parts = [int(p) for p in ip_str.split(".")]
    if len(parts) != 4:
        msg = f"Invalid IP address: {ip_str!r}"
        raise ValueError(msg)

    mac = bytes(parts) + port.to_bytes(2, "big")
    return BACnetAddress(mac_address=mac)
