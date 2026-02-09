"""Phase 5 validation tests: Encoding architecture improvements (A5, E6, E5/A1).

Tests verify BitString hashability, BACnetDouble encoding as Double (tag 5),
and property-aware enum coercion on write.
"""

import struct

from bac_py.encoding.primitives import (
    encode_property_value,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject, BinaryValueObject
from bac_py.objects.multistate import MultiStateInputObject
from bac_py.objects.value_types import LargeAnalogValueObject
from bac_py.types.enums import (
    BinaryPV,
    EngineeringUnits,
    EventState,
    PropertyIdentifier,
)
from bac_py.types.primitives import BACnetDouble, BitString


# ---------------------------------------------------------------------------
# A5: BitString hashability
# ---------------------------------------------------------------------------
class TestA5BitStringHashable:
    """A5: BitString should be hashable and usable in sets/dicts."""

    def test_bitstring_is_hashable(self):
        bs = BitString(b"\xff", 0)
        h = hash(bs)
        assert isinstance(h, int)

    def test_equal_bitstrings_have_same_hash(self):
        bs1 = BitString(b"\xf0", 4)
        bs2 = BitString(b"\xf0", 4)
        assert bs1 == bs2
        assert hash(bs1) == hash(bs2)

    def test_different_data_different_hash(self):
        bs1 = BitString(b"\xf0", 0)
        bs2 = BitString(b"\x0f", 0)
        # Hash collision is possible but extremely unlikely for these values
        assert bs1 != bs2

    def test_different_unused_bits_different_hash(self):
        bs1 = BitString(b"\xf0", 0)
        bs2 = BitString(b"\xf0", 4)
        assert bs1 != bs2
        # Different unused_bits should typically give different hash
        assert hash(bs1) != hash(bs2)

    def test_bitstring_in_set(self):
        bs1 = BitString(b"\xff", 0)
        bs2 = BitString(b"\xff", 0)
        bs3 = BitString(b"\x00", 0)
        s = {bs1, bs2, bs3}
        assert len(s) == 2  # bs1 and bs2 are equal

    def test_bitstring_as_dict_key(self):
        bs = BitString(b"\xaa", 0)
        d = {bs: "value"}
        assert d[BitString(b"\xaa", 0)] == "value"

    def test_empty_bitstring_hashable(self):
        bs = BitString(b"", 0)
        assert isinstance(hash(bs), int)


# ---------------------------------------------------------------------------
# E6: BACnetDouble sentinel type and Double encoding
# ---------------------------------------------------------------------------
class TestE6BACnetDouble:
    """E6: BACnetDouble encodes as Double (tag 5, 8 bytes) not Real (tag 4, 4 bytes)."""

    def test_bacnet_double_is_float_subclass(self):
        d = BACnetDouble(3.14)
        assert isinstance(d, float)
        assert isinstance(d, BACnetDouble)

    def test_bacnet_double_value(self):
        d = BACnetDouble(42.5)
        assert float(d) == 42.5

    def test_bacnet_double_arithmetic(self):
        d = BACnetDouble(10.0)
        # Arithmetic returns plain float, which is expected
        result = d + 5.0
        assert result == 15.0

    def test_encode_bacnet_double_uses_tag_5(self):
        d = BACnetDouble(3.14159)
        encoded = encode_property_value(d)
        tag, offset = decode_tag(encoded, 0)
        assert tag.cls == TagClass.APPLICATION
        assert tag.number == 5  # Double tag
        assert tag.length == 8  # 8 bytes for double

    def test_encode_plain_float_uses_tag_4(self):
        encoded = encode_property_value(3.14159)
        tag, offset = decode_tag(encoded, 0)
        assert tag.cls == TagClass.APPLICATION
        assert tag.number == 4  # Real tag
        assert tag.length == 4  # 4 bytes for real

    def test_double_preserves_full_precision(self):
        # A value that loses precision in 32-bit float
        precise_value = 1.23456789012345
        d = BACnetDouble(precise_value)
        encoded = encode_property_value(d)
        tag, offset = decode_tag(encoded, 0)
        content = encoded[offset:]
        decoded = struct.unpack(">d", content)[0]
        assert decoded == precise_value

    def test_real_loses_precision(self):
        # Same value encoded as Real loses precision
        precise_value = 1.23456789012345
        encoded = encode_property_value(precise_value)  # plain float -> Real
        tag, offset = decode_tag(encoded, 0)
        content = encoded[offset:]
        decoded = struct.unpack(">f", content)[0]
        assert decoded != precise_value  # precision lost

    def test_large_analog_value_present_value_is_double_type(self):
        lav = LargeAnalogValueObject(1)
        pv = lav.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert isinstance(pv, BACnetDouble)

    def test_large_analog_value_encodes_as_double(self):
        lav = LargeAnalogValueObject(1)
        pv = lav.read_property(PropertyIdentifier.PRESENT_VALUE)
        encoded = encode_property_value(pv)
        tag, _offset = decode_tag(encoded, 0)
        assert tag.number == 5  # Double tag

    def test_large_analog_value_write_coerces_to_double(self):
        lav = LargeAnalogValueObject(1)
        # Write a plain float - should be coerced to BACnetDouble
        lav.write_property(PropertyIdentifier.PRESENT_VALUE, 99.99)
        pv = lav.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert isinstance(pv, BACnetDouble)
        assert float(pv) == 99.99

    def test_large_analog_value_commandable_double(self):
        lav = LargeAnalogValueObject(1, commandable=True)
        lav.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0, priority=8)
        pv = lav.read_property(PropertyIdentifier.PRESENT_VALUE)
        # The value should still be usable as a float
        assert pv == 42.0


