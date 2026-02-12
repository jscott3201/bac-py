"""Tests for the BACnet Timer object."""

from __future__ import annotations

from bac_py.types.enums import ObjectType, PropertyIdentifier


class TestTimerObject:
    def test_instantiation(self):
        from bac_py.objects.timer import TimerObject
        from bac_py.types.enums import EventType, TimerState, TimerTransition

        obj = TimerObject(1, object_name="timer-1")
        assert obj.OBJECT_TYPE == ObjectType.TIMER
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0
        assert obj.read_property(PropertyIdentifier.TIMER_STATE) == TimerState.IDLE
        assert obj.read_property(PropertyIdentifier.TIMER_RUNNING) is False
        assert obj.read_property(PropertyIdentifier.LAST_STATE_CHANGE) == TimerTransition.NONE
        assert obj.INTRINSIC_EVENT_ALGORITHM == EventType.CHANGE_OF_TIMER
