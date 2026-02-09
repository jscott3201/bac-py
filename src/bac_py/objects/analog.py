"""BACnet Analog object types per ASHRAE 135-2016 Clause 12.2-12.4."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    commandable_properties,
    intrinsic_reporting_properties,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    EngineeringUnits,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)


class _AnalogBase(BACnetObject):
    """Shared validation for analog object types.

    Validates Present_Value against Min/Max_Pres_Value on writes (V2)
    and ensures COV_Increment is non-negative (V3).
    """

    def write_property(
        self,
        prop_id: PropertyIdentifier,
        value: Any,
        priority: int | None = None,
        array_index: int | None = None,
    ) -> None:
        if prop_id == PropertyIdentifier.PRESENT_VALUE and isinstance(value, (int, float)):
            min_val = self._properties.get(PropertyIdentifier.MIN_PRES_VALUE)
            max_val = self._properties.get(PropertyIdentifier.MAX_PRES_VALUE)
            if min_val is not None and value < min_val:
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_OUT_OF_RANGE)
            if max_val is not None and value > max_val:
                raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_OUT_OF_RANGE)
        if (
            prop_id == PropertyIdentifier.COV_INCREMENT
            and isinstance(value, (int, float))
            and value < 0
        ):
            raise BACnetError(ErrorClass.PROPERTY, ErrorCode.VALUE_OUT_OF_RANGE)
        super().write_property(prop_id, value, priority, array_index)


@register_object_type
class AnalogInputObject(_AnalogBase):
    """BACnet Analog Input object (Clause 12.2).

    Represents an analog sensor input.  Present_Value is read-only
    under normal operation and writable only when Out_Of_Service is TRUE.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ANALOG_INPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.UPDATE_INTERVAL: PropertyDefinition(
            PropertyIdentifier.UPDATE_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **intrinsic_reporting_properties(include_limit=True),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class AnalogOutputObject(_AnalogBase):
    """BACnet Analog Output object (Clause 12.3).

    Represents an analog actuator output.  Always commandable with
    a 16-level priority array.  Present_Value is writable.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ANALOG_OUTPUT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        **commandable_properties(float, 0.0),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.DEVICE_TYPE: PropertyDefinition(
            PropertyIdentifier.DEVICE_TYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **intrinsic_reporting_properties(include_limit=True),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Always commandable
        self._init_commandable(0.0)
        self._init_status_flags()


@register_object_type
class AnalogValueObject(_AnalogBase):
    """BACnet Analog Value object (Clause 12.4).

    Represents an analog configuration parameter or calculated value.
    Optionally commandable when constructed with ``commandable=True``.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ANALOG_VALUE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        **commandable_properties(float, 0.0, required=False),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **intrinsic_reporting_properties(include_limit=True),
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
            self._init_commandable(0.0)
        self._init_status_flags()
