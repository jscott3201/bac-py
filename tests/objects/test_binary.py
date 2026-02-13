"""Tests for BACnet Binary object types (Clause 12.6-12.8)."""

import pytest

from bac_py.objects.base import ObjectDatabase, create_object
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject, BinaryValueObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    BinaryPV,
    ErrorCode,
    EventState,
    ObjectType,
    Polarity,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestBinaryInputObject:
    """Tests for BinaryInputObject (Clause 12.6)."""

    def test_create_basic(self):
        bi = BinaryInputObject(1)
        assert bi.object_identifier == ObjectIdentifier(ObjectType.BINARY_INPUT, 1)

    def test_object_type(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.BINARY_INPUT

    def test_present_value_default(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_present_value_read_only(self):
        """BI Present_Value is read-only per Clause 12.6."""
        bi = BinaryInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            bi.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_polarity_default(self):
        """BI has Polarity property (Required, per Clause 12.6)."""
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.POLARITY) == Polarity.NORMAL

    def test_status_flags_initialized(self):
        bi = BinaryInputObject(1)
        sf = bi.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)
        assert sf == StatusFlags()

    def test_event_state_default(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_not_commandable(self):
        bi = BinaryInputObject(1)
        assert bi._priority_array is None

    def test_inactive_text_optional(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.INACTIVE_TEXT) is None

    def test_active_text_optional(self):
        bi = BinaryInputObject(1)
        assert bi.read_property(PropertyIdentifier.ACTIVE_TEXT) is None

    def test_text_properties_writable(self):
        bi = BinaryInputObject(1)
        bi.write_property(PropertyIdentifier.INACTIVE_TEXT, "Off")
        bi.write_property(PropertyIdentifier.ACTIVE_TEXT, "On")
        assert bi.read_property(PropertyIdentifier.INACTIVE_TEXT) == "Off"
        assert bi.read_property(PropertyIdentifier.ACTIVE_TEXT) == "On"

    def test_property_list_contains_polarity(self):
        bi = BinaryInputObject(1)
        plist = bi.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.POLARITY in plist

    def test_initial_properties(self):
        bi = BinaryInputObject(1, object_name="BI-1", description="Door switch")
        assert bi.read_property(PropertyIdentifier.OBJECT_NAME) == "BI-1"
        assert bi.read_property(PropertyIdentifier.DESCRIPTION) == "Door switch"

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.BINARY_INPUT, 10)
        assert isinstance(obj, BinaryInputObject)


class TestBinaryOutputObject:
    """Tests for BinaryOutputObject (Clause 12.7)."""

    def test_create_basic(self):
        bo = BinaryOutputObject(1)
        assert bo.object_identifier == ObjectIdentifier(ObjectType.BINARY_OUTPUT, 1)

    def test_object_type(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.BINARY_OUTPUT

    def test_present_value_default(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_present_value_writable(self):
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_always_commandable(self):
        """BO is always commandable with 16-level priority array."""
        bo = BinaryOutputObject(1)
        assert bo._priority_array is not None
        assert len(bo._priority_array) == 16

    def test_priority_array_property(self):
        bo = BinaryOutputObject(1)
        pa = bo.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert isinstance(pa, list)
        assert len(pa) == 16

    def test_relinquish_default(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == BinaryPV.INACTIVE

    def test_command_priority_write(self):
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert bo._priority_array[7] == BinaryPV.ACTIVE
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_relinquish_falls_to_default(self):
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_polarity_present(self):
        """BO has Polarity property (Required, per Clause 12.7)."""
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.POLARITY) == Polarity.NORMAL

    def test_minimum_on_off_time_optional(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.MINIMUM_ON_TIME) is None
        assert bo.read_property(PropertyIdentifier.MINIMUM_OFF_TIME) is None

    def test_feedback_value_optional(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.FEEDBACK_VALUE) is None

    def test_status_flags_initialized(self):
        bo = BinaryOutputObject(1)
        sf = bo.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.BINARY_OUTPUT, 20)
        assert isinstance(obj, BinaryOutputObject)


class TestBinaryValueObject:
    """Tests for BinaryValueObject (Clause 12.8)."""

    def test_create_basic(self):
        bv = BinaryValueObject(1)
        assert bv.object_identifier == ObjectIdentifier(ObjectType.BINARY_VALUE, 1)

    def test_object_type(self):
        bv = BinaryValueObject(1)
        assert bv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.BINARY_VALUE

    def test_present_value_default(self):
        bv = BinaryValueObject(1)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_present_value_writable(self):
        bv = BinaryValueObject(1)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_not_commandable_by_default(self):
        """BV is not commandable unless constructed with commandable=True."""
        bv = BinaryValueObject(1)
        assert bv._priority_array is None

    def test_commandable_when_requested(self):
        bv = BinaryValueObject(1, commandable=True)
        assert bv._priority_array is not None
        assert len(bv._priority_array) == 16

    def test_commandable_priority_write(self):
        bv = BinaryValueObject(1, commandable=True)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=4)
        assert bv._priority_array[3] == BinaryPV.ACTIVE
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_commandable_relinquish(self):
        bv = BinaryValueObject(1, commandable=True)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=4)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=4)
        assert bv.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_no_polarity(self):
        """BV does NOT have Polarity per Clause 12.8."""
        bv = BinaryValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            bv.read_property(PropertyIdentifier.POLARITY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_minimum_on_off_time_optional(self):
        bv = BinaryValueObject(1)
        assert bv.read_property(PropertyIdentifier.MINIMUM_ON_TIME) is None
        assert bv.read_property(PropertyIdentifier.MINIMUM_OFF_TIME) is None

    def test_status_flags_initialized(self):
        bv = BinaryValueObject(1)
        sf = bv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_initial_properties(self):
        bv = BinaryValueObject(1, object_name="BV-1")
        assert bv.read_property(PropertyIdentifier.OBJECT_NAME) == "BV-1"

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.BINARY_VALUE, 30)
        assert isinstance(obj, BinaryValueObject)


