"""Tests for the BACnet Pulse Converter object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestPulseConverterObject:
    def test_instantiation(self):
        from bac_py.objects.pulse_converter import PulseConverterObject

        obj = PulseConverterObject(1, object_name="pc-1")
        assert obj.OBJECT_TYPE == ObjectType.PULSE_CONVERTER
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.SCALE_FACTOR) == 1.0
        assert obj.read_property(PropertyIdentifier.COUNT) == 0
