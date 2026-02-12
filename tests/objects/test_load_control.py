"""Tests for the BACnet Load Control object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestLoadControlObject:
    def test_instantiation(self):
        from bac_py.objects.load_control import LoadControlObject
        from bac_py.types.enums import ShedState

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.OBJECT_TYPE == ObjectType.LOAD_CONTROL
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == ShedState.SHED_INACTIVE
        assert obj.read_property(PropertyIdentifier.SHED_DURATION) == 0
