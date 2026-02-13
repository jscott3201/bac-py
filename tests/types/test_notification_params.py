"""Tests for BACnet NotificationParameters CHOICE type (Step 3.7).

Covers round-trip encode/decode, factory dispatch, to_dict/from_dict,
reserved tag handling, and EventNotificationRequest integration
for every variant defined in ASHRAE 135-2020 Clause 13.3.
"""

from typing import ClassVar

import pytest

from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
from bac_py.services.event_notification import EventNotificationRequest
from bac_py.types.constructed import BACnetDateTime, BACnetTimeStamp, StatusFlags
from bac_py.types.enums import (
    EventState,
    EventType,
    LifeSafetyMode,
    LifeSafetyOperation,
    LifeSafetyState,
    NotifyType,
    ObjectType,
    Reliability,
    TimerState,
    TimerTransition,
)
from bac_py.types.notification_params import (
    AccessEvent,
    BufferReady,
    ChangeOfBitstring,
    ChangeOfCharacterstring,
    ChangeOfDiscreteValue,
    ChangeOfLifeSafety,
    ChangeOfReliability,
    ChangeOfState,
    ChangeOfStatusFlags,
    ChangeOfTimer,
    ChangeOfValue,
    CommandFailure,
    DoubleOutOfRange,
    Extended,
    FloatingLimit,
    NoneParams,
    OutOfRange,
    RawNotificationParameters,
    SignedOutOfRange,
    UnsignedOutOfRange,
    UnsignedRange,
    decode_notification_parameters,
    notification_parameters_from_dict,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _round_trip(variant):
    """Encode a variant, decode it back, and return the decoded instance."""
    encoded = variant.encode()
    decoded, offset = decode_notification_parameters(memoryview(encoded))
    assert offset == len(encoded)
    return decoded


def _make_status_flags(in_alarm=False, fault=False, overridden=False, out_of_service=False):
    return StatusFlags(
        in_alarm=in_alarm,
        fault=fault,
        overridden=overridden,
        out_of_service=out_of_service,
    )


def _make_datetime(year=2024, month=6, day=15, dow=6, h=9, m=30, s=0, hs=0):
    return BACnetDateTime(
        date=BACnetDate(year, month, day, dow),
        time=BACnetTime(h, m, s, hs),
    )


def _wildcard_datetime():
    return BACnetDateTime(
        date=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF),
        time=BACnetTime(0xFF, 0xFF, 0xFF, 0xFF),
    )


# ---------------------------------------------------------------------------
# ChangeOfBitstring (TAG=0)
# ---------------------------------------------------------------------------


class TestChangeOfBitstring:
    def test_round_trip_default(self):
        variant = ChangeOfBitstring()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfBitstring)
        assert decoded.referenced_bitstring == variant.referenced_bitstring
        assert decoded.status_flags == StatusFlags()

    def test_round_trip_realistic(self):
        bs = BitString(b"\xa0", 3)
        sf = _make_status_flags(in_alarm=True)
        variant = ChangeOfBitstring(referenced_bitstring=bs, status_flags=sf)
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfBitstring)
        assert decoded.referenced_bitstring == bs
        assert decoded.status_flags.in_alarm is True
        assert decoded.status_flags.fault is False

    def test_to_dict_from_dict(self):
        bs = BitString(b"\xf0", 4)
        variant = ChangeOfBitstring(referenced_bitstring=bs)
        d = variant.to_dict()
        assert d["type"] == "change-of-bitstring"
        restored = ChangeOfBitstring.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfBitstring.TAG == 0


# ---------------------------------------------------------------------------
# ChangeOfState (TAG=1)
# ---------------------------------------------------------------------------


class TestChangeOfState:
    def test_round_trip_default(self):
        variant = ChangeOfState()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfState)
        assert decoded.new_state == b""
        assert decoded.status_flags == StatusFlags()

    def test_round_trip_realistic(self):
        # BACnet application-tagged enumerated value 5 (3 bytes: tag, length, value)
        raw_state = b"\x91\x05"
        sf = _make_status_flags(fault=True)
        variant = ChangeOfState(new_state=raw_state, status_flags=sf)
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfState)
        assert decoded.new_state == raw_state
        assert decoded.status_flags.fault is True

    def test_to_dict_from_dict(self):
        variant = ChangeOfState(new_state=b"\x91\x05")
        d = variant.to_dict()
        assert d["type"] == "change-of-state"
        assert d["new_state"] == "9105"
        restored = ChangeOfState.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfState.TAG == 1


# ---------------------------------------------------------------------------
# ChangeOfValue (TAG=2)
# ---------------------------------------------------------------------------


class TestChangeOfValue:
    def test_round_trip_bitstring_choice(self):
        bs = BitString(b"\xa0", 5)
        variant = ChangeOfValue(
            new_value_choice=0,
            new_value=bs,
            status_flags=_make_status_flags(in_alarm=True),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfValue)
        assert decoded.new_value_choice == 0
        assert decoded.new_value == bs
        assert decoded.status_flags.in_alarm is True

    def test_round_trip_real_choice(self):
        variant = ChangeOfValue(
            new_value_choice=1,
            new_value=42.5,
            status_flags=StatusFlags(),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfValue)
        assert decoded.new_value_choice == 1
        assert decoded.new_value == pytest.approx(42.5)

    def test_round_trip_zero_real(self):
        variant = ChangeOfValue(new_value_choice=1, new_value=0.0)
        decoded = _round_trip(variant)
        assert decoded.new_value == pytest.approx(0.0)

    def test_to_dict_from_dict_changed_bits(self):
        bs = BitString(b"\xa0", 5)
        variant = ChangeOfValue(new_value_choice=0, new_value=bs)
        d = variant.to_dict()
        assert d["type"] == "change-of-value"
        assert d["new_value_choice"] == "changed-bits"
        restored = ChangeOfValue.from_dict(d)
        assert restored == variant

    def test_to_dict_from_dict_changed_value(self):
        variant = ChangeOfValue(new_value_choice=1, new_value=72.3)
        d = variant.to_dict()
        assert d["new_value_choice"] == "changed-value"
        restored = ChangeOfValue.from_dict(d)
        assert restored.new_value == pytest.approx(72.3)

    def test_tag_number(self):
        assert ChangeOfValue.TAG == 2


