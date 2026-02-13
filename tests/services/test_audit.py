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


# ---------------------------------------------------------------------------
# Coverage: audit.py lines 104-105, 112, 127-128, 135, 148, 158, 325-326
# ---------------------------------------------------------------------------


class TestAuditLogQueryRequestNestedTags:
    """Lines 104-105, 112, 127-128, 135: by-source with nested opening/closing tags."""

    def test_round_trip_by_source_with_start_at_seq(self):
        """Exercise nested tag decoding with start_at_sequence_number."""
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 300),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 5),
            query_parameters=query,
            start_at_sequence_number=999999,
            requested_count=10,
        )
        encoded = request.encode()
        decoded = AuditLogQueryRequest.decode(encoded)
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 5)
        assert isinstance(decoded.query_parameters, AuditQueryBySource)
        assert decoded.start_at_sequence_number == 999999
        assert decoded.requested_count == 10

    def test_round_trip_by_target_with_all_fields(self):
        """Lines 96-118: by-target decode with nested tags and sequence number."""
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            target_object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 3),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 10),
            query_parameters=query,
            start_at_sequence_number=0,
            requested_count=200,
        )
        encoded = request.encode()
        decoded = AuditLogQueryRequest.decode(encoded)
        assert isinstance(decoded.query_parameters, AuditQueryByTarget)
        assert decoded.query_parameters.target_device_identifier == ObjectIdentifier(
            ObjectType.DEVICE, 50
        )
        assert decoded.start_at_sequence_number == 0
        assert decoded.requested_count == 200

    def test_decode_missing_tag_148_158(self):
        """Lines 148, 158: tag number other than 3 or 4 stops parsing."""
        # Encode a minimal request that ends without tag 3 or 4
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query,
            # Default requested_count=100 will be encoded
        )
        encoded = request.encode()
        decoded = AuditLogQueryRequest.decode(encoded)
        assert decoded.start_at_sequence_number is None
        assert decoded.requested_count == 100


class TestConfirmedAuditNotificationMultiple:
    """Lines 325-326: ConfirmedAuditNotification with multiple records."""

    def test_round_trip_three_notifications(self):
        """Lines 312-340: multiple notifications with nested constructed tags."""
        notifs = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
                target_property=85,
            )
            for i in range(3)
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifs)
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 3
        for i, n in enumerate(decoded.notifications):
            assert n.target_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, i)
            assert n.target_property == 85

    def test_round_trip_four_notifications_varied_ops(self):
        """More notifications with different operations."""
        notifs = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            ),
            BACnetAuditNotification(
                operation=AuditOperation.CREATE,
                target_object=ObjectIdentifier(ObjectType.BINARY_VALUE, 2),
            ),
            BACnetAuditNotification(
                operation=AuditOperation.DELETE,
                target_object=ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 3),
            ),
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 4),
                target_property=85,
            ),
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifs)
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 4
        assert decoded.notifications[0].operation == AuditOperation.WRITE
        assert decoded.notifications[1].operation == AuditOperation.CREATE
        assert decoded.notifications[2].operation == AuditOperation.DELETE
        assert decoded.notifications[3].target_object == ObjectIdentifier(
            ObjectType.ANALOG_INPUT, 4
        )
        assert decoded.notifications[3].target_property == 85


# ---------------------------------------------------------------------------
# Coverage: audit.py lines 104-105, 112, 127-128, 135, 148, 158, 325-326
# ---------------------------------------------------------------------------


class TestAuditLogQueryByTargetNestedTags:
    """Lines 104-105, 112: by-target decode with nested opening/closing tags."""

    def test_by_target_with_nested_constructed_tags(self):
        """Exercise nested opening/closing tag scanning in by-target decode.

        Manually craft an AuditLogQuery with nested tags inside the [1] block.
        """
        from bac_py.encoding.primitives import (
            encode_context_object_id,
            encode_context_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] audit-log = AUDIT_LOG, 1
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.AUDIT_LOG, 1)))
        # [1] by-target (opening)
        buf.extend(encode_opening_tag(1))
        # Inside: target-device-identifier [0]
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.DEVICE, 100)))
        # Simulate a nested constructed field: opening tag 99 + data + closing tag 99
        # (This forces lines 104-105 to fire)
        buf.extend(encode_opening_tag(99))
        buf.extend(encode_opening_tag(98))  # doubly-nested (line 104-105 again + 112)
        buf.extend(encode_closing_tag(98))  # closes inner (line 112: depth > 0 still)
        buf.extend(encode_closing_tag(99))  # closes outer (depth == 0)
        # [7] result-filter
        from bac_py.encoding.primitives import encode_context_enumerated

        buf.extend(encode_context_enumerated(7, 0))
        # [1] by-target (closing)
        buf.extend(encode_closing_tag(1))
        # [4] requested-count
        buf.extend(encode_context_unsigned(4, 50))

        decoded = AuditLogQueryRequest.decode(bytes(buf))
        assert decoded.audit_log == ObjectIdentifier(ObjectType.AUDIT_LOG, 1)
        assert isinstance(decoded.query_parameters, AuditQueryByTarget)
        assert decoded.requested_count == 50


