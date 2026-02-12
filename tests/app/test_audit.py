"""Tests for AuditManager and audit log integration."""

from unittest.mock import patch

from bac_py.app.audit import AuditManager
from bac_py.objects.audit_log import AuditLogObject
from bac_py.objects.audit_reporter import AuditReporterObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.device import DeviceObject
from bac_py.types.audit_types import BACnetAuditNotification
from bac_py.types.enums import (
    AuditLevel,
    AuditOperation,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BitString, ObjectIdentifier


def _make_db(
    *,
    audit_level: int = AuditLevel.AUDIT_ALL,
    log_enable: bool = True,
    buffer_size: int = 100,
    stop_when_full: bool = False,
    auditable_operations: BitString | None = None,
) -> tuple[ObjectDatabase, AuditReporterObject, AuditLogObject]:
    """Build a minimal DB with device, reporter, and log objects."""
    db = ObjectDatabase()
    device = DeviceObject(1, object_name="test-device")
    db.add(device)

    reporter = AuditReporterObject(1, object_name="reporter-1")
    reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = audit_level
    if auditable_operations is not None:
        reporter._properties[PropertyIdentifier.AUDITABLE_OPERATIONS] = auditable_operations
    db.add(reporter)

    log = AuditLogObject(1, object_name="audit-log-1")
    log._properties[PropertyIdentifier.LOG_ENABLE] = log_enable
    log._properties[PropertyIdentifier.BUFFER_SIZE] = buffer_size
    log._properties[PropertyIdentifier.STOP_WHEN_FULL] = stop_when_full
    db.add(log)

    return db, reporter, log


class TestAuditManagerRecordOperation:
    def test_basic_write_recorded(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            target_property=85,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].sequence_number == 1
        assert buffer[0].notification.operation == AuditOperation.WRITE
        assert buffer[0].notification.target_property == 85

    def test_create_operation_recorded(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.CREATE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 10),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].notification.operation == AuditOperation.CREATE

    def test_delete_operation_recorded(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].notification.operation == AuditOperation.DELETE

    def test_multiple_operations_sequence_numbers(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 5
        for i, record in enumerate(buffer, 1):
            assert record.sequence_number == i

    def test_target_device_set_from_db(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert buffer[0].notification.target_device == ObjectIdentifier(ObjectType.DEVICE, 1)


class TestAuditLevelFiltering:
    def test_audit_level_none_skips(self):
        db, _reporter, log = _make_db(audit_level=AuditLevel.NONE)
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0

    def test_audit_level_audit_all_records_everything(self):
        db, _reporter, log = _make_db(audit_level=AuditLevel.AUDIT_ALL)
        mgr = AuditManager(db)

        for op in [
            AuditOperation.READ,
            AuditOperation.WRITE,
            AuditOperation.CREATE,
            AuditOperation.DELETE,
            AuditOperation.GENERAL,
        ]:
            mgr.record_operation(
                operation=op,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 5

    def test_audit_level_audit_config_only_config_ops(self):
        db, _reporter, log = _make_db(audit_level=AuditLevel.AUDIT_CONFIG)
        mgr = AuditManager(db)

        # Config ops should be recorded
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        mgr.record_operation(
            operation=AuditOperation.CREATE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 2),
        )
        mgr.record_operation(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.BINARY_INPUT, 1),
        )

        # Non-config ops should be skipped
        mgr.record_operation(
            operation=AuditOperation.READ,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        mgr.record_operation(
            operation=AuditOperation.GENERAL,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 3

    def test_no_reporter_skips_all(self):
        db = ObjectDatabase()
        device = DeviceObject(1, object_name="test-device")
        db.add(device)
        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(log)

        mgr = AuditManager(db)
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0


class TestCircularBuffer:
    def test_circular_overflow(self):
        db, _reporter, log = _make_db(buffer_size=3)
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 3
        # Should have the last 3 records (seq 3, 4, 5)
        assert buffer[0].sequence_number == 3
        assert buffer[1].sequence_number == 4
        assert buffer[2].sequence_number == 5

    def test_record_count_and_total_record_count(self):
        db, _reporter, log = _make_db(buffer_size=3)
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        assert log._properties[PropertyIdentifier.RECORD_COUNT] == 3
        assert log._properties[PropertyIdentifier.TOTAL_RECORD_COUNT] == 5


class TestStopWhenFull:
    def test_stop_when_full(self):
        db, _reporter, log = _make_db(buffer_size=3, stop_when_full=True)
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 3
        # Should have the first 3 records only
        assert buffer[0].sequence_number == 1
        assert buffer[1].sequence_number == 2
        assert buffer[2].sequence_number == 3

    def test_stop_when_full_total_count(self):
        db, _reporter, log = _make_db(buffer_size=2, stop_when_full=True)
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        assert log._properties[PropertyIdentifier.RECORD_COUNT] == 2
        assert log._properties[PropertyIdentifier.TOTAL_RECORD_COUNT] == 2


class TestLogDisabled:
    def test_log_disabled_skips_recording(self):
        db, _reporter, log = _make_db(log_enable=False)
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0


class TestAuditLogQueryRecords:
    def test_query_all_records(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        records, no_more = log.query_records()
        assert len(records) == 5
        assert no_more is True

    def test_query_with_start_at(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        for i in range(5):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        records, no_more = log.query_records(start_at=3)
        assert len(records) == 3
        assert records[0].sequence_number == 3
        assert no_more is True

    def test_query_with_count_limit(self):
        db, _reporter, log = _make_db()
        mgr = AuditManager(db)

        for i in range(10):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )

        records, no_more = log.query_records(count=3)
        assert len(records) == 3
        assert no_more is False

    def test_query_empty_buffer(self):
        _db, _reporter, log = _make_db()
        records, no_more = log.query_records()
        assert len(records) == 0
        assert no_more is True


class TestAuditNotificationDirect:
    def test_append_record_returns_record(self):
        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = True
        log._properties[PropertyIdentifier.BUFFER_SIZE] = 100

        notif = BACnetAuditNotification(operation=AuditOperation.WRITE)
        record = log.append_record(notif)
        assert record is not None
        assert record.sequence_number == 1
        assert record.notification.operation == AuditOperation.WRITE

    def test_append_record_disabled_returns_none(self):
        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = False

        notif = BACnetAuditNotification(operation=AuditOperation.WRITE)
        record = log.append_record(notif)
        assert record is None


class TestNoDeviceInDB:
    """Covers lines 77->80: no DeviceObject in DB so target_device stays None."""

    def test_target_device_none_when_no_device_object(self):
        db = ObjectDatabase()
        # No DeviceObject added — only reporter and log.
        reporter = AuditReporterObject(1, object_name="reporter-1")
        reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = AuditLevel.AUDIT_ALL
        db.add(reporter)

        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = True
        log._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        db.add(log)

        mgr = AuditManager(db)
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].notification.target_device is None


class TestMonitoredObjectsFiltering:
    """Covers lines 109-124: _find_reporters monitored_objects matching."""

    def _make_db_with_monitored(
        self, monitored_objects: list[ObjectIdentifier]
    ) -> tuple[ObjectDatabase, AuditReporterObject, AuditLogObject]:
        """Build a DB with a reporter that monitors specific objects."""
        db = ObjectDatabase()
        device = DeviceObject(1, object_name="test-device")
        db.add(device)

        reporter = AuditReporterObject(1, object_name="reporter-1")
        reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = AuditLevel.AUDIT_ALL
        reporter._properties[PropertyIdentifier.MONITORED_OBJECTS] = monitored_objects
        db.add(reporter)

        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = True
        log._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        db.add(log)

        return db, reporter, log

    def test_exact_oid_match_recorded(self):
        target = ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)
        db, _reporter, log = self._make_db_with_monitored([target])
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=target,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1

    def test_exact_oid_no_match_not_recorded(self):
        monitored = ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)
        target = ObjectIdentifier(ObjectType.ANALOG_INPUT, 99)
        db, _reporter, log = self._make_db_with_monitored([monitored])
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=target,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0

    def test_wildcard_type_match_recorded(self):
        # Wildcard: same object type with instance 0x3FFFFF
        wildcard = ObjectIdentifier(ObjectType.ANALOG_INPUT, 0x3FFFFF)
        target = ObjectIdentifier(ObjectType.ANALOG_INPUT, 42)
        db, _reporter, log = self._make_db_with_monitored([wildcard])
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=target,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1

    def test_wildcard_type_no_match_not_recorded(self):
        # Wildcard for ANALOG_INPUT, target is BINARY_INPUT
        wildcard = ObjectIdentifier(ObjectType.ANALOG_INPUT, 0x3FFFFF)
        target = ObjectIdentifier(ObjectType.BINARY_INPUT, 1)
        db, _reporter, log = self._make_db_with_monitored([wildcard])
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=target,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0

    def test_monitored_list_nonempty_target_is_none(self):
        """When monitored_objects is non-empty but target_oid is None.

        The reporter should NOT be selected (the elif branch is skipped).
        """
        monitored = ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)
        db, _reporter, log = self._make_db_with_monitored([monitored])
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=None,
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0


