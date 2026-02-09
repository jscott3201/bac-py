"""BACnet Life Safety object types per ASHRAE 135-2016 Clause 12.15-12.16."""

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
    LifeSafetyMode,
    LifeSafetyOperation,
    LifeSafetyState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
    SilencedState,
)


@register_object_type
class LifeSafetyPointObject(BACnetObject):
    """BACnet Life Safety Point object (Clause 12.15).

    Represents a fire/smoke/gas detector point or similar life safety
    sensor.  Present_Value reflects the current sensor state.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LIFE_SAFETY_POINT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            LifeSafetyState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyState.QUIET,
        ),
        PropertyIdentifier.TRACKING_VALUE: PropertyDefinition(
            PropertyIdentifier.TRACKING_VALUE,
            LifeSafetyState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyState.QUIET,
        ),
        **status_properties(
            reliability_required=True,
            reliability_default=Reliability.NO_FAULT_DETECTED,
        ),
        PropertyIdentifier.MODE: PropertyDefinition(
            PropertyIdentifier.MODE,
            LifeSafetyMode,
            PropertyAccess.READ_WRITE,
            required=True,
            default=LifeSafetyMode.ON,
        ),
        PropertyIdentifier.ACCEPTED_MODES: PropertyDefinition(
            PropertyIdentifier.ACCEPTED_MODES,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.SILENCED: PropertyDefinition(
            PropertyIdentifier.SILENCED,
            SilencedState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=SilencedState.UNSILENCED,
        ),
        PropertyIdentifier.OPERATION_EXPECTED: PropertyDefinition(
            PropertyIdentifier.OPERATION_EXPECTED,
            LifeSafetyOperation,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyOperation.NONE,
        ),
        PropertyIdentifier.SETTING: PropertyDefinition(
            PropertyIdentifier.SETTING,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.DIRECT_READING: PropertyDefinition(
            PropertyIdentifier.DIRECT_READING,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.UNITS: PropertyDefinition(
            PropertyIdentifier.UNITS,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MEMBER_OF: PropertyDefinition(
            PropertyIdentifier.MEMBER_OF,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.FAULT_VALUES: PropertyDefinition(
            PropertyIdentifier.FAULT_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LIFE_SAFETY_ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.LIFE_SAFETY_ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
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


@register_object_type
class LifeSafetyZoneObject(BACnetObject):
    """BACnet Life Safety Zone object (Clause 12.16).

    Represents a grouped area containing one or more life safety points.
    Present_Value reflects the aggregate zone state.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LIFE_SAFETY_ZONE

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            LifeSafetyState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyState.QUIET,
        ),
        PropertyIdentifier.TRACKING_VALUE: PropertyDefinition(
            PropertyIdentifier.TRACKING_VALUE,
            LifeSafetyState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyState.QUIET,
        ),
        **status_properties(
            reliability_required=True,
            reliability_default=Reliability.NO_FAULT_DETECTED,
        ),
        PropertyIdentifier.MODE: PropertyDefinition(
            PropertyIdentifier.MODE,
            LifeSafetyMode,
            PropertyAccess.READ_WRITE,
            required=True,
            default=LifeSafetyMode.ON,
        ),
        PropertyIdentifier.ACCEPTED_MODES: PropertyDefinition(
            PropertyIdentifier.ACCEPTED_MODES,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.SILENCED: PropertyDefinition(
            PropertyIdentifier.SILENCED,
            SilencedState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=SilencedState.UNSILENCED,
        ),
        PropertyIdentifier.OPERATION_EXPECTED: PropertyDefinition(
            PropertyIdentifier.OPERATION_EXPECTED,
            LifeSafetyOperation,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LifeSafetyOperation.NONE,
        ),
        PropertyIdentifier.ZONE_MEMBERS: PropertyDefinition(
            PropertyIdentifier.ZONE_MEMBERS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.MEMBER_OF: PropertyDefinition(
            PropertyIdentifier.MEMBER_OF,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.FAULT_VALUES: PropertyDefinition(
            PropertyIdentifier.FAULT_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LIFE_SAFETY_ALARM_VALUES: PropertyDefinition(
            PropertyIdentifier.LIFE_SAFETY_ALARM_VALUES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
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
