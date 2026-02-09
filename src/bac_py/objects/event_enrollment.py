"""BACnet Event Enrollment object per ASHRAE 135-2016 Clause 12.12."""

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
    Reliability,
)


@register_object_type
class EventEnrollmentObject(BACnetObject):
    """BACnet Event Enrollment object (Clause 12.12).

    Configures alarm/event detection for a monitored property.
    Specifies the event algorithm, parameters, and notification
    routing.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.EVENT_ENROLLMENT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
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
        **status_properties(
            reliability_required=True,
            reliability_default=Reliability.NO_FAULT_DETECTED,
            include_out_of_service=False,
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
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        # Default event_type to 0 (change-of-bitstring) if not set
        self._set_default(PropertyIdentifier.EVENT_TYPE, 0)
        # Default event_parameters if not set
        self._set_default(PropertyIdentifier.EVENT_PARAMETERS, None)
        # Default object property reference if not set
        self._set_default(PropertyIdentifier.OBJECT_PROPERTY_REFERENCE, None)
        # Event_Enable: 3-element list [to-offnormal, to-fault, to-normal]
        self._set_default(PropertyIdentifier.EVENT_ENABLE, [True, True, True])
        # Acked_Transitions: 3-element list [to-offnormal, to-fault, to-normal]
        self._set_default(PropertyIdentifier.ACKED_TRANSITIONS, [True, True, True])
        # Event_Time_Stamps: 3-element list of timestamps
        self._set_default(PropertyIdentifier.EVENT_TIME_STAMPS, [None, None, None])
        # Default notification class if not set
        self._set_default(PropertyIdentifier.NOTIFICATION_CLASS, 0)
        self._init_status_flags()
