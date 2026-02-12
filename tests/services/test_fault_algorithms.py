"""Tests for fault evaluation algorithms (Step 5).

Covers each FAULT_* algorithm per ASHRAE 135-2020 Clause 13.4 with
fault-triggering values, no-fault values, boundary conditions,
delegation chains, and extensibility hooks.
"""

from bac_py.services.fault_algorithms import (
    evaluate_fault_characterstring,
    evaluate_fault_extended,
    evaluate_fault_life_safety,
    evaluate_fault_listed,
    evaluate_fault_out_of_range,
    evaluate_fault_state,
    evaluate_fault_status_flags,
)
from bac_py.types.constructed import BACnetDeviceObjectPropertyReference, StatusFlags
from bac_py.types.enums import (
    LifeSafetyMode,
    LifeSafetyState,
    ObjectType,
    Reliability,
)
from bac_py.types.fault_params import (
    FaultCharacterString,
    FaultExtended,
    FaultLifeSafety,
    FaultListed,
    FaultOutOfRange,
    FaultState,
    FaultStatusFlags,
)
from bac_py.types.primitives import ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ref(obj_type=ObjectType.ANALOG_INPUT, instance=1, prop_id=85):
    return BACnetDeviceObjectPropertyReference(
        object_identifier=ObjectIdentifier(obj_type, instance),
        property_identifier=prop_id,
    )


# ---------------------------------------------------------------------------
# FAULT_CHARACTERSTRING
# ---------------------------------------------------------------------------


