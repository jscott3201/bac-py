"""Tests for the BACnet transportation objects (Elevator Group, Lift, Escalator)."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestElevatorGroupObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import ElevatorGroupObject
        from bac_py.types.enums import LiftGroupMode

        obj = ElevatorGroupObject(1, object_name="eg-1")
        assert obj.OBJECT_TYPE == ObjectType.ELEVATOR_GROUP
        assert obj.read_property(PropertyIdentifier.GROUP_MODE) == LiftGroupMode.UNKNOWN


class TestLiftObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import LiftObject
        from bac_py.types.enums import LiftCarDirection

        obj = LiftObject(1, object_name="lift-1")
        assert obj.OBJECT_TYPE == ObjectType.LIFT
        assert obj.read_property(PropertyIdentifier.CAR_POSITION) == 0
        assert (
            obj.read_property(PropertyIdentifier.CAR_ASSIGNED_DIRECTION)
            == LiftCarDirection.UNKNOWN
        )


class TestEscalatorObject:
    def test_instantiation(self):
        from bac_py.objects.transportation import EscalatorObject
        from bac_py.types.enums import EscalatorMode

        obj = EscalatorObject(1, object_name="esc-1")
        assert obj.OBJECT_TYPE == ObjectType.ESCALATOR
        assert obj.read_property(PropertyIdentifier.ESCALATOR_MODE) == EscalatorMode.UNKNOWN
