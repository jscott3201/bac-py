"""BACnet Alert Enrollment object per ASHRAE 135-2020 Clause 12.52."""

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
class AlertEnrollmentObject(BACnetObject):
    """BACnet Alert Enrollment object (Clause 12.52).

    Generates proprietary alert notifications for vendor-specific conditions.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ALERT_ENROLLMENT

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            object,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.NOTIFICATION_CLASS: PropertyDefinition(
            PropertyIdentifier.NOTIFICATION_CLASS,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EVENT_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_ENABLE,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.EVENT_DETECTION_ENABLE: PropertyDefinition(
            PropertyIdentifier.EVENT_DETECTION_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=False,
            default=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
