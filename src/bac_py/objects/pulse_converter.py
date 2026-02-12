"""BACnet Pulse Converter object per ASHRAE 135-2020 Clause 12.23."""

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
from bac_py.types.enums import (
    EngineeringUnits,
    EventType,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class PulseConverterObject(BACnetObject):
    """BACnet Pulse Converter object (Clause 12.23).

    Converts pulse counts to analog values using a scale factor.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.PULSE_CONVERTER
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.OUT_OF_RANGE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        **status_properties(),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            EngineeringUnits,
            PropertyAccess.READ_WRITE,
            required=True,
            default=EngineeringUnits.NO_UNITS,
        ),
        PropertyIdentifier.SCALE_FACTOR: PropertyDefinition(
            PropertyIdentifier.SCALE_FACTOR,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1.0,
        ),
        PropertyIdentifier.INPUT_REFERENCE: PropertyDefinition(
            PropertyIdentifier.INPUT_REFERENCE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.COUNT: PropertyDefinition(
            PropertyIdentifier.COUNT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.COUNT_BEFORE_CHANGE: PropertyDefinition(
            PropertyIdentifier.COUNT_BEFORE_CHANGE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.COUNT_CHANGE_TIME: PropertyDefinition(
            PropertyIdentifier.COUNT_CHANGE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.UPDATE_TIME: PropertyDefinition(
            PropertyIdentifier.UPDATE_TIME,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.COV_PERIOD: PropertyDefinition(
            PropertyIdentifier.COV_PERIOD,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ADJUST_VALUE: PropertyDefinition(
            PropertyIdentifier.ADJUST_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LIMIT_MONITORING_INTERVAL: PropertyDefinition(
            PropertyIdentifier.LIMIT_MONITORING_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **commandable_properties(float, 0.0, required=False),
        **intrinsic_reporting_properties(include_limit=True),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
