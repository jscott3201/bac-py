"""Tests for EventStateMachine per ASHRAE 135-2020 Clause 13.2."""

from __future__ import annotations

import pytest

from bac_py.app.event_engine import EventStateMachine, EventTransition
from bac_py.types.enums import EventState, Reliability

NO_FAULT = Reliability.NO_FAULT_DETECTED
SENSOR_FAULT = Reliability.NO_SENSOR


class TestBasicTransitions:
    """State transitions from NORMAL and alarm states with time_delay=0."""

    # -- From NORMAL -------------------------------------------------------

    def test_normal_to_offnormal(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.NORMAL
        assert result.to_state == EventState.OFFNORMAL
        assert sm.event_state == EventState.OFFNORMAL

    def test_normal_to_high_limit(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.NORMAL
        assert result.to_state == EventState.HIGH_LIMIT
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_normal_to_low_limit(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.NORMAL
        assert result.to_state == EventState.LOW_LIMIT
        assert sm.event_state == EventState.LOW_LIMIT

    def test_normal_to_fault(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(None, SENSOR_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.NORMAL
        assert result.to_state == EventState.FAULT
        assert sm.event_state == EventState.FAULT

    def test_normal_stays_normal(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is None
        assert sm.event_state == EventState.NORMAL

    def test_normal_stays_normal_with_explicit_normal_result(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.NORMAL, NO_FAULT, 1.0)

        assert result is None
        assert sm.event_state == EventState.NORMAL

    # -- From OFFNORMAL ----------------------------------------------------

    def test_offnormal_to_normal(self) -> None:
        sm = EventStateMachine(event_state=EventState.OFFNORMAL, time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.OFFNORMAL
        assert result.to_state == EventState.NORMAL

    def test_offnormal_to_fault(self) -> None:
        sm = EventStateMachine(event_state=EventState.OFFNORMAL, time_delay=0)
        result = sm.evaluate(EventState.OFFNORMAL, SENSOR_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.OFFNORMAL
        assert result.to_state == EventState.FAULT

    # -- From HIGH_LIMIT ---------------------------------------------------

    def test_high_limit_to_normal(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.NORMAL

    def test_high_limit_to_low_limit(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.LOW_LIMIT

    def test_high_limit_to_fault(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, SENSOR_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.FAULT

    def test_high_limit_stays_high_limit(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)

        assert result is None
        assert sm.event_state == EventState.HIGH_LIMIT

    # -- From LOW_LIMIT ----------------------------------------------------

    def test_low_limit_to_normal(self) -> None:
        sm = EventStateMachine(event_state=EventState.LOW_LIMIT, time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.LOW_LIMIT
        assert result.to_state == EventState.NORMAL

    def test_low_limit_to_high_limit(self) -> None:
        sm = EventStateMachine(event_state=EventState.LOW_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.LOW_LIMIT
        assert result.to_state == EventState.HIGH_LIMIT

    def test_low_limit_to_fault(self) -> None:
        sm = EventStateMachine(event_state=EventState.LOW_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.LOW_LIMIT, SENSOR_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.LOW_LIMIT
        assert result.to_state == EventState.FAULT

    def test_low_limit_stays_low_limit(self) -> None:
        sm = EventStateMachine(event_state=EventState.LOW_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 1.0)

        assert result is None
        assert sm.event_state == EventState.LOW_LIMIT

    # -- From FAULT --------------------------------------------------------

    def test_fault_to_normal(self) -> None:
        sm = EventStateMachine(event_state=EventState.FAULT, time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.FAULT
        assert result.to_state == EventState.NORMAL

    def test_fault_to_offnormal(self) -> None:
        sm = EventStateMachine(event_state=EventState.FAULT, time_delay=0)
        result = sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.FAULT
        assert result.to_state == EventState.OFFNORMAL

    def test_fault_stays_fault_while_faulted(self) -> None:
        sm = EventStateMachine(event_state=EventState.FAULT, time_delay=0)
        result = sm.evaluate(None, SENSOR_FAULT, 1.0)

        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_fault_to_high_limit_on_clear(self) -> None:
        sm = EventStateMachine(event_state=EventState.FAULT, time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)

        assert result is not None
        assert result.from_state == EventState.FAULT
        assert result.to_state == EventState.HIGH_LIMIT


class TestTimeDelay:
    """Time-delay enforcement for transitions to alarm states."""

    def test_brief_excursion_does_not_trigger(self) -> None:
        """Condition true for less than time_delay does not fire."""
        sm = EventStateMachine(time_delay=5.0)

        # t=0: condition detected, delay starts
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 0.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

        # t=3: still less than 5s
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 3.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

        # t=4: condition clears before delay expires
        result = sm.evaluate(None, NO_FAULT, 4.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

    def test_sustained_condition_triggers(self) -> None:
        """Condition held for >= time_delay fires the transition."""
        sm = EventStateMachine(time_delay=5.0)

        # t=0: condition detected
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 0.0)
        assert result is None

        # t=3: still waiting
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 3.0)
        assert result is None

        # t=5: exactly at delay
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 5.0)
        assert result is not None
        assert result.to_state == EventState.HIGH_LIMIT
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_zero_delay_triggers_immediately(self) -> None:
        sm = EventStateMachine(time_delay=0)

        result = sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 10.0)
        assert result is not None
        assert result.to_state == EventState.OFFNORMAL

    def test_time_delay_for_alarm_to_alarm_transition(self) -> None:
        """Delay also applies to alarm-to-alarm transitions (e.g. HIGH -> LOW)."""
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=3.0)

        # t=0: LOW_LIMIT detected
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 0.0)
        assert result is None

        # t=2: not yet
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 2.0)
        assert result is None

        # t=3: fires
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 3.0)
        assert result is not None
        assert result.to_state == EventState.LOW_LIMIT

    def test_time_delay_for_alarm_to_normal(self) -> None:
        """time_delay (not time_delay_normal) used when time_delay_normal is None."""
        sm = EventStateMachine(
            event_state=EventState.OFFNORMAL,
            time_delay=4.0,
            time_delay_normal=None,
        )

        # t=0: normal condition starts
        result = sm.evaluate(None, NO_FAULT, 0.0)
        assert result is None

        # t=3: not yet
        result = sm.evaluate(None, NO_FAULT, 3.0)
        assert result is None

        # t=4: fires
        result = sm.evaluate(None, NO_FAULT, 4.0)
        assert result is not None
        assert result.to_state == EventState.NORMAL

    def test_fault_transition_ignores_time_delay(self) -> None:
        """FAULT transitions fire immediately regardless of time_delay."""
        sm = EventStateMachine(time_delay=10.0)

        result = sm.evaluate(None, SENSOR_FAULT, 0.0)
        assert result is not None
        assert result.to_state == EventState.FAULT

    def test_condition_change_resets_pending_delay(self) -> None:
        """If the alarm condition changes target, the delay restarts."""
        sm = EventStateMachine(time_delay=5.0)

        # t=0: HIGH_LIMIT detected
        sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 0.0)
        assert sm.event_state == EventState.NORMAL

        # t=3: switch to LOW_LIMIT -- should reset the delay timer
        sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 3.0)

        # t=7: 4 seconds since LOW_LIMIT, but delay is 5s -- should not fire
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 7.0)
        assert result is None

        # t=8: 5 seconds since LOW_LIMIT -- fires
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 8.0)
        assert result is not None
        assert result.to_state == EventState.LOW_LIMIT


class TestTimeDelayNormal:
    """time_delay_normal is used for returning to NORMAL, distinct from time_delay."""

    def test_uses_time_delay_normal_for_return(self) -> None:
        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            time_delay=10.0,
            time_delay_normal=3.0,
        )

        # t=0: condition clears
        result = sm.evaluate(None, NO_FAULT, 0.0)
        assert result is None

        # t=2: less than time_delay_normal
        result = sm.evaluate(None, NO_FAULT, 2.0)
        assert result is None

        # t=3: exactly at time_delay_normal -- fires
        result = sm.evaluate(None, NO_FAULT, 3.0)
        assert result is not None
        assert result.to_state == EventState.NORMAL

    def test_falls_back_to_time_delay_when_none(self) -> None:
        sm = EventStateMachine(
            event_state=EventState.OFFNORMAL,
            time_delay=5.0,
            time_delay_normal=None,
        )
        assert sm.effective_time_delay_normal == 5.0

        # t=0: condition clears
        sm.evaluate(None, NO_FAULT, 0.0)

        # t=4: not yet (falls back to time_delay=5)
        result = sm.evaluate(None, NO_FAULT, 4.0)
        assert result is None

        # t=5: fires
        result = sm.evaluate(None, NO_FAULT, 5.0)
        assert result is not None
        assert result.to_state == EventState.NORMAL

    def test_time_delay_normal_zero_triggers_immediately(self) -> None:
        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            time_delay=10.0,
            time_delay_normal=0.0,
        )

        result = sm.evaluate(None, NO_FAULT, 1.0)
        assert result is not None
        assert result.to_state == EventState.NORMAL

    def test_time_delay_normal_does_not_affect_alarm_transitions(self) -> None:
        """time_delay_normal only governs return-to-normal, not alarm transitions."""
        sm = EventStateMachine(
            time_delay=5.0,
            time_delay_normal=0.0,
        )

        # Even though time_delay_normal is 0, alarm transitions use time_delay=5
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 0.0)
        assert result is None

        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 4.0)
        assert result is None

        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 5.0)
        assert result is not None
        assert result.to_state == EventState.HIGH_LIMIT

    def test_effective_time_delay_normal_property(self) -> None:
        sm_with = EventStateMachine(time_delay=10.0, time_delay_normal=2.0)
        assert sm_with.effective_time_delay_normal == 2.0

        sm_without = EventStateMachine(time_delay=10.0, time_delay_normal=None)
        assert sm_without.effective_time_delay_normal == 10.0

    def test_fault_clear_to_normal_uses_time_delay_normal(self) -> None:
        """When clearing from FAULT to NORMAL, time_delay_normal governs the delay."""
        sm = EventStateMachine(
            event_state=EventState.FAULT,
            time_delay=10.0,
            time_delay_normal=2.0,
        )

        # t=0: fault clears, no event condition
        result = sm.evaluate(None, NO_FAULT, 0.0)
        assert result is None

        # t=1: not yet
        result = sm.evaluate(None, NO_FAULT, 1.0)
        assert result is None

        # t=2: fires
        result = sm.evaluate(None, NO_FAULT, 2.0)
        assert result is not None
        assert result.to_state == EventState.NORMAL


