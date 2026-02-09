"""Tests for encode_property_value covering Phase 1 fixes (B1-B4) and context-tagged helpers (E2-E3)."""

import pytest

from bac_py.encoding.primitives import (
    decode_application_value,
    encode_context_bit_string,
    encode_context_boolean,
    encode_context_character_string,
    encode_context_date,
    encode_context_double,
    encode_context_enumerated,
    encode_context_octet_string,
    encode_context_real,
    encode_context_signed,
    encode_context_time,
    encode_context_unsigned,
    encode_property_value,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import BinaryPV, DeviceStatus, ObjectType
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


class TestEncodePropertyValueNull:
    """B2: encode_property_value must handle None -> Null."""

    def test_none_encodes_as_null(self):
        result = encode_property_value(None)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 0  # Null tag
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 0

    def test_none_round_trip(self):
        result = encode_property_value(None)
        assert decode_application_value(result) is None


class TestEncodePropertyValueBoolean:
    """B1: encode_property_value must encode bool as Boolean (tag 1), NOT Enumerated (tag 9)."""

    def test_true_encodes_as_boolean_tag(self):
        result = encode_property_value(True)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 1  # Boolean tag, NOT 9 (Enumerated)
        assert tag.cls == TagClass.APPLICATION

    def test_false_encodes_as_boolean_tag(self):
        result = encode_property_value(False)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 1  # Boolean tag
        assert tag.cls == TagClass.APPLICATION

    def test_true_round_trip(self):
        result = encode_property_value(True)
        assert decode_application_value(result) is True

    def test_false_round_trip(self):
        result = encode_property_value(False)
        assert decode_application_value(result) is False

    def test_bool_not_encoded_as_enumerated(self):
        """Verify tag number is 1 (Boolean) not 9 (Enumerated)."""
        for val in [True, False]:
            result = encode_property_value(val)
            tag, _offset = decode_tag(result, 0)
            assert tag.number != 9, f"bool {val} should not be encoded as enumerated (tag 9)"


class TestEncodePropertyValueDate:
    """B3: encode_property_value must handle BACnetDate."""

    def test_date_encodes_with_date_tag(self):
        date = BACnetDate(2024, 7, 15, 1)
        result = encode_property_value(date)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 10  # Date tag
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_date_round_trip(self):
        date = BACnetDate(2024, 12, 25, 3)
        result = encode_property_value(date)
        decoded = decode_application_value(result)
        assert isinstance(decoded, BACnetDate)
        assert decoded == date

    def test_wildcard_date_round_trip(self):
        date = BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
        result = encode_property_value(date)
        decoded = decode_application_value(result)
        assert decoded == date


class TestEncodePropertyValueTime:
    """B3: encode_property_value must handle BACnetTime."""

    def test_time_encodes_with_time_tag(self):
        time = BACnetTime(14, 30, 45, 50)
        result = encode_property_value(time)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 11  # Time tag
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_time_round_trip(self):
        time = BACnetTime(23, 59, 59, 99)
        result = encode_property_value(time)
        decoded = decode_application_value(result)
        assert isinstance(decoded, BACnetTime)
        assert decoded == time

    def test_wildcard_time_round_trip(self):
        time = BACnetTime(0xFF, 0xFF, 0xFF, 0xFF)
        result = encode_property_value(time)
        decoded = decode_application_value(result)
        assert decoded == time


class TestEncodePropertyValueStatusFlags:
    """B4: encode_property_value must handle StatusFlags -> BitString."""

    def test_status_flags_encodes_as_bit_string(self):
        flags = StatusFlags(in_alarm=False, fault=False, overridden=False, out_of_service=False)
        result = encode_property_value(flags)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 8  # BitString tag
        assert tag.cls == TagClass.APPLICATION

    def test_status_flags_all_normal(self):
        flags = StatusFlags()
        result = encode_property_value(flags)
        decoded = decode_application_value(result)
        assert isinstance(decoded, BitString)
        reconstructed = StatusFlags.from_bit_string(decoded)
        assert reconstructed == flags

    def test_status_flags_in_alarm(self):
        flags = StatusFlags(in_alarm=True)
        result = encode_property_value(flags)
        decoded = decode_application_value(result)
        reconstructed = StatusFlags.from_bit_string(decoded)
        assert reconstructed.in_alarm is True
        assert reconstructed.fault is False
        assert reconstructed.overridden is False
        assert reconstructed.out_of_service is False

    def test_status_flags_all_set(self):
        flags = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        result = encode_property_value(flags)
        decoded = decode_application_value(result)
        reconstructed = StatusFlags.from_bit_string(decoded)
        assert reconstructed == flags

    def test_status_flags_out_of_service(self):
        flags = StatusFlags(out_of_service=True)
        result = encode_property_value(flags)
        decoded = decode_application_value(result)
        reconstructed = StatusFlags.from_bit_string(decoded)
        assert reconstructed.out_of_service is True


class TestEncodePropertyValueExistingTypes:
    """Verify existing type encoding still works correctly after changes."""

    def test_object_identifier(self):
        oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        result = encode_property_value(oid)
        decoded = decode_application_value(result)
        assert decoded == oid

    def test_bit_string(self):
        bs = BitString(b"\xf0", 4)
        result = encode_property_value(bs)
        decoded = decode_application_value(result)
        assert decoded == bs

    def test_string(self):
        result = encode_property_value("hello")
        decoded = decode_application_value(result)
        assert decoded == "hello"

    def test_int_enum(self):
        result = encode_property_value(BinaryPV.ACTIVE)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated tag
        decoded = decode_application_value(result)
        assert decoded == 1

    def test_device_status_enum(self):
        result = encode_property_value(DeviceStatus.OPERATIONAL)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated tag
        decoded = decode_application_value(result)
        assert decoded == 0

    def test_float(self):
        result = encode_property_value(72.5)
        decoded = decode_application_value(result)
        assert decoded == pytest.approx(72.5)

    def test_unsigned_int(self):
        result = encode_property_value(42)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 2  # Unsigned tag
        decoded = decode_application_value(result)
        assert decoded == 42

    def test_int_as_real(self):
        result = encode_property_value(42, int_as_real=True)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 4  # Real tag
        decoded = decode_application_value(result)
        assert decoded == pytest.approx(42.0)

    def test_bytes_passthrough(self):
        original = b"\x44\x91\x00"  # some pre-encoded bytes
        result = encode_property_value(original)
        assert result == original

    def test_list_encoding(self):
        values = [1, 2, 3]
        result = encode_property_value(values)
        # Should be 3 concatenated application-tagged unsigned values
        from bac_py.encoding.primitives import decode_all_application_values

        decoded = decode_all_application_values(result)
        assert decoded == [1, 2, 3]

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="Cannot encode value of type"):
            encode_property_value(object())


