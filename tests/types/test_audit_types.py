"""Tests for BACnet audit constructed types."""

from bac_py.encoding.primitives import (
    encode_context_enumerated,
    encode_context_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    encode_closing_tag,
    encode_opening_tag,
    encode_tag,
)
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


# ---------------------------------------------------------------------------
# Coverage gap tests — exercise uncovered decode paths
# ---------------------------------------------------------------------------


class TestDecodeTimestampSkip:
    """Lines 179-188 and 191-200: skip [0] source-timestamp and [1] target-timestamp."""

    def test_source_timestamp_skipped(self):
        """Constructed [0] source-timestamp with nested content is skipped."""
        buf = bytearray()
        # [0] opening — source-timestamp
        buf.extend(encode_opening_tag(0))
        # Inner: a primitive context tag (fake timestamp data, 2 bytes)
        buf.extend(encode_tag(0, TagClass.CONTEXT, 2))
        buf.extend(b"\x07\xe6")  # arbitrary timestamp bytes
        # [0] closing
        buf.extend(encode_closing_tag(0))
        # [4] operation = WRITE (3)
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.WRITE

    def test_target_timestamp_skipped(self):
        """Constructed [1] target-timestamp with nested content is skipped."""
        buf = bytearray()
        # [1] opening — target-timestamp
        buf.extend(encode_opening_tag(1))
        # Inner: a primitive context tag with 3 bytes
        buf.extend(encode_tag(2, TagClass.CONTEXT, 3))
        buf.extend(b"\x01\x02\x03")
        # [1] closing
        buf.extend(encode_closing_tag(1))
        # [4] operation = READ (2)
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.READ

    def test_both_timestamps_skipped(self):
        """Both source and target timestamps present; both skipped correctly."""
        buf = bytearray()
        # [0] source-timestamp with nested constructed content
        buf.extend(encode_opening_tag(0))
        # Nested opening/closing inside (tests depth tracking)
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_tag(0, TagClass.CONTEXT, 1))
        buf.extend(b"\x01")
        buf.extend(encode_closing_tag(0))
        buf.extend(encode_closing_tag(0))
        # [1] target-timestamp with nested constructed content
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_tag(0, TagClass.CONTEXT, 1))
        buf.extend(b"\x02")
        buf.extend(encode_closing_tag(1))
        buf.extend(encode_closing_tag(1))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.DELETE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.DELETE


class TestDecodeNonDeviceRecipient:
    """Line 212 and 263: inner tag number != 1 in source-device / target-device."""

    def test_source_device_non_device_choice(self):
        """[2] source-device with inner tag [0] (address choice) leaves source_device None."""
        buf = bytearray()
        # [2] opening — source-device
        buf.extend(encode_opening_tag(2))
        # Inner tag [0] = address choice (not [1] = device), 4 bytes of address data
        buf.extend(encode_tag(0, TagClass.CONTEXT, 4))
        buf.extend(b"\xc0\xa8\x01\x01")
        # [2] closing
        buf.extend(encode_closing_tag(2))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.source_device is None
        assert decoded.operation == AuditOperation.WRITE

    def test_target_device_non_device_choice(self):
        """[10] target-device with inner tag [0] (address choice) leaves target_device None."""
        buf = bytearray()
        # [4] operation first
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))
        # [10] opening — target-device
        buf.extend(encode_opening_tag(10))
        # Inner tag [0] = address choice (not device), 3 bytes
        buf.extend(encode_tag(0, TagClass.CONTEXT, 3))
        buf.extend(b"\x0a\x00\x01")
        # [10] closing
        buf.extend(encode_closing_tag(10))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.target_device is None
        assert decoded.operation == AuditOperation.READ


