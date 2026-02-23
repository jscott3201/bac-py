import struct

import pytest

from bac_py.encoding.tags import (
    _MAX_CONTEXT_NESTING_DEPTH,
    Tag,
    TagClass,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    encode_tag,
    extract_context_value,
)


class TestTagClassEnum:
    def test_application_value(self):
        assert TagClass.APPLICATION == 0

    def test_context_value(self):
        assert TagClass.CONTEXT == 1


class TestEncodeTagSmallNumberSmallLength:
    def test_tag0_length0(self):
        result = encode_tag(0, TagClass.APPLICATION, 0)
        assert result == bytes([0x00])

    def test_tag0_length1(self):
        result = encode_tag(0, TagClass.APPLICATION, 1)
        assert result == bytes([0x01])

    def test_tag0_length4(self):
        result = encode_tag(0, TagClass.APPLICATION, 4)
        assert result == bytes([0x04])

    def test_tag5_context_length3(self):
        result = encode_tag(5, TagClass.CONTEXT, 3)
        assert result == bytes([(5 << 4) | 0x08 | 3])

    def test_tag14_application_length2(self):
        result = encode_tag(14, TagClass.APPLICATION, 2)
        assert result == bytes([(14 << 4) | 2])

    def test_tag14_context_length0(self):
        result = encode_tag(14, TagClass.CONTEXT, 0)
        assert result == bytes([(14 << 4) | 0x08])


class TestEncodeTagExtendedTagNumber:
    def test_tag15(self):
        result = encode_tag(15, TagClass.APPLICATION, 1)
        assert result == bytes([0xF1, 15])

    def test_tag20_context(self):
        result = encode_tag(20, TagClass.CONTEXT, 2)
        assert result == bytes([(0x0F << 4) | 0x08 | 2, 20])

    def test_tag254(self):
        result = encode_tag(254, TagClass.APPLICATION, 0)
        assert result == bytes([0xF0, 254])


class TestEncodeTagExtendedLength:
    def test_length5(self):
        result = encode_tag(0, TagClass.APPLICATION, 5)
        assert result == bytes([0x05, 5])

    def test_length100(self):
        result = encode_tag(0, TagClass.APPLICATION, 100)
        assert result == bytes([0x05, 100])

    def test_length253(self):
        result = encode_tag(0, TagClass.APPLICATION, 253)
        assert result == bytes([0x05, 253])

    def test_length254(self):
        result = encode_tag(0, TagClass.APPLICATION, 254)
        expected = bytes([0x05, 254]) + (254).to_bytes(2, "big")
        assert result == expected

    def test_length1000(self):
        result = encode_tag(0, TagClass.APPLICATION, 1000)
        expected = bytes([0x05, 254]) + (1000).to_bytes(2, "big")
        assert result == expected

    def test_length65535(self):
        result = encode_tag(0, TagClass.APPLICATION, 65535)
        expected = bytes([0x05, 254]) + (65535).to_bytes(2, "big")
        assert result == expected

    def test_length65536(self):
        result = encode_tag(0, TagClass.APPLICATION, 65536)
        expected = bytes([0x05, 255]) + (65536).to_bytes(4, "big")
        assert result == expected

    def test_length_large(self):
        result = encode_tag(0, TagClass.APPLICATION, 100000)
        expected = bytes([0x05, 255]) + (100000).to_bytes(4, "big")
        assert result == expected

    def test_extended_tag_and_length(self):
        result = encode_tag(20, TagClass.CONTEXT, 300)
        expected = bytes([(0x0F << 4) | 0x08 | 5, 20, 254]) + (300).to_bytes(2, "big")
        assert result == expected


class TestEncodeOpeningTag:
    def test_small_tag(self):
        result = encode_opening_tag(0)
        assert result == bytes([0x0E])

    def test_tag5(self):
        result = encode_opening_tag(5)
        assert result == bytes([(5 << 4) | 0x0E])

    def test_tag14(self):
        result = encode_opening_tag(14)
        assert result == bytes([(14 << 4) | 0x0E])

    def test_extended_tag(self):
        result = encode_opening_tag(15)
        assert result == bytes([0xFE, 15])

    def test_extended_tag_large(self):
        result = encode_opening_tag(200)
        assert result == bytes([0xFE, 200])


class TestEncodeClosingTag:
    def test_small_tag(self):
        result = encode_closing_tag(0)
        assert result == bytes([0x0F])

    def test_tag5(self):
        result = encode_closing_tag(5)
        assert result == bytes([(5 << 4) | 0x0F])

    def test_tag14(self):
        result = encode_closing_tag(14)
        assert result == bytes([(14 << 4) | 0x0F])

    def test_extended_tag(self):
        result = encode_closing_tag(15)
        assert result == bytes([0xFF, 15])

    def test_extended_tag_large(self):
        result = encode_closing_tag(200)
        assert result == bytes([0xFF, 200])


