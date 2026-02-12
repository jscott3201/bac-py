"""BACnet Structured View object per ASHRAE 135-2020 Clause 12.29."""

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
    NodeType,
    ObjectType,
    PropertyIdentifier,
)


@register_object_type
class StructuredViewObject(BACnetObject):
    """BACnet Structured View object (Clause 12.29).

    Provides hierarchical grouping of objects for organizational
    purposes.  Pure data container with no behavioral logic.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.STRUCTURED_VIEW

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.NODE_TYPE: PropertyDefinition(
            PropertyIdentifier.NODE_TYPE,
            NodeType,
            PropertyAccess.READ_WRITE,
            required=True,
            default=NodeType.UNKNOWN,
        ),
        PropertyIdentifier.NODE_SUBTYPE: PropertyDefinition(
            PropertyIdentifier.NODE_SUBTYPE,
            str,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.SUBORDINATE_LIST: PropertyDefinition(
            PropertyIdentifier.SUBORDINATE_LIST,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.SUBORDINATE_ANNOTATIONS: PropertyDefinition(
            PropertyIdentifier.SUBORDINATE_ANNOTATIONS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