class TestDecodeNestedValues:
    """Lines 303-304, 311, 322-323, 330: nested opening/closing in target/current-value."""

    def test_target_value_with_nested_constructed(self):
        """[14] target-value containing nested opening/closing tags."""
        # The inner content: an opening tag, primitive data, closing tag
        inner = bytearray()
        inner.extend(encode_opening_tag(0))  # nested opening
        inner.extend(encode_tag(0, TagClass.CONTEXT, 2))
        inner.extend(b"\xab\xcd")
        inner.extend(encode_closing_tag(0))  # nested closing
        inner_bytes = bytes(inner)

        buf = bytearray()
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))
        # [14] opening — target-value
        buf.extend(encode_opening_tag(14))
        buf.extend(inner_bytes)
        # [14] closing
        buf.extend(encode_closing_tag(14))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.target_value == inner_bytes
        assert decoded.operation == AuditOperation.WRITE

    def test_current_value_with_nested_constructed(self):
        """[15] current-value containing nested opening/closing tags."""
        inner = bytearray()
        inner.extend(encode_opening_tag(2))  # nested opening
        inner.extend(encode_tag(1, TagClass.CONTEXT, 3))
        inner.extend(b"\x01\x02\x03")
        inner.extend(encode_closing_tag(2))  # nested closing
        inner_bytes = bytes(inner)

        buf = bytearray()
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))
        # [15] opening — current-value
        buf.extend(encode_opening_tag(15))
        buf.extend(inner_bytes)
        # [15] closing
        buf.extend(encode_closing_tag(15))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.current_value == inner_bytes
        assert decoded.operation == AuditOperation.READ

    def test_target_value_deeply_nested(self):
        """[14] target-value with two levels of nesting (depth > 1 after inner closing)."""
        inner = bytearray()
        # Level 1 nested opening
        inner.extend(encode_opening_tag(0))
        # Level 2 nested opening
        inner.extend(encode_opening_tag(1))
        inner.extend(encode_tag(0, TagClass.CONTEXT, 1))
        inner.extend(b"\xff")
        # Level 2 nested closing — depth goes from 3 to 2 (> 0, hits line 311)
        inner.extend(encode_closing_tag(1))
        # Level 1 nested closing — depth goes from 2 to 1 (> 0, hits line 311)
        inner.extend(encode_closing_tag(0))
        inner_bytes = bytes(inner)

        buf = bytearray()
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))
        buf.extend(encode_opening_tag(14))
        buf.extend(inner_bytes)
        buf.extend(encode_closing_tag(14))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.target_value == inner_bytes

    def test_current_value_deeply_nested(self):
        """[15] current-value with two levels of nesting (depth > 1 after inner closing)."""
        inner = bytearray()
        inner.extend(encode_opening_tag(3))
        inner.extend(encode_opening_tag(4))
        inner.extend(encode_tag(0, TagClass.CONTEXT, 1))
        inner.extend(b"\xaa")
        inner.extend(encode_closing_tag(4))
        inner.extend(encode_closing_tag(3))
        inner_bytes = bytes(inner)

        buf = bytearray()
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))
        buf.extend(encode_opening_tag(15))
        buf.extend(inner_bytes)
        buf.extend(encode_closing_tag(15))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.current_value == inner_bytes


class TestDecodeUnknownTag:
    """Lines 345-357: unknown context tag numbers skipped (both primitive and constructed)."""

    def test_unknown_primitive_tag_skipped(self):
        """A primitive context tag with unknown number (e.g., 20) is skipped."""
        buf = bytearray()
        # Unknown primitive context tag [20], 2 bytes of data
        buf.extend(encode_tag(20, TagClass.CONTEXT, 2))
        buf.extend(b"\xde\xad")
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.WRITE

    def test_unknown_constructed_tag_skipped(self):
        """A constructed context tag with unknown number (e.g., 20) is skipped."""
        buf = bytearray()
        # Unknown constructed opening tag [20]
        buf.extend(encode_opening_tag(20))
        # Some nested primitive data inside
        buf.extend(encode_tag(0, TagClass.CONTEXT, 1))
        buf.extend(b"\x42")
        # Closing tag [20]
        buf.extend(encode_closing_tag(20))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.DELETE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.DELETE

    def test_unknown_constructed_tag_with_nesting(self):
        """Unknown constructed tag with nested opening/closing is fully skipped."""
        buf = bytearray()
        # Unknown constructed [21]
        buf.extend(encode_opening_tag(21))
        buf.extend(encode_opening_tag(0))
        buf.extend(encode_tag(0, TagClass.CONTEXT, 1))
        buf.extend(b"\x01")
        buf.extend(encode_closing_tag(0))
        buf.extend(encode_closing_tag(21))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.GENERAL))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.GENERAL


class TestDecodeNonContextTag:
    """Lines 174-175: application-class tags are skipped during decode."""

    def test_application_tag_skipped(self):
        """An APPLICATION-class tag before valid content is skipped."""
        buf = bytearray()
        # Application tag: tag_number=2 (Unsigned), 1 byte of data
        buf.extend(encode_tag(2, TagClass.APPLICATION, 1))
        buf.extend(b"\x05")
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.WRITE

    def test_multiple_application_tags_skipped(self):
        """Multiple APPLICATION tags interspersed are all skipped."""
        buf = bytearray()
        # App tag 1
        buf.extend(encode_tag(4, TagClass.APPLICATION, 4))
        buf.extend(b"\x41\x20\x00\x00")
        # App tag 2
        buf.extend(encode_tag(1, TagClass.APPLICATION, 0))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.READ


