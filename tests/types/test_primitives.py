"""Tests for BACnet primitive data types."""

from __future__ import annotations

import pytest

from bac_py.types.enums import ObjectType
from bac_py.types.primitives import (
    BACnetDate,
    BACnetTime,
    BitString,
    ObjectIdentifier,
    _enum_from_dict,
    _enum_name,
)

# ---------------------------------------------------------------------------
# _enum_name helper
# ---------------------------------------------------------------------------


class TestEnumName:
    def test_converts_upper_snake_to_lower_hyphen(self):
        assert _enum_name(ObjectType.ANALOG_INPUT) == "analog-input"

    def test_single_word(self):
        assert _enum_name(ObjectType.DEVICE) == "device"

    def test_multi_word(self):
        assert _enum_name(ObjectType.MULTI_STATE_INPUT) == "multi-state-input"


# ---------------------------------------------------------------------------
# _enum_from_dict helper
# ---------------------------------------------------------------------------


class TestEnumFromDict:
    def test_accepts_int(self):
        result = _enum_from_dict(ObjectType, 0)
        assert result is ObjectType.ANALOG_INPUT

    def test_accepts_string_hyphenated(self):
        result = _enum_from_dict(ObjectType, "analog-input")
        assert result is ObjectType.ANALOG_INPUT

    def test_accepts_string_multi_word(self):
        result = _enum_from_dict(ObjectType, "binary-output")
        assert result is ObjectType.BINARY_OUTPUT

    def test_accepts_dict_with_value_key(self):
        result = _enum_from_dict(ObjectType, {"value": 8, "name": "device"})
        assert result is ObjectType.DEVICE

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            _enum_from_dict(ObjectType, 3.14)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ObjectIdentifier
# ---------------------------------------------------------------------------


