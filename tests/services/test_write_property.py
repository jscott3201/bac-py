from bac_py.services.write_property import WritePropertyRequest
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestWritePropertyRequest:
    def test_round_trip_basic(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",  # REAL 42.0
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.object_identifier.object_type == ObjectType.ANALOG_OUTPUT
        assert decoded.object_identifier.instance_number == 1
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.property_array_index is None
        assert decoded.priority is None

    def test_round_trip_with_priority(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 5),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x00\x00\x00\x00",
            priority=8,
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.priority == 8

    def test_round_trip_with_array_index(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=b"\x75\x04\x00abc",
            property_array_index=2,
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.property_array_index == 2
        assert decoded.property_value == b"\x75\x04\x00abc"

    def test_round_trip_with_priority_and_array_index(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 3),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x41\xa0\x00\x00",
            property_array_index=1,
            priority=16,
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.property_array_index == 1
        assert decoded.priority == 16
        assert decoded.property_value == b"\x44\x41\xa0\x00\x00"

    def test_round_trip_empty_value(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.DESCRIPTION,
            property_value=b"",
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.property_value == b""

    def test_round_trip_priority_1(self):
        req = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x91\x01",
            priority=1,
        )
        decoded = WritePropertyRequest.decode(req.encode())
        assert decoded.priority == 1


# ---------------------------------------------------------------------------
# Coverage: write_property.py line 115 — priority out of range
# ---------------------------------------------------------------------------


class TestWritePropertyPriorityOutOfRange:
    """Line 114-115: priority out of 1-16 range raises BACnetRejectError."""

    def test_priority_zero_raises(self):
        import pytest

        from bac_py.encoding.primitives import (
            encode_context_object_id,
            encode_context_tagged,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        # [0] objectIdentifier
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)))
        # [1] propertyIdentifier = PRESENT_VALUE (85)
        buf.extend(encode_context_tagged(1, encode_unsigned(85)))
        # [3] propertyValue
        buf.extend(encode_opening_tag(3))
        buf.extend(b"\x44\x00\x00\x00\x00")  # REAL 0.0
        buf.extend(encode_closing_tag(3))
        # [4] priority = 0 (out of range)
        buf.extend(encode_context_tagged(4, encode_unsigned(0)))
        with pytest.raises(BACnetRejectError):
            WritePropertyRequest.decode(bytes(buf))

    def test_priority_17_raises(self):
        import pytest

        from bac_py.encoding.primitives import (
            encode_context_object_id,
            encode_context_tagged,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.services.errors import BACnetRejectError

        buf = bytearray()
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)))
        buf.extend(encode_context_tagged(1, encode_unsigned(85)))
        buf.extend(encode_opening_tag(3))
        buf.extend(b"\x44\x00\x00\x00\x00")
        buf.extend(encode_closing_tag(3))
        # [4] priority = 17 (out of range)
        buf.extend(encode_context_tagged(4, encode_unsigned(17)))
        with pytest.raises(BACnetRejectError):
            WritePropertyRequest.decode(bytes(buf))
