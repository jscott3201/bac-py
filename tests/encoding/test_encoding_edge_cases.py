"""Tests for encoding edge cases: untested functions and boundary conditions."""

import math
import struct

import pytest

from bac_py.encoding.primitives import (
    decode_and_unwrap,
    decode_character_string,
    decode_double,
    decode_object_identifier,
    decode_real,
    decode_signed,
    decode_unsigned,
    encode_application_boolean,
    encode_application_character_string,
    encode_application_null,
    encode_application_object_id,
    encode_application_real,
    encode_application_signed,
    encode_application_tagged,
    encode_application_unsigned,
    encode_character_string,
    encode_context_object_id,
    encode_double,
    encode_real,
    encode_signed,
    encode_unsigned,
)
from bac_py.encoding.tags import (
    TagClass,
    as_memoryview,
    decode_tag,
    encode_tag,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestDecodeAndUnwrap:
    def test_single_element_returns_unwrapped(self):
        """A single application-tagged value should be returned directly, not in a list."""
        data = encode_application_unsigned(42)
        result = decode_and_unwrap(data)
        assert result == 42

    def test_single_real_returns_float(self):
        data = encode_application_real(72.5)
        result = decode_and_unwrap(data)
        assert isinstance(result, float)
        assert result == pytest.approx(72.5)

    def test_single_boolean_true(self):
        data = encode_application_boolean(True)
        result = decode_and_unwrap(data)
        assert result is True

    def test_single_null(self):
        data = encode_application_null()
        result = decode_and_unwrap(data)
        assert result is None

    def test_multi_element_returns_list(self):
        """Multiple application-tagged values should return as a list."""
        data = encode_application_unsigned(1) + encode_application_unsigned(2)
        result = decode_and_unwrap(data)
        assert isinstance(result, list)
        assert result == [1, 2]

    def test_multi_element_mixed_types(self):
        data = (
            encode_application_unsigned(10)
            + encode_application_real(3.14)
            + encode_application_character_string("hello")
        )
        result = decode_and_unwrap(data)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == 10
        assert result[1] == pytest.approx(3.14, rel=1e-6)
        assert result[2] == "hello"

    def test_empty_data_returns_none(self):
        """Empty input should return None."""
        result = decode_and_unwrap(b"")
        assert result is None

    def test_memoryview_input(self):
        data = encode_application_signed(-5)
        result = decode_and_unwrap(memoryview(data))
        assert result == -5

    def test_single_string_returns_string(self):
        data = encode_application_character_string("BACnet test")
        result = decode_and_unwrap(data)
        assert result == "BACnet test"

    def test_single_object_id(self):
        data = encode_application_object_id(8, 100)
        result = decode_and_unwrap(data)
        assert isinstance(result, ObjectIdentifier)
        assert result.object_type == ObjectType.DEVICE
        assert result.instance_number == 100


class TestEncodeApplicationTagged:
    def test_tag_null(self):
        """Tag 0 (Null) with empty data."""
        result = encode_application_tagged(0, b"")
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 0
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 0

    def test_tag_boolean(self):
        """Tag 1 (Boolean) wraps data."""
        result = encode_application_tagged(1, b"\x01")
        tag, offset = decode_tag(result, 0)
        assert tag.number == 1
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 1
        assert result[offset] == 0x01

    def test_tag_unsigned(self):
        """Tag 2 (Unsigned)."""
        data = encode_unsigned(255)
        result = encode_application_tagged(2, data)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 2
        assert tag.cls == TagClass.APPLICATION
        assert decode_unsigned(result[offset : offset + tag.length]) == 255

    def test_tag_signed(self):
        """Tag 3 (Signed)."""
        data = encode_signed(-1)
        result = encode_application_tagged(3, data)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 3
        assert tag.cls == TagClass.APPLICATION
        assert decode_signed(result[offset : offset + tag.length]) == -1

    def test_tag_real(self):
        """Tag 4 (Real)."""
        data = encode_real(1.5)
        result = encode_application_tagged(4, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 4
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_tag_double(self):
        """Tag 5 (Double)."""
        data = encode_double(1.5)
        result = encode_application_tagged(5, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 5
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 8

    def test_tag_octet_string(self):
        """Tag 6 (Octet String)."""
        data = b"\xde\xad\xbe\xef"
        result = encode_application_tagged(6, data)
        tag, offset = decode_tag(result, 0)
        assert tag.number == 6
        assert tag.cls == TagClass.APPLICATION
        assert result[offset : offset + tag.length] == data

    def test_tag_character_string(self):
        """Tag 7 (Character String)."""
        data = encode_character_string("test")
        result = encode_application_tagged(7, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 7
        assert tag.cls == TagClass.APPLICATION

    def test_tag_bit_string(self):
        """Tag 8 (Bit String)."""
        data = b"\x04\xf0"  # 4 unused bits, 0xf0
        result = encode_application_tagged(8, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 8
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 2

    def test_tag_enumerated(self):
        """Tag 9 (Enumerated)."""
        data = encode_unsigned(5)
        result = encode_application_tagged(9, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 9
        assert tag.cls == TagClass.APPLICATION

    def test_tag_date(self):
        """Tag 10 (Date)."""
        data = bytes([124, 7, 15, 1])  # 2024-07-15, Monday
        result = encode_application_tagged(10, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 10
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_tag_time(self):
        """Tag 11 (Time)."""
        data = bytes([14, 30, 0, 0])
        result = encode_application_tagged(11, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 11
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_tag_object_identifier(self):
        """Tag 12 (Object Identifier)."""
        data = ObjectIdentifier(ObjectType.DEVICE, 100).encode()
        result = encode_application_tagged(12, data)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 12
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 4

    def test_wraps_data_correctly(self):
        """The output should be the tag header followed by the raw data."""
        data = b"\x01\x02\x03"
        result = encode_application_tagged(2, data)
        tag_header = encode_tag(2, TagClass.APPLICATION, 3)
        assert result == tag_header + data


class TestEncodeContextObjectId:
    def test_encode_with_context_tag(self):
        """Encoding an ObjectIdentifier with a context tag."""
        obj_id = ObjectIdentifier(ObjectType.DEVICE, 100)
        result = encode_context_object_id(0, obj_id)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 0
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 4

    def test_round_trip_with_decode_object_identifier(self):
        """Encode context object ID and decode the payload back."""
        obj_id = ObjectIdentifier(ObjectType.ANALOG_INPUT, 42)
        result = encode_context_object_id(3, obj_id)
        tag, offset = decode_tag(result, 0)
        payload = result[offset : offset + tag.length]
        obj_type, instance = decode_object_identifier(payload)
        assert obj_type == ObjectType.ANALOG_INPUT
        assert instance == 42

    def test_different_context_tags(self):
        """Different tag numbers should produce different headers but identical payloads."""
        obj_id = ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1)
        result0 = encode_context_object_id(0, obj_id)
        result5 = encode_context_object_id(5, obj_id)
        tag0, offset0 = decode_tag(result0, 0)
        tag5, offset5 = decode_tag(result5, 0)
        assert tag0.number == 0
        assert tag5.number == 5
        # Full encoded bytes differ because tag headers differ
        assert result0 != result5
        # But payloads (after tag header) should be identical
        payload0 = result0[offset0:]
        payload5 = result5[offset5:]
        assert payload0 == payload5

    def test_max_instance(self):
        """Encode an object ID with the maximum instance number."""
        obj_id = ObjectIdentifier(ObjectType.DEVICE, 0x3FFFFF)
        result = encode_context_object_id(1, obj_id)
        tag, offset = decode_tag(result, 0)
        obj_type, instance = decode_object_identifier(result[offset : offset + tag.length])
        assert obj_type == ObjectType.DEVICE
        assert instance == 0x3FFFFF

    def test_extended_context_tag(self):
        """Context tag numbers > 14 should use extended tag format."""
        obj_id = ObjectIdentifier(ObjectType.DEVICE, 1)
        result = encode_context_object_id(20, obj_id)
        tag, _offset = decode_tag(result, 0)
        assert tag.number == 20
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 4


class TestAsMemoryview:
    def test_bytes_input_returns_memoryview(self):
        data = b"\x01\x02\x03"
        result = as_memoryview(data)
        assert isinstance(result, memoryview)
        assert bytes(result) == data

    def test_memoryview_input_returns_same_memoryview(self):
        data = b"\x01\x02\x03"
        mv = memoryview(data)
        result = as_memoryview(mv)
        assert result is mv

    def test_bytearray_input(self):
        """Bytearray wrapped in memoryview should pass through as-is."""
        data = bytearray(b"\x01\x02\x03")
        mv = memoryview(data)
        result = as_memoryview(mv)
        assert isinstance(result, memoryview)
        assert bytes(result) == b"\x01\x02\x03"

    def test_empty_bytes(self):
        result = as_memoryview(b"")
        assert isinstance(result, memoryview)
        assert len(result) == 0

    def test_empty_memoryview(self):
        mv = memoryview(b"")
        result = as_memoryview(mv)
        assert result is mv

    def test_content_accessible_via_index(self):
        data = b"\xaa\xbb\xcc"
        result = as_memoryview(data)
        assert result[0] == 0xAA
        assert result[1] == 0xBB
        assert result[2] == 0xCC

    def test_slicing_works(self):
        data = b"\x01\x02\x03\x04"
        result = as_memoryview(data)
        assert bytes(result[1:3]) == b"\x02\x03"


class TestNumericBoundaryValues:
    # --- encode_unsigned / decode_unsigned boundaries ---

    def test_unsigned_zero(self):
        encoded = encode_unsigned(0)
        assert len(encoded) == 1
        assert decode_unsigned(encoded) == 0

    def test_unsigned_255(self):
        encoded = encode_unsigned(255)
        assert len(encoded) == 1
        assert decode_unsigned(encoded) == 255

    def test_unsigned_256(self):
        encoded = encode_unsigned(256)
        assert len(encoded) == 2
        assert decode_unsigned(encoded) == 256

    def test_unsigned_65535(self):
        encoded = encode_unsigned(65535)
        assert len(encoded) == 2
        assert decode_unsigned(encoded) == 65535

    def test_unsigned_65536(self):
        encoded = encode_unsigned(65536)
        assert len(encoded) == 3
        assert decode_unsigned(encoded) == 65536

    def test_unsigned_2_pow_24_minus_1(self):
        val = (2**24) - 1  # 16777215
        encoded = encode_unsigned(val)
        assert len(encoded) == 3
        assert decode_unsigned(encoded) == val

    def test_unsigned_2_pow_24(self):
        val = 2**24  # 16777216
        encoded = encode_unsigned(val)
        assert len(encoded) == 4
        assert decode_unsigned(encoded) == val

    def test_unsigned_2_pow_32_minus_1(self):
        val = (2**32) - 1  # 4294967295
        encoded = encode_unsigned(val)
        assert len(encoded) == 4
        assert decode_unsigned(encoded) == val

    def test_unsigned_exceeds_4_bytes_raises(self):
        with pytest.raises(ValueError, match="exceeds 4-byte maximum"):
            encode_unsigned(2**32)

    def test_unsigned_negative_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            encode_unsigned(-1)

    # --- encode_signed / decode_signed boundaries ---

    def test_signed_negative_128(self):
        encoded = encode_signed(-128)
        assert len(encoded) == 1
        assert decode_signed(encoded) == -128

    def test_signed_127(self):
        encoded = encode_signed(127)
        assert len(encoded) == 1
        assert decode_signed(encoded) == 127

    def test_signed_128_needs_2_bytes(self):
        encoded = encode_signed(128)
        assert len(encoded) == 2
        assert decode_signed(encoded) == 128

    def test_signed_negative_129_needs_2_bytes(self):
        encoded = encode_signed(-129)
        assert len(encoded) == 2
        assert decode_signed(encoded) == -129

    def test_signed_negative_32768(self):
        encoded = encode_signed(-32768)
        assert len(encoded) == 2
        assert decode_signed(encoded) == -32768

    def test_signed_32767(self):
        encoded = encode_signed(32767)
        assert len(encoded) == 2
        assert decode_signed(encoded) == 32767

    def test_signed_32768_needs_3_bytes(self):
        encoded = encode_signed(32768)
        assert len(encoded) == 3
        assert decode_signed(encoded) == 32768

    def test_signed_negative_2_pow_31(self):
        val = -(2**31)  # -2147483648
        encoded = encode_signed(val)
        assert len(encoded) == 4
        assert decode_signed(encoded) == val

    def test_signed_2_pow_31_minus_1(self):
        val = (2**31) - 1  # 2147483647
        encoded = encode_signed(val)
        assert len(encoded) == 4
        assert decode_signed(encoded) == val

    def test_signed_below_min_raises(self):
        with pytest.raises(ValueError, match="out of 4-byte range"):
            encode_signed(-(2**31) - 1)

    def test_signed_above_max_raises(self):
        with pytest.raises(ValueError, match="out of 4-byte range"):
            encode_signed(2**31)

    # --- encode_application_real / encode_real edge cases ---

    def test_real_zero(self):
        encoded = encode_real(0.0)
        assert decode_real(encoded) == 0.0

    def test_real_negative_zero(self):
        encoded = encode_real(-0.0)
        decoded = decode_real(encoded)
        # -0.0 == 0.0 in Python, but the sign bit is preserved
        assert decoded == 0.0
        assert math.copysign(1, decoded) == -1.0  # verify sign bit

    def test_real_positive_infinity(self):
        encoded = encode_real(float("inf"))
        decoded = decode_real(encoded)
        assert math.isinf(decoded)
        assert decoded > 0

    def test_real_negative_infinity(self):
        encoded = encode_real(float("-inf"))
        decoded = decode_real(encoded)
        assert math.isinf(decoded)
        assert decoded < 0

    def test_real_nan(self):
        encoded = encode_real(float("nan"))
        decoded = decode_real(encoded)
        assert math.isnan(decoded)

    def test_real_smallest_positive_normal(self):
        """Smallest positive normal float32."""
        val = 1.175494e-38
        encoded = encode_real(val)
        decoded = decode_real(encoded)
        assert decoded == pytest.approx(val, rel=1e-6)

    def test_real_largest_finite(self):
        """Largest finite float32 value."""
        val = 3.4028235e38
        encoded = encode_real(val)
        decoded = decode_real(encoded)
        assert decoded == pytest.approx(val, rel=1e-6)

    def test_application_real_inf(self):
        """Ensure application-tagged encoding of inf round-trips through tag decode."""
        from bac_py.encoding.primitives import decode_application_value

        encoded = encode_application_real(float("inf"))
        result = decode_application_value(encoded)
        assert math.isinf(result)
        assert result > 0

    def test_application_real_nan(self):
        from bac_py.encoding.primitives import decode_application_value

        encoded = encode_application_real(float("nan"))
        result = decode_application_value(encoded)
        assert math.isnan(result)

    # --- encode_double / decode_double edge cases ---

    def test_double_zero(self):
        encoded = encode_double(0.0)
        assert decode_double(encoded) == 0.0

    def test_double_negative_zero(self):
        encoded = encode_double(-0.0)
        decoded = decode_double(encoded)
        assert decoded == 0.0
        assert math.copysign(1, decoded) == -1.0

    def test_double_positive_infinity(self):
        encoded = encode_double(float("inf"))
        decoded = decode_double(encoded)
        assert math.isinf(decoded)
        assert decoded > 0

    def test_double_negative_infinity(self):
        encoded = encode_double(float("-inf"))
        decoded = decode_double(encoded)
        assert math.isinf(decoded)
        assert decoded < 0

    def test_double_nan(self):
        encoded = encode_double(float("nan"))
        decoded = decode_double(encoded)
        assert math.isnan(decoded)

    def test_double_max_value(self):
        val = 1.7976931348623157e308
        encoded = encode_double(val)
        assert decode_double(encoded) == val

    def test_double_min_positive_normal(self):
        val = 2.2250738585072014e-308
        encoded = encode_double(val)
        assert decode_double(encoded) == val

    def test_double_precision_preserved(self):
        """Double should preserve more precision than float32."""
        val = 1.23456789012345
        encoded = encode_double(val)
        decoded = decode_double(encoded)
        assert decoded == val  # exact equality for double-precision

    def test_double_always_8_bytes(self):
        for val in [0.0, 1.0, -1.0, float("inf"), float("nan")]:
            assert len(encode_double(val)) == 8


class TestCharacterStringCharsets:
    def test_charset_0_utf8_ascii(self):
        """Charset 0 is ANSI X3.4 / UTF-8. ASCII text should encode and decode."""
        encoded = encode_character_string("Hello", charset=0)
        assert encoded[0] == 0x00
        assert encoded[1:] == b"Hello"
        assert decode_character_string(encoded) == "Hello"

    def test_charset_0_utf8_unicode(self):
        """Charset 0 should handle multi-byte UTF-8 characters."""
        text = "caf\u00e9"
        encoded = encode_character_string(text, charset=0)
        assert encoded[0] == 0x00
        assert decode_character_string(encoded) == text

    def test_charset_0_utf8_emoji(self):
        """Charset 0 should handle 4-byte UTF-8 characters."""
        text = "temp\U0001f321"
        encoded = encode_character_string(text, charset=0)
        assert decode_character_string(encoded) == text

    def test_charset_4_utf16be(self):
        """Charset 4 is UTF-16BE (mapped to index 0x04 in _CHARSET_DECODERS)."""
        text = "Hi"
        encoded = encode_character_string(text, charset=4)
        assert encoded[0] == 0x04
        # UTF-16BE encodes 'H' as \x00\x48, 'i' as \x00\x69
        assert encoded[1:] == text.encode("utf-16-be")
        assert decode_character_string(encoded) == text

    def test_charset_4_utf16be_non_ascii(self):
        text = "\u00e9\u00e0"
        encoded = encode_character_string(text, charset=4)
        assert decode_character_string(encoded) == text

    def test_charset_3_utf32be(self):
        """Charset 3 is UCS-4 / UTF-32BE."""
        text = "AB"
        encoded = encode_character_string(text, charset=3)
        assert encoded[0] == 0x03
        assert encoded[1:] == text.encode("utf-32-be")
        assert decode_character_string(encoded) == text

    def test_charset_5_iso8859_1(self):
        """Charset 5 is ISO 8859-1 (Latin-1)."""
        text = "caf\u00e9"
        encoded = encode_character_string(text, charset=5)
        assert encoded[0] == 0x05
        assert encoded[1:] == text.encode("iso-8859-1")
        assert decode_character_string(encoded) == text

    def test_unknown_charset_encode_raises(self):
        """Encoding with an unknown charset should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported BACnet character set"):
            encode_character_string("hello", charset=0xFF)

    def test_unknown_charset_decode_fallback_latin1(self):
        """Decoding with an unknown charset byte should fall back to latin-1."""
        # Manually construct data with unknown charset byte 0xAA
        data = b"\xaa" + b"Hello"
        result = decode_character_string(data)
        assert result == "Hello"

    def test_unknown_charset_decode_preserves_high_bytes(self):
        """Latin-1 fallback should correctly map high bytes."""
        data = b"\xbb\xe9\xe0\xfc"
        result = decode_character_string(data)
        assert result == "\u00e9\u00e0\u00fc"

    def test_decode_empty_data_raises(self):
        """Empty data (no charset byte) should raise ValueError."""
        with pytest.raises(ValueError, match="too short"):
            decode_character_string(b"")

    def test_charset_byte_only_no_content(self):
        """A charset byte with no content should decode to an empty string."""
        result = decode_character_string(b"\x00")
        assert result == ""

    def test_charset_0_round_trip_empty_string(self):
        encoded = encode_character_string("", charset=0)
        assert decode_character_string(encoded) == ""


class TestMalformedDataHandling:
    def test_decode_tag_offset_beyond_buffer(self):
        """Offset past buffer end should raise ValueError."""
        data = b"\x00"
        with pytest.raises(ValueError, match=r"offset .* beyond buffer length"):
            decode_tag(data, 1)

    def test_decode_tag_offset_at_empty_buffer(self):
        """Offset 0 on empty buffer should raise ValueError."""
        with pytest.raises(ValueError, match=r"offset .* beyond buffer length"):
            decode_tag(b"", 0)

    def test_truncated_extended_tag_number(self):
        """Tag with extended tag number marker but no following byte should raise."""
        # Initial byte 0xF1 means tag number 15 (extended), application, length=1
        # But we only provide the initial byte -- no extended tag number byte
        data = b"\xf0"  # extended tag marker, length=0, but missing ext tag byte
        with pytest.raises((ValueError, IndexError)):
            decode_tag(data, 0)

    def test_truncated_extended_length(self):
        """Tag header indicating extended length but truncated data should raise."""
        # Initial byte with length marker 5 (extended), but no length byte follows
        # tag 0, application, extended length marker
        data = bytes([0x05])  # tag=0, app, lvt=5 (extended), but missing ext length byte
        with pytest.raises((ValueError, IndexError)):
            decode_tag(data, 0)

    def test_truncated_two_byte_extended_length(self):
        """Extended length 254 marker expects 2 more bytes.

        With truncated data, memoryview slicing silently returns fewer bytes,
        so int.from_bytes reads a shorter value rather than raising.
        The parsed length will be incorrect (shorter than intended).
        """
        # Properly encoded: tag=0, app, lvt=5, ext=254, then 2 bytes for length 0x0100 = 256
        proper_data = bytes([0x05, 254, 0x01, 0x00])
        tag, _ = decode_tag(proper_data, 0)
        assert tag.length == 256

        # Truncated: only 1 of the 2 length bytes present
        truncated = bytes([0x05, 254, 0x01])
        tag_trunc, _ = decode_tag(truncated, 0)
        # The truncated parse produces a wrong length value
        assert tag_trunc.length != 256

    def test_truncated_four_byte_extended_length(self):
        """Extended length 255 marker expects 4 more bytes.

        With truncated data, memoryview slicing produces fewer bytes,
        so int.from_bytes reads a shorter value.
        """
        # Properly encoded: tag=0, app, lvt=5, ext=255, then 4 bytes for length
        proper_data = bytes([0x05, 255, 0x00, 0x01, 0x00, 0x00])
        tag, _ = decode_tag(proper_data, 0)
        assert tag.length == 65536

        # Truncated: only 2 of the 4 length bytes present
        truncated = bytes([0x05, 255, 0x00, 0x01])
        tag_trunc, _ = decode_tag(truncated, 0)
        # The truncated parse produces a wrong length value
        assert tag_trunc.length != 65536

    def test_tag_length_exceeds_remaining_data(self):
        """Tag says 4 bytes of content, but buffer is shorter.

        decode_tag itself parses the header successfully; the caller is
        responsible for checking that enough content data follows.
        """
        # tag 0, application, length 4 -- but no content bytes follow
        tag_bytes = encode_tag(0, TagClass.APPLICATION, 4)
        tag, offset = decode_tag(tag_bytes, 0)
        assert tag.length == 4
        # The tag parsed fine, but offset + tag.length > len(tag_bytes)
        assert offset + tag.length > len(tag_bytes)

    def test_decode_object_identifier_too_short(self):
        """Object identifier decode with < 4 bytes should raise."""
        with pytest.raises(ValueError, match="too short"):
            decode_object_identifier(b"\x00\x00")

    def test_decode_signed_empty(self):
        """decode_signed with empty data should raise or return 0."""
        # int.from_bytes(b"", "big", signed=True) returns 0 in Python
        result = decode_signed(b"")
        assert result == 0

    def test_decode_unsigned_empty(self):
        """decode_unsigned with empty data returns 0 (Python int.from_bytes behavior)."""
        result = decode_unsigned(b"")
        assert result == 0

    def test_encode_tag_negative_tag_number_raises(self):
        with pytest.raises(ValueError, match="Tag number must be 0-254"):
            encode_tag(-1, TagClass.APPLICATION, 0)

    def test_encode_tag_too_large_tag_number_raises(self):
        with pytest.raises(ValueError, match="Tag number must be 0-254"):
            encode_tag(255, TagClass.APPLICATION, 0)

    def test_encode_tag_negative_length_raises(self):
        with pytest.raises(ValueError, match="Tag length must be non-negative"):
            encode_tag(0, TagClass.APPLICATION, -1)

    def test_decode_real_truncated(self):
        """decode_real with < 4 bytes should raise from struct.unpack."""
        with pytest.raises(struct.error):
            decode_real(b"\x00\x00")

    def test_decode_double_truncated(self):
        """decode_double with < 8 bytes should raise from struct.unpack."""
        with pytest.raises(struct.error):
            decode_double(b"\x00\x00\x00\x00")

    def test_decode_character_string_memoryview(self):
        """decode_character_string should work with memoryview input."""
        data = memoryview(b"\x00hello")
        assert decode_character_string(data) == "hello"