# ---------------------------------------------------------------------------
# CommandFailure (TAG=3)
# ---------------------------------------------------------------------------


class TestCommandFailure:
    def test_round_trip_default(self):
        variant = CommandFailure()
        decoded = _round_trip(variant)
        assert isinstance(decoded, CommandFailure)
        assert decoded.command_value == b""
        assert decoded.feedback_value == b""

    def test_round_trip_realistic(self):
        # Use valid BACnet application-tagged data (app tag 2/unsigned, len 1)
        cmd = b"\x21\x05"
        fb = b"\x21\x0a"
        variant = CommandFailure(
            command_value=cmd,
            status_flags=_make_status_flags(in_alarm=True, fault=True),
            feedback_value=fb,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, CommandFailure)
        assert decoded.command_value == cmd
        assert decoded.status_flags.in_alarm is True
        assert decoded.status_flags.fault is True
        assert decoded.feedback_value == fb

    def test_to_dict_from_dict(self):
        variant = CommandFailure(
            command_value=b"\xaa\xbb",
            feedback_value=b"\xcc\xdd",
        )
        d = variant.to_dict()
        assert d["type"] == "command-failure"
        restored = CommandFailure.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert CommandFailure.TAG == 3


# ---------------------------------------------------------------------------
# FloatingLimit (TAG=4)
# ---------------------------------------------------------------------------


class TestFloatingLimit:
    def test_round_trip_default(self):
        variant = FloatingLimit()
        decoded = _round_trip(variant)
        assert isinstance(decoded, FloatingLimit)
        assert decoded.reference_value == pytest.approx(0.0)

    def test_round_trip_realistic(self):
        variant = FloatingLimit(
            reference_value=72.5,
            status_flags=_make_status_flags(in_alarm=True),
            setpoint_value=70.0,
            error_limit=2.0,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, FloatingLimit)
        assert decoded.reference_value == pytest.approx(72.5)
        assert decoded.setpoint_value == pytest.approx(70.0)
        assert decoded.error_limit == pytest.approx(2.0)
        assert decoded.status_flags.in_alarm is True

    def test_to_dict_from_dict(self):
        variant = FloatingLimit(
            reference_value=55.0,
            setpoint_value=50.0,
            error_limit=3.0,
        )
        d = variant.to_dict()
        assert d["type"] == "floating-limit"
        restored = FloatingLimit.from_dict(d)
        assert restored.reference_value == pytest.approx(55.0)

    def test_tag_number(self):
        assert FloatingLimit.TAG == 4


# ---------------------------------------------------------------------------
# OutOfRange (TAG=5)
# ---------------------------------------------------------------------------


class TestOutOfRange:
    def test_round_trip_default(self):
        variant = OutOfRange()
        decoded = _round_trip(variant)
        assert isinstance(decoded, OutOfRange)

    def test_round_trip_realistic(self):
        variant = OutOfRange(
            exceeding_value=85.5,
            status_flags=_make_status_flags(in_alarm=True),
            deadband=1.0,
            exceeded_limit=80.0,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, OutOfRange)
        assert decoded.exceeding_value == pytest.approx(85.5)
        assert decoded.deadband == pytest.approx(1.0)
        assert decoded.exceeded_limit == pytest.approx(80.0)
        assert decoded.status_flags.in_alarm is True

    def test_to_dict_from_dict(self):
        variant = OutOfRange(
            exceeding_value=105.0,
            deadband=2.0,
            exceeded_limit=100.0,
        )
        d = variant.to_dict()
        assert d["type"] == "out-of-range"
        restored = OutOfRange.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert OutOfRange.TAG == 5


# ---------------------------------------------------------------------------
# ChangeOfLifeSafety (TAG=8)
# ---------------------------------------------------------------------------


class TestChangeOfLifeSafety:
    def test_round_trip_default(self):
        variant = ChangeOfLifeSafety()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfLifeSafety)
        assert decoded.new_state == LifeSafetyState.QUIET
        assert decoded.new_mode == LifeSafetyMode.OFF
        assert decoded.operation_expected == LifeSafetyOperation.NONE

    def test_round_trip_realistic(self):
        variant = ChangeOfLifeSafety(
            new_state=LifeSafetyState.ALARM,
            new_mode=LifeSafetyMode.ON,
            status_flags=_make_status_flags(in_alarm=True),
            operation_expected=LifeSafetyOperation.SILENCE,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfLifeSafety)
        assert decoded.new_state == LifeSafetyState.ALARM
        assert decoded.new_mode == LifeSafetyMode.ON
        assert decoded.operation_expected == LifeSafetyOperation.SILENCE
        assert decoded.status_flags.in_alarm is True

    def test_to_dict_from_dict(self):
        variant = ChangeOfLifeSafety(
            new_state=LifeSafetyState.FAULT,
            new_mode=LifeSafetyMode.TEST,
            operation_expected=LifeSafetyOperation.RESET,
        )
        d = variant.to_dict()
        assert d["type"] == "change-of-life-safety"
        restored = ChangeOfLifeSafety.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfLifeSafety.TAG == 8


# ---------------------------------------------------------------------------
# Extended (TAG=9)
# ---------------------------------------------------------------------------


class TestExtended:
    def test_round_trip_default(self):
        variant = Extended()
        decoded = _round_trip(variant)
        assert isinstance(decoded, Extended)
        assert decoded.vendor_id == 0
        assert decoded.extended_event_type == 0
        assert decoded.parameters == b""

    def test_round_trip_realistic(self):
        # Use valid BACnet app-tagged data for vendor-defined parameters
        params_data = b"\x21\x05\x91\x03"  # unsigned 5, enumerated 3
        variant = Extended(
            vendor_id=95,
            extended_event_type=42,
            parameters=params_data,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, Extended)
        assert decoded.vendor_id == 95
        assert decoded.extended_event_type == 42
        assert decoded.parameters == params_data

    def test_to_dict_from_dict(self):
        variant = Extended(vendor_id=7, extended_event_type=1, parameters=b"\x01\x02")
        d = variant.to_dict()
        assert d["type"] == "extended"
        assert d["vendor_id"] == 7
        restored = Extended.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert Extended.TAG == 9


