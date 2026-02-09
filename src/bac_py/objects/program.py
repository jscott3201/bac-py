"""BACnet Program object per ASHRAE 135-2016 Clause 12.22."""

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
    ProgramChange,
    ProgramState,
    PropertyIdentifier,
)


@register_object_type
class ProgramObject(BACnetObject):
    """BACnet Program object (Clause 12.22).

    Represents an application program that can be loaded, run,
    halted, and unloaded.  Program_State indicates the current
    execution state; Program_Change requests state transitions.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.PROGRAM

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
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
        **status_properties(event_state_required=False),
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
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
