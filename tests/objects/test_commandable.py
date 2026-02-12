"""Tests for commandable object behavior: priority arrays and value source tracking."""

from typing import ClassVar

import pytest

from bac_py.objects.analog import AnalogOutputObject
from bac_py.objects.base import BACnetObject, PropertyAccess, PropertyDefinition
from bac_py.objects.binary import BinaryOutputObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import BACnetDeviceObjectReference, BACnetValueSource
from bac_py.types.enums import ErrorClass, ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class _CommandableObject(BACnetObject):
    """Test object with commandable Present Value."""

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ANALOG_OUTPUT
    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
    }

    def __init__(self, instance_number: int, **kwargs):
        super().__init__(instance_number, **kwargs)
        self._priority_array = [None] * 16


class TestCommandPriority:
    def test_write_defaults_to_priority_16(self):
        """Commandable writes without explicit priority default to 16 (Clause 19.2)."""
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert obj._priority_array[15] == 42.0  # priority 16 = index 15
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0

    def test_write_with_explicit_priority(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0, priority=8)
        assert obj._priority_array[7] == 99.0  # priority 8 = index 7
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 99.0

    def test_higher_priority_wins(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0, priority=16)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 20.0

    def test_priority_out_of_range_error(self):
        """Priority out of range must use SERVICES/PARAMETER_OUT_OF_RANGE."""
        obj = _CommandableObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0, priority=0)
        assert exc_info.value.error_class == ErrorClass.SERVICES
        assert exc_info.value.error_code == ErrorCode.PARAMETER_OUT_OF_RANGE

    def test_priority_17_out_of_range(self):
        obj = _CommandableObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0, priority=17)
        assert exc_info.value.error_class == ErrorClass.SERVICES
        assert exc_info.value.error_code == ErrorCode.PARAMETER_OUT_OF_RANGE

    def test_relinquish_via_none(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0, priority=8)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        # Should fall back to relinquish default
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    async def test_async_write_defaults_priority_16(self):
        """async_write_property also defaults to priority 16 for commandable."""
        obj = _CommandableObject(1)

        await obj.async_write_property(PropertyIdentifier.PRESENT_VALUE, 55.0)
        assert obj._priority_array[15] == 55.0


class TestValueSourceInitialization:
    def test_commandable_object_has_value_source(self):
        ao = AnalogOutputObject(1)
        vs = ao.read_property(PropertyIdentifier.VALUE_SOURCE)
        assert isinstance(vs, BACnetValueSource)
        assert vs.choice == 0  # none

    def test_commandable_object_has_value_source_array(self):
        ao = AnalogOutputObject(1)
        vsa = ao.read_property(PropertyIdentifier.VALUE_SOURCE_ARRAY)
        assert isinstance(vsa, list)
        assert len(vsa) == 16
        for item in vsa:
            assert isinstance(item, BACnetValueSource)
            assert item.choice == 0

    def test_commandable_object_has_command_time_array(self):
        ao = AnalogOutputObject(1)
        cta = ao.read_property(PropertyIdentifier.COMMAND_TIME_ARRAY)
        assert isinstance(cta, list)
        assert len(cta) == 16
        for item in cta:
            assert item is None

    def test_commandable_object_has_last_command_time(self):
        ao = AnalogOutputObject(1)
        lct = ao.read_property(PropertyIdentifier.LAST_COMMAND_TIME)
        assert lct is None


class TestValueSourceOnWrite:
    def test_write_with_source_updates_array(self):
        ao = AnalogOutputObject(1)
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
        )
        source = BACnetValueSource.from_object(ref)

        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            72.5,
            8,
            value_source=source,
        )

        vsa = ao.read_property(PropertyIdentifier.VALUE_SOURCE_ARRAY)
        assert vsa[7].choice == 1  # slot 7 = priority 8
        assert vsa[7].value == ref

    def test_write_updates_value_source_to_winning(self):
        ao = AnalogOutputObject(1)
        ref_high = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 10),
        )
        ref_low = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 20),
        )

        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            50.0,
            10,
            value_source=BACnetValueSource.from_object(ref_low),
        )
        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            80.0,
            5,
            value_source=BACnetValueSource.from_object(ref_high),
        )

        vs = ao.read_property(PropertyIdentifier.VALUE_SOURCE)
        assert vs.choice == 1
        assert vs.value == ref_high

    def test_relinquish_clears_source(self):
        ao = AnalogOutputObject(1)
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
        )

        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            72.5,
            8,
            value_source=BACnetValueSource.from_object(ref),
        )
        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            None,
            8,
        )

        vsa = ao.read_property(PropertyIdentifier.VALUE_SOURCE_ARRAY)
        assert vsa[7].choice == 0  # cleared

        vs = ao.read_property(PropertyIdentifier.VALUE_SOURCE)
        assert vs.choice == 0  # no winning source

    def test_relinquish_winning_changes_source(self):
        ao = AnalogOutputObject(1)
        ref_high = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 10),
        )
        ref_low = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 20),
        )

        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            50.0,
            10,
            value_source=BACnetValueSource.from_object(ref_low),
        )
        ao._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            80.0,
            5,
            value_source=BACnetValueSource.from_object(ref_high),
        )

        # Relinquish the higher priority
        ao._write_with_priority(PropertyIdentifier.PRESENT_VALUE, None, 5)

        # Now winning is priority 10
        vs = ao.read_property(PropertyIdentifier.VALUE_SOURCE)
        assert vs.choice == 1
        assert vs.value == ref_low

    def test_write_without_source_defaults_to_none(self):
        ao = AnalogOutputObject(1)
        ao._write_with_priority(PropertyIdentifier.PRESENT_VALUE, 72.5, 8)

        vsa = ao.read_property(PropertyIdentifier.VALUE_SOURCE_ARRAY)
        assert vsa[7].choice == 0  # none source by default

    def test_binary_output_value_source(self):
        bo = BinaryOutputObject(1)
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 99),
        )
        source = BACnetValueSource.from_object(ref)

        bo._write_with_priority(
            PropertyIdentifier.PRESENT_VALUE,
            1,
            8,
            value_source=source,
        )

        vs = bo.read_property(PropertyIdentifier.VALUE_SOURCE)
        assert vs.choice == 1
