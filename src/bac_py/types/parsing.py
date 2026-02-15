"""Flexible parsing helpers for BACnet object and property identifiers."""

from __future__ import annotations

from functools import lru_cache

from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

OBJECT_TYPE_ALIASES: dict[str, ObjectType] = {
    # Analog I/O
    "ai": ObjectType.ANALOG_INPUT,
    "ao": ObjectType.ANALOG_OUTPUT,
    "av": ObjectType.ANALOG_VALUE,
    "lav": ObjectType.LARGE_ANALOG_VALUE,
    # Binary I/O
    "bi": ObjectType.BINARY_INPUT,
    "bo": ObjectType.BINARY_OUTPUT,
    "bv": ObjectType.BINARY_VALUE,
    "blo": ObjectType.BINARY_LIGHTING_OUTPUT,
    # Multi-state I/O
    "msi": ObjectType.MULTI_STATE_INPUT,
    "mso": ObjectType.MULTI_STATE_OUTPUT,
    "msv": ObjectType.MULTI_STATE_VALUE,
    # Infrastructure
    "dev": ObjectType.DEVICE,
    "file": ObjectType.FILE,
    "nc": ObjectType.NOTIFICATION_CLASS,
    "np": ObjectType.NETWORK_PORT,
    "cal": ObjectType.CALENDAR,
    "cmd": ObjectType.COMMAND,
    "ch": ObjectType.CHANNEL,
    "prog": ObjectType.PROGRAM,
    # Scheduling & trending
    "sched": ObjectType.SCHEDULE,
    "tl": ObjectType.TREND_LOG,
    "tlm": ObjectType.TREND_LOG_MULTIPLE,
    "el": ObjectType.EVENT_LOG,
    # Control
    "lp": ObjectType.LOOP,
    "lo": ObjectType.LIGHTING_OUTPUT,
    "lc": ObjectType.LOAD_CONTROL,
    "acc": ObjectType.ACCUMULATOR,
    "pc": ObjectType.PULSE_CONVERTER,
    "tmr": ObjectType.TIMER,
    # Monitoring & events
    "ee": ObjectType.EVENT_ENROLLMENT,
    "ae": ObjectType.ALERT_ENROLLMENT,
    "nf": ObjectType.NOTIFICATION_FORWARDER,
    "avg": ObjectType.AVERAGING,
    # Value types
    "iv": ObjectType.INTEGER_VALUE,
    "piv": ObjectType.POSITIVE_INTEGER_VALUE,
    "csv": ObjectType.CHARACTERSTRING_VALUE,
    "bsv": ObjectType.BITSTRING_VALUE,
    "osv": ObjectType.OCTETSTRING_VALUE,
    "dv": ObjectType.DATE_VALUE,
    "dtv": ObjectType.DATETIME_VALUE,
    "tv": ObjectType.TIME_VALUE,
    # Structure & grouping
    "sv": ObjectType.STRUCTURED_VIEW,
    "grp": ObjectType.GROUP,
    "gg": ObjectType.GLOBAL_GROUP,
    # Specialty
    "lsp": ObjectType.LIFE_SAFETY_POINT,
    "lsz": ObjectType.LIFE_SAFETY_ZONE,
    # Access control
    "ad": ObjectType.ACCESS_DOOR,
    "ap": ObjectType.ACCESS_POINT,
    # Audit
    "ar": ObjectType.AUDIT_REPORTER,
    "al": ObjectType.AUDIT_LOG,
}
"""Short aliases for commonly used object types.

Full hyphenated names (e.g. ``"analog-input"``) and underscore names
(e.g. ``"ANALOG_INPUT"``) are always accepted via :func:`_resolve_object_type`
without needing an alias entry here.
"""