# ---------------------------------------------------------------------------
# BufferReady (TAG=10)
# ---------------------------------------------------------------------------


class TestBufferReady:
    def test_round_trip_default(self):
        variant = BufferReady()
        decoded = _round_trip(variant)
        assert isinstance(decoded, BufferReady)
        assert decoded.previous_notification == 0
        assert decoded.current_notification == 0

    def test_round_trip_realistic(self):
        variant = BufferReady(
            buffer_property=b"\x0c\x02\x00\x00\x01\x19\x55",
            previous_notification=10,
            current_notification=25,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, BufferReady)
        assert decoded.buffer_property == b"\x0c\x02\x00\x00\x01\x19\x55"
        assert decoded.previous_notification == 10
        assert decoded.current_notification == 25

    def test_to_dict_from_dict(self):
        variant = BufferReady(
            buffer_property=b"\xaa",
            previous_notification=5,
            current_notification=15,
        )
        d = variant.to_dict()
        assert d["type"] == "buffer-ready"
        restored = BufferReady.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert BufferReady.TAG == 10


# ---------------------------------------------------------------------------
# UnsignedRange (TAG=11)
# ---------------------------------------------------------------------------


class TestUnsignedRange:
    def test_round_trip_default(self):
        variant = UnsignedRange()
        decoded = _round_trip(variant)
        assert isinstance(decoded, UnsignedRange)

    def test_round_trip_realistic(self):
        variant = UnsignedRange(
            exceeding_value=150,
            status_flags=_make_status_flags(in_alarm=True),
            exceeded_limit=100,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, UnsignedRange)
        assert decoded.exceeding_value == 150
        assert decoded.exceeded_limit == 100
        assert decoded.status_flags.in_alarm is True

    def test_to_dict_from_dict(self):
        variant = UnsignedRange(exceeding_value=200, exceeded_limit=180)
        d = variant.to_dict()
        assert d["type"] == "unsigned-range"
        restored = UnsignedRange.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert UnsignedRange.TAG == 11


# ---------------------------------------------------------------------------
# AccessEvent (TAG=13)
# ---------------------------------------------------------------------------


class TestAccessEvent:
    def test_round_trip_default(self):
        variant = AccessEvent()
        decoded = _round_trip(variant)
        assert isinstance(decoded, AccessEvent)
        assert decoded.authentication_factor is None

    def test_round_trip_realistic(self):
        # Use valid BACnet app-tagged data for raw fields
        event_time = b"\x21\x01\x21\x02\x21\x03\x21\x04"  # sequence of unsigned values
        credential = b"\x21\x05"
        variant = AccessEvent(
            access_event=5,
            status_flags=_make_status_flags(in_alarm=True),
            access_event_tag=3,
            access_event_time=event_time,
            access_credential=credential,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, AccessEvent)
        assert decoded.access_event == 5
        assert decoded.access_event_tag == 3
        assert decoded.access_event_time == event_time
        assert decoded.access_credential == credential
        assert decoded.authentication_factor is None

    def test_round_trip_with_authentication_factor(self):
        event_time = b"\x21\x01"
        credential = b"\x21\x02"
        auth_factor = b"\x21\x03"
        variant = AccessEvent(
            access_event=2,
            status_flags=StatusFlags(),
            access_event_tag=1,
            access_event_time=event_time,
            access_credential=credential,
            authentication_factor=auth_factor,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, AccessEvent)
        assert decoded.authentication_factor == auth_factor

    def test_to_dict_from_dict_without_auth(self):
        variant = AccessEvent(
            access_event=1,
            access_event_tag=0,
            access_event_time=b"\x01",
            access_credential=b"\x02",
        )
        d = variant.to_dict()
        assert d["type"] == "access-event"
        assert "authentication_factor" not in d
        restored = AccessEvent.from_dict(d)
        assert restored == variant

    def test_to_dict_from_dict_with_auth(self):
        variant = AccessEvent(
            access_event=3,
            access_event_tag=2,
            access_event_time=b"\xab",
            access_credential=b"\xcd",
            authentication_factor=b"\xef",
        )
        d = variant.to_dict()
        assert "authentication_factor" in d
        restored = AccessEvent.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert AccessEvent.TAG == 13


# ---------------------------------------------------------------------------
# DoubleOutOfRange (TAG=14)
# ---------------------------------------------------------------------------


class TestDoubleOutOfRange:
    def test_round_trip_default(self):
        variant = DoubleOutOfRange()
        decoded = _round_trip(variant)
        assert isinstance(decoded, DoubleOutOfRange)

    def test_round_trip_realistic(self):
        variant = DoubleOutOfRange(
            exceeding_value=1.23456789012345e10,
            status_flags=_make_status_flags(overridden=True),
            deadband=0.001,
            exceeded_limit=1.0e10,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, DoubleOutOfRange)
        assert decoded.exceeding_value == pytest.approx(1.23456789012345e10)
        assert decoded.deadband == pytest.approx(0.001)
        assert decoded.exceeded_limit == pytest.approx(1.0e10)
        assert decoded.status_flags.overridden is True

    def test_to_dict_from_dict(self):
        variant = DoubleOutOfRange(
            exceeding_value=99.99,
            deadband=0.5,
            exceeded_limit=95.0,
        )
        d = variant.to_dict()
        assert d["type"] == "double-out-of-range"
        restored = DoubleOutOfRange.from_dict(d)
        assert restored.exceeding_value == pytest.approx(99.99)

    def test_tag_number(self):
        assert DoubleOutOfRange.TAG == 14


# ---------------------------------------------------------------------------
# SignedOutOfRange (TAG=15)
# ---------------------------------------------------------------------------


