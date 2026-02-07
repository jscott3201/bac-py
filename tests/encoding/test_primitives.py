import struct

import pytest

from bac_py.encoding.primitives import (
    decode_bit_string,
    decode_boolean,
    decode_character_string,
    decode_date,
    decode_double,
    decode_enumerated,
    decode_object_identifier,
    decode_octet_string,
    decode_real,
    decode_signed,
    decode_time,
    decode_unsigned,
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
    encode_bit_string,
    encode_boolean,
    encode_character_string,
    encode_date,
    encode_double,
    encode_enumerated,
    encode_null,
    encode_object_identifier,
    encode_octet_string,
    encode_real,
    encode_signed,
    encode_time,
    encode_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString


class TestUnsigned:
    def test_encode_zero(self):
        assert encode_unsigned(0) == b"\x00"

    def test_encode_one(self):
        assert encode_unsigned(1) == b"\x01"

    def test_encode_255(self):
        assert encode_unsigned(255) == b"\xff"

    def test_encode_256(self):
        result = encode_unsigned(256)
        assert len(result) == 2
        assert result == (256).to_bytes(2, "big")

    def test_encode_65535(self):
        result = encode_unsigned(65535)
        assert len(result) == 2
        assert result == b"\xff\xff"

    def test_encode_large(self):
        result = encode_unsigned(0x01000000)
        assert result == b"\x01\x00\x00\x00"

    def test_encode_negative_raises(self):
        with pytest.raises(ValueError, match="Unsigned integer must be >= 0"):
            encode_unsigned(-1)

    def test_decode_zero(self):
        assert decode_unsigned(b"\x00") == 0

    def test_decode_one(self):
        assert decode_unsigned(b"\x01") == 1

    def test_decode_255(self):
        assert decode_unsigned(b"\xff") == 255

    def test_decode_256(self):
        assert decode_unsigned(b"\x01\x00") == 256

    def test_decode_65535(self):
        assert decode_unsigned(b"\xff\xff") == 65535

    def test_round_trip(self):
        for val in [0, 1, 127, 128, 255, 256, 65535, 65536, 0xFFFFFF, 0xFFFFFFFF]:
            assert decode_unsigned(encode_unsigned(val)) == val


class TestSigned:
    def test_encode_zero(self):
        assert encode_signed(0) == b"\x00"

    def test_encode_one(self):
        assert encode_signed(1) == b"\x01"

    def test_encode_negative_one(self):
        assert encode_signed(-1) == b"\xff"

    def test_encode_127(self):
        assert encode_signed(127) == b"\x7f"

    def test_encode_128(self):
        result = encode_signed(128)
        assert decode_signed(result) == 128

    def test_encode_negative_128(self):
        result = encode_signed(-128)
        assert decode_signed(result) == -128

    def test_encode_negative_129(self):
        result = encode_signed(-129)
        assert decode_signed(result) == -129

    def test_decode_zero(self):
        assert decode_signed(b"\x00") == 0

    def test_decode_negative_one(self):
        assert decode_signed(b"\xff") == -1

    def test_decode_127(self):
        assert decode_signed(b"\x7f") == 127

    def test_decode_negative_128(self):
        assert decode_signed(b"\x80") == -128

    def test_round_trip_positive(self):
        for val in [0, 1, 127, 128, 32767, 32768, 0x7FFFFF]:
            assert decode_signed(encode_signed(val)) == val

    def test_round_trip_negative(self):
        for val in [-1, -128, -129, -32768, -32769]:
            assert decode_signed(encode_signed(val)) == val


class TestReal:
    def test_encode_zero(self):
        assert encode_real(0.0) == struct.pack(">f", 0.0)

    def test_encode_one(self):
        assert encode_real(1.0) == struct.pack(">f", 1.0)

    def test_encode_negative(self):
        assert encode_real(-1.0) == struct.pack(">f", -1.0)

    def test_always_4_bytes(self):
        assert len(encode_real(72.5)) == 4

    def test_round_trip_zero(self):
        assert decode_real(encode_real(0.0)) == 0.0

    def test_round_trip_positive(self):
        assert decode_real(encode_real(1.0)) == 1.0

    def test_round_trip_negative(self):
        assert decode_real(encode_real(-1.0)) == -1.0

    def test_round_trip_fractional(self):
        assert decode_real(encode_real(72.5)) == pytest.approx(72.5)


class TestDouble:
    def test_encode_zero(self):
        assert encode_double(0.0) == struct.pack(">d", 0.0)

    def test_always_8_bytes(self):
        assert len(encode_double(3.14159)) == 8

    def test_round_trip_zero(self):
        assert decode_double(encode_double(0.0)) == 0.0

    def test_round_trip_large(self):
        val = 1.7976931348623157e308
        assert decode_double(encode_double(val)) == val

    def test_round_trip_negative(self):
        assert decode_double(encode_double(-123456.789)) == pytest.approx(-123456.789)


class TestOctetString:
    def test_identity_empty(self):
        assert encode_octet_string(b"") == b""

    def test_identity(self):
        data = b"\x01\x02\x03\x04"
        assert encode_octet_string(data) == data

    def test_decode_identity(self):
        data = b"\xde\xad\xbe\xef"
        assert decode_octet_string(data) == data

    def test_round_trip(self):
        data = b"\x00\xff\x80\x7f"
        assert decode_octet_string(encode_octet_string(data)) == data


class TestCharacterString:
    def test_encode_utf8(self):
        result = encode_character_string("hello")
        assert result[0] == 0x00
        assert result[1:] == b"hello"

    def test_decode_utf8(self):
        data = b"\x00hello"
        assert decode_character_string(data) == "hello"

    def test_round_trip_utf8(self):
        text = "Hello, World!"
        assert decode_character_string(encode_character_string(text)) == text

    def test_round_trip_unicode(self):
        text = "BACnet \u00e9\u00e0\u00fc"
        assert decode_character_string(encode_character_string(text)) == text

    def test_unsupported_charset_encode_raises(self):
        with pytest.raises(ValueError, match="Unsupported BACnet character set"):
            encode_character_string("hello", charset=0x02)

    def test_unsupported_charset_decode_raises(self):
        with pytest.raises(ValueError, match="Unsupported BACnet character set"):
            decode_character_string(b"\x02hello")

    def test_iso_8859_1(self):
        encoded = encode_character_string("caf\u00e9", charset=0x05)
        assert encoded[0] == 0x05
        assert decode_character_string(encoded) == "caf\u00e9"


class TestEnumerated:
    def test_encode_zero(self):
        assert encode_enumerated(0) == b"\x00"

    def test_encode_small(self):
        assert encode_enumerated(5) == b"\x05"

    def test_encode_large(self):
        result = encode_enumerated(256)
        assert len(result) == 2

    def test_round_trip(self):
        for val in [0, 1, 127, 255, 256, 65535]:
            assert decode_enumerated(encode_enumerated(val)) == val


class TestBitString:
    def test_round_trip_simple(self):
        bs = BitString(b"\xa0", 4)
        encoded = encode_bit_string(bs)
        decoded = decode_bit_string(encoded)
        assert decoded == bs

    def test_round_trip_no_unused(self):
        bs = BitString(b"\xff", 0)
        encoded = encode_bit_string(bs)
        decoded = decode_bit_string(encoded)
        assert decoded == bs

    def test_round_trip_multi_byte(self):
        bs = BitString(b"\xab\xcd", 2)
        encoded = encode_bit_string(bs)
        decoded = decode_bit_string(encoded)
        assert decoded == bs

    def test_encode_format(self):
        bs = BitString(b"\xf0", 4)
        encoded = encode_bit_string(bs)
        assert encoded[0] == 4
        assert encoded[1:] == b"\xf0"


class TestDate:
    def test_encode_normal(self):
        date = BACnetDate(2024, 7, 15, 1)
        encoded = encode_date(date)
        assert encoded == bytes([124, 7, 15, 1])

    def test_decode_normal(self):
        data = bytes([124, 7, 15, 1])
        date = decode_date(data)
        assert date.year == 2024
        assert date.month == 7
        assert date.day == 15
        assert date.day_of_week == 1

    def test_round_trip_normal(self):
        date = BACnetDate(2024, 12, 25, 3)
        assert decode_date(encode_date(date)) == date

    def test_wildcard_year(self):
        date = BACnetDate(0xFF, 6, 1, 0xFF)
        encoded = encode_date(date)
        assert encoded[0] == 0xFF
        decoded = decode_date(encoded)
        assert decoded.year == 0xFF

    def test_round_trip_wildcard(self):
        date = BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
        assert decode_date(encode_date(date)) == date


class TestTime:
    def test_encode_normal(self):
        t = BACnetTime(14, 30, 45, 50)
        encoded = encode_time(t)
        assert encoded == bytes([14, 30, 45, 50])

    def test_decode_normal(self):
        data = bytes([14, 30, 45, 50])
        t = decode_time(data)
        assert t.hour == 14
        assert t.minute == 30
        assert t.second == 45
        assert t.hundredth == 50

    def test_round_trip_normal(self):
        t = BACnetTime(23, 59, 59, 99)
        assert decode_time(encode_time(t)) == t

    def test_round_trip_wildcard(self):
        t = BACnetTime(0xFF, 0xFF, 0xFF, 0xFF)
        assert decode_time(encode_time(t)) == t

    def test_round_trip_partial_wildcard(self):
        t = BACnetTime(12, 0, 0xFF, 0xFF)
        assert decode_time(encode_time(t)) == t


class TestObjectIdentifier:
    def test_encode(self):
        encoded = encode_object_identifier(8, 1234)
        value = (8 << 22) | 1234
        assert encoded == value.to_bytes(4, "big")

    def test_decode(self):
        value = (8 << 22) | 1234
        data = value.to_bytes(4, "big")
        obj_type, instance = decode_object_identifier(data)
        assert obj_type == 8
        assert instance == 1234

    def test_round_trip(self):
        obj_type, instance = 0, 0
        assert decode_object_identifier(encode_object_identifier(obj_type, instance)) == (0, 0)

    def test_round_trip_max_instance(self):
        obj_type, instance = 8, 0x3FFFFF
        result = decode_object_identifier(encode_object_identifier(obj_type, instance))
        assert result == (obj_type, instance)

    def test_round_trip_large_type(self):
        obj_type, instance = 59, 100
        result = decode_object_identifier(encode_object_identifier(obj_type, instance))
        assert result == (obj_type, instance)


class TestNull:
    def test_encode_null(self):
        assert encode_null() == b""


class TestBoolean:
    def test_encode_true(self):
        assert encode_boolean(True) == b"\x01"

    def test_encode_false(self):
        assert encode_boolean(False) == b"\x00"

    def test_decode_true(self):
        assert decode_boolean(b"\x01") is True

    def test_decode_false(self):
        assert decode_boolean(b"\x00") is False

    def test_round_trip_true(self):
        assert decode_boolean(encode_boolean(True)) is True

    def test_round_trip_false(self):
        assert decode_boolean(encode_boolean(False)) is False


class TestApplicationTaggedConvenience:
    def test_encode_application_null(self):
        result = encode_application_null()
        tag, offset = decode_tag(result, 0)
        assert tag.number == 0
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 0

    def test_encode_application_boolean_true(self):
        result = encode_application_boolean(True)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 1
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 1

    def test_encode_application_boolean_false(self):
        result = encode_application_boolean(False)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 1
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 0

    def test_encode_application_unsigned(self):
        result = encode_application_unsigned(42)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 2
        assert tag.cls == TagClass.APPLICATION
        payload = result[offset : offset + tag.length]
        assert decode_unsigned(payload) == 42

    def test_encode_application_signed(self):
        result = encode_application_signed(-5)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 3
        assert tag.cls == TagClass.APPLICATION
        payload = result[offset : offset + tag.length]
        assert decode_signed(payload) == -5

    def test_encode_application_real(self):
        result = encode_application_real(3.14)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 4
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4
        payload = result[offset : offset + tag.length]
        assert decode_real(payload) == pytest.approx(3.14, rel=1e-6)

    def test_encode_application_double(self):
        result = encode_application_double(3.14)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 5
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 8

    def test_encode_application_octet_string(self):
        result = encode_application_octet_string(b"\x01\x02")
        tag, offset = decode_tag(result, 0)
        assert tag.number == 6
        assert tag.cls == TagClass.APPLICATION
        assert result[offset:] == b"\x01\x02"

    def test_encode_application_character_string(self):
        result = encode_application_character_string("hi")
        tag, offset = decode_tag(result, 0)
        assert tag.number == 7
        assert tag.cls == TagClass.APPLICATION
        payload = result[offset : offset + tag.length]
        assert decode_character_string(payload) == "hi"

    def test_encode_application_enumerated(self):
        result = encode_application_enumerated(3)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 9
        assert tag.cls == TagClass.APPLICATION
        payload = result[offset : offset + tag.length]
        assert decode_enumerated(payload) == 3

    def test_encode_application_date(self):
        date = BACnetDate(2024, 1, 1, 1)
        result = encode_application_date(date)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 10
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_encode_application_time(self):
        t = BACnetTime(12, 0, 0, 0)
        result = encode_application_time(t)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 11
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_encode_application_object_id(self):
        result = encode_application_object_id(8, 100)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 12
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4
        payload = result[offset : offset + tag.length]
        obj_type, instance = decode_object_identifier(payload)
        assert obj_type == 8
        assert instance == 100

    def test_encode_application_bit_string(self):
        bs = BitString(b"\xf0", 4)
        result = encode_application_bit_string(bs)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 8
        assert tag.cls == TagClass.APPLICATION
