"""BACnet Binary object types per ASHRAE 135-2016 Clause 12.6-12.8."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    commandable_properties,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    BinaryPV,
    ObjectType,
    Polarity,
    PropertyIdentifier,
)


@register_object_type
class BinaryInputObject(BACnetObject):
    """BACnet Binary Input object (Clause 12.6).

    Represents a binary sensor input (on/off, open/closed).
    Present_Value is read-only under normal operation and
    writable only when Out_Of_Service is TRUE.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_INPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **status_properties(),
        PropertyIdentifier.POLARITY: PropertyDefinition(
            PropertyIdentifier.POLARITY,
            Polarity,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Polarity.NORMAL,
        ),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class BinaryOutputObject(BACnetObject):
    """BACnet Binary Output object (Clause 12.7).

    Represents a binary actuator output (relay, fan on/off).
    Always commandable with a 16-level priority array.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_OUTPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **status_properties(),
        PropertyIdentifier.POLARITY: PropertyDefinition(
            PropertyIdentifier.POLARITY,
            Polarity,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Polarity.NORMAL,
        ),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_OFF_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_OFF_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_ON_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_ON_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(BinaryPV, BinaryPV.INACTIVE),
        PropertyIdentifier.FEEDBACK_VALUE: PropertyDefinition(
            PropertyIdentifier.FEEDBACK_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Always commandable
        self._init_commandable(BinaryPV.INACTIVE)
        self._init_status_flags()


@register_object_type
class BinaryValueObject(BACnetObject):
    """BACnet Binary Value object (Clause 12.8).

    Represents an internal binary status or configuration value.
    Optionally commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        **status_properties(),
        PropertyIdentifier.INACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.INACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ACTIVE_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTIVE_TEXT,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_OFF_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_OFF_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MINIMUM_ON_TIME: PropertyDefinition(
            PropertyIdentifier.MINIMUM_ON_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(BinaryPV, BinaryPV.INACTIVE, required=False),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        commandable: bool = False,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        if commandable:
            self._init_commandable(BinaryPV.INACTIVE)
        self._init_status_flags()
