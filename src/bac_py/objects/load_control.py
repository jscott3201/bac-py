"""BACnet Load Control object per ASHRAE 135-2020 Clause 12.28."""

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
from bac_py.types.constructed import BACnetDateTime, BACnetShedLevel
from bac_py.types.enums import (
    ObjectType,
    PropertyIdentifier,
    ShedState,
)


@register_object_type
class LoadControlObject(BACnetObject):
    """BACnet Load Control object (Clause 12.28).

    Manages demand-limiting shed operations.  Accepts shed requests
    specifying level and duration, and reports compliance state.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LOAD_CONTROL

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            ShedState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=ShedState.SHED_INACTIVE,
        ),
        **status_properties(),
        PropertyIdentifier.STATE_DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.STATE_DESCRIPTION,
            str,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.REQUESTED_SHED_LEVEL: PropertyDefinition(
            PropertyIdentifier.REQUESTED_SHED_LEVEL,
            BACnetShedLevel,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EXPECTED_SHED_LEVEL: PropertyDefinition(
            PropertyIdentifier.EXPECTED_SHED_LEVEL,
            BACnetShedLevel,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.ACTUAL_SHED_LEVEL: PropertyDefinition(
            PropertyIdentifier.ACTUAL_SHED_LEVEL,
            BACnetShedLevel,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.SHED_DURATION: PropertyDefinition(
            PropertyIdentifier.SHED_DURATION,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.DUTY_WINDOW: PropertyDefinition(
            PropertyIdentifier.DUTY_WINDOW,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.FULL_DUTY_BASELINE: PropertyDefinition(
            PropertyIdentifier.FULL_DUTY_BASELINE,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.SHED_LEVELS: PropertyDefinition(
            PropertyIdentifier.SHED_LEVELS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.SHED_LEVEL_DESCRIPTIONS: PropertyDefinition(
            PropertyIdentifier.SHED_LEVEL_DESCRIPTIONS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.START_TIME: PropertyDefinition(
            PropertyIdentifier.START_TIME,
            BACnetDateTime,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
