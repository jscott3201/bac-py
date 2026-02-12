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
from bac_py.types.audit_types import BACnetAuditLogRecord, BACnetAuditNotification
from bac_py.types.enums import (
    AuditLevel,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BitString


@register_object_type
class AuditLogObject(BACnetObject):
    """BACnet Audit Log object (Clause 12.64, new in 2020).

    Circular buffer of audit log records with sequence numbering.
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
            default=100,
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
            default=AuditLevel.DEFAULT,
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
        self._sequence_counter = 0

    def append_record(self, notification: BACnetAuditNotification) -> BACnetAuditLogRecord | None:
        """Append an audit notification to the log buffer.

        Handles circular buffer overflow (oldest records removed) and
        stop-when-full behavior. Returns the record if it was added.
        """
        if not self._properties.get(PropertyIdentifier.LOG_ENABLE, False):
            return None

        buffer: list[BACnetAuditLogRecord] = self._properties.get(
            PropertyIdentifier.LOG_BUFFER, []
        )
        buffer_size = self._properties.get(PropertyIdentifier.BUFFER_SIZE, 100)
        stop_when_full = self._properties.get(PropertyIdentifier.STOP_WHEN_FULL, False)

        if stop_when_full and len(buffer) >= buffer_size:
            return None

        self._sequence_counter += 1
        record = BACnetAuditLogRecord(
            sequence_number=self._sequence_counter,
            notification=notification,
        )

        if len(buffer) >= buffer_size:
            # Circular: remove oldest
            buffer.pop(0)

        buffer.append(record)
        self._properties[PropertyIdentifier.RECORD_COUNT] = len(buffer)
        self._properties[PropertyIdentifier.TOTAL_RECORD_COUNT] = self._sequence_counter
        return record

    def query_records(
        self,
        start_at: int | None = None,
        count: int = 100,
    ) -> tuple[list[BACnetAuditLogRecord], bool]:
        """Query records from the log buffer.

        :param start_at: Starting sequence number (inclusive). If None, start from beginning.
        :param count: Maximum number of records to return.
        :returns: Tuple of (matching records, no_more_items flag).
        """
        buffer: list[BACnetAuditLogRecord] = self._properties.get(
            PropertyIdentifier.LOG_BUFFER, []
        )

        if start_at is not None:
            filtered = [r for r in buffer if r.sequence_number >= start_at]
        else:
            filtered = list(buffer)

        result = filtered[:count]
        no_more = len(filtered) <= count
        return result, no_more