class TestDecodeTagRoundTrip:
    @pytest.mark.parametrize("tag_number", [0, 1, 5, 14])
    @pytest.mark.parametrize("length", [0, 1, 4])
    def test_small_tag_small_length(self, tag_number, length):
        encoded = encode_tag(tag_number, TagClass.APPLICATION, length)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == tag_number
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == length
        assert offset == len(encoded)

    @pytest.mark.parametrize("tag_number", [0, 5, 14])
    @pytest.mark.parametrize("length", [0, 3])
    def test_context_class(self, tag_number, length):
        encoded = encode_tag(tag_number, TagClass.CONTEXT, length)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == tag_number
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == length
        assert offset == len(encoded)

    @pytest.mark.parametrize("tag_number", [15, 20, 100, 254])
    def test_extended_tag_number(self, tag_number):
        encoded = encode_tag(tag_number, TagClass.APPLICATION, 2)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == tag_number
        assert tag.cls == TagClass.APPLICATION
        assert tag.length == 2
        assert offset == len(encoded)

    @pytest.mark.parametrize("length", [5, 100, 253])
    def test_extended_length_single_byte(self, length):
        encoded = encode_tag(0, TagClass.APPLICATION, length)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 0
        assert tag.length == length
        assert offset == len(encoded)

    @pytest.mark.parametrize("length", [254, 1000, 65535])
    def test_extended_length_two_bytes(self, length):
        encoded = encode_tag(0, TagClass.APPLICATION, length)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 0
        assert tag.length == length
        assert offset == len(encoded)

    @pytest.mark.parametrize("length", [65536, 100000])
    def test_extended_length_four_bytes(self, length):
        encoded = encode_tag(0, TagClass.APPLICATION, length)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 0
        assert tag.length == length
        assert offset == len(encoded)

    def test_extended_tag_and_extended_length(self):
        encoded = encode_tag(20, TagClass.CONTEXT, 500)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 20
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 500
        assert offset == len(encoded)

    def test_decode_with_offset(self):
        prefix = b"\x00\x00"
        encoded = encode_tag(3, TagClass.APPLICATION, 2)
        buf = prefix + encoded
        tag, offset = decode_tag(buf, 2)
        assert tag.number == 3
        assert tag.length == 2
        assert offset == 2 + len(encoded)

    def test_decode_from_memoryview(self):
        encoded = encode_tag(5, TagClass.CONTEXT, 3)
        tag, _offset = decode_tag(memoryview(encoded), 0)
        assert tag.number == 5
        assert tag.cls == TagClass.CONTEXT
        assert tag.length == 3


class TestDecodeOpeningClosingTags:
    @pytest.mark.parametrize("tag_number", [0, 5, 14])
    def test_opening_tag_small(self, tag_number):
        encoded = encode_opening_tag(tag_number)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == tag_number
        assert tag.cls == TagClass.CONTEXT
        assert tag.is_opening is True
        assert tag.is_closing is False
        assert tag.length == 0
        assert offset == len(encoded)

    @pytest.mark.parametrize("tag_number", [0, 5, 14])
    def test_closing_tag_small(self, tag_number):
        encoded = encode_closing_tag(tag_number)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == tag_number
        assert tag.cls == TagClass.CONTEXT
        assert tag.is_closing is True
        assert tag.is_opening is False
        assert tag.length == 0
        assert offset == len(encoded)

    def test_opening_tag_extended(self):
        encoded = encode_opening_tag(20)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 20
        assert tag.is_opening is True
        assert tag.is_closing is False
        assert offset == len(encoded)

    def test_closing_tag_extended(self):
        encoded = encode_closing_tag(20)
        tag, offset = decode_tag(encoded, 0)
        assert tag.number == 20
        assert tag.is_closing is True
        assert tag.is_opening is False
        assert offset == len(encoded)


class TestTagDataclass:
    def test_default_flags(self):
        tag = Tag(number=0, cls=TagClass.APPLICATION, length=4)
        assert tag.is_opening is False
        assert tag.is_closing is False

    def test_frozen(self):
        tag = Tag(number=0, cls=TagClass.APPLICATION, length=4)
        with pytest.raises(AttributeError):
            tag.number = 1  # type: ignore[misc]