class TestEventEnable:
    """event_enable suppression for each transition direction."""

    def test_to_offnormal_disabled(self) -> None:
        sm = EventStateMachine(
            time_delay=0,
            event_enable=[False, True, True],
        )

        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

    def test_to_fault_disabled(self) -> None:
        sm = EventStateMachine(
            time_delay=0,
            event_enable=[True, False, True],
        )

        result = sm.evaluate(None, SENSOR_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.NORMAL

    def test_to_normal_disabled(self) -> None:
        sm = EventStateMachine(
            event_state=EventState.OFFNORMAL,
            time_delay=0,
            event_enable=[True, True, False],
        )

        result = sm.evaluate(None, NO_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.OFFNORMAL

    def test_to_offnormal_disabled_blocks_alarm_to_alarm(self) -> None:
        """Alarm-to-alarm transitions use the to-offnormal enable bit."""
        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            time_delay=0,
            event_enable=[False, True, True],
        )

        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_to_fault_disabled_from_alarm_state(self) -> None:
        sm = EventStateMachine(
            event_state=EventState.HIGH_LIMIT,
            time_delay=0,
            event_enable=[True, False, True],
        )

        result = sm.evaluate(EventState.HIGH_LIMIT, SENSOR_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.HIGH_LIMIT

    def test_to_normal_disabled_from_fault(self) -> None:
        """Clearing from FAULT to NORMAL is blocked when to-normal is disabled."""
        sm = EventStateMachine(
            event_state=EventState.FAULT,
            time_delay=0,
            event_enable=[True, True, False],
        )

        result = sm.evaluate(None, NO_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_to_offnormal_disabled_blocks_fault_to_alarm(self) -> None:
        """Clearing from FAULT to alarm state is blocked when to-offnormal is disabled."""
        sm = EventStateMachine(
            event_state=EventState.FAULT,
            time_delay=0,
            event_enable=[False, True, True],
        )

        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT

    def test_all_disabled(self) -> None:
        sm = EventStateMachine(
            time_delay=0,
            event_enable=[False, False, False],
        )

        assert sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0) is None
        assert sm.evaluate(None, SENSOR_FAULT, 2.0) is None
        assert sm.event_state == EventState.NORMAL


class TestFaultPrecedence:
    """FAULT transitions take priority over alarm transitions (Clause 13.2.5)."""

    def test_fault_overrides_high_limit(self) -> None:
        sm = EventStateMachine(time_delay=0)

        result = sm.evaluate(EventState.HIGH_LIMIT, SENSOR_FAULT, 1.0)
        assert result is not None
        assert result.to_state == EventState.FAULT
        assert sm.event_state == EventState.FAULT

    def test_fault_overrides_low_limit(self) -> None:
        sm = EventStateMachine(time_delay=0)

        result = sm.evaluate(EventState.LOW_LIMIT, SENSOR_FAULT, 1.0)
        assert result is not None
        assert result.to_state == EventState.FAULT

    def test_fault_overrides_offnormal(self) -> None:
        sm = EventStateMachine(time_delay=0)

        result = sm.evaluate(EventState.OFFNORMAL, SENSOR_FAULT, 1.0)
        assert result is not None
        assert result.to_state == EventState.FAULT

    def test_fault_from_alarm_state_overrides_alarm_change(self) -> None:
        """From HIGH_LIMIT with a fault: FAULT wins over LOW_LIMIT."""
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)

        result = sm.evaluate(EventState.LOW_LIMIT, SENSOR_FAULT, 1.0)
        assert result is not None
        assert result.to_state == EventState.FAULT
        assert result.from_state == EventState.HIGH_LIMIT

    def test_fault_does_not_re_trigger_from_fault(self) -> None:
        """Already in FAULT, a continued fault does not produce a new transition."""
        sm = EventStateMachine(event_state=EventState.FAULT, time_delay=0)

        result = sm.evaluate(EventState.HIGH_LIMIT, SENSOR_FAULT, 1.0)
        assert result is None
        assert sm.event_state == EventState.FAULT


class TestAckedTransitions:
    """acked_transitions bookkeeping on each transition type."""

    def test_to_offnormal_clears_acked_bit_0(self) -> None:
        sm = EventStateMachine(time_delay=0)
        sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 1.0)

        assert sm.acked_transitions[0] is False
        assert sm.acked_transitions[1] is True
        assert sm.acked_transitions[2] is True

    def test_to_high_limit_clears_acked_bit_0(self) -> None:
        sm = EventStateMachine(time_delay=0)
        sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)

        assert sm.acked_transitions[0] is False
        assert sm.acked_transitions[1] is True
        assert sm.acked_transitions[2] is True

    def test_to_fault_clears_acked_bit_1(self) -> None:
        sm = EventStateMachine(time_delay=0)
        sm.evaluate(None, SENSOR_FAULT, 1.0)

        assert sm.acked_transitions[0] is True
        assert sm.acked_transitions[1] is False
        assert sm.acked_transitions[2] is True

    def test_to_normal_clears_acked_bit_2(self) -> None:
        sm = EventStateMachine(event_state=EventState.OFFNORMAL, time_delay=0)
        sm.evaluate(None, NO_FAULT, 1.0)

        assert sm.acked_transitions[0] is True
        assert sm.acked_transitions[1] is True
        assert sm.acked_transitions[2] is False

    def test_multiple_transitions_accumulate(self) -> None:
        """Successive transitions mark multiple bits as unacknowledged."""
        sm = EventStateMachine(time_delay=0)

        # NORMAL -> HIGH_LIMIT (bit 0 unacked)
        sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)
        assert sm.acked_transitions == [False, True, True]

        # HIGH_LIMIT -> NORMAL (bit 2 unacked)
        sm.evaluate(None, NO_FAULT, 2.0)
        assert sm.acked_transitions == [False, True, False]

        # NORMAL -> FAULT (bit 1 unacked)
        sm.evaluate(None, SENSOR_FAULT, 3.0)
        assert sm.acked_transitions == [False, False, False]

    def test_acked_transitions_independent_of_enable(self) -> None:
        """Verify acked_transitions are NOT set when transitions are disabled."""
        sm = EventStateMachine(
            time_delay=0,
            event_enable=[False, True, True],
        )

        sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 1.0)
        # Transition suppressed -- acked_transitions should remain all True
        assert sm.acked_transitions == [True, True, True]