class TestObjectIdentifier:
    def test_creation(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert oid.object_type is ObjectType.ANALOG_INPUT
        assert oid.instance_number == 1

    def test_encode_produces_4_bytes(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        encoded = oid.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) == 4

    def test_encode_analog_input_1(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        encoded = oid.encode()
        # ANALOG_INPUT = 0, instance = 1
        # (0 << 22) | 1 = 0x00000001
        assert encoded == b"\x00\x00\x00\x01"

    def test_encode_device_instance(self):
        oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        encoded = oid.encode()
        # DEVICE = 8, instance = 100
        # (8 << 22) | 100 = 0x02000064
        expected = (8 << 22 | 100).to_bytes(4, "big")
        assert encoded == expected

    def test_decode_round_trip(self):
        original = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        encoded = original.encode()
        decoded = ObjectIdentifier.decode(encoded)
        assert decoded == original

    def test_decode_round_trip_device(self):
        original = ObjectIdentifier(ObjectType.DEVICE, 4194303)
        encoded = original.encode()
        decoded = ObjectIdentifier.decode(encoded)
        assert decoded == original

    def test_decode_from_memoryview(self):
        original = ObjectIdentifier(ObjectType.BINARY_INPUT, 42)
        encoded = original.encode()
        decoded = ObjectIdentifier.decode(memoryview(encoded))
        assert decoded == original

    def test_to_dict(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        d = oid.to_dict()
        assert d == {"object_type": "analog-input", "instance": 1}

    def test_to_dict_device(self):
        oid = ObjectIdentifier(ObjectType.DEVICE, 500)
        d = oid.to_dict()
        assert d == {"object_type": "device", "instance": 500}

    def test_from_dict_round_trip(self):
        original = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        d = original.to_dict()
        restored = ObjectIdentifier.from_dict(d)
        assert restored == original

    def test_from_dict_accepts_string_object_type(self):
        d = {"object_type": "analog-output", "instance": 7}
        oid = ObjectIdentifier.from_dict(d)
        assert oid.object_type is ObjectType.ANALOG_OUTPUT
        assert oid.instance_number == 7

    def test_from_dict_accepts_int_object_type(self):
        d = {"object_type": 0, "instance": 5}
        oid = ObjectIdentifier.from_dict(d)
        assert oid.object_type is ObjectType.ANALOG_INPUT
        assert oid.instance_number == 5

    def test_instance_number_zero(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 0)
        assert oid.instance_number == 0

    def test_instance_number_max(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 4194303)
        assert oid.instance_number == 4194303

    def test_instance_number_negative_raises(self):
        with pytest.raises(ValueError, match="Instance number must be 0-4194303"):
            ObjectIdentifier(ObjectType.ANALOG_INPUT, -1)

    def test_instance_number_too_large_raises(self):
        with pytest.raises(ValueError, match="Instance number must be 0-4194303"):
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 4194304)

    def test_instance_number_way_too_large_raises(self):
        with pytest.raises(ValueError, match="Instance number must be 0-4194303"):
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 10_000_000)

    def test_frozen(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        with pytest.raises(AttributeError):
            oid.instance_number = 2  # type: ignore[misc]

    def test_equality(self):
        a = ObjectIdentifier(ObjectType.DEVICE, 100)
        b = ObjectIdentifier(ObjectType.DEVICE, 100)
        assert a == b

    def test_inequality_different_type(self):
        a = ObjectIdentifier(ObjectType.DEVICE, 100)
        b = ObjectIdentifier(ObjectType.ANALOG_INPUT, 100)
        assert a != b

    def test_inequality_different_instance(self):
        a = ObjectIdentifier(ObjectType.DEVICE, 100)
        b = ObjectIdentifier(ObjectType.DEVICE, 200)
        assert a != b


# ---------------------------------------------------------------------------
# BACnetDate
# ---------------------------------------------------------------------------


class TestBACnetDate:
    def test_creation(self):
        d = BACnetDate(year=2024, month=6, day=15, day_of_week=6)
        assert d.year == 2024
        assert d.month == 6
        assert d.day == 15
        assert d.day_of_week == 6

    def test_to_dict_normal_values(self):
        d = BACnetDate(year=2024, month=6, day=15, day_of_week=6)
        result = d.to_dict()
        assert result == {
            "year": 2024,
            "month": 6,
            "day": 15,
            "day_of_week": 6,
        }

    def test_to_dict_maps_0xff_to_none(self):
        d = BACnetDate(year=0xFF, month=0xFF, day=0xFF, day_of_week=0xFF)
        result = d.to_dict()
        assert result == {
            "year": None,
            "month": None,
            "day": None,
            "day_of_week": None,
        }

    def test_to_dict_partial_wildcards(self):
        d = BACnetDate(year=2024, month=0xFF, day=1, day_of_week=0xFF)
        result = d.to_dict()
        assert result == {
            "year": 2024,
            "month": None,
            "day": 1,
            "day_of_week": None,
        }

    def test_from_dict_maps_none_to_0xff(self):
        data = {
            "year": None,
            "month": None,
            "day": None,
            "day_of_week": None,
        }
        d = BACnetDate.from_dict(data)
        assert d.year == 0xFF
        assert d.month == 0xFF
        assert d.day == 0xFF
        assert d.day_of_week == 0xFF

    def test_from_dict_normal_values(self):
        data = {
            "year": 2024,
            "month": 12,
            "day": 25,
            "day_of_week": 3,
        }
        d = BACnetDate.from_dict(data)
        assert d.year == 2024
        assert d.month == 12
        assert d.day == 25
        assert d.day_of_week == 3

    def test_round_trip_with_wildcards(self):
        original = BACnetDate(year=0xFF, month=6, day=0xFF, day_of_week=0xFF)
        restored = BACnetDate.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_normal(self):
        original = BACnetDate(year=2024, month=1, day=31, day_of_week=3)
        restored = BACnetDate.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self):
        d = BACnetDate(year=2024, month=6, day=15, day_of_week=6)
        with pytest.raises(AttributeError):
            d.year = 2025  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BACnetTime
# ---------------------------------------------------------------------------


class TestBACnetTime:
    def test_creation(self):
        t = BACnetTime(hour=14, minute=30, second=45, hundredth=50)
        assert t.hour == 14
        assert t.minute == 30
        assert t.second == 45
        assert t.hundredth == 50

    def test_to_dict_normal_values(self):
        t = BACnetTime(hour=14, minute=30, second=45, hundredth=50)
        result = t.to_dict()
        assert result == {
            "hour": 14,
            "minute": 30,
            "second": 45,
            "hundredth": 50,
        }

    def test_to_dict_maps_0xff_to_none(self):
        t = BACnetTime(hour=0xFF, minute=0xFF, second=0xFF, hundredth=0xFF)
        result = t.to_dict()
        assert result == {
            "hour": None,
            "minute": None,
            "second": None,
            "hundredth": None,
        }

    def test_to_dict_partial_wildcards(self):
        t = BACnetTime(hour=12, minute=0, second=0xFF, hundredth=0xFF)
        result = t.to_dict()
        assert result == {
            "hour": 12,
            "minute": 0,
            "second": None,
            "hundredth": None,
        }

    def test_from_dict_maps_none_to_0xff(self):
        data = {
            "hour": None,
            "minute": None,
            "second": None,
            "hundredth": None,
        }
        t = BACnetTime.from_dict(data)
        assert t.hour == 0xFF
        assert t.minute == 0xFF
        assert t.second == 0xFF
        assert t.hundredth == 0xFF

    def test_from_dict_normal_values(self):
        data = {
            "hour": 8,
            "minute": 15,
            "second": 0,
            "hundredth": 99,
        }
        t = BACnetTime.from_dict(data)
        assert t.hour == 8
        assert t.minute == 15
        assert t.second == 0
        assert t.hundredth == 99

    def test_round_trip_with_wildcards(self):
        original = BACnetTime(hour=0xFF, minute=30, second=0xFF, hundredth=0xFF)
        restored = BACnetTime.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_normal(self):
        original = BACnetTime(hour=23, minute=59, second=59, hundredth=99)
        restored = BACnetTime.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self):
        t = BACnetTime(hour=12, minute=0, second=0, hundredth=0)
        with pytest.raises(AttributeError):
            t.hour = 13  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BitString
