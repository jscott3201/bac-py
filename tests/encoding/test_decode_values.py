"""Tests for decode_application_value and decode_all_application_values."""

import pytest

from bac_py.encoding.primitives import (
    decode_all_application_values,
    decode_application_value,
    encode_application_bit_string,
    encode_application_boolean,
    encode_application_character_string,
    encode_application_date,
    encode_application_double,
    encode_application_enumerated,
    encode_application_null,
    encode_application_object_id,
    encode_application_octet_string,
    encode_application_real,
    encode_application_signed,
    encode_application_time,
    encode_application_unsigned,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


class TestDecodeApplicationValue:
    def test_null(self):
        data = encode_application_null()
        assert decode_application_value(data) is None

    def test_boolean_true(self):
        data = encode_application_boolean(True)
        assert decode_application_value(data) is True

    def test_boolean_false(self):
        data = encode_application_boolean(False)
        assert decode_application_value(data) is False

    def test_unsigned_zero(self):
        data = encode_application_unsigned(0)
        assert decode_application_value(data) == 0

    def test_unsigned_small(self):
        data = encode_application_unsigned(42)
        assert decode_application_value(data) == 42

    def test_unsigned_large(self):
        data = encode_application_unsigned(100000)
        assert decode_application_value(data) == 100000

    def test_signed_positive(self):
        data = encode_application_signed(42)
        assert decode_application_value(data) == 42

    def test_signed_negative(self):
        data = encode_application_signed(-100)
        assert decode_application_value(data) == -100

    def test_real(self):
        data = encode_application_real(72.5)
        result = decode_application_value(data)
        assert isinstance(result, float)
        assert result == pytest.approx(72.5)

    def test_real_zero(self):
        data = encode_application_real(0.0)
        assert decode_application_value(data) == 0.0

    def test_real_negative(self):
        data = encode_application_real(-42.5)
        assert decode_application_value(data) == pytest.approx(-42.5)

    def test_double(self):
        data = encode_application_double(3.14159265358979)
        result = decode_application_value(data)
        assert isinstance(result, float)
        assert result == pytest.approx(3.14159265358979)

    def test_octet_string(self):
        data = encode_application_octet_string(b"\xde\xad\xbe\xef")
        result = decode_application_value(data)
        assert isinstance(result, bytes)
        assert result == b"\xde\xad\xbe\xef"

    def test_character_string(self):
        data = encode_application_character_string("Hello, BACnet!")
        result = decode_application_value(data)
        assert isinstance(result, str)
        assert result == "Hello, BACnet!"

    def test_character_string_empty(self):
        data = encode_application_character_string("")
        assert decode_application_value(data) == ""

    def test_character_string_unicode(self):
        data = encode_application_character_string("caf\u00e9")
        assert decode_application_value(data) == "caf\u00e9"

    def test_bit_string(self):
        bs = BitString(b"\xf0", 4)
        data = encode_application_bit_string(bs)
        result = decode_application_value(data)
        assert isinstance(result, BitString)
        assert result == bs

    def test_enumerated(self):
        data = encode_application_enumerated(3)
        result = decode_application_value(data)
        assert isinstance(result, int)
        assert result == 3

    def test_date(self):
        date = BACnetDate(2024, 7, 15, 1)
        data = encode_application_date(date)
        result = decode_application_value(data)
        assert isinstance(result, BACnetDate)
        assert result == date

    def test_date_wildcard(self):
        date = BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
        data = encode_application_date(date)
        result = decode_application_value(data)
        assert result == date

    def test_time(self):
        time = BACnetTime(14, 30, 45, 0)
        data = encode_application_time(time)
        result = decode_application_value(data)
        assert isinstance(result, BACnetTime)
        assert result == time

    def test_object_identifier(self):
        data = encode_application_object_id(8, 100)
        result = decode_application_value(data)
        assert isinstance(result, ObjectIdentifier)
        assert result.object_type == ObjectType.DEVICE
        assert result.instance_number == 100

    def test_object_identifier_analog_input(self):
        data = encode_application_object_id(0, 1)
        result = decode_application_value(data)
        assert result.object_type == ObjectType.ANALOG_INPUT
        assert result.instance_number == 1

    def test_context_tagged_raises(self):
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        data = encode_context_tagged(0, encode_unsigned(42))
        with pytest.raises(ValueError, match="Expected application tag"):
            decode_application_value(data)

    def test_memoryview_input(self):
        data = encode_application_unsigned(99)
        result = decode_application_value(memoryview(data))
        assert result == 99


class TestDecodeAllApplicationValues:
    def test_single_value(self):
        data = encode_application_real(72.5)
        result = decode_all_application_values(data)
        assert len(result) == 1
        assert result[0] == pytest.approx(72.5)

    def test_multiple_values(self):
        data = (
            encode_application_unsigned(1)
            + encode_application_real(72.5)
            + encode_application_character_string("test")
        )
        result = decode_all_application_values(data)
        assert len(result) == 3
        assert result[0] == 1
        assert result[1] == pytest.approx(72.5)
        assert result[2] == "test"

    def test_object_id_list(self):
        data = (
            encode_application_object_id(0, 1)
            + encode_application_object_id(0, 2)
            + encode_application_object_id(8, 100)
        )
        result = decode_all_application_values(data)
        assert len(result) == 3
        assert result[0] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert result[1] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 2)
        assert result[2] == ObjectIdentifier(ObjectType.DEVICE, 100)

    def test_empty_data(self):
        result = decode_all_application_values(b"")
        assert result == []

    def test_mixed_types(self):
        data = (
            encode_application_null()
            + encode_application_boolean(True)
            + encode_application_unsigned(42)
            + encode_application_enumerated(1)
        )
        result = decode_all_application_values(data)
        assert len(result) == 4
        assert result[0] is None
        assert result[1] is True
        assert result[2] == 42
        assert result[3] == 1

    def test_memoryview_input(self):
        data = encode_application_unsigned(1) + encode_application_unsigned(2)
        result = decode_all_application_values(memoryview(data))
        assert result == [1, 2]
