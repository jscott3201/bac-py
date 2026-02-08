"""BACnet Calendar object per ASHRAE 135-2016 Clause 12.9."""

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
class CalendarObject(BACnetObject):
    """BACnet Calendar object (Clause 12.9).

    A Calendar object maintains a list of dates, date ranges, and
    date patterns.  Present_Value is TRUE when the current date
    matches any entry in Date_List.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CALENDAR

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.DATE_LIST: PropertyDefinition(
            PropertyIdentifier.DATE_LIST,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        if PropertyIdentifier.DATE_LIST not in self._properties:
            self._properties[PropertyIdentifier.DATE_LIST] = []
