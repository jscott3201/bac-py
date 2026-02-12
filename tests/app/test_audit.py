"""Tests for AuditManager and audit log integration."""

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
        reporter._properties[PropertyIdentifier.AUDITABLE_OPERATIONS] = (
            auditable_operations
        )
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
        assert buffer[0].notification.target_device == ObjectIdentifier(
            ObjectType.DEVICE, 1
        )


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
