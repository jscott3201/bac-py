"""BACnet Multi-State object types per ASHRAE 135-2016 Clause 12.18-12.20."""

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
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)


class _MultiStateBase(BACnetObject):
    """Shared validation for multi-state object types.

    Validates that Present_Value is within 1..Number_Of_States
    on writes per Clause 12.18/12.19/12.20.
    """

    def write_property(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        if prop_id == PropertyIdentifier.PRESENT_VALUE and isinstance(value, int):
            num_states = self._properties.get(PropertyIdentifier.NUMBER_OF_STATES)
            if num_states is not None and (value < 1 or value > num_states):
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_OUT_OF_RANGE)
        super().write_property(prop_id, value, priority, array_index)


@register_object_type
class MultiStateInputObject(_MultiStateBase):
    """BACnet Multi-State Input object (Clause 12.18).

    Represents an enumerated sensor input with N possible states.
    Present_Value is a 1-based unsigned integer (1..Number_Of_States).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_INPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=1,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
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
    }

    def __init__(
        self,
        instance_number: int,
        *,
        number_of_states: int = 2,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        self._set_default(PropertyIdentifier.NUMBER_OF_STATES, number_of_states)
        self._init_status_flags()


@register_object_type
class MultiStateOutputObject(_MultiStateBase):
    """BACnet Multi-State Output object (Clause 12.19).

    Represents an enumerated actuator command with N possible states.
    Always commandable with a 16-level priority array.
    Present_Value is a 1-based unsigned integer.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_OUTPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
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
        **commandable_properties(int, 1),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        number_of_states: int = 2,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        self._set_default(PropertyIdentifier.NUMBER_OF_STATES, number_of_states)
        # Always commandable
        self._init_commandable(1)
        self._init_status_flags()


@register_object_type
class MultiStateValueObject(_MultiStateBase):
    """BACnet Multi-State Value object (Clause 12.20).

    Represents an enumerated configuration or status value.
    Optionally commandable when constructed with ``commandable=True``.
    Present_Value is a 1-based unsigned integer.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.MULTI_STATE_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1,
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
        **commandable_properties(int, 1, required=False),
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
        self._set_default(PropertyIdentifier.NUMBER_OF_STATES, number_of_states)
        if commandable:
            self._init_commandable(1)
        self._init_status_flags()
