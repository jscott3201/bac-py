"""BACnet Notification Class object per ASHRAE 135-2016 Clause 12.21."""

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
class NotificationClassObject(BACnetObject):
    """BACnet Notification Class object (Clause 12.21).

    Defines alarm/event notification routing.  Each Notification Class
    specifies priorities, acknowledgment requirements, and a recipient
    list for to-offnormal, to-fault, and to-normal transitions.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.NOTIFICATION_CLASS

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRIORITY: PropertyDefinition(
            PropertyIdentifier.PRIORITY,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.ACK_REQUIRED: PropertyDefinition(
            PropertyIdentifier.ACK_REQUIRED,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.RECIPIENT_LIST: PropertyDefinition(
            PropertyIdentifier.RECIPIENT_LIST,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Notification_Class value defaults to instance number per spec
        self._set_default(PropertyIdentifier.NOTIFICATION_CLASS, instance_number)
        # Priority: 3-element list [to-offnormal, to-fault, to-normal]
        self._set_default(PropertyIdentifier.PRIORITY, [0, 0, 0])
        # Ack_Required: 3-element list [to-offnormal, to-fault, to-normal]
        self._set_default(PropertyIdentifier.ACK_REQUIRED, [False, False, False])
        # Recipient_List defaults empty
        self._set_default(PropertyIdentifier.RECIPIENT_LIST, [])
