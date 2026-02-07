import pytest

from bac_py.encoding.tags import (
    Tag,
    TagClass,
    decode_tag,
    encode_closing_tag,
    encode_opening_tag,
    encode_tag,
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
        tag, offset = decode_tag(memoryview(encoded), 0)
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
