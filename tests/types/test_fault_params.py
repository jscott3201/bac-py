"""Tests for BACnetFaultParameter CHOICE type (Step 5).

Covers round-trip encode/decode, factory dispatch, to_dict/from_dict,
and error handling for every variant defined in ASHRAE 135-2020 Clause 13.4.
"""

from typing import ClassVar

import pytest

from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
from bac_py.types.constructed import BACnetDeviceObjectPropertyReference
from bac_py.types.enums import LifeSafetyMode, LifeSafetyState, ObjectType
from bac_py.types.fault_params import (
    FaultCharacterString,
    FaultExtended,
    FaultLifeSafety,
    FaultListed,
    FaultNone,
    FaultOutOfRange,
    FaultState,
    FaultStatusFlags,
    decode_fault_parameter,
    fault_parameter_from_dict,
)
from bac_py.types.primitives import ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _round_trip(variant):
    encoded = variant.encode()
    decoded, offset = decode_fault_parameter(memoryview(encoded))
    assert offset == len(encoded)
    return decoded


def _make_ref(obj_type=ObjectType.ANALOG_INPUT, instance=1, prop_id=85):
    return BACnetDeviceObjectPropertyReference(
        object_identifier=ObjectIdentifier(obj_type, instance),
        property_identifier=prop_id,
    )


# ---------------------------------------------------------------------------
# FaultNone (TAG=0)
# ---------------------------------------------------------------------------


class TestFaultNone:
    def test_round_trip(self):
        variant = FaultNone()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultNone)

    def test_to_dict_from_dict(self):
        variant = FaultNone()
        d = variant.to_dict()
        assert d == {"type": "fault-none"}
        restored = FaultNone.from_dict(d)
        assert isinstance(restored, FaultNone)

    def test_tag_number(self):
        assert FaultNone.TAG == 0


# ---------------------------------------------------------------------------
# FaultCharacterString (TAG=1)
# ---------------------------------------------------------------------------


class TestFaultCharacterString:
    def test_round_trip_empty(self):
        variant = FaultCharacterString()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultCharacterString)
        assert decoded.fault_values == ()

    def test_round_trip_single_value(self):
        variant = FaultCharacterString(fault_values=("FAULT",))
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultCharacterString)
        assert decoded.fault_values == ("FAULT",)

    def test_round_trip_multiple_values(self):
        variant = FaultCharacterString(fault_values=("FAULT", "ERROR", "OFFLINE"))
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultCharacterString)
        assert decoded.fault_values == ("FAULT", "ERROR", "OFFLINE")

    def test_to_dict_from_dict(self):
        variant = FaultCharacterString(fault_values=("ALARM", "FAULT"))
        d = variant.to_dict()
        assert d["type"] == "fault-characterstring"
        assert d["fault_values"] == ["ALARM", "FAULT"]
        restored = FaultCharacterString.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert FaultCharacterString.TAG == 1


# ---------------------------------------------------------------------------
# FaultExtended (TAG=2)
# ---------------------------------------------------------------------------


class TestFaultExtended:
    def test_round_trip_default(self):
        variant = FaultExtended()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultExtended)
        assert decoded.vendor_id == 0
        assert decoded.extended_fault_type == 0
        assert decoded.parameters == b""

    def test_round_trip_realistic(self):
        params_data = b"\x21\x05\x91\x03"
        variant = FaultExtended(
            vendor_id=95,
            extended_fault_type=42,
            parameters=params_data,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultExtended)
        assert decoded.vendor_id == 95
        assert decoded.extended_fault_type == 42
        assert decoded.parameters == params_data

    def test_to_dict_from_dict(self):
        variant = FaultExtended(
            vendor_id=7,
            extended_fault_type=1,
            parameters=b"\x01\x02",
        )
        d = variant.to_dict()
        assert d["type"] == "fault-extended"
        assert d["vendor_id"] == 7
        assert d["parameters"] == "0102"
        restored = FaultExtended.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert FaultExtended.TAG == 2


# ---------------------------------------------------------------------------
# FaultLifeSafety (TAG=3)
# ---------------------------------------------------------------------------