PROPERTY_ALIASES: dict[str, PropertyIdentifier] = {
    # Core properties
    "pv": PropertyIdentifier.PRESENT_VALUE,
    "name": PropertyIdentifier.OBJECT_NAME,
    "type": PropertyIdentifier.OBJECT_TYPE,
    "desc": PropertyIdentifier.DESCRIPTION,
    "units": PropertyIdentifier.UNITS,
    "status": PropertyIdentifier.STATUS_FLAGS,
    "oos": PropertyIdentifier.OUT_OF_SERVICE,
    "reliability": PropertyIdentifier.RELIABILITY,
    "event-state": PropertyIdentifier.EVENT_STATE,
    # Object list & identification
    "list": PropertyIdentifier.OBJECT_LIST,
    "prop-list": PropertyIdentifier.PROPERTY_LIST,
    "profile-name": PropertyIdentifier.PROFILE_NAME,
    # Commandable properties
    "priority": PropertyIdentifier.PRIORITY_ARRAY,
    "relinquish": PropertyIdentifier.RELINQUISH_DEFAULT,
    # Analog properties
    "min": PropertyIdentifier.MIN_PRES_VALUE,
    "max": PropertyIdentifier.MAX_PRES_VALUE,
    "res": PropertyIdentifier.RESOLUTION,
    "cov-inc": PropertyIdentifier.COV_INCREMENT,
    "deadband": PropertyIdentifier.DEADBAND,
    "high-limit": PropertyIdentifier.HIGH_LIMIT,
    "low-limit": PropertyIdentifier.LOW_LIMIT,
    # Binary/multistate properties
    "polarity": PropertyIdentifier.POLARITY,
    "active-text": PropertyIdentifier.ACTIVE_TEXT,
    "inactive-text": PropertyIdentifier.INACTIVE_TEXT,
    "num-states": PropertyIdentifier.NUMBER_OF_STATES,
    "state-text": PropertyIdentifier.STATE_TEXT,
    # Event/alarm properties
    "event-enable": PropertyIdentifier.EVENT_ENABLE,
    "acked-transitions": PropertyIdentifier.ACKED_TRANSITIONS,
    "notify-type": PropertyIdentifier.NOTIFY_TYPE,
    "time-delay": PropertyIdentifier.TIME_DELAY,
    "notify-class": PropertyIdentifier.NOTIFICATION_CLASS,
    "limit-enable": PropertyIdentifier.LIMIT_ENABLE,
    # Scheduling & trending
    "log-buffer": PropertyIdentifier.LOG_BUFFER,
    "record-count": PropertyIdentifier.RECORD_COUNT,
    "enable": PropertyIdentifier.LOG_ENABLE,
    "weekly-schedule": PropertyIdentifier.WEEKLY_SCHEDULE,
    "exception-schedule": PropertyIdentifier.EXCEPTION_SCHEDULE,
    "schedule-default": PropertyIdentifier.SCHEDULE_DEFAULT,
    # Device properties
    "system-status": PropertyIdentifier.SYSTEM_STATUS,
    "vendor-name": PropertyIdentifier.VENDOR_NAME,
    "vendor-id": PropertyIdentifier.VENDOR_IDENTIFIER,
    "model-name": PropertyIdentifier.MODEL_NAME,
    "firmware-rev": PropertyIdentifier.FIRMWARE_REVISION,
    "app-version": PropertyIdentifier.APPLICATION_SOFTWARE_VERSION,
    "protocol-version": PropertyIdentifier.PROTOCOL_VERSION,
    "protocol-revision": PropertyIdentifier.PROTOCOL_REVISION,
    "max-apdu": PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED,
    "seg-supported": PropertyIdentifier.SEGMENTATION_SUPPORTED,
    "db-revision": PropertyIdentifier.DATABASE_REVISION,
}
"""Short aliases for commonly used property identifiers.

Full hyphenated names (e.g. ``"present-value"``) and underscore names
(e.g. ``"PRESENT_VALUE"``) are always accepted via
:func:`_resolve_property_identifier` without needing an alias entry here.
"""


