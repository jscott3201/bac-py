"""BACnet Audit Log object per ASHRAE 135-2020 Clause 12.64 (new in 2020)."""

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
class AuditLogObject(BACnetObject):
    """BACnet Audit Log object (Clause 12.64, new in 2020).

    Circular buffer of audit log records.  Full audit integration
    including AuditLogQuery is in Phase 4; this provides the object
    shell with required properties.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.AUDIT_LOG

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        **status_properties(include_out_of_service=False),
        PropertyIdentifier.LOG_ENABLE: PropertyDefinition(
            PropertyIdentifier.LOG_ENABLE,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
        PropertyIdentifier.LOG_BUFFER: PropertyDefinition(
            PropertyIdentifier.LOG_BUFFER,
            list,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.RECORD_COUNT: PropertyDefinition(
            PropertyIdentifier.RECORD_COUNT,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.TOTAL_RECORD_COUNT: PropertyDefinition(
            PropertyIdentifier.TOTAL_RECORD_COUNT,
            int,
            PropertyAccess.READ_ONLY,
            required=True,
            default=0,
        ),
        PropertyIdentifier.BUFFER_SIZE: PropertyDefinition(
            PropertyIdentifier.BUFFER_SIZE,
            int,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0,
        ),
        PropertyIdentifier.STOP_WHEN_FULL: PropertyDefinition(
            PropertyIdentifier.STOP_WHEN_FULL,
            bool,
            PropertyAccess.READ_WRITE,
            required=True,
            default=False,
        ),
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
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._init_status_flags()
        self._set_default(PropertyIdentifier.LOG_BUFFER, [])