class TestFaultLifeSafety:
    def test_round_trip_empty(self):
        variant = FaultLifeSafety()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultLifeSafety)
        assert decoded.fault_values == ()
        assert decoded.mode_values == ()

    def test_round_trip_realistic(self):
        variant = FaultLifeSafety(
            fault_values=(LifeSafetyState.FAULT, LifeSafetyState.ALARM),
            mode_values=(LifeSafetyMode.ON, LifeSafetyMode.TEST),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultLifeSafety)
        assert decoded.fault_values == (LifeSafetyState.FAULT, LifeSafetyState.ALARM)
        assert decoded.mode_values == (LifeSafetyMode.ON, LifeSafetyMode.TEST)

    def test_round_trip_single_each(self):
        variant = FaultLifeSafety(
            fault_values=(LifeSafetyState.TAMPER,),
            mode_values=(LifeSafetyMode.ARMED,),
        )
        decoded = _round_trip(variant)
        assert decoded.fault_values == (LifeSafetyState.TAMPER,)
        assert decoded.mode_values == (LifeSafetyMode.ARMED,)

    def test_to_dict_from_dict(self):
        variant = FaultLifeSafety(
            fault_values=(LifeSafetyState.FAULT, LifeSafetyState.ALARM),
            mode_values=(LifeSafetyMode.ON,),
        )
        d = variant.to_dict()
        assert d["type"] == "fault-life-safety"
        assert d["fault_values"] == [LifeSafetyState.FAULT.value, LifeSafetyState.ALARM.value]
        assert d["mode_values"] == [LifeSafetyMode.ON.value]
        restored = FaultLifeSafety.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert FaultLifeSafety.TAG == 3


# ---------------------------------------------------------------------------
# FaultState (TAG=4)
# ---------------------------------------------------------------------------


class TestFaultState:
    def test_round_trip_default(self):
        variant = FaultState()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultState)
        assert decoded.fault_values == b""

    def test_round_trip_realistic(self):
        raw = b"\x91\x05\x91\x09"
        variant = FaultState(fault_values=raw)
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultState)
        assert decoded.fault_values == raw

    def test_to_dict_from_dict(self):
        variant = FaultState(fault_values=b"\xab\xcd")
        d = variant.to_dict()
        assert d["type"] == "fault-state"
        assert d["fault_values"] == "abcd"
        restored = FaultState.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert FaultState.TAG == 4


# ---------------------------------------------------------------------------
# FaultStatusFlags (TAG=5)
# ---------------------------------------------------------------------------


class TestFaultStatusFlags:
    def test_round_trip(self):
        ref = _make_ref()
        variant = FaultStatusFlags(status_flags_ref=ref)
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultStatusFlags)
        assert decoded.status_flags_ref.object_identifier == ref.object_identifier
        assert decoded.status_flags_ref.property_identifier == ref.property_identifier

    def test_round_trip_with_different_property(self):
        ref = _make_ref(
            obj_type=ObjectType.BINARY_INPUT,
            instance=42,
            prop_id=111,
        )
        variant = FaultStatusFlags(status_flags_ref=ref)
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultStatusFlags)
        assert decoded.status_flags_ref.object_identifier.instance_number == 42
        assert decoded.status_flags_ref.property_identifier == 111

    def test_to_dict_from_dict(self):
        ref = _make_ref()
        variant = FaultStatusFlags(status_flags_ref=ref)
        d = variant.to_dict()
        assert d["type"] == "fault-status-flags"
        assert "status_flags_ref" in d
        restored = FaultStatusFlags.from_dict(d)
        assert restored.status_flags_ref.property_identifier == ref.property_identifier

    def test_tag_number(self):
        assert FaultStatusFlags.TAG == 5


# ---------------------------------------------------------------------------
# FaultOutOfRange (TAG=6) -- all 4 choice types
# ---------------------------------------------------------------------------


