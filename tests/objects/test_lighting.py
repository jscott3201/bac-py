"""Tests for the BACnet Lighting Output and Binary Lighting Output objects."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestLightingOutputObject:
    def test_instantiation(self):
        from bac_py.objects.lighting import LightingOutputObject
        from bac_py.types.enums import LightingInProgress

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.OBJECT_TYPE == ObjectType.LIGHTING_OUTPUT
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.TRACKING_VALUE) == 0.0
        assert obj.read_property(PropertyIdentifier.IN_PROGRESS) == LightingInProgress.IDLE
        assert obj.read_property(PropertyIdentifier.DEFAULT_FADE_TIME) == 0

    def test_commandable(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 75.0, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 75.0


class TestBinaryLightingOutputObject:
    def test_instantiation(self):
        from bac_py.objects.lighting import BinaryLightingOutputObject
        from bac_py.types.enums import BinaryPV

        obj = BinaryLightingOutputObject(1, object_name="blo-1")
        assert obj.OBJECT_TYPE == ObjectType.BINARY_LIGHTING_OUTPUT
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_commandable(self):
        from bac_py.objects.lighting import BinaryLightingOutputObject
        from bac_py.types.enums import BinaryPV

        obj = BinaryLightingOutputObject(1, object_name="blo-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE
