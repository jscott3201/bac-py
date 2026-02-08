"""BACnet Schedule object per ASHRAE 135-2016 Clause 12.24."""

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
class ScheduleObject(BACnetObject):
    """BACnet Schedule object (Clause 12.24).

    Provides time-based scheduling with weekly schedules and
    exception schedules.  Present_Value is computed from the
    active schedule entry for the current time.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.SCHEDULE

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
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
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
            required=False,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Reliability.NO_FAULT_DETECTED,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
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
        if PropertyIdentifier.EFFECTIVE_PERIOD not in self._properties:
            self._properties[PropertyIdentifier.EFFECTIVE_PERIOD] = (
                (1900, 1, 1),
                (2155, 12, 31),
            )
        if PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES not in self._properties:
            self._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = []
        if PropertyIdentifier.PRIORITY_FOR_WRITING not in self._properties:
            self._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 16
        if PropertyIdentifier.SCHEDULE_DEFAULT not in self._properties:
            self._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = None
