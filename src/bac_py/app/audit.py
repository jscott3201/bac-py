"""Audit logging manager per ASHRAE 135-2020 Clause 19.6.

Intercepts auditable operations and records them into Audit Log objects.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bac_py.objects.audit_log import AuditLogObject
from bac_py.objects.audit_reporter import AuditReporterObject
from bac_py.types.audit_types import BACnetAuditNotification
from bac_py.types.enums import (
    AuditLevel,
    AuditOperation,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.objects.base import ObjectDatabase

logger = logging.getLogger(__name__)


class AuditManager:
    """Manages audit logging per Clause 19.6.

    Intercepts auditable operations (writes, creates, deletes, etc.)
    and records them into Audit Log objects. Checks audit level and
    auditable operations filters before recording.
    """

    def __init__(self, object_db: ObjectDatabase) -> None:
        self._db = object_db

    def record_operation(
        self,
        operation: AuditOperation,
        source_device: ObjectIdentifier | None = None,
        target_object: ObjectIdentifier | None = None,
        target_property: int | None = None,
        target_array_index: int | None = None,
        target_priority: int | None = None,
        target_value: bytes | None = None,
        current_value: bytes | None = None,
        invoke_id: int | None = None,
        result_error: tuple[int, int] | None = None,
        source_comment: str | None = None,
        target_comment: str | None = None,
    ) -> None:
        """Check audit config and record if auditable.

        1. Find Audit Reporter object(s)
        2. Resolve effective audit level
        3. Check auditable_operations bitstring filter
        4. Construct BACnetAuditNotification
        5. Append to local Audit Log buffer
        """
        reporters = self._find_reporters(target_object)
        if not reporters:
            return

        for reporter in reporters:
            if not self._should_audit(reporter, operation):
                continue

            # Build the notification
            result_error_class = result_error[0] if result_error else None
            result_error_code = result_error[1] if result_error else None

            # Find the target device from our device object
            target_device = None
            device_objects = self._db.get_objects_of_type(ObjectType.DEVICE)
            if device_objects:
                target_device = device_objects[0].object_identifier

            notification = BACnetAuditNotification(
                operation=operation,
                source_device=source_device,
                target_device=target_device,
                target_object=target_object,
                target_property=target_property,
                target_array_index=target_array_index,
                target_priority=target_priority,
                target_value=target_value,
                current_value=current_value,
                invoke_id=invoke_id,
                result_error_class=result_error_class,
                result_error_code=result_error_code,
                source_comment=source_comment,
                target_comment=target_comment,
            )

            self._append_to_logs(notification)

    def _find_reporters(self, target_oid: ObjectIdentifier | None) -> list[AuditReporterObject]:
        """Find Audit Reporter objects that monitor the target object."""
        reporters: list[AuditReporterObject] = []
        for obj in self._db.get_objects_of_type(ObjectType.AUDIT_REPORTER):
            if not isinstance(obj, AuditReporterObject):
                continue
            monitored: list[object] = obj._properties.get(PropertyIdentifier.MONITORED_OBJECTS, [])
            if not monitored:
                # Empty monitored list means monitor everything
                reporters.append(obj)
            elif target_oid is not None:
                # Check if the target is in the monitored list
                for m in monitored:
                    if isinstance(m, ObjectIdentifier) and m == target_oid:
                        reporters.append(obj)
                        break
                else:
                    # Also check by object type match
                    for m in monitored:
                        if (
                            isinstance(m, ObjectIdentifier)
                            and m.object_type == target_oid.object_type
                            and m.instance_number == 0x3FFFFF
                        ):
                            reporters.append(obj)
                            break
        return reporters

    def _resolve_audit_level(self, reporter: AuditReporterObject) -> AuditLevel:
        """Resolve effective audit level from the reporter."""
        level = reporter._properties.get(PropertyIdentifier.AUDIT_LEVEL, AuditLevel.DEFAULT)
        try:
            return AuditLevel(level)
        except ValueError:
            return AuditLevel.NONE

    def _should_audit(
        self,
        reporter: AuditReporterObject,
        operation: AuditOperation,
    ) -> bool:
        """Check whether this operation should be audited.

        Checks audit level and auditable_operations bitstring filter.
        """
        level = self._resolve_audit_level(reporter)

        if level == AuditLevel.NONE:
            return False

        if level == AuditLevel.AUDIT_CONFIG:
            # Only audit config changes: WRITE, CREATE, DELETE
            config_ops = {
                AuditOperation.WRITE,
                AuditOperation.CREATE,
                AuditOperation.DELETE,
            }
            if operation not in config_ops:
                return False

        # Check auditable_operations bitstring
        auditable_ops = reporter._properties.get(PropertyIdentifier.AUDITABLE_OPERATIONS)
        if auditable_ops is not None and hasattr(auditable_ops, "data"):
            op_bit = int(operation)
            byte_index = op_bit // 8
            bit_index = 7 - (op_bit % 8)
            if byte_index < len(auditable_ops.data):
                if not (auditable_ops.data[byte_index] & (1 << bit_index)):
                    return False
            else:
                # Bit position beyond the bitstring length means not set
                return False

        return True

    def _append_to_logs(self, notification: BACnetAuditNotification) -> None:
        """Append notification to all enabled Audit Log objects."""
        for obj in self._db.get_objects_of_type(ObjectType.AUDIT_LOG):
            if isinstance(obj, AuditLogObject):
                obj.append_record(notification)
