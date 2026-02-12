"""BACnet Group object per ASHRAE 135-2020 Clause 12.14."""

from __future__ import annotations

from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
)
from bac_py.types.enums import (
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class GroupObject(BACnetObject):
    """BACnet Group object (Clause 12.14).

    Provides local grouped property reads.  Present_Value returns
    the current values of all members in a single read.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.GROUP

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.LIST_OF_GROUP_MEMBERS: PropertyDefinition(
            PropertyIdentifier.LIST_OF_GROUP_MEMBERS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
