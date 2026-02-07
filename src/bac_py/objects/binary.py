"""BACnet Binary object types per ASHRAE 135-2016 Clause 12.6-12.8."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
)
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    BinaryPV,
    EventState,
    ObjectType,
    Polarity,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class BinaryInputObject(BACnetObject):
    """BACnet Binary Input object (Clause 12.6).

    Represents a binary sensor input (on/off, open/closed).
    Present_Value is read-only under normal operation and
    writable only when Out_Of_Service is TRUE.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_INPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS,
            StatusFlags,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE,
            EventState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
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
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class BinaryOutputObject(BACnetObject):
    """BACnet Binary Output object (Clause 12.7).

    Represents a binary actuator output (relay, fan on/off).
    Always commandable with a 16-level priority array.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_OUTPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS,
            StatusFlags,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE,
            EventState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.FEEDBACK_VALUE: PropertyDefinition(
            PropertyIdentifier.FEEDBACK_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Always commandable
        self._priority_array = [None] * 16
        self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class BinaryValueObject(BACnetObject):
    """BACnet Binary Value object (Clause 12.8).

    Represents an internal binary status or configuration value.
    Optionally commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_NAME: PropertyDefinition(
            PropertyIdentifier.OBJECT_NAME,
            str,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS,
            StatusFlags,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE,
            EventState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
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
        PropertyIdentifier.PRIORITY_ARRAY: PropertyDefinition(
            PropertyIdentifier.PRIORITY_ARRAY,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CURRENT_COMMAND_PRIORITY: PropertyDefinition(
            PropertyIdentifier.CURRENT_COMMAND_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROPERTY_LIST: PropertyDefinition(
            PropertyIdentifier.PROPERTY_LIST,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
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
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = BinaryPV.INACTIVE
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()