class TestSignedOutOfRange:
    def test_round_trip_default(self):
        variant = SignedOutOfRange()
        decoded = _round_trip(variant)
        assert isinstance(decoded, SignedOutOfRange)

    def test_round_trip_realistic(self):
        variant = SignedOutOfRange(
            exceeding_value=-50,
            status_flags=_make_status_flags(in_alarm=True),
            deadband=5,
            exceeded_limit=-40,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, SignedOutOfRange)
        assert decoded.exceeding_value == -50
        assert decoded.deadband == 5
        assert decoded.exceeded_limit == -40

    def test_round_trip_positive_values(self):
        variant = SignedOutOfRange(
            exceeding_value=120,
            deadband=10,
            exceeded_limit=100,
        )
        decoded = _round_trip(variant)
        assert decoded.exceeding_value == 120
        assert decoded.exceeded_limit == 100

    def test_to_dict_from_dict(self):
        variant = SignedOutOfRange(
            exceeding_value=-10,
            deadband=2,
            exceeded_limit=-5,
        )
        d = variant.to_dict()
        assert d["type"] == "signed-out-of-range"
        restored = SignedOutOfRange.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert SignedOutOfRange.TAG == 15


# ---------------------------------------------------------------------------
# UnsignedOutOfRange (TAG=16)
# ---------------------------------------------------------------------------


class TestUnsignedOutOfRange:
    def test_round_trip_default(self):
        variant = UnsignedOutOfRange()
        decoded = _round_trip(variant)
        assert isinstance(decoded, UnsignedOutOfRange)

    def test_round_trip_realistic(self):
        variant = UnsignedOutOfRange(
            exceeding_value=300,
            status_flags=_make_status_flags(in_alarm=True, out_of_service=True),
            deadband=10,
            exceeded_limit=250,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, UnsignedOutOfRange)
        assert decoded.exceeding_value == 300
        assert decoded.deadband == 10
        assert decoded.exceeded_limit == 250
        assert decoded.status_flags.out_of_service is True

    def test_to_dict_from_dict(self):
        variant = UnsignedOutOfRange(
            exceeding_value=1000,
            deadband=50,
            exceeded_limit=900,
        )
        d = variant.to_dict()
        assert d["type"] == "unsigned-out-of-range"
        restored = UnsignedOutOfRange.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert UnsignedOutOfRange.TAG == 16


# ---------------------------------------------------------------------------
# ChangeOfCharacterstring (TAG=17)
# ---------------------------------------------------------------------------


class TestChangeOfCharacterstring:
    def test_round_trip_default(self):
        variant = ChangeOfCharacterstring()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfCharacterstring)
        assert decoded.changed_value == ""
        assert decoded.alarm_value == ""

    def test_round_trip_realistic(self):
        variant = ChangeOfCharacterstring(
            changed_value="RUNNING",
            status_flags=_make_status_flags(in_alarm=True),
            alarm_value="STOPPED",
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfCharacterstring)
        assert decoded.changed_value == "RUNNING"
        assert decoded.alarm_value == "STOPPED"
        assert decoded.status_flags.in_alarm is True

    def test_round_trip_unicode(self):
        variant = ChangeOfCharacterstring(
            changed_value="temp\u00e9rature",
            alarm_value="\u00e9lev\u00e9",
        )
        decoded = _round_trip(variant)
        assert decoded.changed_value == "temp\u00e9rature"
        assert decoded.alarm_value == "\u00e9lev\u00e9"

    def test_to_dict_from_dict(self):
        variant = ChangeOfCharacterstring(
            changed_value="ACTIVE",
            alarm_value="ALARM",
        )
        d = variant.to_dict()
        assert d["type"] == "change-of-characterstring"
        restored = ChangeOfCharacterstring.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfCharacterstring.TAG == 17


# ---------------------------------------------------------------------------
# ChangeOfStatusFlags (TAG=18)
# ---------------------------------------------------------------------------


class TestChangeOfStatusFlags:
    def test_round_trip_default(self):
        variant = ChangeOfStatusFlags()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfStatusFlags)
        assert decoded.present_value == b""

    def test_round_trip_realistic(self):
        variant = ChangeOfStatusFlags(
            present_value=b"\x44\x42\x48\x00\x00",
            referenced_flags=_make_status_flags(fault=True, overridden=True),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfStatusFlags)
        assert decoded.present_value == b"\x44\x42\x48\x00\x00"
        assert decoded.referenced_flags.fault is True
        assert decoded.referenced_flags.overridden is True

    def test_to_dict_from_dict(self):
        variant = ChangeOfStatusFlags(
            present_value=b"\x01\x02",
            referenced_flags=_make_status_flags(in_alarm=True),
        )
        d = variant.to_dict()
        assert d["type"] == "change-of-status-flags"
        restored = ChangeOfStatusFlags.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfStatusFlags.TAG == 18


# ---------------------------------------------------------------------------
# ChangeOfReliability (TAG=19)
# ---------------------------------------------------------------------------


class TestChangeOfReliability:
    def test_round_trip_default(self):
        variant = ChangeOfReliability()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfReliability)
        assert decoded.reliability == Reliability.NO_FAULT_DETECTED

    def test_round_trip_realistic(self):
        # Use valid BACnet app-tagged data for property_values
        pv = b"\x21\x55\x91\x03"  # unsigned 0x55, enumerated 3
        variant = ChangeOfReliability(
            reliability=Reliability.COMMUNICATION_FAILURE,
            status_flags=_make_status_flags(fault=True),
            property_values=pv,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfReliability)
        assert decoded.reliability == Reliability.COMMUNICATION_FAILURE
        assert decoded.status_flags.fault is True
        assert decoded.property_values == pv

    def test_to_dict_from_dict(self):
        variant = ChangeOfReliability(
            reliability=Reliability.OPEN_LOOP,
            property_values=b"\xab",
        )
        d = variant.to_dict()
        assert d["type"] == "change-of-reliability"
        assert d["reliability"] == Reliability.OPEN_LOOP.value
        restored = ChangeOfReliability.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfReliability.TAG == 19


