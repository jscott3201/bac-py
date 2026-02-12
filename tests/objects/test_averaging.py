"""Tests for the BACnet Averaging object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestAveragingObject:
    def test_instantiation(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.OBJECT_TYPE == ObjectType.AVERAGING
        assert obj.read_property(PropertyIdentifier.AVERAGE_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.MINIMUM_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.MAXIMUM_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.WINDOW_INTERVAL) == 60
        assert obj.read_property(PropertyIdentifier.WINDOW_SAMPLES) == 10

    def test_required_properties_present(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.AVERAGE_VALUE in prop_list
        assert PropertyIdentifier.UNITS in prop_list
