"""Tests for Minimum On/Off Time enforcement (Clause 19.2)."""

import time
from unittest.mock import patch

from bac_py.objects.binary import BinaryOutputObject, BinaryValueObject
from bac_py.types.enums import BinaryPV, PropertyIdentifier

# ---------------------------------------------------------------------------
# BinaryOutputObject -- basic min-time enforcement
# ---------------------------------------------------------------------------


class TestMinOnTimeOutput:
    def test_lock_prevents_rapid_state_change(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 10  # 10 seconds

        # Write ACTIVE at priority 16
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        # Lock should be active now -- writing INACTIVE should be accepted
        # into priority array but present_value stays ACTIVE
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_no_lock_without_min_time(self):
        bo = BinaryOutputObject(1)
        # No MINIMUM_ON_TIME set

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE


class TestMinOffTimeOutput:
    def test_lock_prevents_rapid_state_change(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_OFF_TIME] = 10

        # Start ACTIVE, then go INACTIVE
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        bo._min_time_lock_until = None  # Clear any on-time lock

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

        # Now try to go back to ACTIVE -- should be locked
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE


# ---------------------------------------------------------------------------
# Lock expiry
# ---------------------------------------------------------------------------


class TestMinTimeLockExpiry:
    def test_check_expiry_re_evaluates(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 10

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        # Write INACTIVE while locked
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        # Simulate time passing by setting lock in the past
        bo._min_time_lock_until = time.monotonic() - 1

        # Check expiry should re-evaluate and pick up INACTIVE from priority array
        result = bo.check_min_time_expiry()
        assert result is True
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_check_expiry_returns_false_when_no_lock(self):
        bo = BinaryOutputObject(1)
        assert bo.check_min_time_expiry() is False

    def test_check_expiry_returns_false_when_still_locked(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 10

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        # Lock is still active (10 seconds from now)
        assert bo.check_min_time_expiry() is False


# ---------------------------------------------------------------------------
# Lock start with mocked time
# ---------------------------------------------------------------------------


class TestMinTimeLockStart:
    def test_lock_duration_matches_min_on_time(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 30  # 30 seconds

        fake_now = 1000.0
        with patch("bac_py.objects.binary.time.monotonic", return_value=fake_now):
            bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)

        assert bo._min_time_lock_until == 1030.0
        assert bo._min_time_locked_value == BinaryPV.ACTIVE

    def test_lock_duration_matches_min_off_time(self):
        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_OFF_TIME] = 20

        # First go ACTIVE
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        bo._min_time_lock_until = None  # Clear on-time lock

        fake_now = 2000.0
        with patch("bac_py.objects.binary.time.monotonic", return_value=fake_now):
            bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)

        assert bo._min_time_lock_until == 2020.0
        assert bo._min_time_locked_value == BinaryPV.INACTIVE


# ---------------------------------------------------------------------------
# BinaryValueObject (commandable mode)
# ---------------------------------------------------------------------------


class TestMinTimeBinaryValue:
    def test_commandable_binary_value_enforces_min_time(self):
        bv = BinaryValueObject(1, commandable=True)
        bv._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 10

        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=16)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=16)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_non_commandable_binary_value_no_min_time(self):
        bv = BinaryValueObject(1, commandable=False)
        # Non-commandable doesn't use priority array, so min-time
        # enforcement via _write_with_priority doesn't apply
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE


# ---------------------------------------------------------------------------
# Priority 6 rejection
# ---------------------------------------------------------------------------


class TestPriority6Rejection:
    def test_priority_6_rejected_when_min_time_defined(self):
        import pytest

        from bac_py.services.errors import BACnetError

        bo = BinaryOutputObject(1)
        bo._properties[PropertyIdentifier.MINIMUM_ON_TIME] = 10

        with pytest.raises(BACnetError):
            bo.write_property(
                PropertyIdentifier.PRESENT_VALUE,
                BinaryPV.ACTIVE,
                priority=6,
            )
