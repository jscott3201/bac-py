"""Tests for the 18 event algorithm evaluator functions in event_engine.py.

Each evaluator is a pure function per ASHRAE 135-2020 Clause 13.3.  Tests are
grouped by evaluator into classes covering normal conditions, alarm conditions,
boundary/deadband behaviour, and empty alarm-value lists where applicable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bac_py.app.event_engine import (
    evaluate_access_event,
    evaluate_buffer_ready,
    evaluate_change_of_bitstring,
    evaluate_change_of_characterstring,
    evaluate_change_of_life_safety,
    evaluate_change_of_reliability,
    evaluate_change_of_state,
    evaluate_change_of_status_flags,
    evaluate_change_of_timer,
    evaluate_change_of_value,
    evaluate_command_failure,
    evaluate_double_out_of_range,
    evaluate_extended,
    evaluate_floating_limit,
    evaluate_out_of_range,
    evaluate_signed_out_of_range,
    evaluate_unsigned_out_of_range,
    evaluate_unsigned_range,
)
from bac_py.types.enums import EventState, LifeSafetyState, Reliability, TimerState

if TYPE_CHECKING:
    from typing import ClassVar


# ---------------------------------------------------------------------------
# Group A -- Threshold-based evaluators
# ---------------------------------------------------------------------------


class TestEvaluateOutOfRange:
    """Tests for evaluate_out_of_range (Clause 13.3.6)."""

    HIGH: ClassVar[float] = 100.0
    LOW: ClassVar[float] = 0.0
    DEADBAND: ClassVar[float] = 5.0

    # -- Normal conditions --

    def test_value_within_range_returns_none(self):
        result = evaluate_out_of_range(50.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is None

    def test_value_exactly_at_high_limit_returns_none(self):
        result = evaluate_out_of_range(100.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is None

    def test_value_exactly_at_low_limit_returns_none(self):
        result = evaluate_out_of_range(0.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is None

    # -- Alarm conditions --

    def test_value_above_high_limit_returns_high_limit(self):
        result = evaluate_out_of_range(100.1, self.HIGH, self.LOW, self.DEADBAND)
        assert result is EventState.HIGH_LIMIT

    def test_value_below_low_limit_returns_low_limit(self):
        result = evaluate_out_of_range(-0.1, self.HIGH, self.LOW, self.DEADBAND)
        assert result is EventState.LOW_LIMIT

    def test_value_far_above_high_limit(self):
        result = evaluate_out_of_range(500.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is EventState.HIGH_LIMIT

    def test_value_far_below_low_limit(self):
        result = evaluate_out_of_range(-500.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is EventState.LOW_LIMIT

    # -- Deadband hysteresis --

    def test_deadband_keeps_high_limit_when_within_deadband(self):
        # Value dropped below high_limit but still above (high_limit - deadband)
        result = evaluate_out_of_range(
            96.0,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_exactly_at_high_limit_minus_deadband_stays_alarmed(self):
        # value == high_limit - deadband => still within deadband (> not >=)
        result = evaluate_out_of_range(
            95.0,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_clears_high_limit_when_below_deadband(self):
        # Value dropped below (high_limit - deadband)
        result = evaluate_out_of_range(
            94.9,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is None

    def test_deadband_keeps_low_limit_when_within_deadband(self):
        result = evaluate_out_of_range(
            4.0,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.LOW_LIMIT,
        )
        assert result is EventState.LOW_LIMIT

    def test_deadband_exactly_at_low_limit_plus_deadband_stays_alarmed(self):
        result = evaluate_out_of_range(
            5.0,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.LOW_LIMIT,
        )
        assert result is EventState.LOW_LIMIT

    def test_deadband_clears_low_limit_when_above_deadband(self):
        result = evaluate_out_of_range(
            5.1,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.LOW_LIMIT,
        )
        assert result is None

    def test_deadband_zero_no_hysteresis(self):
        # With zero deadband, dropping below high_limit clears alarm
        result = evaluate_out_of_range(
            99.9,
            self.HIGH,
            self.LOW,
            0.0,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is None

    def test_normal_state_no_deadband_effect(self):
        # When current_state is NORMAL, deadband logic should not apply
        result = evaluate_out_of_range(
            96.0,
            self.HIGH,
            self.LOW,
            self.DEADBAND,
            current_state=EventState.NORMAL,
        )
        assert result is None

    # -- Default current_state --

    def test_default_current_state_is_normal(self):
        result = evaluate_out_of_range(96.0, self.HIGH, self.LOW, self.DEADBAND)
        assert result is None


class TestEvaluateDoubleOutOfRange:
    """Tests for evaluate_double_out_of_range (Clause 13.3.14)."""

    def test_normal_returns_none(self):
        result = evaluate_double_out_of_range(50.0, 100.0, 0.0, 5.0)
        assert result is None

    def test_above_high_limit(self):
        result = evaluate_double_out_of_range(100.1, 100.0, 0.0, 5.0)
        assert result is EventState.HIGH_LIMIT

    def test_below_low_limit(self):
        result = evaluate_double_out_of_range(-0.1, 100.0, 0.0, 5.0)
        assert result is EventState.LOW_LIMIT

    def test_deadband_hysteresis_high(self):
        result = evaluate_double_out_of_range(
            96.0, 100.0, 0.0, 5.0, current_state=EventState.HIGH_LIMIT
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_clears_high(self):
        result = evaluate_double_out_of_range(
            94.9, 100.0, 0.0, 5.0, current_state=EventState.HIGH_LIMIT
        )
        assert result is None

    def test_deadband_hysteresis_low(self):
        result = evaluate_double_out_of_range(
            4.0, 100.0, 0.0, 5.0, current_state=EventState.LOW_LIMIT
        )
        assert result is EventState.LOW_LIMIT

    def test_deadband_clears_low(self):
        result = evaluate_double_out_of_range(
            5.1, 100.0, 0.0, 5.0, current_state=EventState.LOW_LIMIT
        )
        assert result is None


class TestEvaluateSignedOutOfRange:
    """Tests for evaluate_signed_out_of_range (Clause 13.3.15)."""

    def test_normal_returns_none(self):
        result = evaluate_signed_out_of_range(0, 100, -100, 5)
        assert result is None

    def test_above_high_limit(self):
        result = evaluate_signed_out_of_range(101, 100, -100, 5)
        assert result is EventState.HIGH_LIMIT

    def test_below_low_limit(self):
        result = evaluate_signed_out_of_range(-101, 100, -100, 5)
        assert result is EventState.LOW_LIMIT

    def test_negative_range_normal(self):
        result = evaluate_signed_out_of_range(-50, -10, -100, 5)
        assert result is None

    def test_negative_range_above_high(self):
        result = evaluate_signed_out_of_range(-9, -10, -100, 5)
        assert result is EventState.HIGH_LIMIT

    def test_deadband_hysteresis_high(self):
        result = evaluate_signed_out_of_range(
            96, 100, -100, 5, current_state=EventState.HIGH_LIMIT
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_clears_high(self):
        result = evaluate_signed_out_of_range(
            94, 100, -100, 5, current_state=EventState.HIGH_LIMIT
        )
        assert result is None


class TestEvaluateUnsignedOutOfRange:
    """Tests for evaluate_unsigned_out_of_range (Clause 13.3.16)."""

    def test_normal_returns_none(self):
        result = evaluate_unsigned_out_of_range(50, 100, 10, 5)
        assert result is None

    def test_above_high_limit(self):
        result = evaluate_unsigned_out_of_range(101, 100, 10, 5)
        assert result is EventState.HIGH_LIMIT

    def test_below_low_limit(self):
        result = evaluate_unsigned_out_of_range(9, 100, 10, 5)
        assert result is EventState.LOW_LIMIT

    def test_deadband_hysteresis_high(self):
        result = evaluate_unsigned_out_of_range(
            96, 100, 10, 5, current_state=EventState.HIGH_LIMIT
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_clears_high(self):
        result = evaluate_unsigned_out_of_range(
            94, 100, 10, 5, current_state=EventState.HIGH_LIMIT
        )
        assert result is None

    def test_deadband_hysteresis_low(self):
        result = evaluate_unsigned_out_of_range(14, 100, 10, 5, current_state=EventState.LOW_LIMIT)
        assert result is EventState.LOW_LIMIT

    def test_deadband_clears_low(self):
        result = evaluate_unsigned_out_of_range(16, 100, 10, 5, current_state=EventState.LOW_LIMIT)
        assert result is None


class TestEvaluateUnsignedRange:
    """Tests for evaluate_unsigned_range (Clause 13.3.11) -- no deadband."""

    def test_value_within_range_returns_none(self):
        result = evaluate_unsigned_range(50, 100, 10)
        assert result is None

    def test_value_exactly_at_high_limit_returns_none(self):
        result = evaluate_unsigned_range(100, 100, 10)
        assert result is None

    def test_value_exactly_at_low_limit_returns_none(self):
        result = evaluate_unsigned_range(10, 100, 10)
        assert result is None

    def test_above_high_limit(self):
        result = evaluate_unsigned_range(101, 100, 10)
        assert result is EventState.HIGH_LIMIT

    def test_below_low_limit(self):
        result = evaluate_unsigned_range(9, 100, 10)
        assert result is EventState.LOW_LIMIT

    def test_far_above_high_limit(self):
        result = evaluate_unsigned_range(9999, 100, 10)
        assert result is EventState.HIGH_LIMIT

    def test_zero_below_low_limit(self):
        result = evaluate_unsigned_range(0, 100, 10)
        assert result is EventState.LOW_LIMIT

    def test_equal_limits_within(self):
        # high == low; value == both limits is normal
        result = evaluate_unsigned_range(50, 50, 50)
        assert result is None


class TestEvaluateFloatingLimit:
    """Tests for evaluate_floating_limit (Clause 13.3.5)."""

    SETPOINT: ClassVar[float] = 72.0
    HIGH_DIFF: ClassVar[float] = 5.0
    LOW_DIFF: ClassVar[float] = 5.0
    DEADBAND: ClassVar[float] = 2.0

    # Effective limits: high = 77.0, low = 67.0

    def test_normal_returns_none(self):
        result = evaluate_floating_limit(
            72.0, self.SETPOINT, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND
        )
        assert result is None

    def test_exactly_at_effective_high_limit_returns_none(self):
        result = evaluate_floating_limit(
            77.0, self.SETPOINT, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND
        )
        assert result is None

    def test_exactly_at_effective_low_limit_returns_none(self):
        result = evaluate_floating_limit(
            67.0, self.SETPOINT, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND
        )
        assert result is None

    def test_above_effective_high_limit(self):
        result = evaluate_floating_limit(
            77.1, self.SETPOINT, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND
        )
        assert result is EventState.HIGH_LIMIT

    def test_below_effective_low_limit(self):
        result = evaluate_floating_limit(
            66.9, self.SETPOINT, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND
        )
        assert result is EventState.LOW_LIMIT

    def test_deadband_keeps_high_alarm(self):
        # effective high = 77.0, deadband = 2.0, so must drop below 75.0
        result = evaluate_floating_limit(
            76.0,
            self.SETPOINT,
            self.HIGH_DIFF,
            self.LOW_DIFF,
            self.DEADBAND,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is EventState.HIGH_LIMIT

    def test_deadband_clears_high_alarm(self):
        result = evaluate_floating_limit(
            74.9,
            self.SETPOINT,
            self.HIGH_DIFF,
            self.LOW_DIFF,
            self.DEADBAND,
            current_state=EventState.HIGH_LIMIT,
        )
        assert result is None

    def test_deadband_keeps_low_alarm(self):
        # effective low = 67.0, deadband = 2.0, so must rise above 69.0
        result = evaluate_floating_limit(
            68.0,
            self.SETPOINT,
            self.HIGH_DIFF,
            self.LOW_DIFF,
            self.DEADBAND,
            current_state=EventState.LOW_LIMIT,
        )
        assert result is EventState.LOW_LIMIT

    def test_deadband_clears_low_alarm(self):
        result = evaluate_floating_limit(
            69.1,
            self.SETPOINT,
            self.HIGH_DIFF,
            self.LOW_DIFF,
            self.DEADBAND,
            current_state=EventState.LOW_LIMIT,
        )
        assert result is None

    def test_setpoint_shift_moves_limits(self):
        # Setpoint 80.0 => effective high = 85.0, low = 75.0
        result = evaluate_floating_limit(78.0, 80.0, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND)
        assert result is None

        result = evaluate_floating_limit(86.0, 80.0, self.HIGH_DIFF, self.LOW_DIFF, self.DEADBAND)
        assert result is EventState.HIGH_LIMIT

    def test_asymmetric_diff_limits(self):
        # high_diff=10, low_diff=3 => effective high=82, low=69
        result = evaluate_floating_limit(81.0, 72.0, 10.0, 3.0, 2.0)
        assert result is None

        result = evaluate_floating_limit(83.0, 72.0, 10.0, 3.0, 2.0)
        assert result is EventState.HIGH_LIMIT

        result = evaluate_floating_limit(68.0, 72.0, 10.0, 3.0, 2.0)
        assert result is EventState.LOW_LIMIT


# ---------------------------------------------------------------------------
# Group B -- Set membership evaluators
# ---------------------------------------------------------------------------


class TestEvaluateChangeOfState:
    """Tests for evaluate_change_of_state (Clause 13.3.2)."""

    ALARM_VALUES: ClassVar[tuple[int, ...]] = (1, 3, 5)

    def test_value_not_in_alarm_values_returns_none(self):
        result = evaluate_change_of_state(0, self.ALARM_VALUES)
        assert result is None

    def test_value_in_alarm_values_returns_offnormal(self):
        result = evaluate_change_of_state(1, self.ALARM_VALUES)
        assert result is EventState.OFFNORMAL

    def test_all_alarm_values_detected(self):
        for val in self.ALARM_VALUES:
            result = evaluate_change_of_state(val, self.ALARM_VALUES)
            assert result is EventState.OFFNORMAL

    def test_empty_alarm_values_never_alarms(self):
        result = evaluate_change_of_state(1, ())
        assert result is None

    def test_value_just_outside_alarm_values(self):
        result = evaluate_change_of_state(2, self.ALARM_VALUES)
        assert result is None

    def test_large_value(self):
        result = evaluate_change_of_state(999, (999,))
        assert result is EventState.OFFNORMAL

    def test_single_alarm_value(self):
        result = evaluate_change_of_state(42, (42,))
        assert result is EventState.OFFNORMAL


class TestEvaluateChangeOfBitstring:
    """Tests for evaluate_change_of_bitstring (Clause 13.3.1)."""

    def test_no_match_returns_none(self):
        value = (1, 0, 1, 0)
        bitmask = (1, 1, 0, 0)
        alarm_values = ((0, 0),)
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is None

    def test_masked_value_matches_alarm_returns_offnormal(self):
        value = (1, 0, 1, 0)
        bitmask = (1, 1, 0, 0)
        alarm_values = ((1, 0, 0, 0),)  # masked = (1, 0, 0, 0)
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_mask_zeroes_all_bits(self):
        value = (1, 1, 1, 1)
        bitmask = (0, 0, 0, 0)
        alarm_values = ((0, 0, 0, 0),)
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_empty_alarm_values_never_alarms(self):
        value = (1, 1)
        bitmask = (1, 1)
        alarm_values: tuple[tuple[int, ...], ...] = ()
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is None

    def test_multiple_alarm_values_first_match(self):
        value = (0, 1)
        bitmask = (1, 1)
        alarm_values = ((0, 1), (1, 0))
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_multiple_alarm_values_second_match(self):
        value = (1, 0)
        bitmask = (1, 1)
        alarm_values = ((0, 1), (1, 0))
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_multiple_alarm_values_no_match(self):
        value = (1, 1)
        bitmask = (1, 1)
        alarm_values = ((0, 1), (1, 0))
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is None

    def test_partial_mask_ignores_unmasked_bits(self):
        # value = (1, 1, 0), bitmask = (1, 0, 0) => masked = (1, 0, 0)
        value = (1, 1, 0)
        bitmask = (1, 0, 0)
        alarm_values = ((1, 0, 0),)
        result = evaluate_change_of_bitstring(value, bitmask, alarm_values)
        assert result is EventState.OFFNORMAL


class TestEvaluateChangeOfLifeSafety:
    """Tests for evaluate_change_of_life_safety (Clause 13.3.8)."""

    ALARM_VALUES: ClassVar[tuple[int, ...]] = (
        int(LifeSafetyState.PRE_ALARM),
        int(LifeSafetyState.TAMPER),
    )
    LIFE_SAFETY_ALARM_VALUES: ClassVar[tuple[int, ...]] = (
        int(LifeSafetyState.ALARM),
        int(LifeSafetyState.HOLDUP),
    )

    def test_quiet_state_returns_none(self):
        result = evaluate_change_of_life_safety(
            LifeSafetyState.QUIET,
            0,
            self.ALARM_VALUES,
            self.LIFE_SAFETY_ALARM_VALUES,
        )
        assert result is None

    def test_alarm_value_returns_offnormal(self):
        result = evaluate_change_of_life_safety(
            LifeSafetyState.PRE_ALARM,
            0,
            self.ALARM_VALUES,
            self.LIFE_SAFETY_ALARM_VALUES,
        )
        assert result is EventState.OFFNORMAL

    def test_life_safety_alarm_value_returns_life_safety_alarm(self):
        result = evaluate_change_of_life_safety(
            LifeSafetyState.ALARM, 0, self.ALARM_VALUES, self.LIFE_SAFETY_ALARM_VALUES
        )
        assert result is EventState.LIFE_SAFETY_ALARM

    def test_life_safety_alarm_takes_priority_over_offnormal(self):
        # If a state appears in both lists, LIFE_SAFETY_ALARM wins
        shared_value = int(LifeSafetyState.ALARM)
        both_alarm = (shared_value,)
        both_life_safety = (shared_value,)
        result = evaluate_change_of_life_safety(
            LifeSafetyState.ALARM, 0, both_alarm, both_life_safety
        )
        assert result is EventState.LIFE_SAFETY_ALARM

    def test_empty_alarm_values_never_offnormal(self):
        result = evaluate_change_of_life_safety(
            LifeSafetyState.PRE_ALARM, 0, (), self.LIFE_SAFETY_ALARM_VALUES
        )
        assert result is None

    def test_empty_life_safety_alarm_values_never_life_safety_alarm(self):
        result = evaluate_change_of_life_safety(LifeSafetyState.ALARM, 0, self.ALARM_VALUES, ())
        # ALARM is not in alarm_values, so returns None
        assert result is None

    def test_both_empty_never_alarms(self):
        result = evaluate_change_of_life_safety(LifeSafetyState.ALARM, 0, (), ())
        assert result is None

    def test_mode_parameter_accepted(self):
        # Mode is accepted but not used for filtering in the evaluator itself
        result = evaluate_change_of_life_safety(
            LifeSafetyState.TAMPER, 5, self.ALARM_VALUES, self.LIFE_SAFETY_ALARM_VALUES
        )
        assert result is EventState.OFFNORMAL

    def test_holdup_returns_life_safety_alarm(self):
        result = evaluate_change_of_life_safety(
            LifeSafetyState.HOLDUP, 0, self.ALARM_VALUES, self.LIFE_SAFETY_ALARM_VALUES
        )
        assert result is EventState.LIFE_SAFETY_ALARM


class TestEvaluateChangeOfCharacterstring:
    """Tests for evaluate_change_of_characterstring (Clause 13.3.17)."""

    ALARM_VALUES: ClassVar[tuple[str, ...]] = ("FAULT", "ERROR", "CRITICAL")

    def test_normal_string_returns_none(self):
        result = evaluate_change_of_characterstring("OK", self.ALARM_VALUES)
        assert result is None

    def test_alarm_string_returns_offnormal(self):
        result = evaluate_change_of_characterstring("FAULT", self.ALARM_VALUES)
        assert result is EventState.OFFNORMAL

    def test_all_alarm_values_detected(self):
        for val in self.ALARM_VALUES:
            assert (
                evaluate_change_of_characterstring(val, self.ALARM_VALUES) is EventState.OFFNORMAL
            )

    def test_empty_alarm_values_never_alarms(self):
        result = evaluate_change_of_characterstring("FAULT", ())
        assert result is None

    def test_case_sensitive_no_match(self):
        result = evaluate_change_of_characterstring("fault", self.ALARM_VALUES)
        assert result is None

    def test_empty_string_can_be_alarm(self):
        result = evaluate_change_of_characterstring("", ("",))
        assert result is EventState.OFFNORMAL

    def test_empty_string_not_in_alarm_values(self):
        result = evaluate_change_of_characterstring("", self.ALARM_VALUES)
        assert result is None


class TestEvaluateAccessEvent:
    """Tests for evaluate_access_event (Clause 13.3.13)."""

    ACCESS_LIST: ClassVar[tuple[int, ...]] = (1, 5, 10)

    def test_event_not_in_list_returns_none(self):
        result = evaluate_access_event(0, self.ACCESS_LIST)
        assert result is None

    def test_event_in_list_returns_offnormal(self):
        result = evaluate_access_event(1, self.ACCESS_LIST)
        assert result is EventState.OFFNORMAL

    def test_all_events_detected(self):
        for val in self.ACCESS_LIST:
            assert evaluate_access_event(val, self.ACCESS_LIST) is EventState.OFFNORMAL

    def test_empty_list_never_alarms(self):
        result = evaluate_access_event(1, ())
        assert result is None

    def test_value_not_in_list(self):
        result = evaluate_access_event(99, self.ACCESS_LIST)
        assert result is None


# ---------------------------------------------------------------------------
# Group C -- Change detection evaluators
# ---------------------------------------------------------------------------


class TestEvaluateChangeOfValue:
    """Tests for evaluate_change_of_value (Clause 13.3.3)."""

    def test_no_change_returns_none(self):
        result = evaluate_change_of_value(10.0, 10.0, 5.0)
        assert result is None

    def test_change_below_increment_returns_none(self):
        result = evaluate_change_of_value(14.9, 10.0, 5.0)
        assert result is None

    def test_change_exactly_at_increment_returns_offnormal(self):
        result = evaluate_change_of_value(15.0, 10.0, 5.0)
        assert result is EventState.OFFNORMAL

    def test_change_above_increment_returns_offnormal(self):
        result = evaluate_change_of_value(20.0, 10.0, 5.0)
        assert result is EventState.OFFNORMAL

    def test_negative_change_exceeds_increment(self):
        result = evaluate_change_of_value(5.0, 10.0, 5.0)
        assert result is EventState.OFFNORMAL

    def test_negative_change_below_increment(self):
        result = evaluate_change_of_value(5.1, 10.0, 5.0)
        assert result is None

    def test_zero_increment_any_change_triggers(self):
        result = evaluate_change_of_value(10.001, 10.0, 0.0)
        assert result is EventState.OFFNORMAL

    def test_zero_increment_no_change_triggers(self):
        # abs(10.0 - 10.0) == 0.0 >= 0.0 is True
        result = evaluate_change_of_value(10.0, 10.0, 0.0)
        assert result is EventState.OFFNORMAL

    def test_large_increment_suppresses_alarm(self):
        result = evaluate_change_of_value(100.0, 0.0, 200.0)
        assert result is None


class TestEvaluateChangeOfStatusFlags:
    """Tests for evaluate_change_of_status_flags (Clause 13.3.18)."""

    def test_no_change_returns_none(self):
        current = (False, False, False, False)
        previous = (False, False, False, False)
        selected = (True, True, True, True)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is None

    def test_selected_flag_changed_returns_offnormal(self):
        current = (True, False, False, False)
        previous = (False, False, False, False)
        selected = (True, True, True, True)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is EventState.OFFNORMAL

    def test_unselected_flag_changed_returns_none(self):
        current = (True, False, False, False)
        previous = (False, False, False, False)
        selected = (False, True, True, True)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is None

    def test_multiple_flags_changed_one_selected(self):
        current = (True, True, False, False)
        previous = (False, False, False, False)
        selected = (False, True, False, False)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is EventState.OFFNORMAL

    def test_all_flags_changed_none_selected(self):
        current = (True, True, True, True)
        previous = (False, False, False, False)
        selected = (False, False, False, False)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is None

    def test_flag_changed_back_is_still_change(self):
        # Flag went True -> False, this is a change
        current = (False, False, False, False)
        previous = (True, False, False, False)
        selected = (True, True, True, True)
        result = evaluate_change_of_status_flags(current, previous, selected)
        assert result is EventState.OFFNORMAL

    def test_empty_flags_no_alarm(self):
        result = evaluate_change_of_status_flags((), (), ())
        assert result is None


class TestEvaluateChangeOfReliability:
    """Tests for evaluate_change_of_reliability (Clause 13.3.19)."""

    def test_no_fault_returns_none(self):
        result = evaluate_change_of_reliability(Reliability.NO_FAULT_DETECTED)
        assert result is None

    def test_fault_returns_offnormal(self):
        result = evaluate_change_of_reliability(Reliability.OVER_RANGE)
        assert result is EventState.OFFNORMAL

    def test_various_faults_all_return_offnormal(self):
        faults = [
            Reliability.NO_SENSOR,
            Reliability.UNDER_RANGE,
            Reliability.OPEN_LOOP,
            Reliability.SHORTED_LOOP,
            Reliability.NO_OUTPUT,
            Reliability.UNRELIABLE_OTHER,
            Reliability.PROCESS_ERROR,
            Reliability.MULTI_STATE_FAULT,
            Reliability.CONFIGURATION_ERROR,
            Reliability.COMMUNICATION_FAILURE,
        ]
        for fault in faults:
            assert evaluate_change_of_reliability(fault) is EventState.OFFNORMAL


class TestEvaluateCommandFailure:
    """Tests for evaluate_command_failure (Clause 13.3.4)."""

    def test_matching_values_returns_none(self):
        result = evaluate_command_failure(42, 42)
        assert result is None

    def test_mismatched_values_returns_offnormal(self):
        result = evaluate_command_failure(42, 43)
        assert result is EventState.OFFNORMAL

    def test_string_comparison_match(self):
        result = evaluate_command_failure("on", "on")
        assert result is None

    def test_string_comparison_mismatch(self):
        result = evaluate_command_failure("on", "off")
        assert result is EventState.OFFNORMAL

    def test_none_values_match(self):
        result = evaluate_command_failure(None, None)
        assert result is None

    def test_none_vs_value_mismatch(self):
        result = evaluate_command_failure(None, 1)
        assert result is EventState.OFFNORMAL

    def test_float_comparison_match(self):
        result = evaluate_command_failure(3.14, 3.14)
        assert result is None

    def test_float_comparison_mismatch(self):
        result = evaluate_command_failure(3.14, 3.15)
        assert result is EventState.OFFNORMAL


# ---------------------------------------------------------------------------
# Group D -- Specialized evaluators
# ---------------------------------------------------------------------------


class TestEvaluateBufferReady:
    """Tests for evaluate_buffer_ready (Clause 13.3.10)."""

    def test_below_threshold_returns_none(self):
        result = evaluate_buffer_ready(current_count=5, previous_count=3, notification_threshold=5)
        assert result is None

    def test_exactly_at_threshold_returns_offnormal(self):
        result = evaluate_buffer_ready(current_count=8, previous_count=3, notification_threshold=5)
        assert result is EventState.OFFNORMAL

    def test_above_threshold_returns_offnormal(self):
        result = evaluate_buffer_ready(
            current_count=20, previous_count=3, notification_threshold=5
        )
        assert result is EventState.OFFNORMAL

    def test_no_new_records_returns_none(self):
        result = evaluate_buffer_ready(
            current_count=10, previous_count=10, notification_threshold=1
        )
        assert result is None

    def test_single_record_threshold_one(self):
        result = evaluate_buffer_ready(
            current_count=11, previous_count=10, notification_threshold=1
        )
        assert result is EventState.OFFNORMAL

    def test_threshold_zero_always_alarms_on_any_records(self):
        # 0 new records >= 0 threshold is True
        result = evaluate_buffer_ready(
            current_count=10, previous_count=10, notification_threshold=0
        )
        assert result is EventState.OFFNORMAL

    def test_large_gap(self):
        result = evaluate_buffer_ready(
            current_count=1000, previous_count=0, notification_threshold=100
        )
        assert result is EventState.OFFNORMAL


class TestEvaluateExtended:
    """Tests for evaluate_extended (Clause 13.3.9)."""

    def test_no_callback_returns_none(self):
        result = evaluate_extended("some_value", {"threshold": 10})
        assert result is None

    def test_callback_returning_none(self):
        result = evaluate_extended(
            "some_value", {"threshold": 10}, vendor_callback=lambda v, p: None
        )
        assert result is None

    def test_callback_returning_offnormal(self):
        def _check(v, p):
            return EventState.OFFNORMAL if v > p["threshold"] else None

        result = evaluate_extended(42, {"threshold": 10}, vendor_callback=_check)
        assert result is EventState.OFFNORMAL

    def test_callback_returning_high_limit(self):
        result = evaluate_extended(100, {}, vendor_callback=lambda v, p: EventState.HIGH_LIMIT)
        assert result is EventState.HIGH_LIMIT

    def test_callback_returning_low_limit(self):
        result = evaluate_extended(-100, {}, vendor_callback=lambda v, p: EventState.LOW_LIMIT)
        assert result is EventState.LOW_LIMIT

    def test_callback_receives_correct_args(self):
        received_args: list[tuple[object, object]] = []

        def capture(value, params):
            received_args.append((value, params))
            return None

        evaluate_extended("my_value", {"key": "data"}, vendor_callback=capture)
        assert len(received_args) == 1
        assert received_args[0] == ("my_value", {"key": "data"})

    def test_callback_normal_condition(self):
        def _check(v, p):
            return EventState.OFFNORMAL if v > p["threshold"] else None

        result = evaluate_extended(5, {"threshold": 10}, vendor_callback=_check)
        assert result is None

    def test_explicit_none_callback(self):
        result = evaluate_extended("value", "params", vendor_callback=None)
        assert result is None


class TestEvaluateChangeOfTimer:
    """Tests for evaluate_change_of_timer (Clause 13.3.20)."""

    def test_idle_not_in_alarm_values_returns_none(self):
        alarm_values = (int(TimerState.EXPIRED),)
        result = evaluate_change_of_timer(TimerState.IDLE, alarm_values)
        assert result is None

    def test_expired_in_alarm_values_returns_offnormal(self):
        alarm_values = (int(TimerState.EXPIRED),)
        result = evaluate_change_of_timer(TimerState.EXPIRED, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_running_in_alarm_values_returns_offnormal(self):
        alarm_values = (int(TimerState.RUNNING),)
        result = evaluate_change_of_timer(TimerState.RUNNING, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_empty_alarm_values_never_alarms(self):
        result = evaluate_change_of_timer(TimerState.EXPIRED, ())
        assert result is None

    def test_all_states_in_alarm_values(self):
        alarm_values = (
            int(TimerState.IDLE),
            int(TimerState.RUNNING),
            int(TimerState.EXPIRED),
        )
        for state in TimerState:
            result = evaluate_change_of_timer(state, alarm_values)
            assert result is EventState.OFFNORMAL

    def test_idle_in_alarm_values(self):
        alarm_values = (int(TimerState.IDLE),)
        result = evaluate_change_of_timer(TimerState.IDLE, alarm_values)
        assert result is EventState.OFFNORMAL

    def test_multiple_alarm_values(self):
        alarm_values = (int(TimerState.RUNNING), int(TimerState.EXPIRED))
        idle = evaluate_change_of_timer(TimerState.IDLE, alarm_values)
        assert idle is None
        running = evaluate_change_of_timer(TimerState.RUNNING, alarm_values)
        assert running is EventState.OFFNORMAL
        expired = evaluate_change_of_timer(TimerState.EXPIRED, alarm_values)
        assert expired is EventState.OFFNORMAL
