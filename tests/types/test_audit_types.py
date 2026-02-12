"""Tests for BACnet audit constructed types."""

from bac_py.types.audit_types import (
    AuditQueryBySource,
    AuditQueryByTarget,
    BACnetAuditLogRecord,
    BACnetAuditNotification,
)
from bac_py.types.enums import AuditOperation, ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestBACnetAuditNotification:
    def test_round_trip_minimal(self):
        notif = BACnetAuditNotification(operation=AuditOperation.WRITE)
        encoded = notif.encode()
        decoded = BACnetAuditNotification.decode(encoded)
        assert decoded.operation == AuditOperation.WRITE
        assert decoded.source_device is None
        assert decoded.target_object is None
        assert decoded.target_property is None

    def test_round_trip_all_fields(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            source_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            source_comment="test source",
            target_comment="test target",
            invoke_id=42,
            source_user_id=1000,
            source_user_role=5,
            target_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            target_object=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2),
            target_property=85,  # PRESENT_VALUE
            target_array_index=3,
            target_priority=10,
            target_value=b"\x44\x42\xc8\x00\x00",  # some raw value
            current_value=b"\x44\x42\x48\x00\x00",
            result_error_class=2,
            result_error_code=31,
        )
        encoded = notif.encode()
        decoded = BACnetAuditNotification.decode(encoded)

        assert decoded.operation == AuditOperation.WRITE
        assert decoded.source_device == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.source_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert decoded.source_comment == "test source"
        assert decoded.target_comment == "test target"
        assert decoded.invoke_id == 42
        assert decoded.source_user_id == 1000
        assert decoded.source_user_role == 5
        assert decoded.target_device == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.target_object == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2)
        assert decoded.target_property == 85
        assert decoded.target_array_index == 3
        assert decoded.target_priority == 10
        assert decoded.target_value == b"\x44\x42\xc8\x00\x00"
        assert decoded.current_value == b"\x44\x42\x48\x00\x00"
        assert decoded.result_error_class == 2
        assert decoded.result_error_code == 31

    def test_round_trip_with_error_no_value(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
            result_error_class=1,
            result_error_code=44,
        )
        encoded = notif.encode()
        decoded = BACnetAuditNotification.decode(encoded)
        assert decoded.operation == AuditOperation.DELETE
        assert decoded.target_object == ObjectIdentifier(ObjectType.BINARY_INPUT, 5)
        assert decoded.result_error_class == 1
        assert decoded.result_error_code == 44
        assert decoded.target_value is None

    def test_round_trip_property_without_array_index(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_property=85,
        )
        encoded = notif.encode()
        decoded = BACnetAuditNotification.decode(encoded)
        assert decoded.target_property == 85
        assert decoded.target_array_index is None

    def test_all_operations(self):
        for op in AuditOperation:
            notif = BACnetAuditNotification(operation=op)
            encoded = notif.encode()
            decoded = BACnetAuditNotification.decode(encoded)
            assert decoded.operation == op

    def test_frozen(self):
        notif = BACnetAuditNotification()
        import pytest

        with pytest.raises(AttributeError):
            notif.operation = AuditOperation.READ  # type: ignore[misc]


class TestBACnetAuditLogRecord:
    def test_round_trip(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.CREATE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 10),
        )
        record = BACnetAuditLogRecord(sequence_number=42, notification=notif)
        encoded = record.encode()
        decoded = BACnetAuditLogRecord.decode(encoded)
        assert decoded.sequence_number == 42
        assert decoded.notification.operation == AuditOperation.CREATE
        assert decoded.notification.target_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, 10)

    def test_large_sequence_number(self):
        notif = BACnetAuditNotification(operation=AuditOperation.GENERAL)
        record = BACnetAuditLogRecord(sequence_number=0xFFFFFFFF, notification=notif)
        encoded = record.encode()
        decoded = BACnetAuditLogRecord.decode(encoded)
        assert decoded.sequence_number == 0xFFFFFFFF


class TestAuditQueryByTarget:
    def test_round_trip_minimal(self):
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        encoded = query.encode()
        decoded = AuditQueryByTarget.decode(encoded)
        assert decoded.target_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.target_object_identifier is None
        assert decoded.result_filter == 0

    def test_round_trip_all_fields(self):
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_device_address=b"\xc0\xa8\x01\x01\xba\xc0",
            target_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            target_property_identifier=85,
            target_array_index=0,
            target_priority=8,
            operations=0x03,
            result_filter=1,
        )
        encoded = query.encode()
        decoded = AuditQueryByTarget.decode(encoded)
        assert decoded.target_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.target_device_address == b"\xc0\xa8\x01\x01\xba\xc0"
        assert decoded.target_object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert decoded.target_property_identifier == 85
        assert decoded.target_array_index == 0
        assert decoded.target_priority == 8
        assert decoded.operations == 0x03
        assert decoded.result_filter == 1


class TestAuditQueryBySource:
    def test_round_trip_minimal(self):
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
        )
        encoded = query.encode()
        decoded = AuditQueryBySource.decode(encoded)
        assert decoded.source_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.source_object_identifier is None
        assert decoded.result_filter == 0

    def test_round_trip_all_fields(self):
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            source_device_address=b"\x0a\x00\x01\x01\xba\xc0",
            source_object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            operations=0xFF,
            result_filter=2,
        )
        encoded = query.encode()
        decoded = AuditQueryBySource.decode(encoded)
        assert decoded.source_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.source_device_address == b"\x0a\x00\x01\x01\xba\xc0"
        assert decoded.source_object_identifier == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.operations == 0xFF
        assert decoded.result_filter == 2
