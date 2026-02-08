"""BACnet Accumulator object per ASHRAE 135-2016 Clause 12.1."""

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
    EngineeringUnits,
    EventState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class AccumulatorObject(BACnetObject):
    """BACnet Accumulator object (Clause 12.1).

    Represents a pulse-counting device such as an energy meter or
    water meter.  Present_Value accumulates counts; Scale and Prescale
    control unit conversion.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ACCUMULATOR

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
            default=0,
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
        if PropertyIdentifier.SCALE not in self._properties:
            self._properties[PropertyIdentifier.SCALE] = 1.0
        if PropertyIdentifier.PRESCALE not in self._properties:
            self._properties[PropertyIdentifier.PRESCALE] = 1