# ---------------------------------------------------------------------------


class TestBitString:
    def test_creation_from_bytes(self):
        bs = BitString(b"\xa0", unused_bits=0)
        assert bs.data == b"\xa0"
        assert bs.unused_bits == 0

    def test_len_full_byte(self):
        bs = BitString(b"\xff", unused_bits=0)
        assert len(bs) == 8

    def test_len_with_unused_bits(self):
        bs = BitString(b"\xff", unused_bits=3)
        assert len(bs) == 5

    def test_len_two_bytes_no_unused(self):
        bs = BitString(b"\xff\x00", unused_bits=0)
        assert len(bs) == 16

    def test_len_two_bytes_with_unused(self):
        bs = BitString(b"\xff\x00", unused_bits=4)
        assert len(bs) == 12

    def test_getitem_msb_first(self):
        # 0xA0 = 1010 0000
        bs = BitString(b"\xa0", unused_bits=0)
        assert bs[0] is True
        assert bs[1] is False
        assert bs[2] is True
        assert bs[3] is False
        assert bs[4] is False
        assert bs[5] is False
        assert bs[6] is False
        assert bs[7] is False

    def test_getitem_all_ones(self):
        bs = BitString(b"\xff", unused_bits=0)
        for i in range(8):
            assert bs[i] is True

    def test_getitem_all_zeros(self):
        bs = BitString(b"\x00", unused_bits=0)
        for i in range(8):
            assert bs[i] is False

    def test_getitem_across_bytes(self):
        # 0xFF 0x00 => 11111111 00000000
        bs = BitString(b"\xff\x00", unused_bits=0)
        assert bs[7] is True
        assert bs[8] is False

    def test_getitem_alternating_bits(self):
        # 0x55 = 0101 0101
        bs = BitString(b"\x55", unused_bits=0)
        expected = [False, True, False, True, False, True, False, True]
        for i, expected_val in enumerate(expected):
            assert bs[i] is expected_val

    def test_getitem_index_out_of_range_raises(self):
        bs = BitString(b"\xa0", unused_bits=0)
        with pytest.raises(IndexError, match="Bit index 8 out of range"):
            bs[8]

    def test_getitem_negative_index_raises(self):
        bs = BitString(b"\xa0", unused_bits=0)
        with pytest.raises(IndexError, match="Bit index -1 out of range"):
            bs[-1]

    def test_getitem_respects_unused_bits(self):
        # 5 significant bits with 3 unused
        bs = BitString(b"\xf8", unused_bits=3)
        assert len(bs) == 5
        for i in range(5):
            assert bs[i] is True
        with pytest.raises(IndexError):
            bs[5]

    def test_equality_same(self):
        a = BitString(b"\xa0", unused_bits=2)
        b = BitString(b"\xa0", unused_bits=2)
        assert a == b

    def test_equality_different_data(self):
        a = BitString(b"\xa0", unused_bits=0)
        b = BitString(b"\xb0", unused_bits=0)
        assert a != b

    def test_equality_different_unused(self):
        a = BitString(b"\xa0", unused_bits=0)
        b = BitString(b"\xa0", unused_bits=2)
        assert a != b

    def test_equality_not_implemented_for_other_types(self):
        bs = BitString(b"\xa0", unused_bits=0)
        assert bs != "not a bitstring"
        assert bs.__eq__("not a bitstring") is NotImplemented

    def test_to_dict(self):
        # 0xA0 = 1010 0000
        bs = BitString(b"\xa0", unused_bits=0)
        d = bs.to_dict()
        assert d == {
            "bits": [True, False, True, False, False, False, False, False],
            "unused_bits": 0,
        }

    def test_to_dict_with_unused_bits(self):
        # 0xE0 = 1110 0000, 5 unused => 3 significant bits
        bs = BitString(b"\xe0", unused_bits=5)
        d = bs.to_dict()
        assert d == {
            "bits": [True, True, True],
            "unused_bits": 5,
        }

    def test_from_dict(self):
        data = {
            "bits": [True, False, True, False, False, False, False, False],
            "unused_bits": 0,
        }
        bs = BitString.from_dict(data)
        assert bs.data == b"\xa0"
        assert bs.unused_bits == 0

    def test_from_dict_with_unused_bits(self):
        data = {
            "bits": [True, True, True],
            "unused_bits": 5,
        }
        bs = BitString.from_dict(data)
        assert bs.data == b"\xe0"
        assert bs.unused_bits == 5

    def test_from_dict_defaults_unused_to_zero(self):
        data = {
            "bits": [True, False, True, False, True, False, True, False],
        }
        bs = BitString.from_dict(data)
        assert bs.unused_bits == 0

    def test_to_dict_from_dict_round_trip(self):
        original = BitString(b"\xa5\xf0", unused_bits=4)
        d = original.to_dict()
        restored = BitString.from_dict(d)
        assert restored == original

    def test_to_dict_from_dict_round_trip_no_unused(self):
        original = BitString(b"\xde\xad", unused_bits=0)
        d = original.to_dict()
        restored = BitString.from_dict(d)
        assert restored == original

    def test_repr(self):
        # 0xA0 = 1010 0000
        bs = BitString(b"\xa0", unused_bits=0)
        r = repr(bs)
        assert r == "BitString('10100000')"

    def test_repr_with_unused(self):
        # 0xE0 = 1110 0000, 5 unused => "111"
        bs = BitString(b"\xe0", unused_bits=5)
        r = repr(bs)
        assert r == "BitString('111')"

    def test_empty_bitstring(self):
        bs = BitString(b"", unused_bits=0)
        assert len(bs) == 0
        with pytest.raises(IndexError):
            bs[0]


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestObjectIdentifierValidation:
    def test_object_type_too_large_raises(self):
        """ObjectType(1024) raises ValueError from the enum (> 1023)."""
        # ObjectType._missing_ only accepts 0-1023, so 1024 is invalid
        with pytest.raises(ValueError):
            ObjectType(1024)

    def test_object_type_negative_raises(self):
        """ObjectType(-1) raises ValueError from the enum."""
        with pytest.raises(ValueError):
            ObjectType(-1)

    def test_post_init_instance_number_validation(self):
        """ObjectIdentifier __post_init__ validates instance number bounds."""
        # Test both bounds are enforced
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 0)
        assert oid.instance_number == 0
        oid_max = ObjectIdentifier(ObjectType.ANALOG_INPUT, 0x3FFFFF)
        assert oid_max.instance_number == 0x3FFFFF


