"""Tests for BACnet Life Safety objects."""

from bac_py.objects.base import create_object
from bac_py.objects.life_safety import LifeSafetyPointObject, LifeSafetyZoneObject
from bac_py.types.enums import (
    LifeSafetyMode,
    LifeSafetyState,
    ObjectType,
    PropertyIdentifier,
    SilencedState,
)


class TestLifeSafetyPointObject:
    """LifeSafetyPoint object (Clause 12.15)."""

    def test_object_type(self):
        obj = LifeSafetyPointObject(1)
        assert obj.OBJECT_TYPE == ObjectType.LIFE_SAFETY_POINT

    def test_registry_creation(self):
        obj = create_object(ObjectType.LIFE_SAFETY_POINT, 1)
        assert isinstance(obj, LifeSafetyPointObject)

    def test_default_present_value(self):
        obj = LifeSafetyPointObject(1)
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == LifeSafetyState.QUIET
        assert isinstance(pv, LifeSafetyState)

    def test_default_tracking_value(self):
        obj = LifeSafetyPointObject(1)
        tv = obj.read_property(PropertyIdentifier.TRACKING_VALUE)
        assert tv == LifeSafetyState.QUIET

    def test_default_mode(self):
        obj = LifeSafetyPointObject(1)
        mode = obj.read_property(PropertyIdentifier.MODE)
        assert mode == LifeSafetyMode.ON

    def test_mode_writable(self):
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.MODE, LifeSafetyMode.TEST)
        assert obj.read_property(PropertyIdentifier.MODE) == LifeSafetyMode.TEST

    def test_default_silenced(self):
        obj = LifeSafetyPointObject(1)
        assert obj.read_property(PropertyIdentifier.SILENCED) == SilencedState.UNSILENCED

    def test_present_value_writable_when_oos(self):
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, LifeSafetyState.ALARM)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == LifeSafetyState.ALARM

    def test_enum_coercion_on_mode(self):
        """Raw int from wire should be coerced to LifeSafetyMode."""
        obj = LifeSafetyPointObject(1)
        obj.write_property(PropertyIdentifier.MODE, 2)  # raw int for TEST
        mode = obj.read_property(PropertyIdentifier.MODE)
        assert isinstance(mode, LifeSafetyMode)
        assert mode == LifeSafetyMode.TEST


class TestLifeSafetyZoneObject:
    """LifeSafetyZone object (Clause 12.16)."""

    def test_object_type(self):
        obj = LifeSafetyZoneObject(1)
        assert obj.OBJECT_TYPE == ObjectType.LIFE_SAFETY_ZONE

    def test_registry_creation(self):
        obj = create_object(ObjectType.LIFE_SAFETY_ZONE, 1)
        assert isinstance(obj, LifeSafetyZoneObject)

    def test_default_present_value(self):
        obj = LifeSafetyZoneObject(1)
        pv = obj.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert pv == LifeSafetyState.QUIET

    def test_zone_members_default(self):
        obj = LifeSafetyZoneObject(1)
        members = obj.read_property(PropertyIdentifier.ZONE_MEMBERS)
        assert members == []

    def test_mode_writable(self):
        obj = LifeSafetyZoneObject(1)
        obj.write_property(PropertyIdentifier.MODE, LifeSafetyMode.ARMED)
        assert obj.read_property(PropertyIdentifier.MODE) == LifeSafetyMode.ARMED
