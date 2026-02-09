"""BACnet Accumulator object per ASHRAE 135-2016 Clause 12.2."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.enums import (
    EngineeringUnits,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class AccumulatorObject(BACnetObject):
    """BACnet Accumulator object (Clause 12.2).

    Represents a pulse-counting device such as an energy meter or
    water meter.  Present_Value accumulates counts; Scale and Prescale
    control unit conversion.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCUMULATOR

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        **status_properties(),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.SCALE: PropertyDefinition(
            PropertyIdentifier.SCALE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.PRESCALE: PropertyDefinition(
            PropertyIdentifier.PRESCALE,
            object,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0xFFFFFFFF,
        ),
        PropertyIdentifier.PULSE_RATE: PropertyDefinition(
            PropertyIdentifier.PULSE_RATE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.VALUE_BEFORE_CHANGE: PropertyDefinition(
            PropertyIdentifier.VALUE_BEFORE_CHANGE,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.VALUE_SET: PropertyDefinition(
            PropertyIdentifier.VALUE_SET,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.VALUE_CHANGE_TIME: PropertyDefinition(
            PropertyIdentifier.VALUE_CHANGE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EVENT_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_ENABLE,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
        self._set_default(PropertyIdentifier.SCALE, 1.0)
        self._set_default(PropertyIdentifier.PRESCALE, 1)
