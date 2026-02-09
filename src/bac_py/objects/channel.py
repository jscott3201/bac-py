"""BACnet Channel object type per ASHRAE 135-2016 Clause 12.53."""

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
    WriteStatus,
)


@register_object_type
class ChannelObject(BACnetObject):
    """BACnet Channel object (Clause 12.53).

    Provides multi-object control via a single write operation.
    A Channel can simultaneously command multiple other objects
    (e.g. lighting groups, HVAC zones) by writing to its
    Present_Value property.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CHANNEL

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            object,  # type varies - can be any BACnet value type
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        **status_properties(),
        PropertyIdentifier.LAST_PRIORITY: PropertyDefinition(
            PropertyIdentifier.LAST_PRIORITY,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.WRITE_STATUS: PropertyDefinition(
            PropertyIdentifier.WRITE_STATUS,
            WriteStatus,
            PropertyAccess.READ_ONLY,
            required=True,
            default=WriteStatus.IDLE,
        ),
        PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES: PropertyDefinition(
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.CHANNEL_NUMBER: PropertyDefinition(
            PropertyIdentifier.CHANNEL_NUMBER,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.CONTROL_GROUPS: PropertyDefinition(
            PropertyIdentifier.CONTROL_GROUPS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.EXECUTION_DELAY: PropertyDefinition(
            PropertyIdentifier.EXECUTION_DELAY,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.ALLOW_GROUP_DELAY_INHIBIT: PropertyDefinition(
            PropertyIdentifier.ALLOW_GROUP_DELAY_INHIBIT,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }

    def __init__(
        self,
        instance_number: int,
        *,
        channel_number: int = 0,
        **initial_properties: Any,
    ) -> None:
        super().__init__(instance_number, **initial_properties)
        self._set_default(PropertyIdentifier.CHANNEL_NUMBER, channel_number)
        self._init_status_flags()
