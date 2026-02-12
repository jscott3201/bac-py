"""BACnet Timer object per ASHRAE 135-2020 Clause 12.57."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    intrinsic_reporting_properties,
    register_object_type,
    standard_properties,
    status_properties,
)
from bac_py.types.constructed import BACnetDateTime
from bac_py.types.enums import (
    EventType,
    ObjectType,
    PropertyIdentifier,
    TimerState,
    TimerTransition,
)


@register_object_type
class TimerObject(BACnetObject):
    """BACnet Timer object (Clause 12.57).

    Provides countdown and periodic timer functionality with a
    state machine (IDLE, RUNNING, EXPIRED).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.TIMER
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.CHANGE_OF_TIMER

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        **status_properties(),
        PropertyIdentifier.TIMER_STATE: PropertyDefinition(
            PropertyIdentifier.TIMER_STATE,
            TimerState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=TimerState.IDLE,
        ),
        PropertyIdentifier.TIMER_RUNNING: PropertyDefinition(
            PropertyIdentifier.TIMER_RUNNING,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.UPDATE_TIME: PropertyDefinition(
            PropertyIdentifier.UPDATE_TIME,
            BACnetDateTime,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LAST_STATE_CHANGE: PropertyDefinition(
            PropertyIdentifier.LAST_STATE_CHANGE,
            TimerTransition,
            PropertyAccess.READ_ONLY,
            required=True,
            default=TimerTransition.NONE,
        ),
        PropertyIdentifier.EXPIRATION_TIME: PropertyDefinition(
            PropertyIdentifier.EXPIRATION_TIME,
            BACnetDateTime,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.INITIAL_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.INITIAL_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.DEFAULT_TIMEOUT: PropertyDefinition(
            PropertyIdentifier.DEFAULT_TIMEOUT,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MIN_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_PRES_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MAX_PRES_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_PRES_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.RESOLUTION: PropertyDefinition(
            PropertyIdentifier.RESOLUTION,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.STATE_CHANGE_VALUES: PropertyDefinition(
            PropertyIdentifier.STATE_CHANGE_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES: PropertyDefinition(
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.PRIORITY_FOR_WRITING: PropertyDefinition(
            PropertyIdentifier.PRIORITY_FOR_WRITING,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **intrinsic_reporting_properties(),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