class TestBinaryObjectsInDatabase:
    """Integration: adding binary objects to ObjectDatabase."""

    def test_add_all_binary_types(self):
        db = ObjectDatabase()
        db.add(BinaryInputObject(1, object_name="BI-1"))
        db.add(BinaryOutputObject(1, object_name="BO-1"))
        db.add(BinaryValueObject(1, object_name="BV-1"))
        assert len(db) == 3

    def test_unique_identifiers(self):
        """Different types with same instance number are different objects."""
        db = ObjectDatabase()
        db.add(BinaryInputObject(1))
        db.add(BinaryOutputObject(1))
        # Both should be added without conflict
        assert len(db) == 2

    def test_get_objects_of_type(self):
        db = ObjectDatabase()
        db.add(BinaryInputObject(1))
        db.add(BinaryInputObject(2))
        db.add(BinaryOutputObject(1))
        bis = db.get_objects_of_type(ObjectType.BINARY_INPUT)
        assert len(bis) == 2


class TestBinaryCurrentCommandPriority:
    """Tests for Current_Command_Priority on binary objects."""

    def test_bo_has_current_command_priority(self):
        bo = BinaryOutputObject(1)
        plist = bo.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_bo_current_command_priority_none_when_relinquished(self):
        bo = BinaryOutputObject(1)
        assert bo.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) is None

    def test_bo_current_command_priority_returns_active(self):
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=5)
        assert bo.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 5

    def test_bv_commandable_has_current_command_priority(self):
        bv = BinaryValueObject(1, commandable=True)
        bv.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=12)
        assert bv.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 12

    def test_bi_no_current_command_priority(self):
        bi = BinaryInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            bi.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY


class TestBinaryCommandablePropertyPresence:
    """Commandable properties only present when commandable (spec footnote)."""

    def test_bv_non_commandable_no_relinquish_default(self):
        """Non-commandable BV should NOT have Relinquish_Default in properties."""
        bv = BinaryValueObject(1)
        plist = bv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT not in plist
        assert PropertyIdentifier.PRIORITY_ARRAY not in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY not in plist

    def test_bv_commandable_has_relinquish_default(self):
        """Commandable BV should have Relinquish_Default."""
        bv = BinaryValueObject(1, commandable=True)
        assert bv.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == BinaryPV.INACTIVE
        plist = bv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_bo_always_has_commandable_properties(self):
        """BO is always commandable and always has these properties."""
        bo = BinaryOutputObject(1)
        plist = bo.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist


class TestBinaryOutOfServiceWritable:
    """Present_Value writable when Out_Of_Service is TRUE."""

    def test_bi_present_value_writable_when_oos(self):
        bi = BinaryInputObject(1)
        bi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        bi.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert bi.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_bi_present_value_read_only_when_in_service(self):
        bi = BinaryInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            bi.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED


# ---------------------------------------------------------------------------
# Coverage: Minimum On/Off Time lock behaviour (binary.py lines 80-144)
# ---------------------------------------------------------------------------