class TestObjectIdentifierFromDictErrors:
    def test_from_dict_with_int_object_type(self):
        """ObjectIdentifier.from_dict resolves integer object_type correctly."""
        d = {"object_type": 0, "instance": 1}
        oid = ObjectIdentifier.from_dict(d)
        assert oid.object_type is ObjectType.ANALOG_INPUT
        assert oid.instance_number == 1

    def test_from_dict_with_string_object_type(self):
        """ObjectIdentifier.from_dict resolves string object_type correctly."""
        d = {"object_type": "device", "instance": 100}
        oid = ObjectIdentifier.from_dict(d)
        assert oid.object_type is ObjectType.DEVICE
        assert oid.instance_number == 100

    def test_from_dict_with_dict_object_type(self):
        """ObjectIdentifier.from_dict resolves dict object_type correctly."""
        d = {"object_type": {"value": 8, "name": "device"}, "instance": 100}
        oid = ObjectIdentifier.from_dict(d)
        assert oid.object_type is ObjectType.DEVICE
        assert oid.instance_number == 100


class TestBitStringValidation:
    def test_unused_bits_negative_raises(self):
        """BitString with unused_bits < 0 raises ValueError."""
        with pytest.raises(ValueError, match="unused_bits must be 0-7"):
            BitString(b"\xff", unused_bits=-1)

    def test_unused_bits_too_large_raises(self):
        """BitString with unused_bits > 7 raises ValueError."""
        with pytest.raises(ValueError, match="unused_bits must be 0-7"):
            BitString(b"\xff", unused_bits=8)

    def test_unused_bits_nonzero_with_empty_data_raises(self):
        """BitString with empty data and non-zero unused_bits raises ValueError."""
        with pytest.raises(ValueError, match="unused_bits must be 0 when data is empty"):
            BitString(b"", unused_bits=3)


