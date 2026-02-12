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

    def test_default_no_priority_array(self):
        from bac_py.objects.pulse_converter import PulseConverterObject

        obj = PulseConverterObject(2, object_name="pc-2")
        # Optional property not initialized returns None
        assert obj.read_property(PropertyIdentifier.PRIORITY_ARRAY) is None

    def test_commandable_has_priority_array(self):
        from bac_py.objects.pulse_converter import PulseConverterObject

        obj = PulseConverterObject(3, object_name="pc-3", commandable=True)
        pa = obj.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert pa is not None
        assert len(pa) == 16

    def test_commandable_write_with_priority(self):
        from bac_py.objects.pulse_converter import PulseConverterObject

        obj = PulseConverterObject(4, object_name="pc-4", commandable=True)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.5, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.5