class TestDecodePropertyNoArrayIndex:
    """Line 279->290: [12] target-property where peek sees closing tag (no array_index)."""

    def test_property_ref_no_array_index_followed_by_more_tags(self):
        """Property reference without array index; closing tag [12] is next after [0]."""
        buf = bytearray()
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))
        # [12] target-property (BACnetPropertyReference) - property_id=85 only
        buf.extend(encode_opening_tag(12))
        buf.extend(encode_context_unsigned(0, 85))  # property-identifier
        # No [1] array-index -- closing tag follows immediately
        buf.extend(encode_closing_tag(12))
        # [13] target-priority follows to ensure decode continues
        buf.extend(encode_context_unsigned(13, 8))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.target_property == 85
        assert decoded.target_array_index is None
        assert decoded.target_priority == 8


class TestToDictArrayIndex:
    """Line 410: to_dict() includes target_array_index when set."""

    def test_to_dict_with_array_index(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_property=85,
            target_array_index=7,
        )
        d = notif.to_dict()
        assert d["target_array_index"] == 7
        assert d["target_property"] == 85
        assert d["operation"] == int(AuditOperation.WRITE)

    def test_to_dict_without_array_index(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_property=85,
        )
        d = notif.to_dict()
        assert "target_array_index" not in d


class TestQueryByTargetEdgeCases:
    """Lines 607, 636: AuditQueryByTarget decode with non-context and unknown tags."""

    def test_trailing_application_tag_breaks_decode(self):
        """Non-context tag after valid fields causes loop exit (line 607)."""
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            result_filter=1,
        )
        encoded = bytearray(query.encode())
        # Append an application-class tag (non-context) after valid data
        encoded.extend(encode_tag(2, TagClass.APPLICATION, 1))
        encoded.extend(b"\x42")

        decoded = AuditQueryByTarget.decode(bytes(encoded))
        assert decoded.target_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.result_filter == 1

    def test_unknown_context_tag_number_breaks_decode(self):
        """Unknown context tag number (e.g., 9) causes loop exit (line 636)."""
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            result_filter=0,
        )
        encoded = bytearray(query.encode())
        # Append a context tag with unknown tag number 9 (valid numbers are 1-7)
        encoded.extend(encode_tag(9, TagClass.CONTEXT, 1))
        encoded.extend(b"\x01")

        decoded = AuditQueryByTarget.decode(bytes(encoded))
        assert decoded.target_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.result_filter == 0


class TestQueryBySourceEdgeCases:
    """Lines 698, 716: AuditQueryBySource decode with non-context and unknown tags."""

    def test_trailing_application_tag_breaks_decode(self):
        """Non-context tag after valid fields causes loop exit (line 698)."""
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            result_filter=2,
        )
        encoded = bytearray(query.encode())
        # Append an application-class tag
        encoded.extend(encode_tag(3, TagClass.APPLICATION, 2))
        encoded.extend(b"\x00\x01")

        decoded = AuditQueryBySource.decode(bytes(encoded))
        assert decoded.source_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.result_filter == 2

    def test_unknown_context_tag_number_breaks_decode(self):
        """Unknown context tag number (e.g., 8) causes loop exit (line 716)."""
        query = AuditQueryBySource(
            source_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            result_filter=1,
        )
        encoded = bytearray(query.encode())
        # Append a context tag with unknown tag number 8 (valid numbers are 1-4)
        encoded.extend(encode_tag(8, TagClass.CONTEXT, 1))
        encoded.extend(b"\x05")

        decoded = AuditQueryBySource.decode(bytes(encoded))
        assert decoded.source_device_identifier == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.result_filter == 1