# ---------------------------------------------------------------------------
# NoneParams (TAG=20)
# ---------------------------------------------------------------------------


class TestNoneParams:
    def test_round_trip(self):
        variant = NoneParams()
        decoded = _round_trip(variant)
        assert isinstance(decoded, NoneParams)

    def test_to_dict_from_dict(self):
        variant = NoneParams()
        d = variant.to_dict()
        assert d == {"type": "none"}
        restored = NoneParams.from_dict(d)
        assert isinstance(restored, NoneParams)

    def test_tag_number(self):
        assert NoneParams.TAG == 20


# ---------------------------------------------------------------------------
# ChangeOfDiscreteValue (TAG=21)
# ---------------------------------------------------------------------------


class TestChangeOfDiscreteValue:
    def test_round_trip_default(self):
        variant = ChangeOfDiscreteValue()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfDiscreteValue)
        assert decoded.new_value == b""

    def test_round_trip_realistic(self):
        variant = ChangeOfDiscreteValue(
            new_value=b"\x91\x03",
            status_flags=_make_status_flags(in_alarm=True),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfDiscreteValue)
        assert decoded.new_value == b"\x91\x03"
        assert decoded.status_flags.in_alarm is True

    def test_to_dict_from_dict(self):
        variant = ChangeOfDiscreteValue(new_value=b"\xaa\xbb")
        d = variant.to_dict()
        assert d["type"] == "change-of-discrete-value"
        restored = ChangeOfDiscreteValue.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfDiscreteValue.TAG == 21


# ---------------------------------------------------------------------------
# ChangeOfTimer (TAG=22)
# ---------------------------------------------------------------------------


class TestChangeOfTimer:
    def test_round_trip_required_fields_only(self):
        variant = ChangeOfTimer(
            new_state=TimerState.RUNNING,
            status_flags=StatusFlags(),
            update_time=_make_datetime(),
            last_state_change=TimerTransition.IDLE_TO_RUNNING,
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfTimer)
        assert decoded.new_state == TimerState.RUNNING
        assert decoded.last_state_change == TimerTransition.IDLE_TO_RUNNING
        assert decoded.initial_timeout is None
        assert decoded.expiration_time is None
        assert decoded.update_time.date.year == 2024
        assert decoded.update_time.time.hour == 9

    def test_round_trip_with_optional_fields(self):
        variant = ChangeOfTimer(
            new_state=TimerState.EXPIRED,
            status_flags=_make_status_flags(in_alarm=True),
            update_time=_make_datetime(),
            last_state_change=TimerTransition.RUNNING_TO_EXPIRED,
            initial_timeout=300,
            expiration_time=_make_datetime(h=14, m=30),
        )
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfTimer)
        assert decoded.new_state == TimerState.EXPIRED
        assert decoded.initial_timeout == 300
        assert decoded.expiration_time is not None
        assert decoded.expiration_time.time.hour == 14
        assert decoded.expiration_time.time.minute == 30

    def test_round_trip_with_initial_timeout_only(self):
        variant = ChangeOfTimer(
            new_state=TimerState.RUNNING,
            update_time=_make_datetime(),
            last_state_change=TimerTransition.EXPIRED_TO_RUNNING,
            initial_timeout=60,
        )
        decoded = _round_trip(variant)
        assert decoded.initial_timeout == 60
        assert decoded.expiration_time is None

    def test_round_trip_default_wildcard_datetime(self):
        variant = ChangeOfTimer()
        decoded = _round_trip(variant)
        assert isinstance(decoded, ChangeOfTimer)
        assert decoded.new_state == TimerState.IDLE
        assert decoded.update_time.date.year == 0xFF
        assert decoded.update_time.time.hour == 0xFF

    def test_to_dict_from_dict_without_optionals(self):
        variant = ChangeOfTimer(
            new_state=TimerState.RUNNING,
            update_time=_make_datetime(),
            last_state_change=TimerTransition.IDLE_TO_RUNNING,
        )
        d = variant.to_dict()
        assert d["type"] == "change-of-timer"
        assert "initial_timeout" not in d
        assert "expiration_time" not in d
        restored = ChangeOfTimer.from_dict(d)
        assert restored == variant

    def test_to_dict_from_dict_with_optionals(self):
        variant = ChangeOfTimer(
            new_state=TimerState.EXPIRED,
            update_time=_make_datetime(),
            last_state_change=TimerTransition.RUNNING_TO_EXPIRED,
            initial_timeout=120,
            expiration_time=_make_datetime(h=10, m=0),
        )
        d = variant.to_dict()
        assert "initial_timeout" in d
        assert "expiration_time" in d
        restored = ChangeOfTimer.from_dict(d)
        assert restored == variant

    def test_tag_number(self):
        assert ChangeOfTimer.TAG == 22


# ---------------------------------------------------------------------------
# RawNotificationParameters (reserved tags)
# ---------------------------------------------------------------------------