class TestEvaluateFaultCharacterString:
    def test_fault_when_value_matches(self):
        params = FaultCharacterString(fault_values=("FAULT", "ERROR"))
        result = evaluate_fault_characterstring("FAULT", params)
        assert result == Reliability.MULTI_STATE_FAULT

    def test_fault_when_second_value_matches(self):
        params = FaultCharacterString(fault_values=("FAULT", "ERROR"))
        result = evaluate_fault_characterstring("ERROR", params)
        assert result == Reliability.MULTI_STATE_FAULT

    def test_no_fault_when_value_not_in_list(self):
        params = FaultCharacterString(fault_values=("FAULT", "ERROR"))
        result = evaluate_fault_characterstring("NORMAL", params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_no_fault_when_list_empty(self):
        params = FaultCharacterString(fault_values=())
        result = evaluate_fault_characterstring("ANYTHING", params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_case_sensitive(self):
        params = FaultCharacterString(fault_values=("FAULT",))
        result = evaluate_fault_characterstring("fault", params)
        assert result == Reliability.NO_FAULT_DETECTED


# ---------------------------------------------------------------------------
# FAULT_EXTENDED
# ---------------------------------------------------------------------------


class TestEvaluateFaultExtended:
    def test_no_fault_without_callback(self):
        params = FaultExtended(vendor_id=95, extended_fault_type=42)
        result = evaluate_fault_extended("some_value", params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_no_fault_with_none_callback(self):
        params = FaultExtended(vendor_id=95, extended_fault_type=42)
        result = evaluate_fault_extended("value", params, vendor_callback=None)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_fault_via_vendor_callback(self):
        def my_callback(value, p):
            return Reliability.UNRELIABLE_OTHER

        params = FaultExtended(vendor_id=95, extended_fault_type=42)
        result = evaluate_fault_extended("value", params, vendor_callback=my_callback)
        assert result == Reliability.UNRELIABLE_OTHER

    def test_callback_returns_no_fault(self):
        def my_callback(value, p):
            return Reliability.NO_FAULT_DETECTED

        params = FaultExtended(vendor_id=95, extended_fault_type=42)
        result = evaluate_fault_extended("value", params, vendor_callback=my_callback)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_callback_receives_correct_args(self):
        received = {}

        def my_callback(value, p):
            received["value"] = value
            received["params"] = p
            return Reliability.NO_FAULT_DETECTED

        params = FaultExtended(vendor_id=95, extended_fault_type=42)
        evaluate_fault_extended("test_val", params, vendor_callback=my_callback)
        assert received["value"] == "test_val"
        assert received["params"] is params


# ---------------------------------------------------------------------------
# FAULT_LIFE_SAFETY
# ---------------------------------------------------------------------------


class TestEvaluateFaultLifeSafety:
    def test_fault_when_state_in_list(self):
        params = FaultLifeSafety(
            fault_values=(LifeSafetyState.FAULT, LifeSafetyState.ALARM),
            mode_values=(LifeSafetyMode.ON,),
        )
        result = evaluate_fault_life_safety(LifeSafetyState.FAULT, params)
        assert result == Reliability.MULTI_STATE_FAULT

    def test_fault_when_alarm_state_in_list(self):
        params = FaultLifeSafety(
            fault_values=(LifeSafetyState.FAULT, LifeSafetyState.ALARM),
            mode_values=(LifeSafetyMode.ON,),
        )
        result = evaluate_fault_life_safety(LifeSafetyState.ALARM, params)
        assert result == Reliability.MULTI_STATE_FAULT

    def test_no_fault_when_state_not_in_list(self):
        params = FaultLifeSafety(
            fault_values=(LifeSafetyState.FAULT, LifeSafetyState.ALARM),
            mode_values=(LifeSafetyMode.ON,),
        )
        result = evaluate_fault_life_safety(LifeSafetyState.QUIET, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_no_fault_when_list_empty(self):
        params = FaultLifeSafety(fault_values=(), mode_values=())
        result = evaluate_fault_life_safety(LifeSafetyState.FAULT, params)
        assert result == Reliability.NO_FAULT_DETECTED


# ---------------------------------------------------------------------------
# FAULT_STATE
# ---------------------------------------------------------------------------


class TestEvaluateFaultState:
    def test_fault_when_value_in_enum_values(self):
        params = FaultState(fault_values=b"\x91\x05")
        result = evaluate_fault_state(5, params, fault_enum_values=(5, 9))
        assert result == Reliability.MULTI_STATE_FAULT

    def test_no_fault_when_value_not_in_enum_values(self):
        params = FaultState(fault_values=b"\x91\x05")
        result = evaluate_fault_state(3, params, fault_enum_values=(5, 9))
        assert result == Reliability.NO_FAULT_DETECTED

    def test_no_fault_when_enum_values_empty(self):
        params = FaultState(fault_values=b"\x91\x05")
        result = evaluate_fault_state(5, params, fault_enum_values=())
        assert result == Reliability.NO_FAULT_DETECTED

    def test_fault_when_second_enum_value_matches(self):
        params = FaultState(fault_values=b"\x91\x05")
        result = evaluate_fault_state(9, params, fault_enum_values=(5, 9))
        assert result == Reliability.MULTI_STATE_FAULT


# ---------------------------------------------------------------------------
# FAULT_STATUS_FLAGS
# ---------------------------------------------------------------------------


class TestEvaluateFaultStatusFlags:
    def test_fault_when_fault_flag_set(self):
        params = FaultStatusFlags(status_flags_ref=_make_ref())
        flags = StatusFlags(fault=True)
        result = evaluate_fault_status_flags(flags, params)
        assert result == Reliability.MEMBER_FAULT

    def test_no_fault_when_all_clear(self):
        params = FaultStatusFlags(status_flags_ref=_make_ref())
        flags = StatusFlags()
        result = evaluate_fault_status_flags(flags, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_no_fault_when_only_alarm(self):
        params = FaultStatusFlags(status_flags_ref=_make_ref())
        flags = StatusFlags(in_alarm=True)
        result = evaluate_fault_status_flags(flags, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_fault_when_fault_and_other_flags_set(self):
        params = FaultStatusFlags(status_flags_ref=_make_ref())
        flags = StatusFlags(in_alarm=True, fault=True, out_of_service=True)
        result = evaluate_fault_status_flags(flags, params)
        assert result == Reliability.MEMBER_FAULT


# ---------------------------------------------------------------------------
# FAULT_OUT_OF_RANGE -- boundary conditions
# ---------------------------------------------------------------------------


class TestEvaluateFaultOutOfRange:
    def test_over_range(self):
        params = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        result = evaluate_fault_out_of_range(95.0, params)
        assert result == Reliability.OVER_RANGE

    def test_under_range(self):
        params = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        result = evaluate_fault_out_of_range(5.0, params)
        assert result == Reliability.UNDER_RANGE

    def test_in_range(self):
        params = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        result = evaluate_fault_out_of_range(50.0, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_exactly_at_min(self):
        params = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        result = evaluate_fault_out_of_range(10.0, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_exactly_at_max(self):
        params = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        result = evaluate_fault_out_of_range(90.0, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_just_below_min(self):
        params = FaultOutOfRange(
            min_normal_value=10,
            max_normal_value=90,
            min_choice=1,
            max_choice=1,
        )
        result = evaluate_fault_out_of_range(9, params)
        assert result == Reliability.UNDER_RANGE

    def test_just_above_max(self):
        params = FaultOutOfRange(
            min_normal_value=10,
            max_normal_value=90,
            min_choice=1,
            max_choice=1,
        )
        result = evaluate_fault_out_of_range(91, params)
        assert result == Reliability.OVER_RANGE

    def test_integer_range(self):
        params = FaultOutOfRange(
            min_normal_value=-50,
            max_normal_value=50,
            min_choice=3,
            max_choice=3,
        )
        result = evaluate_fault_out_of_range(0, params)
        assert result == Reliability.NO_FAULT_DETECTED

    def test_integer_under_range(self):
        params = FaultOutOfRange(
            min_normal_value=-50,
            max_normal_value=50,
            min_choice=3,
            max_choice=3,
        )
        result = evaluate_fault_out_of_range(-100, params)
        assert result == Reliability.UNDER_RANGE

    def test_integer_over_range(self):
        params = FaultOutOfRange(
            min_normal_value=-50,
            max_normal_value=50,
            min_choice=3,
            max_choice=3,
        )
        result = evaluate_fault_out_of_range(100, params)
        assert result == Reliability.OVER_RANGE


# ---------------------------------------------------------------------------
# FAULT_LISTED -- delegation chain
# ---------------------------------------------------------------------------


class TestEvaluateFaultListed:
    """Tests for evaluate_fault_listed.

    The fault_list parameter is a sequence of (sub_params, evaluator_fn)
    pairs.  Each evaluator_fn is called with (current_value, sub_params) and
    the first non-NO_FAULT_DETECTED result wins.
    """

    @staticmethod
    def _char_evaluator(value: object, p: object) -> Reliability:
        """Return MULTI_STATE_FAULT if value matches, else NO_FAULT_DETECTED."""
        if value == p:
            return Reliability.MULTI_STATE_FAULT
        return Reliability.NO_FAULT_DETECTED

    def test_no_fault_when_list_empty(self):
        params = FaultListed(fault_list_ref=_make_ref())
        result = evaluate_fault_listed("value", params, fault_list=())
        assert result == Reliability.NO_FAULT_DETECTED

    def test_fault_when_sub_evaluator_matches(self):
        params = FaultListed(fault_list_ref=_make_ref())
        result = evaluate_fault_listed(
            "FAULT_A",
            params,
            fault_list=(("FAULT_A", self._char_evaluator),),
        )
        assert result == Reliability.MULTI_STATE_FAULT

    def test_no_fault_when_no_sub_evaluator_matches(self):
        params = FaultListed(fault_list_ref=_make_ref())
        result = evaluate_fault_listed(
            "NORMAL",
            params,
            fault_list=(
                ("FAULT_A", self._char_evaluator),
                ("FAULT_B", self._char_evaluator),
            ),
        )
        assert result == Reliability.NO_FAULT_DETECTED

    def test_fault_with_second_evaluator(self):
        params = FaultListed(fault_list_ref=_make_ref())
        result = evaluate_fault_listed(
            "FAULT_B",
            params,
            fault_list=(
                ("FAULT_A", self._char_evaluator),
                ("FAULT_B", self._char_evaluator),
            ),
        )
        assert result == Reliability.MULTI_STATE_FAULT

    def test_first_fault_wins(self):
        """When multiple evaluators match, the first non-NO_FAULT result wins."""
        params = FaultListed(fault_list_ref=_make_ref())

        def always_fault(_v: object, _p: object) -> Reliability:
            return Reliability.UNDER_RANGE

        def also_fault(_v: object, _p: object) -> Reliability:
            return Reliability.OVER_RANGE

        result = evaluate_fault_listed(
            "x",
            params,
            fault_list=((None, always_fault), (None, also_fault)),
        )
        assert result == Reliability.UNDER_RANGE