class TestAuditLogQueryBySourceNestedTags:
    """Lines 127-128, 135: by-source decode with nested opening/closing tags."""

    def test_by_source_with_nested_constructed_tags(self):
        """Exercise nested opening/closing tag scanning in by-source decode."""
        from bac_py.encoding.primitives import (
            encode_context_object_id,
            encode_context_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        buf = bytearray()
        # [0] audit-log = AUDIT_LOG, 2
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.AUDIT_LOG, 2)))
        # [2] by-source (opening)
        buf.extend(encode_opening_tag(2))
        # Inside: source-device-identifier [0]
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.DEVICE, 200)))
        # Simulate nested constructed field
        buf.extend(encode_opening_tag(99))
        buf.extend(encode_opening_tag(98))  # lines 127-128: nested opening
        buf.extend(encode_closing_tag(98))  # line 135: closing with depth > 0
        buf.extend(encode_closing_tag(99))
        # result-filter [7]
        from bac_py.encoding.primitives import encode_context_enumerated

        buf.extend(encode_context_enumerated(7, 0))
        # [2] by-source (closing)
        buf.extend(encode_closing_tag(2))
        # [4] requested-count
        buf.extend(encode_context_unsigned(4, 25))

        decoded = AuditLogQueryRequest.decode(bytes(buf))
        assert isinstance(decoded.query_parameters, AuditQueryBySource)
        assert decoded.requested_count == 25


class TestAuditLogQueryNonContextTag:
    """Line 148: non-context tag stops parsing of optional fields."""

    def test_non_context_tag_stops_parsing(self):
        """Append an application-tagged value after the query to exercise line 148."""
        from bac_py.encoding.primitives import encode_application_unsigned

        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query,
        )
        encoded = bytearray(request.encode())
        # Append an application-tagged unsigned (non-context tag)
        encoded.extend(encode_application_unsigned(999))
        decoded = AuditLogQueryRequest.decode(bytes(encoded))
        assert decoded.start_at_sequence_number is None
        assert decoded.requested_count == 100


class TestAuditLogQueryUnknownTag:
    """Line 158: unknown context tag number stops parsing."""

    def test_unknown_context_tag_stops_parsing(self):
        """Append a context tag with number 5 after the query to exercise line 158."""
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query,
        )
        encoded = bytearray(request.encode())
        # Append an unknown context tag (number 5)
        encoded.extend(encode_context_tagged(5, encode_unsigned(999)))
        decoded = AuditLogQueryRequest.decode(bytes(encoded))
        assert decoded.start_at_sequence_number is None
        assert decoded.requested_count == 100


class TestConfirmedAuditNotificationNestedOpening:
    """Lines 325-326: ConfirmedAuditNotification decode with nested opening tags."""

    def test_round_trip_with_constructed_fields(self):
        """Notifications with constructed fields exercise nested tag scanning.

        Lines 324-326 need doubly-nested opening tags inside a constructed element.
        """
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag

        # Create a target_value that contains nested constructed data
        nested_value = bytearray()
        nested_value.extend(encode_opening_tag(0))
        nested_value.extend(b"\x21\x05")  # unsigned 5
        nested_value.extend(encode_closing_tag(0))
        target_val = bytes(nested_value)

        notifs = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                target_property=85,
                target_value=target_val,
            ),
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 2),
                target_property=85,
            ),
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifs)
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 2
        assert decoded.notifications[0].target_value == target_val
        assert decoded.notifications[1].target_object == ObjectIdentifier(
            ObjectType.ANALOG_INPUT, 2
        )


# ---------------------------------------------------------------------------
# Coverage: audit.py branch partials 214->248, 230->243, 292->344, 313->340
# ---------------------------------------------------------------------------


class TestAuditLogQueryACKEmptyRecords:
    """Branch 214->248: while loop exit in AuditLogQueryACK.decode.

    While loop exits immediately because the first tag after opening [1]
    is closing [1].
    """

    def test_empty_records_while_loop_break(self):
        """Empty records list: while enters and immediately breaks at closing tag."""
        ack = AuditLogQueryACK(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            records=[],
            no_more_items=False,
        )
        encoded = ack.encode()
        decoded = AuditLogQueryACK.decode(encoded)
        assert decoded.records == []
        assert decoded.no_more_items is False


class TestAuditLogQueryACKRecordNotOpening:
    """Branch 230->243: record tag is_opening check in AuditLogQueryACK.decode.

    When rec_tag.is_opening is False, the code skips the depth-tracking loop
    and goes directly to BACnetAuditLogRecord.decode.
    """

    def test_single_record_round_trip(self):
        """Single record exercises the is_opening branch for [1] tag."""
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            target_property=85,
        )
        record = BACnetAuditLogRecord(sequence_number=42, notification=notif)
        ack = AuditLogQueryACK(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            records=[record],
            no_more_items=True,
        )
        encoded = ack.encode()
        decoded = AuditLogQueryACK.decode(encoded)
        assert len(decoded.records) == 1
        assert decoded.records[0].sequence_number == 42
        assert decoded.records[0].notification.operation == AuditOperation.WRITE


class TestConfirmedAuditNotificationEmptyList:
    """Branch 292->344: while loop exit in ConfirmedAuditNotificationRequest.decode.

    While loop exits because the first tag is a closing tag [0].
    """

    def test_single_notification_decode(self):
        """Single notification exercises the full while loop path."""
        notif = BACnetAuditNotification(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.BINARY_VALUE, 5),
        )
        request = ConfirmedAuditNotificationRequest(notifications=[notif])
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 1
        assert decoded.notifications[0].operation == AuditOperation.DELETE


class TestConfirmedAuditNotificationScanLoop:
    """Branch 313->340: inner scan while loop in ConfirmedAuditNotification.decode.

    The inner scan while loop exits when scan reaches end of data.
    """

    def test_five_notifications_scan_boundary(self):
        """Multiple notifications without constructed fields to exercise scan."""
        notifs = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i),
                target_property=85,
            )
            for i in range(5)
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifs)
        encoded = request.encode()
        decoded = ConfirmedAuditNotificationRequest.decode(encoded)
        assert len(decoded.notifications) == 5
        for i, n in enumerate(decoded.notifications):
            assert n.target_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, i)
