"""Tests for audit services encode/decode."""

from bac_py.services.audit import (
    AuditLogQueryACK,
    AuditLogQueryRequest,
    ConfirmedAuditNotificationRequest,
    UnconfirmedAuditNotificationRequest,
)
from bac_py.types.audit_types import (
    AuditQueryBySource,
    AuditQueryByTarget,
    BACnetAuditLogRecord,
    BACnetAuditNotification,
)
from bac_py.types.enums import AuditOperation, ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestAuditLogQueryRequest:
    def test_round_trip_by_target(self):
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query,
            requested_count=50,
        )
        encoded = request.encode()
        decoded = AuditLogQueryRequest.decode(encoded)
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 1)
        assert isinstance(decoded.query_parameters, AuditQueryByTarget)
        assert decoded.query_parameters.target_device_identifier == ObjectIdentifier(
            ObjectType.DEVICE, 100
        )
        assert decoded.requested_count == 50
        assert decoded.start_at_sequence_number is None

    def test_round_trip_by_source(self):
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 2),
            query_parameters=query,
            start_at_sequence_number=1000,
            requested_count=25,
        )
        encoded = request.encode()
        decoded = AuditLogQueryRequest.decode(encoded)
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 2)
        assert isinstance(decoded.query_parameters, AuditQueryBySource)
        assert decoded.query_parameters.source_device_identifier == ObjectIdentifier(
            ObjectType.DEVICE, 200
        )
        assert decoded.start_at_sequence_number == 1000
        assert decoded.requested_count == 25


class TestAuditLogQueryACK:
    def test_round_trip_empty_records(self):
        ack = AuditLogQueryACK(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            records=[],
            no_more_items=True,
        )
        encoded = ack.encode()
        decoded = AuditLogQueryACK.decode(encoded)
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 1)
        assert decoded.records == []
        assert decoded.no_more_items is True

    def test_round_trip_with_records(self):
        notif1 = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            target_property=85,
        )
        notif2 = BACnetAuditNotification(
            operation=AuditOperation.CREATE,
            target_object=ObjectIdentifier(ObjectType.BINARY_INPUT, 2),
        )
        records = [
            BACnetAuditLogRecord(sequence_number=1, notification=notif1),
            BACnetAuditLogRecord(sequence_number=2, notification=notif2),
        ]
        ack = AuditLogQueryACK(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            records=records,
            no_more_items=False,
        )
        encoded = ack.encode()
        decoded = AuditLogQueryACK.decode(encoded)
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 1)
        assert len(decoded.records) == 2
        assert decoded.records[0].sequence_number == 1
        assert decoded.records[0].notification.operation == AuditOperation.WRITE
        assert decoded.records[1].sequence_number == 2
        assert decoded.records[1].notification.operation == AuditOperation.CREATE
        assert decoded.no_more_items is False


class TestConfirmedAuditNotificationRequest:
    def test_round_trip_single_notification(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_object=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 5),
            target_property=85,
        )
        request = ConfirmedAuditNotificationRequest(notifications=[notif])
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 1
        assert decoded.notifications[0].operation == AuditOperation.WRITE
        assert decoded.notifications[0].source_device == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.notifications[0].target_property == 85

    def test_round_trip_multiple_notifications(self):
        notifs = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
            )
            for i in range(3)
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifs)
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 3
        for i, n in enumerate(decoded.notifications):
            assert n.operation == AuditOperation.WRITE
            assert n.target_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, i)


class TestUnconfirmedAuditNotificationRequest:
    def test_round_trip(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1),
        )
        request = UnconfirmedAuditNotificationRequest(notifications=[notif])
        encoded = request.encode()
        decoded = UnconfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 1
        assert decoded.notifications[0].operation == AuditOperation.DELETE

    def test_inherits_from_confirmed(self):
        assert issubclass(
            UnconfirmedAuditNotificationRequest,
            ConfirmedAuditNotificationRequest,
        )