class TestToDictFromDictAllFields:
    """Lines 390-420, 430-448: to_dict/from_dict with all optional fields populated."""

    def test_to_dict_all_fields(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            source_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            source_comment="src comment",
            target_comment="tgt comment",
            invoke_id=42,
            source_user_id=1000,
            source_user_role=5,
            target_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            target_object=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2),
            target_property=85,
            target_array_index=3,
            target_priority=10,
            target_value=b"\xab\xcd",
            current_value=b"\xef\x01",
            result_error_class=2,
            result_error_code=31,
        )
        d = notif.to_dict()
        assert d["operation"] == int(AuditOperation.WRITE)
        assert d["source_device"] == ObjectIdentifier(ObjectType.DEVICE, 100).to_dict()
        assert d["source_object"] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1).to_dict()
        assert d["source_comment"] == "src comment"
        assert d["target_comment"] == "tgt comment"
        assert d["invoke_id"] == 42
        assert d["source_user_id"] == 1000
        assert d["source_user_role"] == 5
        assert d["target_device"] == ObjectIdentifier(ObjectType.DEVICE, 200).to_dict()
        assert d["target_object"] == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2).to_dict()
        assert d["target_property"] == 85
        assert d["target_array_index"] == 3
        assert d["target_priority"] == 10
        assert d["target_value"] == "abcd"
        assert d["current_value"] == "ef01"
        assert d["result_error_class"] == 2
        assert d["result_error_code"] == 31

    def test_from_dict_all_fields(self):
        d = {
            "operation": int(AuditOperation.WRITE),
            "source_device": ObjectIdentifier(ObjectType.DEVICE, 100).to_dict(),
            "source_object": ObjectIdentifier(ObjectType.ANALOG_INPUT, 1).to_dict(),
            "source_comment": "src comment",
            "target_comment": "tgt comment",
            "invoke_id": 42,
            "source_user_id": 1000,
            "source_user_role": 5,
            "target_device": ObjectIdentifier(ObjectType.DEVICE, 200).to_dict(),
            "target_object": ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2).to_dict(),
            "target_property": 85,
            "target_array_index": 3,
            "target_priority": 10,
            "target_value": "abcd",
            "current_value": "ef01",
            "result_error_class": 2,
            "result_error_code": 31,
        }
        notif = BACnetAuditNotification.from_dict(d)
        assert notif.operation == AuditOperation.WRITE
        assert notif.source_device == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert notif.source_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert notif.source_comment == "src comment"
        assert notif.target_comment == "tgt comment"
        assert notif.invoke_id == 42
        assert notif.source_user_id == 1000
        assert notif.source_user_role == 5
        assert notif.target_device == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert notif.target_object == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2)
        assert notif.target_property == 85
        assert notif.target_array_index == 3
        assert notif.target_priority == 10
        assert notif.target_value == b"\xab\xcd"
        assert notif.current_value == b"\xef\x01"
        assert notif.result_error_class == 2
        assert notif.result_error_code == 31

    def test_to_dict_from_dict_round_trip(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.DELETE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 50),
            target_value=b"\x01\x02\x03",
            current_value=b"\x04\x05\x06",
        )
        d = notif.to_dict()
        restored = BACnetAuditNotification.from_dict(d)
        assert restored.operation == notif.operation
        assert restored.source_device == notif.source_device
        assert restored.target_value == notif.target_value
        assert restored.current_value == notif.current_value


class TestAuditLogRecordSerialization:
    """Lines 506-507, 514, 526, 538: BACnetAuditLogRecord to_dict/from_dict and nested decode."""

    def test_to_dict(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 10),
        )
        record = BACnetAuditLogRecord(sequence_number=99, notification=notif)
        d = record.to_dict()
        assert d["sequence_number"] == 99
        assert d["notification"]["operation"] == int(AuditOperation.WRITE)

    def test_from_dict(self):
        d = {
            "sequence_number": 99,
            "notification": {
                "operation": int(AuditOperation.WRITE),
                "target_object": ObjectIdentifier(ObjectType.ANALOG_INPUT, 10).to_dict(),
            },
        }
        record = BACnetAuditLogRecord.from_dict(d)
        assert record.sequence_number == 99
        assert record.notification.operation == AuditOperation.WRITE
        assert record.notification.target_object == ObjectIdentifier(ObjectType.ANALOG_INPUT, 10)

    def test_to_dict_from_dict_round_trip(self):
        notif = BACnetAuditNotification(
            operation=AuditOperation.CREATE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_object=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
        )
        record = BACnetAuditLogRecord(sequence_number=12345, notification=notif)
        d = record.to_dict()
        restored = BACnetAuditLogRecord.from_dict(d)
        assert restored.sequence_number == record.sequence_number
        assert restored.notification.operation == record.notification.operation
        assert restored.notification.source_device == record.notification.source_device
        assert restored.notification.target_object == record.notification.target_object

    def test_decode_with_nested_constructed_notification(self):
        """BACnetAuditLogRecord decode with notification containing constructed fields.

        This tests the depth tracking in BACnetAuditLogRecord.decode() (lines 505-516)
        when the inner notification has constructed tags (opening/closing).
        """
        notif = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            target_property=85,
            target_array_index=3,
            target_value=b"\x44\x42\xc8\x00\x00",
            current_value=b"\x44\x42\x48\x00\x00",
            result_error_class=2,
            result_error_code=31,
        )
        record = BACnetAuditLogRecord(sequence_number=9999, notification=notif)
        encoded = record.encode()
        decoded = BACnetAuditLogRecord.decode(encoded)
        assert decoded.sequence_number == 9999
        assert decoded.notification.source_device == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.notification.target_device == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.notification.target_property == 85
        assert decoded.notification.target_array_index == 3
        assert decoded.notification.target_value == b"\x44\x42\xc8\x00\x00"
        assert decoded.notification.result_error_class == 2