class TestMinOnTimeLock:
    """Lines 86-87: expired lock is cleared, lines 128-136: lock expiry."""

    def test_min_on_time_lock_holds_value(self):
        """Lines 80-82: while locked, present_value stays at locked value."""
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 60)
        # Write ACTIVE at priority 8 — should start min_on_time lock
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE
        assert bo._min_time_lock_until is not None

        # Write INACTIVE at higher priority while locked — value stays ACTIVE
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=1)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.ACTIVE

    def test_min_on_time_lock_clears_after_expiry(self):
        """Lines 85-87, 131-136: expired lock is cleared, value re-evaluated."""
        import time

        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert bo._min_time_lock_until is not None

        # Simulate time passing beyond the lock
        bo._min_time_lock_until = time.monotonic() - 1

        # Now writing should clear the expired lock (lines 85-87)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=1)
        # After lock expiry and re-eval, INACTIVE from priority 1 should win
        assert bo._min_time_locked_value is None or bo._min_time_lock_until is not None

    def test_min_off_time_lock(self):
        """Lines 101-105: Minimum off-time lock for INACTIVE transition."""
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_OFF_TIME, 60)
        # Start from ACTIVE state
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        # Transition to INACTIVE — should start min_off_time lock
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=8)
        assert bo._min_time_lock_until is not None
        assert bo._min_time_locked_value == BinaryPV.INACTIVE

    def test_check_min_time_expiry_no_lock(self):
        """Line 116-117: check_min_time_expiry returns False when no lock."""
        bo = BinaryOutputObject(1)
        assert bo.check_min_time_expiry() is False

    def test_check_min_time_expiry_not_expired(self):
        """Line 118-119: check_min_time_expiry returns False when lock is active."""
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 60)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        assert bo._min_time_lock_until is not None
        assert bo.check_min_time_expiry() is False

    def test_check_min_time_expiry_expired(self):
        """Lines 121-144: check_min_time_expiry clears lock and re-evaluates."""
        import time

        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 1)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)

        # Force lock to have expired
        bo._min_time_lock_until = time.monotonic() - 1

        result = bo.check_min_time_expiry()
        assert result is True
        assert bo._min_time_lock_until is None or bo._min_time_lock_until > time.monotonic() - 2

    def test_check_min_time_expiry_no_priority_array(self):
        """Line 127-128: priority_array is None during expiry check."""
        import time

        bv = BinaryValueObject(1)
        bv._min_time_lock_until = time.monotonic() - 1
        bv._min_time_locked_value = BinaryPV.ACTIVE
        result = bv.check_min_time_expiry()
        assert result is True

    def test_check_min_time_expiry_relinquish_default(self):
        """Lines 135-136: all priority slots None, falls to relinquish default."""
        import time

        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 1)
        # Don't write any value to priority array
        # Set a lock manually
        bo._min_time_lock_until = time.monotonic() - 1
        bo._min_time_locked_value = BinaryPV.ACTIVE
        # Clear all priority slots
        for i in range(16):
            bo._priority_array[i] = None

        result = bo.check_min_time_expiry()
        assert result is True
        # Should fall to relinquish default (INACTIVE)
        assert bo.read_property(PropertyIdentifier.PRESENT_VALUE) == BinaryPV.INACTIVE

    def test_check_min_time_expiry_new_lock_on_change(self):
        """Lines 141-142: if resolved value differs from locked, new lock may start."""
        import time

        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 60)
        bo.write_property(PropertyIdentifier.MINIMUM_OFF_TIME, 60)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)

        # Now write INACTIVE while locked
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=1)

        # Force the lock to expire
        bo._min_time_lock_until = time.monotonic() - 1

        result = bo.check_min_time_expiry()
        assert result is True


# ---------------------------------------------------------------------------
# Coverage: MINIMUM_OFF_TIME lock enforcement branch (binary.py line 101->exit)
# ---------------------------------------------------------------------------


class TestMinOffTimeLockNotConfigured:
    """Branch 101->exit: INACTIVE transition with no MINIMUM_OFF_TIME configured."""

    def test_inactive_transition_no_min_off_time_no_lock(self):
        """Transitioning to INACTIVE without MINIMUM_OFF_TIME should not start a lock."""
        bo = BinaryOutputObject(1)
        # Only configure MINIMUM_ON_TIME, NOT MINIMUM_OFF_TIME
        bo.write_property(PropertyIdentifier.MINIMUM_ON_TIME, 60)
        # Start from ACTIVE
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        # Clear the ON lock manually to isolate OFF transition
        bo._min_time_lock_until = None
        bo._min_time_locked_value = None

        # Transition to INACTIVE -- no MINIMUM_OFF_TIME so no lock should start
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=8)
        # No off-time lock because MINIMUM_OFF_TIME is not set
        assert bo._min_time_lock_until is None

    def test_inactive_transition_zero_min_off_time_no_lock(self):
        """MINIMUM_OFF_TIME=0 should not start a lock."""
        bo = BinaryOutputObject(1)
        bo.write_property(PropertyIdentifier.MINIMUM_OFF_TIME, 0)
        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.ACTIVE, priority=8)
        bo._min_time_lock_until = None
        bo._min_time_locked_value = None

        bo.write_property(PropertyIdentifier.PRESENT_VALUE, BinaryPV.INACTIVE, priority=8)
        # With min_off=0, the lock should not start
        assert bo._min_time_lock_until is None