class TestRawNotificationParameters:
    def test_reserved_tag_6(self):
        # Use valid BACnet app-tagged data inside the reserved tag
        raw_content = b"\x21\x05"  # app-tagged unsigned, value 5
        wire = encode_opening_tag(6) + raw_content + encode_closing_tag(6)
        decoded, offset = decode_notification_parameters(memoryview(wire))
        assert isinstance(decoded, RawNotificationParameters)
        assert decoded.tag_number == 6
        assert decoded.raw_data == raw_content
        assert offset == len(wire)

    def test_reserved_tag_7(self):
        raw_content = b"\x91\x03"  # app-tagged enumerated, value 3
        wire = encode_opening_tag(7) + raw_content + encode_closing_tag(7)
        decoded, _offset = decode_notification_parameters(memoryview(wire))
        assert isinstance(decoded, RawNotificationParameters)
        assert decoded.tag_number == 7
        assert decoded.raw_data == raw_content

    def test_reserved_tag_12(self):
        raw_content = b"\x21\x01"  # app-tagged unsigned, value 1
        wire = encode_opening_tag(12) + raw_content + encode_closing_tag(12)
        decoded, _offset = decode_notification_parameters(memoryview(wire))
        assert isinstance(decoded, RawNotificationParameters)
        assert decoded.tag_number == 12

    def test_raw_round_trip(self):
        raw_content = b"\x21\x05"  # valid app-tagged unsigned
        raw = RawNotificationParameters(tag_number=6, raw_data=raw_content)
        encoded = raw.encode()
        decoded, _offset = decode_notification_parameters(memoryview(encoded))
        assert isinstance(decoded, RawNotificationParameters)
        assert decoded.tag_number == 6
        assert decoded.raw_data == raw_content

    def test_raw_to_dict_from_dict(self):
        raw = RawNotificationParameters(tag_number=7, raw_data=b"\xde\xad")
        d = raw.to_dict()
        assert d["type"] == "raw"
        assert d["tag_number"] == 7
        restored = RawNotificationParameters.from_dict(d)
        assert restored == raw

    def test_reserved_tag_empty_content(self):
        wire = encode_opening_tag(6) + encode_closing_tag(6)
        decoded, _offset = decode_notification_parameters(memoryview(wire))
        assert isinstance(decoded, RawNotificationParameters)
        assert decoded.tag_number == 6
        assert decoded.raw_data == b""


# ---------------------------------------------------------------------------
# Factory dispatch tests
# ---------------------------------------------------------------------------


class TestFactoryDispatch:
    """Verify decode_notification_parameters returns the correct subclass.

    Checks each known EventType / tag number.
    """

    DISPATCH_TABLE: ClassVar[list[tuple[type, int]]] = [
        (ChangeOfBitstring, 0),
        (ChangeOfState, 1),
        (ChangeOfValue, 2),
        (CommandFailure, 3),
        (FloatingLimit, 4),
        (OutOfRange, 5),
        (ChangeOfLifeSafety, 8),
        (Extended, 9),
        (BufferReady, 10),
        (UnsignedRange, 11),
        (AccessEvent, 13),
        (DoubleOutOfRange, 14),
        (SignedOutOfRange, 15),
        (UnsignedOutOfRange, 16),
        (ChangeOfCharacterstring, 17),
        (ChangeOfStatusFlags, 18),
        (ChangeOfReliability, 19),
        (NoneParams, 20),
        (ChangeOfDiscreteValue, 21),
        (ChangeOfTimer, 22),
    ]

    @pytest.mark.parametrize("cls, tag", DISPATCH_TABLE)
    def test_dispatch_returns_correct_class(self, cls, tag):
        """Each variant's encode -> decode round-trip returns the correct class."""
        variant = cls()
        encoded = variant.encode()
        decoded, _ = decode_notification_parameters(memoryview(encoded))
        assert isinstance(decoded, cls), (
            f"Expected {cls.__name__} for tag {tag}, got {type(decoded).__name__}"
        )

    @pytest.mark.parametrize("cls, tag", DISPATCH_TABLE)
    def test_tag_constant_matches(self, cls, tag):
        assert tag == cls.TAG


class TestNotificationParametersFromDict:
    """Verify notification_parameters_from_dict dispatches to correct variant."""

    TYPE_MAP: ClassVar[dict[str, type]] = {
        "change-of-bitstring": ChangeOfBitstring,
        "change-of-state": ChangeOfState,
        "change-of-value": ChangeOfValue,
        "command-failure": CommandFailure,
        "floating-limit": FloatingLimit,
        "out-of-range": OutOfRange,
        "change-of-life-safety": ChangeOfLifeSafety,
        "extended": Extended,
        "buffer-ready": BufferReady,
        "unsigned-range": UnsignedRange,
        "access-event": AccessEvent,
        "double-out-of-range": DoubleOutOfRange,
        "signed-out-of-range": SignedOutOfRange,
        "unsigned-out-of-range": UnsignedOutOfRange,
        "change-of-characterstring": ChangeOfCharacterstring,
        "change-of-status-flags": ChangeOfStatusFlags,
        "change-of-reliability": ChangeOfReliability,
        "none": NoneParams,
        "change-of-discrete-value": ChangeOfDiscreteValue,
        "change-of-timer": ChangeOfTimer,
        "raw": RawNotificationParameters,
    }

    def test_from_dict_out_of_range(self):
        d = OutOfRange(exceeding_value=85.0, deadband=1.0, exceeded_limit=80.0).to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, OutOfRange)
        assert result.exceeding_value == pytest.approx(85.0)

    def test_from_dict_none_params(self):
        d = NoneParams().to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, NoneParams)

    def test_from_dict_change_of_timer(self):
        variant = ChangeOfTimer(
            new_state=TimerState.RUNNING,
            update_time=_make_datetime(),
            last_state_change=TimerTransition.IDLE_TO_RUNNING,
            initial_timeout=60,
        )
        d = variant.to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, ChangeOfTimer)
        assert result.initial_timeout == 60

    def test_from_dict_raw(self):
        d = RawNotificationParameters(tag_number=6, raw_data=b"\x01").to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, RawNotificationParameters)
        assert result.tag_number == 6

    def test_from_dict_change_of_value_real(self):
        variant = ChangeOfValue(new_value_choice=1, new_value=42.5)
        d = variant.to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, ChangeOfValue)
        assert result.new_value_choice == 1

    def test_from_dict_change_of_value_bitstring(self):
        bs = BitString(b"\xa0", 5)
        variant = ChangeOfValue(new_value_choice=0, new_value=bs)
        d = variant.to_dict()
        result = notification_parameters_from_dict(d)
        assert isinstance(result, ChangeOfValue)
        assert result.new_value_choice == 0

    def test_from_dict_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            notification_parameters_from_dict({"type": "nonexistent-type"})

    def test_from_dict_empty_type_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            notification_parameters_from_dict({})

    def test_round_trip_all_variants_through_dict(self):
        """Every variant should survive to_dict -> from_dict."""
        variants = [
            ChangeOfBitstring(referenced_bitstring=BitString(b"\xa0", 5)),
            ChangeOfState(new_state=b"\x91\x01"),
            ChangeOfValue(new_value_choice=1, new_value=25.0),
            CommandFailure(command_value=b"\x01", feedback_value=b"\x02"),
            FloatingLimit(reference_value=10.0, setpoint_value=9.0, error_limit=1.0),
            OutOfRange(exceeding_value=50.0, deadband=1.0, exceeded_limit=45.0),
            ChangeOfLifeSafety(new_state=LifeSafetyState.ALARM, new_mode=LifeSafetyMode.ON),
            Extended(vendor_id=7, extended_event_type=1, parameters=b"\xab"),
            BufferReady(buffer_property=b"\x01", previous_notification=0, current_notification=5),
            UnsignedRange(exceeding_value=100, exceeded_limit=90),
            AccessEvent(
                access_event=1,
                access_event_tag=0,
                access_event_time=b"\x01",
                access_credential=b"\x02",
            ),
            DoubleOutOfRange(exceeding_value=1e10, deadband=0.1, exceeded_limit=9e9),
            SignedOutOfRange(exceeding_value=-10, deadband=2, exceeded_limit=-5),
            UnsignedOutOfRange(exceeding_value=200, deadband=10, exceeded_limit=190),
            ChangeOfCharacterstring(changed_value="ON", alarm_value="OFF"),
            ChangeOfStatusFlags(
                present_value=b"\x44", referenced_flags=StatusFlags(in_alarm=True)
            ),
            ChangeOfReliability(reliability=Reliability.OPEN_LOOP, property_values=b"\x01"),
            NoneParams(),
            ChangeOfDiscreteValue(new_value=b"\x91\x03"),
            ChangeOfTimer(
                new_state=TimerState.RUNNING,
                update_time=_make_datetime(),
                last_state_change=TimerTransition.IDLE_TO_RUNNING,
            ),
        ]
        for variant in variants:
            d = variant.to_dict()
            restored = notification_parameters_from_dict(d)
            assert type(restored) is type(variant), (
                f"Type mismatch for {type(variant).__name__}: got {type(restored).__name__}"
            )