class TestEventTransitionResult:
    """Verify fields of the returned EventTransition dataclass."""

    def test_from_state_and_to_state(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 42.0)

        assert isinstance(result, EventTransition)
        assert result.from_state == EventState.NORMAL
        assert result.to_state == EventState.HIGH_LIMIT

    def test_timestamp_matches_current_time(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 99.5)

        assert result is not None
        assert result.timestamp == 99.5

    def test_timestamp_with_delayed_transition(self) -> None:
        """Timestamp reflects the evaluation time, not the original detection time."""
        sm = EventStateMachine(time_delay=5.0)

        sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 10.0)
        result = sm.evaluate(EventState.HIGH_LIMIT, NO_FAULT, 15.0)

        assert result is not None
        assert result.timestamp == 15.0

    def test_frozen_dataclass(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(EventState.OFFNORMAL, NO_FAULT, 1.0)

        assert result is not None
        with pytest.raises(AttributeError):
            result.from_state = EventState.NORMAL  # type: ignore[misc]

    def test_none_when_no_transition(self) -> None:
        sm = EventStateMachine(time_delay=0)
        result = sm.evaluate(None, NO_FAULT, 1.0)

        assert result is None

    def test_fault_transition_result_fields(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(None, SENSOR_FAULT, 7.0)

        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.FAULT
        assert result.timestamp == 7.0

    def test_alarm_to_alarm_transition_result(self) -> None:
        sm = EventStateMachine(event_state=EventState.HIGH_LIMIT, time_delay=0)
        result = sm.evaluate(EventState.LOW_LIMIT, NO_FAULT, 3.0)

        assert result is not None
        assert result.from_state == EventState.HIGH_LIMIT
        assert result.to_state == EventState.LOW_LIMIT
        assert result.timestamp == 3.0
