"""BACnet Lighting objects per ASHRAE 135-2020 Clauses 12.54-12.55."""

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
from bac_py.types.constructed import BACnetLightingCommand
from bac_py.types.enums import (
    BinaryPV,
    EventType,
    LightingInProgress,
    LightingOperation,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class LightingOutputObject(BACnetObject):
    """BACnet Lighting Output object (Clause 12.54).

    Dimmable lighting control with fade, ramp, and step operations.
    Present_Value represents the current lighting level (0.0--100.0%).
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LIGHTING_OUTPUT
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
        PropertyIdentifier.TRACKING_VALUE: PropertyDefinition(
            PropertyIdentifier.TRACKING_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.LIGHTING_COMMAND: PropertyDefinition(
            PropertyIdentifier.LIGHTING_COMMAND,
            BACnetLightingCommand,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.IN_PROGRESS: PropertyDefinition(
            PropertyIdentifier.IN_PROGRESS,
            LightingInProgress,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LightingInProgress.IDLE,
        ),
        **status_properties(),
        **commandable_properties(float, 0.0),
        PropertyIdentifier.LIGHTING_COMMAND_DEFAULT_PRIORITY: PropertyDefinition(
            PropertyIdentifier.LIGHTING_COMMAND_DEFAULT_PRIORITY,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=16,
        ),
        PropertyIdentifier.COV_INCREMENT: PropertyDefinition(
            PropertyIdentifier.COV_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.BLINK_WARN_ENABLE: PropertyDefinition(
            PropertyIdentifier.BLINK_WARN_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.EGRESS_TIME: PropertyDefinition(
            PropertyIdentifier.EGRESS_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EGRESS_ACTIVE: PropertyDefinition(
            PropertyIdentifier.EGRESS_ACTIVE,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
            default=False,
        ),
        PropertyIdentifier.DEFAULT_FADE_TIME: PropertyDefinition(
            PropertyIdentifier.DEFAULT_FADE_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.DEFAULT_RAMP_RATE: PropertyDefinition(
            PropertyIdentifier.DEFAULT_RAMP_RATE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=100.0,
        ),
        PropertyIdentifier.DEFAULT_STEP_INCREMENT: PropertyDefinition(
            PropertyIdentifier.DEFAULT_STEP_INCREMENT,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=1.0,
        ),
        PropertyIdentifier.TRANSITION: PropertyDefinition(
            PropertyIdentifier.TRANSITION,
            LightingOperation,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.INSTANTANEOUS_POWER: PropertyDefinition(
            PropertyIdentifier.INSTANTANEOUS_POWER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MIN_ACTUAL_VALUE: PropertyDefinition(
            PropertyIdentifier.MIN_ACTUAL_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.MAX_ACTUAL_VALUE: PropertyDefinition(
            PropertyIdentifier.MAX_ACTUAL_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.POWER: PropertyDefinition(
            PropertyIdentifier.POWER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **intrinsic_reporting_properties(include_limit=True),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_commandable(0.0)
        self._init_status_flags()


@register_object_type
class BinaryLightingOutputObject(BACnetObject):
    """BACnet Binary Lighting Output object (Clause 12.55).

    On/off lighting control with optional blink and warn patterns.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.BINARY_LIGHTING_OUTPUT
    INTRINSIC_EVENT_ALGORITHM: ClassVar[EventType | None] = EventType.CHANGE_OF_STATE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            BinaryPV,
            PropertyAccess.READ_WRITE,
            required=True,
            default=BinaryPV.INACTIVE,
        ),
        **status_properties(),
        **commandable_properties(BinaryPV, BinaryPV.INACTIVE),
        PropertyIdentifier.LIGHTING_COMMAND: PropertyDefinition(
            PropertyIdentifier.LIGHTING_COMMAND,
            BACnetLightingCommand,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.LIGHTING_COMMAND_DEFAULT_PRIORITY: PropertyDefinition(
            PropertyIdentifier.LIGHTING_COMMAND_DEFAULT_PRIORITY,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=16,
        ),
        PropertyIdentifier.BLINK_WARN_ENABLE: PropertyDefinition(
            PropertyIdentifier.BLINK_WARN_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=False,
        ),
        PropertyIdentifier.EGRESS_TIME: PropertyDefinition(
            PropertyIdentifier.EGRESS_TIME,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.EGRESS_ACTIVE: PropertyDefinition(
            PropertyIdentifier.EGRESS_ACTIVE,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
            default=False,
        ),
        PropertyIdentifier.POWER: PropertyDefinition(
            PropertyIdentifier.POWER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.INSTANTANEOUS_POWER: PropertyDefinition(
            PropertyIdentifier.INSTANTANEOUS_POWER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.FEEDBACK_VALUE: PropertyDefinition(
            PropertyIdentifier.FEEDBACK_VALUE,
            BinaryPV,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        **intrinsic_reporting_properties(),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_commandable(BinaryPV.INACTIVE)
        self._init_status_flags()