# ---------------------------------------------------------------------------
# Integration with EventNotificationRequest
# ---------------------------------------------------------------------------


class TestEventNotificationIntegration:
    """Test NotificationParameters variants embedded in EventNotificationRequest."""

    def _make_request(self, event_values, event_type=EventType.OUT_OF_RANGE):
        return EventNotificationRequest(
            process_identifier=42,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=10),
            notification_class=5,
            priority=100,
            event_type=event_type,
            notify_type=NotifyType.ALARM,
            to_state=EventState.HIGH_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
            event_values=event_values,
        )

    def test_out_of_range_in_event_notification(self):
        params = OutOfRange(
            exceeding_value=85.5,
            status_flags=_make_status_flags(in_alarm=True),
            deadband=1.0,
            exceeded_limit=80.0,
        )
        req = self._make_request(params)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, OutOfRange)
        assert decoded.event_values.exceeding_value == pytest.approx(85.5)
        assert decoded.event_values.deadband == pytest.approx(1.0)
        assert decoded.event_values.exceeded_limit == pytest.approx(80.0)
        assert decoded.event_values.status_flags.in_alarm is True

    def test_floating_limit_in_event_notification(self):
        params = FloatingLimit(
            reference_value=72.5,
            status_flags=_make_status_flags(in_alarm=True),
            setpoint_value=70.0,
            error_limit=2.0,
        )
        req = self._make_request(params, event_type=EventType.FLOATING_LIMIT)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, FloatingLimit)
        assert decoded.event_values.reference_value == pytest.approx(72.5)

    def test_change_of_bitstring_in_event_notification(self):
        bs = BitString(b"\xf0", 4)
        params = ChangeOfBitstring(
            referenced_bitstring=bs,
            status_flags=StatusFlags(),
        )
        req = self._make_request(params, event_type=EventType.CHANGE_OF_BITSTRING)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, ChangeOfBitstring)
        assert decoded.event_values.referenced_bitstring == bs

    def test_none_params_in_event_notification(self):
        params = NoneParams()
        req = self._make_request(params, event_type=EventType.NONE)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, NoneParams)

    def test_change_of_timer_in_event_notification(self):
        params = ChangeOfTimer(
            new_state=TimerState.EXPIRED,
            status_flags=_make_status_flags(in_alarm=True),
            update_time=_make_datetime(),
            last_state_change=TimerTransition.RUNNING_TO_EXPIRED,
            initial_timeout=300,
        )
        req = self._make_request(params, event_type=EventType.CHANGE_OF_TIMER)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, ChangeOfTimer)
        assert decoded.event_values.new_state == TimerState.EXPIRED
        assert decoded.event_values.initial_timeout == 300

    def test_change_of_life_safety_in_event_notification(self):
        params = ChangeOfLifeSafety(
            new_state=LifeSafetyState.ALARM,
            new_mode=LifeSafetyMode.ON,
            status_flags=_make_status_flags(in_alarm=True),
            operation_expected=LifeSafetyOperation.SILENCE,
        )
        req = self._make_request(params, event_type=EventType.CHANGE_OF_LIFE_SAFETY)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, ChangeOfLifeSafety)
        assert decoded.event_values.new_state == LifeSafetyState.ALARM
        assert decoded.event_values.new_mode == LifeSafetyMode.ON
        assert decoded.event_values.operation_expected == LifeSafetyOperation.SILENCE

    def test_change_of_value_real_in_event_notification(self):
        params = ChangeOfValue(
            new_value_choice=1,
            new_value=42.5,
            status_flags=StatusFlags(),
        )
        req = self._make_request(params, event_type=EventType.CHANGE_OF_VALUE)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, ChangeOfValue)
        assert decoded.event_values.new_value_choice == 1
        assert decoded.event_values.new_value == pytest.approx(42.5)

    def test_double_out_of_range_in_event_notification(self):
        params = DoubleOutOfRange(
            exceeding_value=1e10,
            status_flags=_make_status_flags(in_alarm=True),
            deadband=0.001,
            exceeded_limit=9.5e9,
        )
        req = self._make_request(params, event_type=EventType.DOUBLE_OUT_OF_RANGE)
        encoded = req.encode()
        decoded = EventNotificationRequest.decode(encoded)

        assert isinstance(decoded.event_values, DoubleOutOfRange)
        assert decoded.event_values.exceeding_value == pytest.approx(1e10)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_decode_invalid_non_opening_tag(self):
        """Attempting to decode from data that doesn't start with an opening tag."""
        # A simple application-tagged byte (not an opening tag)
        with pytest.raises(ValueError, match="Expected opening tag"):
            decode_notification_parameters(memoryview(b"\x09\x01"))

    def test_from_dict_unknown_type_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown"):
            notification_parameters_from_dict({"type": "not-a-real-type"})

    def test_mismatched_closing_tag_raises(self):
        """Lines 1665-1669: mismatched closing tag raises ValueError."""
        # Encode an OutOfRange variant (tag 5), then replace closing tag 5 with tag 6
        variant = OutOfRange(
            exceeding_value=85.5,
            status_flags=StatusFlags(),
            deadband=1.0,
            exceeded_limit=80.0,
        )
        encoded = bytearray(variant.encode())
        # Find and replace the closing tag at the end
        # Closing tag for tag 5 is encoded as: 0x5F (tag 5, closing)
        # We need to replace it with closing tag 6: 0x6F
        assert encoded[-1] == 0x5F  # closing tag 5
        encoded[-1] = 0x6F  # closing tag 6
        with pytest.raises(ValueError, match="Expected closing tag"):
            decode_notification_parameters(memoryview(bytes(encoded)))


