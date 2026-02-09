"""Flexible parsing helpers for BACnet object and property identifiers."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

# Short aliases for commonly used object types.
OBJECT_TYPE_ALIASES: dict[str, ObjectType] = {
    "ai": ObjectType.ANALOG_INPUT,
    "ao": ObjectType.ANALOG_OUTPUT,
    "av": ObjectType.ANALOG_VALUE,
    "bi": ObjectType.BINARY_INPUT,
    "bo": ObjectType.BINARY_OUTPUT,
    "bv": ObjectType.BINARY_VALUE,
    "msi": ObjectType.MULTI_STATE_INPUT,
    "mso": ObjectType.MULTI_STATE_OUTPUT,
    "msv": ObjectType.MULTI_STATE_VALUE,
    "dev": ObjectType.DEVICE,
}

# Short aliases for commonly used property identifiers.
PROPERTY_ALIASES: dict[str, PropertyIdentifier] = {
    "pv": PropertyIdentifier.PRESENT_VALUE,
    "name": PropertyIdentifier.OBJECT_NAME,
    "desc": PropertyIdentifier.DESCRIPTION,
    "units": PropertyIdentifier.UNITS,
    "status": PropertyIdentifier.STATUS_FLAGS,
    "oos": PropertyIdentifier.OUT_OF_SERVICE,
    "cov-inc": PropertyIdentifier.COV_INCREMENT,
    "reliability": PropertyIdentifier.RELIABILITY,
}


def _resolve_object_type(name: str) -> ObjectType:
    """Resolve an object type name (alias, hyphenated, or underscore) to an ObjectType.

    Raises:
        ValueError: If the name is not recognised.
    """
    lower = name.lower().strip()

    # Check short aliases first
    if lower in OBJECT_TYPE_ALIASES:
        return OBJECT_TYPE_ALIASES[lower]

    # Try hyphenated -> UPPER_SNAKE
    enum_name = lower.replace("-", "_").upper()
    try:
        return ObjectType[enum_name]
    except KeyError:
        pass

    # Try as raw integer
    try:
        return ObjectType(int(lower))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown object type: {name!r}"
    raise ValueError(msg)


def parse_object_identifier(
    obj: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
) -> ObjectIdentifier:
    """Parse a flexible object identifier to ObjectIdentifier.

    Accepted formats::

        "analog-input,1"                  -> ObjectIdentifier(ANALOG_INPUT, 1)
        "analog-input:1"                  -> ObjectIdentifier(ANALOG_INPUT, 1)
        "ai,1"                            -> ObjectIdentifier(ANALOG_INPUT, 1)
        ("analog-input", 1)               -> ObjectIdentifier(ANALOG_INPUT, 1)
        (ObjectType.ANALOG_INPUT, 1)      -> ObjectIdentifier(ANALOG_INPUT, 1)
        (0, 1)                            -> ObjectIdentifier(ANALOG_INPUT, 1)
        ObjectIdentifier(...)             -> pass-through

    Args:
        obj: Object identifier in any supported format.

    Returns:
        Parsed ObjectIdentifier.

    Raises:
        ValueError: If the format is not recognised.
    """
    if isinstance(obj, ObjectIdentifier):
        return obj

    if isinstance(obj, tuple):
        if len(obj) != 2:
            msg = f"Object identifier tuple must have 2 elements, got {len(obj)}"
            raise ValueError(msg)
        type_part, instance = obj
        if isinstance(type_part, ObjectType):
            return ObjectIdentifier(type_part, instance)
        if isinstance(type_part, int):
            return ObjectIdentifier(ObjectType(type_part), instance)
        if isinstance(type_part, str):
            return ObjectIdentifier(_resolve_object_type(type_part), instance)
        msg = f"Cannot parse object type from {type(type_part).__name__}"
        raise ValueError(msg)

    if isinstance(obj, str):
        # Split on comma or colon
        for sep in (",", ":"):
            if sep in obj:
                parts = obj.split(sep, 1)
                type_name = parts[0].strip()
                try:
                    instance = int(parts[1].strip())
                except ValueError:
                    msg = f"Invalid instance number in {obj!r}"
                    raise ValueError(msg) from None
                return ObjectIdentifier(_resolve_object_type(type_name), instance)

        msg = (
            f"Cannot parse object identifier: {obj!r}. "
            "Expected format like 'analog-input,1' or 'ai:1'"
        )
        raise ValueError(msg)

    msg = f"Cannot parse object identifier from {type(obj).__name__}"
    raise ValueError(msg)


def _resolve_property_identifier(name: str) -> PropertyIdentifier:
    """Resolve a property name (alias, hyphenated, or underscore) to a PropertyIdentifier.

    Raises:
        ValueError: If the name is not recognised.
    """
    lower = name.lower().strip()

    # Check short aliases first
    if lower in PROPERTY_ALIASES:
        return PROPERTY_ALIASES[lower]

    # Try hyphenated -> UPPER_SNAKE
    enum_name = lower.replace("-", "_").upper()
    try:
        return PropertyIdentifier[enum_name]
    except KeyError:
        pass

    # Try as raw integer
    try:
        return PropertyIdentifier(int(lower))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown property identifier: {name!r}"
    raise ValueError(msg)


def parse_property_identifier(
    prop: str | int | PropertyIdentifier,
) -> PropertyIdentifier:
    """Parse a flexible property identifier to PropertyIdentifier.

    Accepted formats::

        "present-value"                   -> PropertyIdentifier.PRESENT_VALUE
        "present_value"                   -> PropertyIdentifier.PRESENT_VALUE
        "pv"                              -> PropertyIdentifier.PRESENT_VALUE
        "object-name"                     -> PropertyIdentifier.OBJECT_NAME
        "name"                            -> PropertyIdentifier.OBJECT_NAME
        85                                -> PropertyIdentifier(85)
        PropertyIdentifier.PRESENT_VALUE  -> pass-through

    Args:
        prop: Property identifier in any supported format.

    Returns:
        Parsed PropertyIdentifier.

    Raises:
        ValueError: If the format is not recognised.
    """
    if isinstance(prop, PropertyIdentifier):
        return prop
    if isinstance(prop, int):
        return PropertyIdentifier(prop)
    if isinstance(prop, str):
        return _resolve_property_identifier(prop)

    msg = f"Cannot parse property identifier from {type(prop).__name__}"
    raise ValueError(msg)