class TestFaultOutOfRange:
    def test_round_trip_real(self):
        variant = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultOutOfRange)
        assert decoded.min_normal_value == pytest.approx(10.0)
        assert decoded.max_normal_value == pytest.approx(90.0)
        assert decoded.min_choice == 0
        assert decoded.max_choice == 0

    def test_round_trip_unsigned(self):
        variant = FaultOutOfRange(
            min_normal_value=0,
            max_normal_value=100,
            min_choice=1,
            max_choice=1,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultOutOfRange)
        assert decoded.min_normal_value == 0
        assert decoded.max_normal_value == 100
        assert decoded.min_choice == 1
        assert decoded.max_choice == 1

    def test_round_trip_double(self):
        variant = FaultOutOfRange(
            min_normal_value=-1.5e10,
            max_normal_value=1.5e10,
            min_choice=2,
            max_choice=2,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultOutOfRange)
        assert decoded.min_normal_value == pytest.approx(-1.5e10)
        assert decoded.max_normal_value == pytest.approx(1.5e10)
        assert decoded.min_choice == 2
        assert decoded.max_choice == 2

    def test_round_trip_integer(self):
        variant = FaultOutOfRange(
            min_normal_value=-50,
            max_normal_value=50,
            min_choice=3,
            max_choice=3,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultOutOfRange)
        assert decoded.min_normal_value == -50
        assert decoded.max_normal_value == 50
        assert decoded.min_choice == 3
        assert decoded.max_choice == 3

    def test_round_trip_mixed_choices(self):
        variant = FaultOutOfRange(
            min_normal_value=5.0,
            max_normal_value=200,
            min_choice=0,
            max_choice=1,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultOutOfRange)
        assert decoded.min_normal_value == pytest.approx(5.0)
        assert decoded.max_normal_value == 200
        assert decoded.min_choice == 0
        assert decoded.max_choice == 1

    def test_to_dict_from_dict_real(self):
        variant = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        )
        d = variant.to_dict()
        assert d["type"] == "fault-out-of-range"
        assert d["min_choice"] == "real"
        assert d["max_choice"] == "real"
        restored = FaultOutOfRange.from_dict(d)
        assert restored.min_normal_value == pytest.approx(10.0)
        assert restored.max_normal_value == pytest.approx(90.0)

    def test_to_dict_from_dict_unsigned(self):
        variant = FaultOutOfRange(
            min_normal_value=0,
            max_normal_value=255,
            min_choice=1,
            max_choice=1,
        )
        d = variant.to_dict()
        assert d["min_choice"] == "unsigned"
        assert d["max_choice"] == "unsigned"
        restored = FaultOutOfRange.from_dict(d)
        assert restored.min_choice == 1
        assert restored.max_choice == 1

    def test_to_dict_from_dict_double(self):
        variant = FaultOutOfRange(
            min_normal_value=-1e5,
            max_normal_value=1e5,
            min_choice=2,
            max_choice=2,
        )
        d = variant.to_dict()
        assert d["min_choice"] == "double"
        assert d["max_choice"] == "double"
        restored = FaultOutOfRange.from_dict(d)
        assert restored.min_choice == 2

    def test_to_dict_from_dict_integer(self):
        variant = FaultOutOfRange(
            min_normal_value=-100,
            max_normal_value=100,
            min_choice=3,
            max_choice=3,
        )
        d = variant.to_dict()
        assert d["min_choice"] == "integer"
        assert d["max_choice"] == "integer"
        restored = FaultOutOfRange.from_dict(d)
        assert restored.min_choice == 3

    def test_tag_number(self):
        assert FaultOutOfRange.TAG == 6


# ---------------------------------------------------------------------------
# FaultListed (TAG=7)
# ---------------------------------------------------------------------------


class TestFaultListed:
    def test_round_trip(self):
        ref = _make_ref()
        variant = FaultListed(fault_list_ref=ref)
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultListed)
        assert decoded.fault_list_ref.object_identifier == ref.object_identifier
        assert decoded.fault_list_ref.property_identifier == ref.property_identifier

    def test_round_trip_with_different_ref(self):
        ref = _make_ref(
            obj_type=ObjectType.MULTI_STATE_VALUE,
            instance=99,
            prop_id=39,
        )
        variant = FaultListed(fault_list_ref=ref)
        decoded = _round_trip(variant)
        assert isinstance(decoded, FaultListed)
        assert decoded.fault_list_ref.object_identifier.instance_number == 99
        assert decoded.fault_list_ref.property_identifier == 39

    def test_to_dict_from_dict(self):
        ref = _make_ref()
        variant = FaultListed(fault_list_ref=ref)
        d = variant.to_dict()
        assert d["type"] == "fault-listed"
        assert "fault_list_ref" in d
        restored = FaultListed.from_dict(d)
        assert restored.fault_list_ref.property_identifier == ref.property_identifier

    def test_tag_number(self):
        assert FaultListed.TAG == 7


# ---------------------------------------------------------------------------
# Factory dispatch tests -- decode_fault_parameter
# ---------------------------------------------------------------------------