# ---------------------------------------------------------------------------
# E5/A1: Property-aware enum coercion on write
# ---------------------------------------------------------------------------
class TestE5PropertyAwareEnumCoercion:
    """E5/A1: Plain int values written to enum-typed properties are coerced."""

    def test_binary_input_present_value_coercion(self):
        bi = BinaryInputObject(1)
        bi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        # Write raw int 1 (as if decoded from wire)
        bi.write_property(PropertyIdentifier.PRESENT_VALUE, 1)
        pv = bi.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == BinaryPV.ACTIVE
        assert isinstance(pv, BinaryPV)

    def test_binary_output_present_value_coercion(self):
        bo = BinaryOutputObject(1)
        # Write raw int 0 (as decoded from wire) with priority
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, 0, priority=16)
        pv = bo.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == BinaryPV.INACTIVE
        assert isinstance(pv, BinaryPV)

    def test_binary_value_coercion(self):
        bv = BinaryValueObject(1)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, 1)
        pv = bv.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert isinstance(pv, BinaryPV)
        assert pv == BinaryPV.ACTIVE

    def test_enum_already_correct_type_unchanged(self):
        bi = BinaryInputObject(1)
        bi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        bi.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        pv = bi.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert isinstance(pv, BinaryPV)

    def test_units_coercion(self):
        ai = AnalogInputObject(1)
        # Write raw int for engineering units
        ai.write_property(PropertyIdentifier.UNITS, 62)  # degrees-celsius
        units = ai.read_property(PropertyIdentifier.UNITS)
        assert isinstance(units, EngineeringUnits)
        assert units == EngineeringUnits.DEGREES_CELSIUS

    def test_event_state_coercion(self):
        ao = AnalogOutputObject(1)
        prop_def = ao.PROPERTY_DEFINITIONS[PropertyIdentifier.EVENT_STATE]
        # Direct test of _coerce_value since Event_State is read-only
        from bac_py.objects.base import BACnetObject

        result = BACnetObject._coerce_value(prop_def, 0)
        assert isinstance(result, EventState)
        assert result == EventState.NORMAL

    def test_invalid_enum_value_passes_through(self):
        """An int value not matching any enum member should pass through unchanged."""
        from bac_py.objects.base import BACnetObject

        ao = AnalogOutputObject(1)
        prop_def = ao.PROPERTY_DEFINITIONS[PropertyIdentifier.EVENT_STATE]
        # 9999 is not a valid EventState value
        result = BACnetObject._coerce_value(prop_def, 9999)
        assert result == 9999
        assert isinstance(result, int)
        assert not isinstance(result, EventState)

    def test_bool_not_coerced_to_enum(self):
        """Booleans should not be coerced even though bool is a subclass of int."""
        bi = BinaryInputObject(1)
        # Out_Of_Service is a bool-typed property
        bi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        oos = bi.read_property(PropertyIdentifier.OUT_OF_SERVICE)
        assert oos is True
        assert isinstance(oos, bool)

    def test_none_not_coerced(self):
        """None values should pass through coercion unchanged."""
        from bac_py.objects.base import BACnetObject

        ao = AnalogOutputObject(1)
        prop_def = ao.PROPERTY_DEFINITIONS[PropertyIdentifier.EVENT_STATE]
        result = BACnetObject._coerce_value(prop_def, None)
        assert result is None

    def test_multistate_int_not_coerced(self):
        """MultiState Present_Value is int (not IntEnum), so no coercion needed."""
        msi = MultiStateInputObject(1)
        msi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        msi.write_property(PropertyIdentifier.PRESENT_VALUE, 2)
        pv = msi.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == 2
        assert isinstance(pv, int)

    def test_float_to_bacnet_double_coercion(self):
        """Plain float written to BACnetDouble property gets coerced."""
        from bac_py.objects.base import BACnetObject

        lav = LargeAnalogValueObject(1)
        prop_def = lav.PROPERTY_DEFINITIONS[PropertyIdentifier.PRESENT_VALUE]
        result = BACnetObject._coerce_value(prop_def, 3.14)
        assert isinstance(result, BACnetDouble)
        assert float(result) == 3.14

    def test_bacnet_double_not_double_wrapped(self):
        """BACnetDouble written to BACnetDouble property stays as-is."""
        from bac_py.objects.base import BACnetObject

        lav = LargeAnalogValueObject(1)
        prop_def = lav.PROPERTY_DEFINITIONS[PropertyIdentifier.PRESENT_VALUE]
        d = BACnetDouble(3.14)
        result = BACnetObject._coerce_value(prop_def, d)
        assert isinstance(result, BACnetDouble)
        assert result is d  # Same object, not re-wrapped
