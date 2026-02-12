"""BACnet Notification Forwarder object per ASHRAE 135-2020 Clause 12.51."""

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
class NotificationForwarderObject(BACnetObject):
    """BACnet Notification Forwarder object (Clause 12.51).

    Filters and routes event notifications to subscribed recipients.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.NOTIFICATION_FORWARDER

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.PROCESS_IDENTIFIER_FILTER: PropertyDefinition(
            PropertyIdentifier.PROCESS_IDENTIFIER_FILTER,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.SUBSCRIBED_RECIPIENTS: PropertyDefinition(
            PropertyIdentifier.SUBSCRIBED_RECIPIENTS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
        PropertyIdentifier.PORT_FILTER: PropertyDefinition(
            PropertyIdentifier.PORT_FILTER,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
        PropertyIdentifier.LOCAL_FORWARDING_ONLY: PropertyDefinition(
            PropertyIdentifier.LOCAL_FORWARDING_ONLY,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