@lru_cache(maxsize=256)
def _resolve_object_type(name: str) -> ObjectType:
    """Resolve an object type name to an :class:`~bac_py.types.enums.ObjectType`.

    Accepts short aliases (e.g. ``"ai"``), hyphenated names
    (e.g. ``"analog-input"``), underscore names (e.g. ``"ANALOG_INPUT"``),
    or raw integer strings.

    Results are cached so repeated lookups of the same alias (e.g. ``"ai"``)
    are O(1) after the first call.

    :param name: Object type name in any supported format.
    :returns: Resolved :class:`~bac_py.types.enums.ObjectType` member.
    :raises ValueError: If *name* is not recognised.
    """
    lower = name.lower().strip()

    if lower in OBJECT_TYPE_ALIASES:
        return OBJECT_TYPE_ALIASES[lower]

    enum_name = lower.replace("-", "_").upper()
    try:
        return ObjectType[enum_name]
    except KeyError:
        pass

    try:
        return ObjectType(int(lower))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown object type: {name!r}"
    raise ValueError(msg)


def parse_object_identifier(
    obj: str | tuple[str | ObjectType | int, int] | ObjectIdentifier,
) -> ObjectIdentifier:
    """Parse a flexible object identifier to :class:`~bac_py.types.primitives.ObjectIdentifier`.

    Accepted formats::

        "analog-input,1"                  -> ObjectIdentifier(ANALOG_INPUT, 1)
        "analog-input:1"                  -> ObjectIdentifier(ANALOG_INPUT, 1)
        "ai,1"                            -> ObjectIdentifier(ANALOG_INPUT, 1)
        ("analog-input", 1)               -> ObjectIdentifier(ANALOG_INPUT, 1)
        (ObjectType.ANALOG_INPUT, 1)      -> ObjectIdentifier(ANALOG_INPUT, 1)
        (0, 1)                            -> ObjectIdentifier(ANALOG_INPUT, 1)
        ObjectIdentifier(...)             -> pass-through

    :param obj: Object identifier in any supported format.
    :returns: Parsed :class:`~bac_py.types.primitives.ObjectIdentifier`.
    :raises ValueError: If the format is not recognised.
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


@lru_cache(maxsize=512)
def _resolve_property_identifier(name: str) -> PropertyIdentifier:
    """Resolve a property name to a :class:`~bac_py.types.enums.PropertyIdentifier`.

    Accepts short aliases (e.g. ``"pv"``), hyphenated names
    (e.g. ``"present-value"``), underscore names (e.g. ``"PRESENT_VALUE"``),
    or raw integer strings.

    Results are cached so repeated lookups of the same alias (e.g. ``"pv"``)
    are O(1) after the first call.

    :param name: Property name in any supported format.
    :returns: Resolved :class:`~bac_py.types.enums.PropertyIdentifier` member.
    :raises ValueError: If *name* is not recognised.
    """
    lower = name.lower().strip()

    if lower in PROPERTY_ALIASES:
        return PROPERTY_ALIASES[lower]

    enum_name = lower.replace("-", "_").upper()
    try:
        return PropertyIdentifier[enum_name]
    except KeyError:
        pass

    try:
        return PropertyIdentifier(int(lower))
    except (ValueError, KeyError):
        pass

    msg = f"Unknown property identifier: {name!r}"
    raise ValueError(msg)


def parse_property_identifier(
    prop: str | int | PropertyIdentifier,
) -> PropertyIdentifier:
    """Parse a flexible property identifier to :class:`~bac_py.types.enums.PropertyIdentifier`.

    Accepted formats::

        "present-value"                   -> PropertyIdentifier.PRESENT_VALUE
        "present_value"                   -> PropertyIdentifier.PRESENT_VALUE
        "pv"                              -> PropertyIdentifier.PRESENT_VALUE
        "object-name"                     -> PropertyIdentifier.OBJECT_NAME
        "name"                            -> PropertyIdentifier.OBJECT_NAME
        85                                -> PropertyIdentifier(85)
        PropertyIdentifier.PRESENT_VALUE  -> pass-through

    :param prop: Property identifier in any supported format.
    :returns: Parsed :class:`~bac_py.types.enums.PropertyIdentifier`.
    :raises ValueError: If the format is not recognised.
    """
    if isinstance(prop, PropertyIdentifier):
        return prop
    if isinstance(prop, int):
        return PropertyIdentifier(prop)
    if isinstance(prop, str):
        return _resolve_property_identifier(prop)

    msg = f"Cannot parse property identifier from {type(prop).__name__}"
    raise ValueError(msg)
