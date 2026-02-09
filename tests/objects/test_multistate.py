"""Tests for BACnet Multi-State object types (Clause 12.18-12.20)."""

import pytest

from bac_py.objects.base import ObjectDatabase, create_object
from bac_py.objects.multistate import (
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
)
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestMultiStateInputObject:
    """Tests for MultiStateInputObject (Clause 12.18)."""

    def test_create_basic(self):
        msi = MultiStateInputObject(1)
        assert msi.object_identifier == ObjectIdentifier(ObjectType.MULTI_STATE_INPUT, 1)

    def test_object_type(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.MULTI_STATE_INPUT

    def test_present_value_default(self):
        """Present_Value is a 1-based unsigned integer, defaulting to 1."""
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.PRESENT_VALUE) == 1

    def test_present_value_read_only(self):
        """MSI Present_Value is read-only per Clause 12.18."""
        msi = MultiStateInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            msi.write_property(PropertyIdentifier.PRESENT_VALUE, 2)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_number_of_states_default(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 2

    def test_number_of_states_custom(self):
        msi = MultiStateInputObject(1, number_of_states=5)
        assert msi.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 5

    def test_state_text_optional(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.STATE_TEXT) is None

    def test_state_text_writable(self):
        msi = MultiStateInputObject(1, number_of_states=3)
        msi.write_property(PropertyIdentifier.STATE_TEXT, ["Off", "Low", "High"])
        assert msi.read_property(PropertyIdentifier.STATE_TEXT) == ["Off", "Low", "High"]

    def test_status_flags_initialized(self):
        msi = MultiStateInputObject(1)
        sf = msi.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)
        assert sf == StatusFlags()

    def test_event_state_default(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        msi = MultiStateInputObject(1)
        assert msi.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_not_commandable(self):
        msi = MultiStateInputObject(1)
        assert msi._priority_array is None

    def test_initial_properties(self):
        msi = MultiStateInputObject(1, object_name="MSI-1")
        assert msi.read_property(PropertyIdentifier.OBJECT_NAME) == "MSI-1"

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.MULTI_STATE_INPUT, 1)
        assert isinstance(obj, MultiStateInputObject)


class TestMultiStateOutputObject:
    """Tests for MultiStateOutputObject (Clause 12.19)."""

    def test_create_basic(self):
        mso = MultiStateOutputObject(1)
        assert mso.object_identifier == ObjectIdentifier(ObjectType.MULTI_STATE_OUTPUT, 1)

    def test_object_type(self):
        mso = MultiStateOutputObject(1)
        assert mso.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.MULTI_STATE_OUTPUT

    def test_present_value_default(self):
        mso = MultiStateOutputObject(1)
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 1

    def test_present_value_writable(self):
        mso = MultiStateOutputObject(1, number_of_states=5)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 3

    def test_always_commandable(self):
        """MSO is always commandable with 16-level priority array."""
        mso = MultiStateOutputObject(1)
        assert mso._priority_array is not None
        assert len(mso._priority_array) == 16

    def test_priority_array_property(self):
        mso = MultiStateOutputObject(1)
        pa = mso.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert isinstance(pa, list)
        assert len(pa) == 16

    def test_relinquish_default(self):
        mso = MultiStateOutputObject(1)
        assert mso.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 1

    def test_command_priority_write(self):
        mso = MultiStateOutputObject(1, number_of_states=5)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 5, priority=8)
        assert mso._priority_array[7] == 5
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 5

    def test_command_higher_priority_wins(self):
        mso = MultiStateOutputObject(1, number_of_states=5)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 2, priority=16)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 4, priority=8)
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 4

    def test_relinquish_falls_to_default(self):
        mso = MultiStateOutputObject(1, number_of_states=5)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 3, priority=8)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 1

    def test_number_of_states_default(self):
        mso = MultiStateOutputObject(1)
        assert mso.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 2

    def test_number_of_states_custom(self):
        mso = MultiStateOutputObject(1, number_of_states=10)
        assert mso.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 10

    def test_status_flags_initialized(self):
        mso = MultiStateOutputObject(1)
        sf = mso.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.MULTI_STATE_OUTPUT, 2)
        assert isinstance(obj, MultiStateOutputObject)