# ---------------------------------------------------------------------------
# Coverage: branch partials for timestamp loop bodies and property ref
# ---------------------------------------------------------------------------


class TestTimestampLoopMultiplePrimitiveTags:
    """Branches 187->181 and 199->193: loop continuation with multiple primitive tags.

    These branches exercise the loop body in the source/target-timestamp
    decoders where primitive tags (not opening/closing) advance the offset
    and loop back to the while condition.
    """

    def test_source_timestamp_with_multiple_inner_tags(self):
        """Multiple primitive tags inside [0] source-timestamp exercises loop back."""
        buf = bytearray()
        # [0] opening — source-timestamp
        buf.extend(encode_opening_tag(0))
        # First primitive tag with 2 bytes
        buf.extend(encode_tag(0, TagClass.CONTEXT, 2))
        buf.extend(b"\x01\x02")
        # Second primitive tag with 1 byte — causes another iteration (187->181)
        buf.extend(encode_tag(1, TagClass.CONTEXT, 1))
        buf.extend(b"\x03")
        # [0] closing
        buf.extend(encode_closing_tag(0))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.WRITE

    def test_target_timestamp_with_multiple_inner_tags(self):
        """Multiple primitive tags inside [1] target-timestamp exercises loop back."""
        buf = bytearray()
        # [1] opening — target-timestamp
        buf.extend(encode_opening_tag(1))
        # First primitive tag
        buf.extend(encode_tag(0, TagClass.CONTEXT, 2))
        buf.extend(b"\x04\x05")
        # Second primitive tag — causes another iteration (199->193)
        buf.extend(encode_tag(1, TagClass.CONTEXT, 2))
        buf.extend(b"\x06\x07")
        # Third primitive tag — yet another iteration
        buf.extend(encode_tag(2, TagClass.CONTEXT, 1))
        buf.extend(b"\x08")
        # [1] closing
        buf.extend(encode_closing_tag(1))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.READ))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.READ


class TestPropertyRefPeekClosingTag:
    """Branch 279->290: peek at tag after property-identifier sees closing tag.

    When [12] target-property has only [0] property-identifier and the
    next tag is the [12] closing tag, the peek condition at line 281-284
    is False (closing tag, not context tag [1]), so we skip array-index.
    """

    def test_property_ref_closing_tag_immediately_after_property_id(self):
        """The immediate next tag after property_id is closing [12]."""
        buf = bytearray()
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.WRITE))
        # [12] target-property
        buf.extend(encode_opening_tag(12))
        buf.extend(encode_context_unsigned(0, 85))  # property-identifier = 85
        # Closing [12] immediately — no array index
        buf.extend(encode_closing_tag(12))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.target_property == 85
        assert decoded.target_array_index is None


class TestUnknownTagSkipMultiplePrimitiveTags:
    """Branch 354->348: unknown constructed tag with multiple primitive inner tags.

    The skip-loop body processes multiple primitive tags, each advancing
    offset and looping back (354->348).
    """

    def test_unknown_constructed_with_multiple_primitives(self):
        """Unknown tag [25] with 3 primitive inner tags — full loop exercise."""
        buf = bytearray()
        # Unknown constructed [25]
        buf.extend(encode_opening_tag(25))
        # Multiple primitive inner tags
        buf.extend(encode_tag(0, TagClass.CONTEXT, 2))
        buf.extend(b"\xaa\xbb")
        buf.extend(encode_tag(1, TagClass.CONTEXT, 1))
        buf.extend(b"\xcc")
        buf.extend(encode_tag(2, TagClass.CONTEXT, 3))
        buf.extend(b"\xdd\xee\xff")
        # Closing [25]
        buf.extend(encode_closing_tag(25))
        # [4] operation
        buf.extend(encode_context_enumerated(4, AuditOperation.GENERAL))

        decoded = BACnetAuditNotification.decode(bytes(buf))
        assert decoded.operation == AuditOperation.GENERAL
