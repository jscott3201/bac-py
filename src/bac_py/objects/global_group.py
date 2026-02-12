"""BACnet Global Group object per ASHRAE 135-2020 Clause 12.50."""

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
class GlobalGroupObject(BACnetObject):
    """BACnet Global Group object (Clause 12.50).

    Provides grouped property reads across multiple devices.
    Each member specifies a device, object, and property.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.GLOBAL_GROUP

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.GROUP_MEMBERS: PropertyDefinition(
            PropertyIdentifier.GROUP_MEMBERS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.GROUP_MEMBER_NAMES: PropertyDefinition(
            PropertyIdentifier.GROUP_MEMBER_NAMES,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
            default=[],
        ),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.MEMBER_STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.MEMBER_STATUS_FLAGS,
            list,
            PropertyAccess.READ_ONLY,
            required=False,
        ),
        PropertyIdentifier.REQUESTED_UPDATE_INTERVAL: PropertyDefinition(
            PropertyIdentifier.REQUESTED_UPDATE_INTERVAL,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.COVU_PERIOD: PropertyDefinition(
            PropertyIdentifier.COVU_PERIOD,
            int,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.COVU_RECIPIENTS: PropertyDefinition(
            PropertyIdentifier.COVU_RECIPIENTS,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