class TestInvalidAuditLevel:
    """Covers lines 132-133: ValueError in AuditLevel(level) falls back to NONE."""

    def test_invalid_audit_level_falls_back_to_none(self):
        db = ObjectDatabase()
        device = DeviceObject(1, object_name="test-device")
        db.add(device)

        reporter = AuditReporterObject(1, object_name="reporter-1")
        # Set an int that is not a valid AuditLevel member
        reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = 999
        db.add(reporter)

        log = AuditLogObject(1, object_name="audit-log-1")
        log._properties[PropertyIdentifier.LOG_ENABLE] = True
        log._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        db.add(log)

        mgr = AuditManager(db)
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        # AuditLevel.NONE means nothing gets recorded
        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0


class TestAuditableOperationsBitstring:
    """Covers lines 162-170: auditable_operations bitstring filtering."""

    def test_operation_bit_set_recorded(self):
        # AuditOperation.WRITE = 1 => byte 0, bit index 6 (7 - 1%8)
        # Set bit 1: byte value = 0b01000000 = 0x40
        bs = BitString(bytes([0b11000000]))  # bits 0 and 1 set
        db, _reporter, log = _make_db(auditable_operations=bs)
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1

    def test_operation_bit_not_set_not_recorded(self):
        # Only bit 0 (READ) set, bit 1 (WRITE) not set
        # byte value = 0b10000000 = 0x80
        bs = BitString(bytes([0b10000000]))
        db, _reporter, log = _make_db(auditable_operations=bs)
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0

    def test_operation_bit_beyond_length_not_recorded(self):
        # AuditOperation.GENERAL = 15 => byte 1, bit index 0
        # Only provide 1 byte so byte_index (1) >= len(data) (1)
        bs = BitString(bytes([0xFF]))  # all bits in byte 0 set
        db, _reporter, log = _make_db(auditable_operations=bs)
        mgr = AuditManager(db)

        mgr.record_operation(
            operation=AuditOperation.GENERAL,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 0


class TestNonReporterObjectSkipped:
    """Covers line 104: non-AuditReporterObject returned by get_objects_of_type is skipped."""

    def test_non_reporter_object_skipped_in_find_reporters(self):
        db, _reporter, log = _make_db()

        # Patch get_objects_of_type to inject a plain BACnetObject alongside the reporter
        original_get = db.get_objects_of_type

        def patched_get(obj_type):
            results = original_get(obj_type)
            if obj_type == ObjectType.AUDIT_REPORTER:
                # Prepend a non-AuditReporterObject that would be filtered out
                fake = object()  # not an AuditReporterObject instance
                return [fake, *results]
            return results

        mgr = AuditManager(db)
        with patch.object(db, "get_objects_of_type", side_effect=patched_get):
            mgr.record_operation(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            )

        # The real reporter still works; fake one is skipped
        buffer = log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1


class TestAppendToLogsIteration:
    """Covers line 177->176: _append_to_logs iterates over audit log objects."""

    def test_notification_appended_to_multiple_logs(self):
        db = ObjectDatabase()
        device = DeviceObject(1, object_name="test-device")
        db.add(device)

        reporter = AuditReporterObject(1, object_name="reporter-1")
        reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = AuditLevel.AUDIT_ALL
        db.add(reporter)

        log1 = AuditLogObject(1, object_name="audit-log-1")
        log1._properties[PropertyIdentifier.LOG_ENABLE] = True
        log1._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        db.add(log1)

        log2 = AuditLogObject(2, object_name="audit-log-2")
        log2._properties[PropertyIdentifier.LOG_ENABLE] = True
        log2._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        db.add(log2)

        mgr = AuditManager(db)
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        buf1 = log1._properties[PropertyIdentifier.LOG_BUFFER]
        buf2 = log2._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buf1) == 1
        assert len(buf2) == 1

    def test_no_audit_logs_in_db(self):
        """When no AuditLogObject exists, _append_to_logs loop body never executes."""
        db = ObjectDatabase()
        device = DeviceObject(1, object_name="test-device")
        db.add(device)

        reporter = AuditReporterObject(1, object_name="reporter-1")
        reporter._properties[PropertyIdentifier.AUDIT_LEVEL] = AuditLevel.AUDIT_ALL
        db.add(reporter)

        # No AuditLogObject added
        mgr = AuditManager(db)
        # Should not raise, just silently do nothing
        mgr.record_operation(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