class TestEncodePropertyValuePriorityArray:
    """Verify Priority_Array encoding with None (relinquished) slots works."""

    def test_priority_array_with_none_slots(self):
        """A priority array with relinquished slots should encode Null for None values."""
        from bac_py.encoding.primitives import decode_all_application_values

        priority_array = [
            None,
            None,
            None,
            None,
            72.5,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        result = encode_property_value(priority_array)
        decoded = decode_all_application_values(result)
        assert len(decoded) == 16
        assert decoded[0] is None
        assert decoded[4] == pytest.approx(72.5)
        for i in [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]:
            assert decoded[i] is None

    def test_mixed_priority_array(self):
        """Priority array with mixed types including None."""
        from bac_py.encoding.primitives import decode_all_application_values

        priority_array = [
            None,
            50.0,
            None,
            None,
            None,
            None,
            None,
            None,
            25.0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        result = encode_property_value(priority_array)
        decoded = decode_all_application_values(result)
        assert decoded[0] is None
        assert decoded[1] == pytest.approx(50.0)
        assert decoded[8] == pytest.approx(25.0)


class TestContextTaggedHelpers:
    """E2/E3: Context-tagged encoding helpers for all primitive types."""

    def test_context_unsigned(self):
        result = encode_context_unsigned(0, 42)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 0
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_unsigned

        assert decode_unsigned(result[offset : offset + tag.length]) == 42

    def test_context_signed(self):
        result = encode_context_signed(1, -10)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 1
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_signed

        assert decode_signed(result[offset : offset + tag.length]) == -10

    def test_context_enumerated(self):
        result = encode_context_enumerated(2, 5)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 2
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_enumerated

        assert decode_enumerated(result[offset : offset + tag.length]) == 5

    def test_context_boolean_true(self):
        result = encode_context_boolean(3, True)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 3
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 1
        from bac_py.encoding.primitives import decode_boolean

        assert decode_boolean(result[offset : offset + tag.length]) is True

    def test_context_boolean_false(self):
        result = encode_context_boolean(0, False)
        tag, offset = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 1
        from bac_py.encoding.primitives import decode_boolean

        assert decode_boolean(result[offset : offset + tag.length]) is False

    def test_context_real(self):
        result = encode_context_real(4, 3.14)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 4
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 4
        from bac_py.encoding.primitives import decode_real

        assert decode_real(result[offset : offset + tag.length]) == pytest.approx(3.14, rel=1e-6)

    def test_context_double(self):
        result = encode_context_double(5, 3.14159265358979)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 5
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 8
        from bac_py.encoding.primitives import decode_double

        assert decode_double(result[offset : offset + tag.length]) == pytest.approx(
            3.14159265358979
        )

    def test_context_character_string(self):
        result = encode_context_character_string(6, "hello")
        tag, offset = decode_tag(result, 0)
        assert tag.number == 6
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_character_string

        assert decode_character_string(result[offset : offset + tag.length]) == "hello"

    def test_context_octet_string(self):
        result = encode_context_octet_string(7, b"\xde\xad")
        tag, offset = decode_tag(result, 0)
        assert tag.number == 7
        assert tag.cls == TagClass.CONTEXT
        assert result[offset : offset + tag.length] == b"\xde\xad"

    def test_context_bit_string(self):
        bs = BitString(b"\xf0", 4)
        result = encode_context_bit_string(0, bs)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 0
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_bit_string

        decoded = decode_bit_string(result[offset : offset + tag.length])
        assert decoded == bs

    def test_context_date(self):
        date = BACnetDate(2024, 7, 15, 1)
        result = encode_context_date(1, date)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 1
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 4
        from bac_py.encoding.primitives import decode_date

        assert decode_date(result[offset : offset + tag.length]) == date

    def test_context_time(self):
        time = BACnetTime(14, 30, 45, 50)
        result = encode_context_time(2, time)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 2
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 4
        from bac_py.encoding.primitives import decode_time

        assert decode_time(result[offset : offset + tag.length]) == time

    def test_context_high_tag_number(self):
        """Context tags with tag number > 14 use extended encoding."""
        result = encode_context_unsigned(15, 100)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 15
        assert tag.cls == TagClass.CONTEXT
        from bac_py.encoding.primitives import decode_unsigned

        assert decode_unsigned(result[offset : offset + tag.length]) == 100


class TestDeviceStatusEnum:
    """B5: DeviceStatus enum values and usage."""

    def test_device_status_values(self):
        assert DeviceStatus.OPERATIONAL == 0
        assert DeviceStatus.OPERATIONAL_READ_ONLY == 1
        assert DeviceStatus.DOWNLOAD_REQUIRED == 2
        assert DeviceStatus.DOWNLOAD_IN_PROGRESS == 3
        assert DeviceStatus.NON_OPERATIONAL == 4
        assert DeviceStatus.BACKUP_IN_PROGRESS == 5

    def test_device_status_encodes_as_enumerated(self):
        result = encode_property_value(DeviceStatus.OPERATIONAL)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated
        decoded = decode_application_value(result)
        assert decoded == 0

    def test_device_object_uses_device_status(self):
        from bac_py.objects.device import DeviceObject
        from bac_py.types.enums import PropertyIdentifier

        dev = DeviceObject(
            100,
            object_name="Test Device",
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )
        status = dev.read_property(PropertyIdentifier.SYSTEM_STATUS)
        assert status == DeviceStatus.OPERATIONAL
        assert isinstance(status, DeviceStatus)

    def test_device_status_round_trip(self):
        for status in DeviceStatus:
            result = encode_property_value(status)
            decoded = decode_application_value(result)
            assert decoded == status.value


class TestTypeOrderPrecedence:
    """Verify isinstance check ordering is correct in encode_property_value."""

    def test_bool_before_int(self):
        """Bool is a subclass of int, must be checked first."""
        result = encode_property_value(True)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 1  # Boolean, not Unsigned (2)

    def test_int_enum_before_int(self):
        """IntEnum is a subclass of int, must be checked first."""
        result = encode_property_value(BinaryPV.ACTIVE)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated, not Unsigned (2)

    def test_status_flags_before_generic(self):
        """StatusFlags should be handled before generic types."""
        flags = StatusFlags(in_alarm=True)
        result = encode_property_value(flags)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 8  # BitString

    def test_object_identifier_handled(self):
        """ObjectIdentifier should encode as tag 12."""
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        result = encode_property_value(oid)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 12  # Object Identifier
