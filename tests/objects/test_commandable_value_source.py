"""Tests for Value Source tracking on commandable objects (Clause 19.5)."""

from bac_py.objects.analog import AnalogOutputObject
from bac_py.objects.binary import BinaryOutputObject
from bac_py.types.constructed import BACnetDeviceObjectReference, BACnetValueSource
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


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
