"""BACnet Transportation objects per ASHRAE 135-2020 Clauses 12.58-12.60."""

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
    EscalatorMode,
    LiftCarDirection,
    LiftGroupMode,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class ElevatorGroupObject(BACnetObject):
    """BACnet Elevator Group object (Clause 12.58).

    Represents a group of lifts managed together for landing calls.
    Primarily a data container -- physical logic runs on the
    transportation controller.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ELEVATOR_GROUP

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.GROUP_ID: PropertyDefinition(
            PropertyIdentifier.GROUP_ID,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.GROUP_MEMBERS: PropertyDefinition(
            PropertyIdentifier.GROUP_MEMBERS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.GROUP_MODE: PropertyDefinition(
            PropertyIdentifier.GROUP_MODE,
            LiftGroupMode,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LiftGroupMode.UNKNOWN,
        ),
        PropertyIdentifier.LANDING_CALLS: PropertyDefinition(
            PropertyIdentifier.LANDING_CALLS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.LANDING_CALL_CONTROL: PropertyDefinition(
            PropertyIdentifier.LANDING_CALL_CONTROL,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.MACHINE_ROOM_ID: PropertyDefinition(
            PropertyIdentifier.MACHINE_ROOM_ID,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)


@register_object_type
class LiftObject(BACnetObject):
    """BACnet Lift object (Clause 12.59).

    Represents a single elevator car with position, direction, and door status.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.LIFT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.TRACKING_VALUE: PropertyDefinition(
            PropertyIdentifier.TRACKING_VALUE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.CAR_ASSIGNED_DIRECTION: PropertyDefinition(
            PropertyIdentifier.CAR_ASSIGNED_DIRECTION,
            LiftCarDirection,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LiftCarDirection.UNKNOWN,
        ),
        PropertyIdentifier.CAR_MOVING_DIRECTION: PropertyDefinition(
            PropertyIdentifier.CAR_MOVING_DIRECTION,
            LiftCarDirection,
            PropertyAccess.READ_ONLY,
            required=True,
            default=LiftCarDirection.UNKNOWN,
        ),
        PropertyIdentifier.CAR_POSITION: PropertyDefinition(
            PropertyIdentifier.CAR_POSITION,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.CAR_DOOR_STATUS: PropertyDefinition(
            PropertyIdentifier.CAR_DOOR_STATUS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.CAR_DOOR_TEXT: PropertyDefinition(
            PropertyIdentifier.CAR_DOOR_TEXT,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.CAR_DOOR_ZONE: PropertyDefinition(
            PropertyIdentifier.CAR_DOOR_ZONE,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.CAR_DRIVE_STATUS: PropertyDefinition(
            PropertyIdentifier.CAR_DRIVE_STATUS,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.CAR_LOAD: PropertyDefinition(
            PropertyIdentifier.CAR_LOAD,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.CAR_LOAD_UNITS: PropertyDefinition(
            PropertyIdentifier.CAR_LOAD_UNITS,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.CAR_MODE: PropertyDefinition(
            PropertyIdentifier.CAR_MODE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.ELEVATOR_GROUP: PropertyDefinition(
            PropertyIdentifier.ELEVATOR_GROUP,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.ENERGY_METER: PropertyDefinition(
            PropertyIdentifier.ENERGY_METER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.ENERGY_METER_REF: PropertyDefinition(
            PropertyIdentifier.ENERGY_METER_REF,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.FAULT_SIGNALS: PropertyDefinition(
            PropertyIdentifier.FAULT_SIGNALS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.FLOOR_TEXT: PropertyDefinition(
            PropertyIdentifier.FLOOR_TEXT,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.HIGHER_DECK: PropertyDefinition(
            PropertyIdentifier.HIGHER_DECK,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LOWER_DECK: PropertyDefinition(
            PropertyIdentifier.LOWER_DECK,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.LANDING_DOOR_STATUS: PropertyDefinition(
            PropertyIdentifier.LANDING_DOOR_STATUS,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.MAKING_CAR_CALL: PropertyDefinition(
            PropertyIdentifier.MAKING_CAR_CALL,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.NEXT_STOPPING_FLOOR: PropertyDefinition(
            PropertyIdentifier.NEXT_STOPPING_FLOOR,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.PASSENGER_ALARM: PropertyDefinition(
            PropertyIdentifier.PASSENGER_ALARM,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.REGISTERED_CAR_CALL: PropertyDefinition(
            PropertyIdentifier.REGISTERED_CAR_CALL,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.CAR_DOOR_COMMAND: PropertyDefinition(
            PropertyIdentifier.CAR_DOOR_COMMAND,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()


@register_object_type
class EscalatorObject(BACnetObject):
    """BACnet Escalator object (Clause 12.60).

    Represents an escalator with mode and fault reporting.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ESCALATOR

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(),
        PropertyIdentifier.ESCALATOR_MODE: PropertyDefinition(
            PropertyIdentifier.ESCALATOR_MODE,
            EscalatorMode,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EscalatorMode.UNKNOWN,
        ),
        PropertyIdentifier.FAULT_SIGNALS: PropertyDefinition(
            PropertyIdentifier.FAULT_SIGNALS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        PropertyIdentifier.ENERGY_METER: PropertyDefinition(
            PropertyIdentifier.ENERGY_METER,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.ENERGY_METER_REF: PropertyDefinition(
            PropertyIdentifier.ENERGY_METER_REF,
            object,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.INSTALLATION_ID: PropertyDefinition(
            PropertyIdentifier.INSTALLATION_ID,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.POWER_MODE: PropertyDefinition(
            PropertyIdentifier.POWER_MODE,
            bool,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.OPERATION_DIRECTION: PropertyDefinition(
            PropertyIdentifier.OPERATION_DIRECTION,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.PASSENGER_ALARM: PropertyDefinition(
            PropertyIdentifier.PASSENGER_ALARM,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
