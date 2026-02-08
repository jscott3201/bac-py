"""BACnet Program object per ASHRAE 135-2016 Clause 12.22."""

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
    ProgramChange,
    ProgramState,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class ProgramObject(BACnetObject):
    """BACnet Program object (Clause 12.22).

    Represents an application program that can be loaded, run,
    halted, and unloaded.  Program_State indicates the current
    execution state; Program_Change requests state transitions.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.PROGRAM

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
        PropertyIdentifier.DESCRIPTION: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.PROGRAM_STATE: PropertyDefinition(
            PropertyIdentifier.PROGRAM_STATE,
            ProgramState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=ProgramState.IDLE,
        ),
        PropertyIdentifier.PROGRAM_CHANGE: PropertyDefinition(
            PropertyIdentifier.PROGRAM_CHANGE,
            ProgramChange,
            PropertyAccess.READ_WRITE,
            required=True,
            default=ProgramChange.READY,
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
            required=False,
        ),
        PropertyIdentifier.OUT_OF_SERVICE: PropertyDefinition(
            PropertyIdentifier.OUT_OF_SERVICE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.REASON_FOR_HALT: PropertyDefinition(
            PropertyIdentifier.REASON_FOR_HALT,
            int,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.DESCRIPTION_OF_HALT: PropertyDefinition(
            PropertyIdentifier.DESCRIPTION_OF_HALT,
            str,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.PROGRAM_LOCATION: PropertyDefinition(
            PropertyIdentifier.PROGRAM_LOCATION,
            str,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.INSTANCE_OF: PropertyDefinition(
            PropertyIdentifier.INSTANCE_OF,
            str,
            PropertyAccess.READ_ONLY,
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