class TestMultiStateValueObject:
    """Tests for MultiStateValueObject (Clause 12.20)."""

    def test_create_basic(self):
        msv = MultiStateValueObject(1)
        assert msv.object_identifier == ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 1)

    def test_object_type(self):
        msv = MultiStateValueObject(1)
        assert msv.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.MULTI_STATE_VALUE

    def test_present_value_default(self):
        msv = MultiStateValueObject(1)
        assert msv.read_property(PropertyIdentifier.PRESENT_VALUE) == 1

    def test_present_value_writable(self):
        msv = MultiStateValueObject(1, number_of_states=5)
        msv.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        assert msv.read_property(PropertyIdentifier.PRESENT_VALUE) == 3

    def test_not_commandable_by_default(self):
        """MSV is not commandable unless constructed with commandable=True."""
        msv = MultiStateValueObject(1)
        assert msv._priority_array is None

    def test_commandable_when_requested(self):
        msv = MultiStateValueObject(1, commandable=True)
        assert msv._priority_array is not None
        assert len(msv._priority_array) == 16

    def test_commandable_priority_write(self):
        msv = MultiStateValueObject(1, commandable=True, number_of_states=5)
        msv.write_property(PropertyIdentifier.PRESENT_VALUE, 4, priority=4)
        assert msv._priority_array[3] == 4
        assert msv.read_property(PropertyIdentifier.PRESENT_VALUE) == 4

    def test_commandable_relinquish(self):
        msv = MultiStateValueObject(1, commandable=True, number_of_states=5)
        msv.write_property(PropertyIdentifier.PRESENT_VALUE, 4, priority=4)
        msv.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=4)
        assert msv.read_property(PropertyIdentifier.PRESENT_VALUE) == 1

    def test_number_of_states_default(self):
        msv = MultiStateValueObject(1)
        assert msv.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 2

    def test_number_of_states_custom(self):
        msv = MultiStateValueObject(1, number_of_states=8)
        assert msv.read_property(PropertyIdentifier.NUMBER_OF_STATES) == 8

    def test_state_text_writable(self):
        msv = MultiStateValueObject(1, number_of_states=3)
        msv.write_property(PropertyIdentifier.STATE_TEXT, ["A", "B", "C"])
        assert msv.read_property(PropertyIdentifier.STATE_TEXT) == ["A", "B", "C"]

    def test_status_flags_initialized(self):
        msv = MultiStateValueObject(1)
        sf = msv.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_initial_properties(self):
        msv = MultiStateValueObject(1, object_name="MSV-1")
        assert msv.read_property(PropertyIdentifier.OBJECT_NAME) == "MSV-1"

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.MULTI_STATE_VALUE, 3)
        assert isinstance(obj, MultiStateValueObject)


class TestMultiStateObjectsInDatabase:
    """Integration: multi-state objects in ObjectDatabase."""

    def test_add_all_multistate_types(self):
        db = ObjectDatabase()
        db.add(MultiStateInputObject(1, object_name="MSI-1"))
        db.add(MultiStateOutputObject(1, object_name="MSO-1"))
        db.add(MultiStateValueObject(1, object_name="MSV-1"))
        assert len(db) == 3

    def test_get_objects_of_type(self):
        db = ObjectDatabase()
        db.add(MultiStateInputObject(1))
        db.add(MultiStateInputObject(2))
        db.add(MultiStateOutputObject(1))
        msis = db.get_objects_of_type(ObjectType.MULTI_STATE_INPUT)
        assert len(msis) == 2
        msos = db.get_objects_of_type(ObjectType.MULTI_STATE_OUTPUT)
        assert len(msos) == 1

    def test_priority_6_allowed_for_multistate(self):
        """Priority 6 is only reserved for objects with Minimum On/Off Time.

        MultiState Output does not define those properties, so priority 6
        writes should succeed (Clause 19.2.3).
        """
        mso = MultiStateOutputObject(1)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 2, priority=6)
        assert mso.read_property(PropertyIdentifier.PRESENT_VALUE) == 2


class TestMultiStateCurrentCommandPriority:
    """Tests for Current_Command_Priority on multi-state objects."""

    def test_mso_has_current_command_priority(self):
        mso = MultiStateOutputObject(1)
        plist = mso.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_mso_current_command_priority_returns_active(self):
        mso = MultiStateOutputObject(1, number_of_states=5)
        mso.write_property(PropertyIdentifier.PRESENT_VALUE, 3, priority=7)
        assert mso.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 7

    def test_msv_commandable_has_current_command_priority(self):
        msv = MultiStateValueObject(1, commandable=True)
        msv.write_property(PropertyIdentifier.PRESENT_VALUE, 2, priority=15)
        assert msv.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 15

    def test_msi_no_current_command_priority(self):
        msi = MultiStateInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            msi.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY


class TestMultiStateCommandablePropertyPresence:
    """Commandable properties only present when commandable (spec footnote)."""

    def test_msv_non_commandable_no_relinquish_default(self):
        """Non-commandable MSV should NOT have Relinquish_Default in properties."""
        msv = MultiStateValueObject(1)
        plist = msv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT not in plist
        assert PropertyIdentifier.PRIORITY_ARRAY not in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY not in plist

    def test_msv_commandable_has_relinquish_default(self):
        """Commandable MSV should have Relinquish_Default."""
        msv = MultiStateValueObject(1, commandable=True)
        assert msv.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 1
        plist = msv.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_mso_always_has_commandable_properties(self):
        """MSO is always commandable and always has these properties."""
        mso = MultiStateOutputObject(1)
        plist = mso.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist


class TestMultiStateOutOfServiceWritable:
    """Present_Value writable when Out_Of_Service is TRUE."""

    def test_msi_present_value_writable_when_oos(self):
        msi = MultiStateInputObject(1, number_of_states=3)
        msi.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        msi.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        assert msi.read_property(PropertyIdentifier.PRESENT_VALUE) == 3

    def test_msi_present_value_read_only_when_in_service(self):
        msi = MultiStateInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            msi.write_property(PropertyIdentifier.PRESENT_VALUE, 2)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED
