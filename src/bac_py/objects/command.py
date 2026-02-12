"""BACnet Command object per ASHRAE 135-2020 Clause 12.10."""

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
)


@register_object_type
class CommandObject(BACnetObject):
    """BACnet Command object (Clause 12.10).

    Executes an action list when Present_Value is written.
    Each action specifies a target object, property, and value.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.COMMAND

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.IN_PROCESS: PropertyDefinition(
            PropertyIdentifier.IN_PROCESS,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.ALL_WRITES_SUCCESSFUL: PropertyDefinition(
            PropertyIdentifier.ALL_WRITES_SUCCESSFUL,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=True,
        ),
        PropertyIdentifier.ACTION: PropertyDefinition(
            PropertyIdentifier.ACTION,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.ACTION_TEXT: PropertyDefinition(
            PropertyIdentifier.ACTION_TEXT,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        **status_properties(include_out_of_service=False),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
