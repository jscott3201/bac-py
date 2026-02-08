"""Tests for BACnet Value object types (Clause 12.36-12.45)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.value_types import (
    BitStringValueObject,
    CharacterStringValueObject,
    DateTimeValueObject,
    IntegerValueObject,
    LargeAnalogValueObject,
    OctetStringValueObject,
    PositiveIntegerValueObject,
)
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    EngineeringUnits,
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier

# --- IntegerValueObject ---


class TestIntegerValueObject:
    """Tests for IntegerValueObject (Clause 12.43)."""

    def test_create_basic(self):
        iv = IntegerValueObject(1)
        assert iv.object_identifier == ObjectIdentifier(ObjectType.INTEGER_VALUE, 1)

    def test_object_type(self):
        iv = IntegerValueObject(1)
        assert iv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.INTEGER_VALUE

    def test_present_value_default(self):
        iv = IntegerValueObject(1)
        assert iv.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_present_value_writable(self):
        iv = IntegerValueObject(1)
        iv.write_property(PropertyIdentifier.PRESENT_VALUE, -42)
        assert iv.read_property(PropertyIdentifier.PRESENT_VALUE) == -42

    def test_units_default(self):
        iv = IntegerValueObject(1)
        assert iv.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_status_flags_initialized(self):
        iv = IntegerValueObject(1)
        sf = iv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_event_state_default(self):
        iv = IntegerValueObject(1)
        assert iv.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        iv = IntegerValueObject(1)
        assert iv.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_not_commandable_by_default(self):
        iv = IntegerValueObject(1)
        assert iv._priority_array is None

    def test_commandable_when_requested(self):
        iv = IntegerValueObject(1, commandable=True)
        assert iv._priority_array is not None
        assert len(iv._priority_array) == 16

    def test_commandable_priority_write(self):
        iv = IntegerValueObject(1, commandable=True)
        iv.write_property(PropertyIdentifier.PRESENT_VALUE, 99, priority=4)
        assert iv._priority_array[3] == 99
        assert iv.read_property(PropertyIdentifier.PRESENT_VALUE) == 99

    def test_commandable_relinquish(self):
        iv = IntegerValueObject(1, commandable=True)
        iv.write_property(PropertyIdentifier.PRESENT_VALUE, 99, priority=4)
        iv.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=4)
        assert iv.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_property_list(self):
        iv = IntegerValueObject(1)
        plist = iv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.UNITS in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist
        assert PropertyIdentifier.OBJECT_NAME not in plist
        assert PropertyIdentifier.OBJECT_TYPE not in plist
        assert PropertyIdentifier.PROPERTY_LIST not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.INTEGER_VALUE, 5)
        assert isinstance(obj, IntegerValueObject)

    def test_initial_properties(self):
        iv = IntegerValueObject(1, object_name="IV-1", description="Test int")
        assert iv.read_property(PropertyIdentifier.OBJECT_NAME) == "IV-1"
        assert iv.read_property(PropertyIdentifier.DESCRIPTION) == "Test int"


# --- PositiveIntegerValueObject ---


class TestPositiveIntegerValueObject:
    """Tests for PositiveIntegerValueObject (Clause 12.44)."""

    def test_create_basic(self):
        piv = PositiveIntegerValueObject(1)
        assert piv.object_identifier == ObjectIdentifier(ObjectType.POSITIVE_INTEGER_VALUE, 1)

    def test_object_type(self):
        piv = PositiveIntegerValueObject(1)
        assert (
            piv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.POSITIVE_INTEGER_VALUE
        )

    def test_present_value_default(self):
        piv = PositiveIntegerValueObject(1)
        assert piv.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_present_value_writable(self):
        piv = PositiveIntegerValueObject(1)
        piv.write_property(PropertyIdentifier.PRESENT_VALUE, 100)
        assert piv.read_property(PropertyIdentifier.PRESENT_VALUE) == 100

    def test_units_required(self):
        piv = PositiveIntegerValueObject(1)
        assert piv.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_commandable_when_requested(self):
        piv = PositiveIntegerValueObject(1, commandable=True)
        assert piv._priority_array is not None
        assert len(piv._priority_array) == 16

    def test_not_commandable_by_default(self):
        piv = PositiveIntegerValueObject(1)
        assert piv._priority_array is None

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.POSITIVE_INTEGER_VALUE, 3)
        assert isinstance(obj, PositiveIntegerValueObject)


# --- LargeAnalogValueObject ---


class TestLargeAnalogValueObject:
    """Tests for LargeAnalogValueObject (Clause 12.42)."""

    def test_create_basic(self):
        lav = LargeAnalogValueObject(1)
        assert lav.object_identifier == ObjectIdentifier(ObjectType.LARGE_ANALOG_VALUE, 1)

    def test_object_type(self):
        lav = LargeAnalogValueObject(1)
        assert lav.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.LARGE_ANALOG_VALUE

    def test_present_value_default(self):
        lav = LargeAnalogValueObject(1)
        assert lav.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_present_value_writable(self):
        lav = LargeAnalogValueObject(1)
        lav.write_property(PropertyIdentifier.PRESENT_VALUE, 1.23456789e15)
        assert lav.read_property(PropertyIdentifier.PRESENT_VALUE) == 1.23456789e15

    def test_units_required(self):
        lav = LargeAnalogValueObject(1)
        assert lav.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_commandable_when_requested(self):
        lav = LargeAnalogValueObject(1, commandable=True)
        assert lav._priority_array is not None
        assert len(lav._priority_array) == 16

    def test_commandable_relinquish_default(self):
        lav = LargeAnalogValueObject(1, commandable=True)
        assert lav.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 0.0

    def test_not_commandable_by_default(self):
        lav = LargeAnalogValueObject(1)
        assert lav._priority_array is None

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.LARGE_ANALOG_VALUE, 2)
        assert isinstance(obj, LargeAnalogValueObject)


# --- CharacterStringValueObject ---


class TestCharacterStringValueObject:
    """Tests for CharacterStringValueObject (Clause 12.37)."""

    def test_create_basic(self):
        csv = CharacterStringValueObject(1)
        assert csv.object_identifier == ObjectIdentifier(ObjectType.CHARACTERSTRING_VALUE, 1)

    def test_object_type(self):
        csv = CharacterStringValueObject(1)
        assert (
            csv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.CHARACTERSTRING_VALUE
        )

    def test_present_value_default(self):
        csv = CharacterStringValueObject(1)
        assert csv.read_property(PropertyIdentifier.PRESENT_VALUE) == ""

    def test_present_value_writable(self):
        csv = CharacterStringValueObject(1)
        csv.write_property(PropertyIdentifier.PRESENT_VALUE, "Hello BACnet")
        assert csv.read_property(PropertyIdentifier.PRESENT_VALUE) == "Hello BACnet"

    def test_no_units_property(self):
        """CharacterString Value has no Units property per spec."""
        csv = CharacterStringValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            csv.read_property(PropertyIdentifier.UNITS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_commandable_when_requested(self):
        csv = CharacterStringValueObject(1, commandable=True)
        assert csv._priority_array is not None
        assert len(csv._priority_array) == 16

    def test_commandable_relinquish_default(self):
        csv = CharacterStringValueObject(1, commandable=True)
        assert csv.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == ""

    def test_commandable_priority_write(self):
        csv = CharacterStringValueObject(1, commandable=True)
        csv.write_property(PropertyIdentifier.PRESENT_VALUE, "high", priority=1)
        csv.write_property(PropertyIdentifier.PRESENT_VALUE, "low", priority=16)
        assert csv.read_property(PropertyIdentifier.PRESENT_VALUE) == "high"

    def test_not_commandable_by_default(self):
        csv = CharacterStringValueObject(1)
        assert csv._priority_array is None

    def test_status_flags_initialized(self):
        csv = CharacterStringValueObject(1)
        sf = csv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_property_list_no_units(self):
        csv = CharacterStringValueObject(1)
        plist = csv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.UNITS not in plist
        assert PropertyIdentifier.PRESENT_VALUE in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.CHARACTERSTRING_VALUE, 4)
        assert isinstance(obj, CharacterStringValueObject)


# --- DateTimeValueObject ---


class TestDateTimeValueObject:
    """Tests for DateTimeValueObject (Clause 12.40)."""

    def test_create_basic(self):
        dtv = DateTimeValueObject(1)
        assert dtv.object_identifier == ObjectIdentifier(ObjectType.DATETIME_VALUE, 1)

    def test_object_type(self):
        dtv = DateTimeValueObject(1)
        assert dtv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.DATETIME_VALUE

    def test_present_value_writable(self):
        dt = (2024, 6, 15, 14, 30, 0, 0)
        dtv = DateTimeValueObject(1, present_value=dt)
        dtv.write_property(PropertyIdentifier.PRESENT_VALUE, (2024, 12, 25, 0, 0, 0, 0))
        assert dtv.read_property(PropertyIdentifier.PRESENT_VALUE) == (2024, 12, 25, 0, 0, 0, 0)

    def test_commandable_when_requested(self):
        dtv = DateTimeValueObject(1, commandable=True)
        assert dtv._priority_array is not None

    def test_not_commandable_by_default(self):
        dtv = DateTimeValueObject(1)
        assert dtv._priority_array is None

    def test_status_flags_initialized(self):
        dtv = DateTimeValueObject(1)
        sf = dtv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_is_utc_optional(self):
        dtv = DateTimeValueObject(1)
        assert dtv.read_property(PropertyIdentifier.IS_UTC) is None

    def test_no_units_property(self):
        dtv = DateTimeValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            dtv.read_property(PropertyIdentifier.UNITS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.DATETIME_VALUE, 6)
        assert isinstance(obj, DateTimeValueObject)


# --- BitStringValueObject ---


class TestBitStringValueObject:
    """Tests for BitStringValueObject (Clause 12.36)."""

    def test_create_basic(self):
        bsv = BitStringValueObject(1)
        assert bsv.object_identifier == ObjectIdentifier(ObjectType.BITSTRING_VALUE, 1)

    def test_object_type(self):
        bsv = BitStringValueObject(1)
        assert bsv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.BITSTRING_VALUE

    def test_present_value_writable(self):
        bits = [True, False, True, True]
        bsv = BitStringValueObject(1, present_value=bits)
        assert bsv.read_property(PropertyIdentifier.PRESENT_VALUE) == bits

    def test_write_present_value(self):
        bsv = BitStringValueObject(1, present_value=[False, False])
        bsv.write_property(PropertyIdentifier.PRESENT_VALUE, [True, True])
        assert bsv.read_property(PropertyIdentifier.PRESENT_VALUE) == [True, True]

    def test_commandable_when_requested(self):
        bsv = BitStringValueObject(1, commandable=True)
        assert bsv._priority_array is not None

    def test_not_commandable_by_default(self):
        bsv = BitStringValueObject(1)
        assert bsv._priority_array is None

    def test_bit_text_optional(self):
        bsv = BitStringValueObject(1)
        assert bsv.read_property(PropertyIdentifier.BIT_TEXT) is None

    def test_bit_text_writable(self):
        bsv = BitStringValueObject(1)
        bsv.write_property(PropertyIdentifier.BIT_TEXT, ["On", "Off"])
        assert bsv.read_property(PropertyIdentifier.BIT_TEXT) == ["On", "Off"]

    def test_status_flags_initialized(self):
        bsv = BitStringValueObject(1)
        sf = bsv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_no_units_property(self):
        bsv = BitStringValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            bsv.read_property(PropertyIdentifier.UNITS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.BITSTRING_VALUE, 8)
        assert isinstance(obj, BitStringValueObject)


# --- OctetStringValueObject ---


class TestOctetStringValueObject:
    """Tests for OctetStringValueObject (Clause 12.45)."""

    def test_create_basic(self):
        osv = OctetStringValueObject(1)
        assert osv.object_identifier == ObjectIdentifier(ObjectType.OCTETSTRING_VALUE, 1)

    def test_object_type(self):
        osv = OctetStringValueObject(1)
        assert osv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.OCTETSTRING_VALUE

    def test_present_value_default(self):
        osv = OctetStringValueObject(1)
        assert osv.read_property(PropertyIdentifier.PRESENT_VALUE) == b""

    def test_present_value_writable(self):
        osv = OctetStringValueObject(1)
        osv.write_property(PropertyIdentifier.PRESENT_VALUE, b"\x01\x02\x03")
        assert osv.read_property(PropertyIdentifier.PRESENT_VALUE) == b"\x01\x02\x03"

    def test_commandable_when_requested(self):
        osv = OctetStringValueObject(1, commandable=True)
        assert osv._priority_array is not None
        assert len(osv._priority_array) == 16

    def test_commandable_relinquish_default(self):
        osv = OctetStringValueObject(1, commandable=True)
        assert osv.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == b""

    def test_not_commandable_by_default(self):
        osv = OctetStringValueObject(1)
        assert osv._priority_array is None

    def test_status_flags_initialized(self):
        osv = OctetStringValueObject(1)
        sf = osv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_no_units_property(self):
        osv = OctetStringValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            osv.read_property(PropertyIdentifier.UNITS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.OCTETSTRING_VALUE, 9)
        assert isinstance(obj, OctetStringValueObject)


# --- Cross-cutting commandable property tests ---


class TestValueObjectsCommandablePropertyPresence:
    """Commandable properties only present when commandable."""

    def test_non_commandable_no_priority_array(self):
        iv = IntegerValueObject(1)
        plist = iv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRIORITY_ARRAY not in plist
        assert PropertyIdentifier.RELINQUISH_DEFAULT not in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY not in plist

    def test_commandable_has_priority_array(self):
        iv = IntegerValueObject(1, commandable=True)
        plist = iv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_current_command_priority_none_when_relinquished(self):
        iv = IntegerValueObject(1, commandable=True)
        assert iv.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) is None

    def test_current_command_priority_returns_active(self):
        iv = IntegerValueObject(1, commandable=True)
        iv.write_property(PropertyIdentifier.PRESENT_VALUE, 42, priority=8)
        assert iv.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 8