# ---------------------------------------------------------------------------
# Coverage: branch partials for optional fields in decode_inner
# ---------------------------------------------------------------------------


class TestAccessEventDecodeInnerNoTrailingData:
    """Branch 861->866: offset >= len(data) after mandatory fields.

    When decode_inner is called with data ending right after the
    access_credential closing tag, there's no data left to peek for
    authentication_factor, so the optional check is skipped entirely.
    """

    def test_no_data_after_mandatory_fields(self):
        from bac_py.encoding.primitives import (
            encode_context_enumerated,
            encode_context_tagged,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.types.notification_params import AccessEvent, _encode_sf

        # Build inner data for AccessEvent WITHOUT outer opening/closing tags
        # and WITHOUT authentication_factor, and WITHOUT trailing closing tag
        buf = bytearray()
        # [0] access_event
        buf.extend(encode_context_enumerated(0, 1))
        # [1] status_flags
        buf.extend(_encode_sf(1, StatusFlags()))
        # [2] access_event_tag
        buf.extend(encode_context_tagged(2, encode_unsigned(0)))
        # [3] access_event_time
        buf.extend(encode_opening_tag(3))
        buf.extend(b"\x21\x01")  # some inner data
        buf.extend(encode_closing_tag(3))
        # [4] access_credential
        buf.extend(encode_opening_tag(4))
        buf.extend(b"\x21\x02")  # some inner data
        buf.extend(encode_closing_tag(4))
        # NO trailing data -- offset will == len(data)

        data = memoryview(bytes(buf))
        result, offset = AccessEvent.decode_inner(data, 0)
        assert result.authentication_factor is None
        assert offset == len(data)


class TestChangeOfTimerDecodeInnerNoOptionals:
    """Branches 1463->1468, 1469->1479: offset >= len(data) after mandatory fields.

    When decode_inner is called with data ending right after
    last_state_change, there's no data left for initial_timeout
    or expiration_time.
    """

    def test_no_data_after_last_state_change(self):
        from bac_py.encoding.primitives import (
            encode_context_enumerated,
            encode_date,
            encode_time,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.types.notification_params import ChangeOfTimer, _encode_sf

        # Build inner data for ChangeOfTimer WITHOUT optional fields
        # and WITHOUT trailing closing tag
        buf = bytearray()
        # [0] new_state = IDLE (0)
        buf.extend(encode_context_enumerated(0, 0))
        # [1] status_flags
        buf.extend(_encode_sf(1, StatusFlags()))
        # [2] update_time (opening tag 2, date, time, closing tag 2)
        buf.extend(encode_opening_tag(2))
        buf.extend(encode_date(BACnetDate(2024, 1, 15, 1)))
        buf.extend(encode_time(BACnetTime(10, 30, 0, 0)))
        buf.extend(encode_closing_tag(2))
        # [3] last_state_change
        buf.extend(encode_context_enumerated(3, 0))
        # NO trailing data -- offset will == len(data)

        data = memoryview(bytes(buf))
        result, offset = ChangeOfTimer.decode_inner(data, 0)
        assert result.initial_timeout is None
        assert result.expiration_time is None
        assert offset == len(data)

    def test_initial_timeout_present_no_expiration(self):
        """Exercise the path where initial_timeout is present but data ends.

        Before expiration_time check (branch 1469->1479).
        """
        from bac_py.encoding.primitives import (
            encode_context_enumerated,
            encode_context_tagged,
            encode_date,
            encode_time,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.types.notification_params import ChangeOfTimer, _encode_sf

        buf = bytearray()
        # [0] new_state
        buf.extend(encode_context_enumerated(0, 1))  # RUNNING
        # [1] status_flags
        buf.extend(_encode_sf(1, StatusFlags()))
        # [2] update_time
        buf.extend(encode_opening_tag(2))
        buf.extend(encode_date(BACnetDate(2024, 6, 15, 3)))
        buf.extend(encode_time(BACnetTime(14, 30, 0, 0)))
        buf.extend(encode_closing_tag(2))
        # [3] last_state_change
        buf.extend(encode_context_enumerated(3, 1))
        # [4] initial_timeout = 60
        buf.extend(encode_context_tagged(4, encode_unsigned(60)))
        # NO expiration_time, NO trailing data

        data = memoryview(bytes(buf))
        result, offset = ChangeOfTimer.decode_inner(data, 0)
        assert result.initial_timeout == 60
        assert result.expiration_time is None
        assert offset == len(data)
