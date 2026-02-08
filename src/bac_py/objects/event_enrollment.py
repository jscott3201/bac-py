"""BACnet Event Enrollment object per ASHRAE 135-2016 Clause 12.12."""

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
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


@register_object_type
class EventEnrollmentObject(BACnetObject):
    """BACnet Event Enrollment object (Clause 12.12).

    Configures alarm/event detection for a monitored property.
    Specifies the event algorithm, parameters, and notification
    routing.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.EVENT_ENROLLMENT

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
        PropertyIdentifier.EVENT_TYPE: PropertyDefinition(
            PropertyIdentifier.EVENT_TYPE,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.EVENT_PARAMETERS: PropertyDefinition(
            PropertyIdentifier.EVENT_PARAMETERS,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.OBJECT_PROPERTY_REFERENCE: PropertyDefinition(
            PropertyIdentifier.OBJECT_PROPERTY_REFERENCE,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EVENT_STATE: PropertyDefinition(
            PropertyIdentifier.EVENT_STATE,
            EventState,
            PropertyAccess.READ_ONLY,
            required=True,
            default=EventState.NORMAL,
        ),
        PropertyIdentifier.EVENT_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_ENABLE,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.ACKED_TRANSITIONS: PropertyDefinition(
            PropertyIdentifier.ACKED_TRANSITIONS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.NOTIFY_TYPE: PropertyDefinition(
            PropertyIdentifier.NOTIFY_TYPE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.EVENT_TIME_STAMPS: PropertyDefinition(
            PropertyIdentifier.EVENT_TIME_STAMPS,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EVENT_DETECTION_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_DETECTION_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=True,
        ),
        PropertyIdentifier.STATUS_FLAGS: PropertyDefinition(
            PropertyIdentifier.STATUS_FLAGS,
            StatusFlags,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.RELIABILITY: PropertyDefinition(
            PropertyIdentifier.RELIABILITY,
            Reliability,
            PropertyAccess.READ_ONLY,
            required=True,
            default=Reliability.NO_FAULT_DETECTED,
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
        # Default event_type to 0 (change-of-bitstring) if not set
        if PropertyIdentifier.EVENT_TYPE not in self._properties:
            self._properties[PropertyIdentifier.EVENT_TYPE] = 0
        # Default event_parameters if not set
        if PropertyIdentifier.EVENT_PARAMETERS not in self._properties:
            self._properties[PropertyIdentifier.EVENT_PARAMETERS] = None
        # Default object property reference if not set
        if PropertyIdentifier.OBJECT_PROPERTY_REFERENCE not in self._properties:
            self._properties[PropertyIdentifier.OBJECT_PROPERTY_REFERENCE] = None
        # Event_Enable: 3-element list [to-offnormal, to-fault, to-normal]
        if PropertyIdentifier.EVENT_ENABLE not in self._properties:
            self._properties[PropertyIdentifier.EVENT_ENABLE] = [True, True, True]
        # Acked_Transitions: 3-element list [to-offnormal, to-fault, to-normal]
        if PropertyIdentifier.ACKED_TRANSITIONS not in self._properties:
            self._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        # Event_Time_Stamps: 3-element list of timestamps
        if PropertyIdentifier.EVENT_TIME_STAMPS not in self._properties:
            self._properties[PropertyIdentifier.EVENT_TIME_STAMPS] = [None, None, None]
        # Default notification class if not set
        if PropertyIdentifier.NOTIFICATION_CLASS not in self._properties:
            self._properties[PropertyIdentifier.NOTIFICATION_CLASS] = 0
        if PropertyIdentifier.STATUS_FLAGS not in self._properties:
            self._properties[PropertyIdentifier.STATUS_FLAGS] = StatusFlags()
        if PropertyIdentifier.RELIABILITY not in self._properties:
            self._properties[PropertyIdentifier.RELIABILITY] = Reliability.NO_FAULT_DETECTED