class TestFactoryDispatch:
    DISPATCH_TABLE: ClassVar[list[tuple[type, int]]] = [
        (FaultNone, 0),
        (FaultCharacterString, 1),
        (FaultExtended, 2),
        (FaultLifeSafety, 3),
        (FaultState, 4),
        (FaultStatusFlags, 5),
        (FaultOutOfRange, 6),
        (FaultListed, 7),
    ]

    @pytest.mark.parametrize("cls, tag", DISPATCH_TABLE)
    def test_dispatch_returns_correct_class(self, cls, tag):
        variant = cls()
        encoded = variant.encode()
        decoded, _ = decode_fault_parameter(memoryview(encoded))
        assert isinstance(decoded, cls), (
            f"Expected {cls.__name__} for tag {tag}, got {type(decoded).__name__}"
        )

    @pytest.mark.parametrize("cls, tag", DISPATCH_TABLE)
    def test_tag_constant_matches(self, cls, tag):
        assert tag == cls.TAG


# ---------------------------------------------------------------------------
# Factory dispatch tests -- fault_parameter_from_dict
# ---------------------------------------------------------------------------


class TestFaultParameterFromDict:
    TYPE_MAP: ClassVar[dict[str, type]] = {
        "fault-none": FaultNone,
        "fault-characterstring": FaultCharacterString,
        "fault-extended": FaultExtended,
        "fault-life-safety": FaultLifeSafety,
        "fault-state": FaultState,
        "fault-status-flags": FaultStatusFlags,
        "fault-out-of-range": FaultOutOfRange,
        "fault-listed": FaultListed,
    }

    def test_from_dict_fault_none(self):
        d = FaultNone().to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultNone)

    def test_from_dict_fault_characterstring(self):
        d = FaultCharacterString(fault_values=("FAULT",)).to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultCharacterString)
        assert result.fault_values == ("FAULT",)

    def test_from_dict_fault_extended(self):
        d = FaultExtended(vendor_id=7, extended_fault_type=1).to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultExtended)
        assert result.vendor_id == 7

    def test_from_dict_fault_life_safety(self):
        variant = FaultLifeSafety(
            fault_values=(LifeSafetyState.ALARM,),
            mode_values=(LifeSafetyMode.ON,),
        )
        d = variant.to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultLifeSafety)
        assert result.fault_values == (LifeSafetyState.ALARM,)

    def test_from_dict_fault_state(self):
        d = FaultState(fault_values=b"\xab").to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultState)

    def test_from_dict_fault_status_flags(self):
        ref = _make_ref()
        d = FaultStatusFlags(status_flags_ref=ref).to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultStatusFlags)

    def test_from_dict_fault_out_of_range(self):
        d = FaultOutOfRange(
            min_normal_value=10.0,
            max_normal_value=90.0,
            min_choice=0,
            max_choice=0,
        ).to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultOutOfRange)
        assert result.min_normal_value == pytest.approx(10.0)

    def test_from_dict_fault_listed(self):
        ref = _make_ref()
        d = FaultListed(fault_list_ref=ref).to_dict()
        result = fault_parameter_from_dict(d)
        assert isinstance(result, FaultListed)

    def test_from_dict_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            fault_parameter_from_dict({"type": "nonexistent-fault"})

    def test_from_dict_empty_type_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            fault_parameter_from_dict({})

    def test_round_trip_all_variants_through_dict(self):
        ref = _make_ref()
        variants = [
            FaultNone(),
            FaultCharacterString(fault_values=("FAULT", "ERROR")),
            FaultExtended(vendor_id=10, extended_fault_type=3, parameters=b"\xab"),
            FaultLifeSafety(
                fault_values=(LifeSafetyState.FAULT,),
                mode_values=(LifeSafetyMode.ON,),
            ),
            FaultState(fault_values=b"\x91\x05"),
            FaultStatusFlags(status_flags_ref=ref),
            FaultOutOfRange(
                min_normal_value=0.0,
                max_normal_value=100.0,
                min_choice=0,
                max_choice=0,
            ),
            FaultListed(fault_list_ref=ref),
        ]
        for variant in variants:
            d = variant.to_dict()
            restored = fault_parameter_from_dict(d)
            assert type(restored) is type(variant), (
                f"Type mismatch for {type(variant).__name__}: got {type(restored).__name__}"
            )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_decode_invalid_non_opening_tag(self):
        with pytest.raises(ValueError, match="Expected opening tag"):
            decode_fault_parameter(memoryview(b"\x09\x01"))

    def test_decode_unknown_tag(self):
        wire = encode_opening_tag(15) + encode_closing_tag(15)
        with pytest.raises(ValueError, match="Unknown FaultParameter choice tag"):
            decode_fault_parameter(memoryview(wire))

    def test_from_dict_unknown_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown"):
            fault_parameter_from_dict({"type": "not-a-real-fault"})
