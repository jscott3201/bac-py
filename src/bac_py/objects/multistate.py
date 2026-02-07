"""BACnet Multi-State object types per ASHRAE 135-2016 Clause 12.18-12.20."""

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
    EventState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class MultiStateInputObject(BACnetObject):
    """BACnet Multi-State Input object (Clause 12.18).

    Represents an enumerated sensor input with N possible states.
    Present_Value is a 1-based unsigned integer (1..Number_Of_States).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_INPUT

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
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=1,
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
        PropertyIdentifier.NUMBER_OF_STATES: PropertyDefinition(
            PropertyIdentifier.NUMBER_OF_STATES,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.STATE_TEXT: PropertyDefinition(
            PropertyIdentifier.STATE_TEXT,
            list,
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

    def __init__(
        self,
        instance_number: int,
        *,
        number_of_states: int = 2,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        if PropertyIdentifier.NUMBER_OF_STATES not in self._properties:
            self._properties[PropertyIdentifier.NUMBER_OF_STATES] = number_of_states
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class MultiStateOutputObject(BACnetObject):
    """BACnet Multi-State Output object (Clause 12.19).

    Represents an enumerated actuator command with N possible states.
    Always commandable with a 16-level priority array.
    Present_Value is a 1-based unsigned integer.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_OUTPUT

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
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1,
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
        PropertyIdentifier.NUMBER_OF_STATES: PropertyDefinition(
            PropertyIdentifier.NUMBER_OF_STATES,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.STATE_TEXT: PropertyDefinition(
            PropertyIdentifier.STATE_TEXT,
            list,
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
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1,
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

    def __init__(
        self,
        instance_number: int,
        *,
        number_of_states: int = 2,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        if PropertyIdentifier.NUMBER_OF_STATES not in self._properties:
            self._properties[PropertyIdentifier.NUMBER_OF_STATES] = number_of_states
        # Always commandable
        self._priority_array = [None] * 16
        self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()


@register_object_type
class MultiStateValueObject(BACnetObject):
    """BACnet Multi-State Value object (Clause 12.20).

    Represents an enumerated configuration or status value.
    Optionally commandable when constructed with ``commandable=True``.
    Present_Value is a 1-based unsigned integer.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_VALUE

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
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1,
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
        PropertyIdentifier.NUMBER_OF_STATES: PropertyDefinition(
            PropertyIdentifier.NUMBER_OF_STATES,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.STATE_TEXT: PropertyDefinition(
            PropertyIdentifier.STATE_TEXT,
            list,
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
            int,
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
        number_of_states: int = 2,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        if PropertyIdentifier.NUMBER_OF_STATES not in self._properties:
            self._properties[PropertyIdentifier.NUMBER_OF_STATES] = number_of_states
        if commandable:
            self._priority_array = [None] * 16
            self._properties[PropertyIdentifier.PRIORITY_ARRAY] = self._priority_array
            if PropertyIdentifier.RELINQUISH_DEFAULT not in self._properties:
                self._properties[PropertyIdentifier.RELINQUISH_DEFAULT] = 1
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()