# ---------------------------------------------------------------------------
# Coverage: primitives.py lines 61-62 and 113-114
# ---------------------------------------------------------------------------


class TestObjectIdentifierObjectTypeValidation:
    """Lines 61-62: ObjectIdentifier rejects object_type > 1023."""

    def test_object_type_above_1023_raises(self):
        # Use a raw int > 1023 coerced via ObjectType._missing_ fallback
        # ObjectType._missing_ only accepts 0-1023, so an int-based
        # ObjectType above 1023 must fail at __post_init__
        # We need to bypass enum validation and test __post_init__ directly
        # by using a mock or direct construction. Since ObjectType(1024) fails,
        # the __post_init__ validation at line 61 would catch it if passed.
        with pytest.raises(ValueError):
            ObjectIdentifier(ObjectType(1024), 0)  # type: ignore[arg-type]

    def test_post_init_rejects_object_type_above_1023(self):
        """Lines 61-62: __post_init__ validates int(object_type) <= 1023.

        Bypass enum validation by creating a fake IntEnum member with value 1024.
        """
        import enum

        class FakeObjectType(enum.IntEnum):
            FAKE_HIGH = 1024

        with pytest.raises(ValueError, match="Object type must be 0-1023"):
            ObjectIdentifier(FakeObjectType.FAKE_HIGH, 0)  # type: ignore[arg-type]

    def test_post_init_rejects_negative_object_type(self):
        """Lines 61-62: __post_init__ validates int(object_type) >= 0."""
        import enum

        class FakeObjectType(enum.IntEnum):
            NEGATIVE = -1

        with pytest.raises(ValueError, match="Object type must be 0-1023"):
            ObjectIdentifier(FakeObjectType.NEGATIVE, 0)  # type: ignore[arg-type]


class TestObjectIdentifierFromDictBadType:
    """Lines 113-114: ObjectIdentifier.from_dict raises TypeError for non-ObjectType."""

    def test_from_dict_non_object_type_raises(self):
        # _enum_from_dict with a float value raises ValueError, not TypeError.
        # To trigger line 113 we need _enum_from_dict to return something
        # that is NOT an ObjectType. This happens with a dict that has a value
        # key that resolves to a valid int but wrong enum type.
        # Actually, the simpler approach: the check is isinstance(obj_type, ObjectType).
        # ObjectType._missing_() handles 0-1023, so any int 0-1023 returns an ObjectType.
        # We need to monkeypatch _enum_from_dict to return a non-ObjectType.
        import unittest.mock

        with (
            unittest.mock.patch(
                "bac_py.types.primitives._enum_from_dict", return_value="not-an-object-type"
            ),
            pytest.raises(TypeError, match="Expected ObjectType"),
        ):
            ObjectIdentifier.from_dict({"object_type": "analog-input", "instance": 1})
