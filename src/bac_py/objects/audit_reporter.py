"""BACnet Audit Reporter object per ASHRAE 135-2020 Clause 12.63 (new in 2020)."""

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
from bac_py.types.primitives import BitString


@register_object_type
class AuditReporterObject(BACnetObject):
    """BACnet Audit Reporter object (Clause 12.63, new in 2020).

    Monitors objects and generates audit notifications.  Full audit
    integration is in Phase 4; this provides the object shell with
    required properties.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.AUDIT_REPORTER

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.AUDIT_LEVEL: PropertyDefinition(
            PropertyIdentifier.AUDIT_LEVEL,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.AUDITABLE_OPERATIONS: PropertyDefinition(
            PropertyIdentifier.AUDITABLE_OPERATIONS,
            BitString,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.AUDIT_NOTIFICATION_RECIPIENT: PropertyDefinition(
            PropertyIdentifier.AUDIT_NOTIFICATION_RECIPIENT,
            object,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
        PropertyIdentifier.MONITORED_OBJECTS: PropertyDefinition(
            PropertyIdentifier.MONITORED_OBJECTS,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
            default=[],
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