class TestExtractContextValue:
    def test_simple_value(self):
        """Extract value between opening tag 3 and closing tag 3."""
        inner = encode_tag(1, TagClass.APPLICATION, 2) + b"\x01\x02"
        buf = encode_opening_tag(3) + inner + encode_closing_tag(3)
        # offset starts after opening tag
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 3)
        assert value == inner
        assert end_offset == len(buf)

    def test_nested_opening_closing(self):
        """Handle nested opening/closing tag pairs correctly."""
        inner_nested = (
            encode_opening_tag(5)
            + encode_tag(0, TagClass.APPLICATION, 1)
            + b"\x42"
            + encode_closing_tag(5)
        )
        buf = encode_opening_tag(3) + inner_nested + encode_closing_tag(3)
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 3)
        assert value == inner_nested
        assert end_offset == len(buf)

    def test_empty_value(self):
        """Opening tag immediately followed by closing tag."""
        buf = encode_opening_tag(2) + encode_closing_tag(2)
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 2)
        assert value == b""
        assert end_offset == len(buf)

    def test_application_boolean_true(self):
        """Application-tagged Boolean True (LVT=1, zero content octets)."""
        # Boolean True: tag=1, APPLICATION, LVT=1 → single byte 0x11
        bool_true = b"\x11"
        buf = encode_opening_tag(3) + bool_true + encode_closing_tag(3)
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 3)
        assert value == bool_true
        assert end_offset == len(buf)

    def test_application_boolean_false(self):
        """Application-tagged Boolean False (LVT=0, zero content octets)."""
        # Boolean False: tag=1, APPLICATION, LVT=0 → single byte 0x10
        bool_false = b"\x10"
        buf = encode_opening_tag(3) + bool_false + encode_closing_tag(3)
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 3)
        assert value == bool_false
        assert end_offset == len(buf)

    def test_missing_closing_tag_raises(self):
        """Missing closing tag raises ValueError."""
        buf = encode_opening_tag(3) + encode_tag(0, TagClass.APPLICATION, 1) + b"\x42"
        _, offset = decode_tag(buf, 0)
        with pytest.raises(ValueError, match="Missing closing tag"):
            extract_context_value(buf, offset, 3)

    def test_bytes_input(self):
        """Works with bytes (not just memoryview)."""
        inner = b"\xde\xad"
        buf = bytes(
            encode_opening_tag(4)
            + encode_tag(0, TagClass.APPLICATION, 2)
            + inner
            + encode_closing_tag(4)
        )
        _, offset = decode_tag(buf, 0)
        value, _ = extract_context_value(buf, offset, 4)
        expected_inner = encode_tag(0, TagClass.APPLICATION, 2) + inner
        assert value == expected_inner

    def test_memoryview_input(self):
        """Works with memoryview input."""
        inner = encode_tag(2, TagClass.APPLICATION, 1) + b"\xff"
        buf = memoryview(encode_opening_tag(0) + inner + encode_closing_tag(0))
        _, offset = decode_tag(buf, 0)
        value, _ = extract_context_value(buf, offset, 0)
        assert value == inner

    def test_deeply_nested(self):
        """Handle multiple levels of nesting."""
        level2 = (
            encode_opening_tag(7)
            + encode_tag(0, TagClass.APPLICATION, 1)
            + b"\x01"
            + encode_closing_tag(7)
        )
        level1 = encode_opening_tag(5) + level2 + encode_closing_tag(5)
        buf = encode_opening_tag(3) + level1 + encode_closing_tag(3)
        _, offset = decode_tag(buf, 0)
        value, end_offset = extract_context_value(buf, offset, 3)
        assert value == level1
        assert end_offset == len(buf)


# ---------------------------------------------------------------------------
# Security: nesting depth limit
# ---------------------------------------------------------------------------


class TestContextNestingDepthLimit:
    def test_excessive_nesting_raises(self):
        """Deeply nested opening tags should raise ValueError."""
        depth = _MAX_CONTEXT_NESTING_DEPTH + 2
        buf = bytearray()
        for _ in range(depth):
            buf.extend(encode_opening_tag(0))
        for _ in range(depth):
            buf.extend(encode_closing_tag(0))
        _, offset = decode_tag(bytes(buf), 0)
        with pytest.raises(ValueError, match="nesting depth exceeds maximum"):
            extract_context_value(bytes(buf), offset, 0)

    def test_valid_nesting_within_limit(self):
        """Nesting at exactly the limit should work."""
        # Build nesting depth of 3 (1 outer + 2 inner) — well within limit
        inner = encode_opening_tag(1) + encode_closing_tag(1)
        buf = encode_opening_tag(0) + inner + encode_closing_tag(0)
        _, offset = decode_tag(buf, 0)
        value, _ = extract_context_value(buf, offset, 0)
        assert value == inner


# ---------------------------------------------------------------------------
# Security: tag length sanity limit
# ---------------------------------------------------------------------------


class TestTagLengthSanityLimit:
    def test_oversized_tag_length_raises(self):
        """Tag with length > 1MB should raise ValueError."""
        # Craft a tag header claiming 2MB of content:
        # tag_number=2, APPLICATION, extended length with 4-byte size
        # Initial byte: (2 << 4) | (0 << 3) | 5 = 0x25
        # Extended length: 255 (4-byte marker), then 0x00200000 (2MB)
        header = bytes([0x25, 255]) + struct.pack(">I", 2_000_000)
        with pytest.raises(ValueError, match="exceeds sanity limit"):
            decode_tag(header, 0)

    def test_valid_large_tag_within_limit(self):
        """Tag with length < 1MB should decode fine."""
        # 500KB — within limit
        header = bytes([0x25, 255]) + struct.pack(">I", 500_000)
        tag, _offset = decode_tag(header, 0)
        assert tag.length == 500_000
        assert tag.number == 2
