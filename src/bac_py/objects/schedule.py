"""BACnet Schedule object per ASHRAE 135-2016 Clause 12.24."""

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
    ObjectType,
    PropertyIdentifier,
    Reliability,
)


@register_object_type
class ScheduleObject(BACnetObject):
    """BACnet Schedule object (Clause 12.24).

    Provides time-based scheduling with weekly schedules and
    exception schedules.  Present_Value is computed from the
    active schedule entry for the current time.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.SCHEDULE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            object,  # Polymorphic: actual type depends on Schedule_Default
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EFFECTIVE_PERIOD: PropertyDefinition(
            PropertyIdentifier.EFFECTIVE_PERIOD,
            tuple,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.WEEKLY_SCHEDULE: PropertyDefinition(
            PropertyIdentifier.WEEKLY_SCHEDULE,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EXCEPTION_SCHEDULE: PropertyDefinition(
            PropertyIdentifier.EXCEPTION_SCHEDULE,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.SCHEDULE_DEFAULT: PropertyDefinition(
            PropertyIdentifier.SCHEDULE_DEFAULT,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES: PropertyDefinition(
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.PRIORITY_FOR_WRITING: PropertyDefinition(
            PropertyIdentifier.PRIORITY_FOR_WRITING,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=16,
        ),
        **status_properties(
            event_state_required=False,
            reliability_required=True,
            reliability_default=Reliability.NO_FAULT_DETECTED,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
        self._set_default(
            PropertyIdentifier.EFFECTIVE_PERIOD,
            ((1900, 1, 1), (2155, 12, 31)),
        )
        self._set_default(PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES, [])
        self._set_default(PropertyIdentifier.PRIORITY_FOR_WRITING, 16)
        self._set_default(PropertyIdentifier.SCHEDULE_DEFAULT, None)
