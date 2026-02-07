"""Tests for BACnet Analog object types (Clause 12.2-12.4)."""

import asyncio

import pytest

from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.base import ObjectDatabase, create_object
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    EngineeringUnits,
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestAnalogInputObject:
    """Tests for AnalogInputObject (Clause 12.2)."""

    def test_create_basic(self):
        ai = AnalogInputObject(1)
        assert ai.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

    def test_object_type(self):
        ai = AnalogInputObject(1)
        assert ai.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.ANALOG_INPUT

    def test_present_value_default(self):
        ai = AnalogInputObject(1)
        assert ai.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_present_value_read_only(self):
        """AI Present_Value is read-only per Clause 12.2."""
        ai = AnalogInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ai.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_units_default(self):
        ai = AnalogInputObject(1)
        assert ai.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_units_writable(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.UNITS, EngineeringUnits.DEGREES_CELSIUS)
        assert ai.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.DEGREES_CELSIUS

    def test_status_flags_initialized(self):
        ai = AnalogInputObject(1)
        sf = ai.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)
        assert sf == StatusFlags()

    def test_event_state_default(self):
        ai = AnalogInputObject(1)
        assert ai.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        ai = AnalogInputObject(1)
        assert ai.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_out_of_service_writable(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        assert ai.read_property(PropertyIdentifier.OUT_OF_SERVICE) is True

    def test_description_optional(self):
        ai = AnalogInputObject(1)
        # Description is optional, should return None
        assert ai.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_description_writable(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.DESCRIPTION, "Room Temp")
        assert ai.read_property(PropertyIdentifier.DESCRIPTION) == "Room Temp"

    def test_initial_properties(self):
        ai = AnalogInputObject(1, object_name="AI-1", description="Test sensor")
        assert ai.read_property(PropertyIdentifier.OBJECT_NAME) == "AI-1"
        assert ai.read_property(PropertyIdentifier.DESCRIPTION) == "Test sensor"

    def test_not_commandable(self):
        """AI must not have a priority array."""
        ai = AnalogInputObject(1)
        assert ai._priority_array is None

    def test_property_list_contains_required(self):
        ai = AnalogInputObject(1)
        plist = ai.read_property(PropertyIdentifier.PROPERTY_LIST)
        # Spec excludes Object_Identifier, Object_Name, Object_Type, Property_List
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist
        assert PropertyIdentifier.OBJECT_NAME not in plist
        assert PropertyIdentifier.OBJECT_TYPE not in plist
        assert PropertyIdentifier.PROPERTY_LIST not in plist
        # Other required properties should be present
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.UNITS in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist

    def test_unknown_property_raises(self):
        ai = AnalogInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ai.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_factory_creation(self):
        """AnalogInputObject must be registered in the factory."""
        # Ensure the module is imported
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.ANALOG_INPUT, 5)
        assert isinstance(obj, AnalogInputObject)
        assert obj.object_identifier.instance_number == 5


class TestAnalogOutputObject:
    """Tests for AnalogOutputObject (Clause 12.3)."""

    def test_create_basic(self):
        ao = AnalogOutputObject(1)
        assert ao.object_identifier == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)

    def test_object_type(self):
        ao = AnalogOutputObject(1)
        assert ao.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.ANALOG_OUTPUT

    def test_present_value_default(self):
        ao = AnalogOutputObject(1)
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_present_value_writable(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 72.5)
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.5

    def test_always_commandable(self):
        """AO is always commandable with a 16-level priority array."""
        ao = AnalogOutputObject(1)
        assert ao._priority_array is not None
        assert len(ao._priority_array) == 16

    def test_priority_array_property(self):
        ao = AnalogOutputObject(1)
        pa = ao.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert isinstance(pa, list)
        assert len(pa) == 16

    def test_relinquish_default(self):
        ao = AnalogOutputObject(1)
        assert ao.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 0.0

    def test_command_priority_16_default(self):
        """Write without explicit priority should go to priority 16."""
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0)
        assert ao._priority_array[15] == 50.0

    def test_command_higher_priority_wins(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0, priority=16)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0, priority=8)
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 20.0

    def test_relinquish_all_falls_to_default(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0, priority=8)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_units_default(self):
        ao = AnalogOutputObject(1)
        assert ao.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_status_flags_initialized(self):
        ao = AnalogOutputObject(1)
        sf = ao.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.ANALOG_OUTPUT, 3)
        assert isinstance(obj, AnalogOutputObject)


class TestAnalogValueObject:
    """Tests for AnalogValueObject (Clause 12.4)."""

    def test_create_basic(self):
        av = AnalogValueObject(1)
        assert av.object_identifier == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

    def test_object_type(self):
        av = AnalogValueObject(1)
        assert av.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.ANALOG_VALUE

    def test_present_value_default(self):
        av = AnalogValueObject(1)
        assert av.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_present_value_writable(self):
        av = AnalogValueObject(1)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 100.0)
        assert av.read_property(PropertyIdentifier.PRESENT_VALUE) == 100.0

    def test_not_commandable_by_default(self):
        """AV is not commandable unless constructed with commandable=True."""
        av = AnalogValueObject(1)
        assert av._priority_array is None

    def test_commandable_when_requested(self):
        av = AnalogValueObject(1, commandable=True)
        assert av._priority_array is not None
        assert len(av._priority_array) == 16

    def test_commandable_priority_write(self):
        av = AnalogValueObject(1, commandable=True)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 55.0, priority=4)
        assert av._priority_array[3] == 55.0
        assert av.read_property(PropertyIdentifier.PRESENT_VALUE) == 55.0

    def test_commandable_relinquish(self):
        av = AnalogValueObject(1, commandable=True)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 55.0, priority=4)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=4)
        # Falls back to relinquish default
        assert av.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_non_commandable_ignores_priority(self):
        """Non-commandable AV should write directly, ignoring priority."""
        av = AnalogValueObject(1)
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0, priority=8)
        # Value written directly since not commandable
        assert av.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0

    def test_units_default(self):
        av = AnalogValueObject(1)
        assert av.read_property(PropertyIdentifier.UNITS) == EngineeringUnits.NO_UNITS

    def test_status_flags_initialized(self):
        av = AnalogValueObject(1)
        sf = av.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.ANALOG_VALUE, 7)
        assert isinstance(obj, AnalogValueObject)


class TestAnalogObjectsInDatabase:
    """Integration: adding analog objects to ObjectDatabase."""

    def test_add_multiple_types(self):
        db = ObjectDatabase()
        ai = AnalogInputObject(1, object_name="AI-1")
        ao = AnalogOutputObject(1, object_name="AO-1")
        av = AnalogValueObject(1, object_name="AV-1")
        db.add(ai)
        db.add(ao)
        db.add(av)
        assert len(db) == 3

    def test_get_objects_of_type(self):
        db = ObjectDatabase()
        db.add(AnalogInputObject(1))
        db.add(AnalogInputObject(2))
        db.add(AnalogOutputObject(1))
        ais = db.get_objects_of_type(ObjectType.ANALOG_INPUT)
        assert len(ais) == 2
        aos = db.get_objects_of_type(ObjectType.ANALOG_OUTPUT)
        assert len(aos) == 1

    def test_async_write(self):
        ao = AnalogOutputObject(1)

        async def run():
            await ao.async_write_property(PropertyIdentifier.PRESENT_VALUE, 99.0)

        asyncio.get_event_loop().run_until_complete(run())
        assert ao.read_property(PropertyIdentifier.PRESENT_VALUE) == 99.0


class TestAnalogCurrentCommandPriority:
    """Tests for Current_Command_Priority (Clause 19.5)."""

    def test_ao_has_current_command_priority(self):
        """AO must have Current_Command_Priority as required."""
        ao = AnalogOutputObject(1)
        plist = ao.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_ao_current_command_priority_none_when_relinquished(self):
        ao = AnalogOutputObject(1)
        assert ao.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) is None

    def test_ao_current_command_priority_returns_active(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0, priority=8)
        assert ao.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 8

    def test_ao_current_command_priority_highest_wins(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0, priority=16)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0, priority=4)
        assert ao.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 4

    def test_ao_current_command_priority_after_relinquish(self):
        ao = AnalogOutputObject(1)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0, priority=4)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0, priority=8)
        ao.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=4)
        assert ao.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 8

    def test_av_commandable_has_current_command_priority(self):
        av = AnalogValueObject(1, commandable=True)
        assert av.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) is None
        av.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0, priority=10)
        assert av.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY) == 10

    def test_av_non_commandable_no_current_command_priority(self):
        """Non-commandable AV should raise UNKNOWN_PROPERTY for Current_Command_Priority."""
        from bac_py.services.errors import BACnetError
        from bac_py.types.enums import ErrorCode

        av = AnalogValueObject(1)
        with pytest.raises(BACnetError) as exc_info:
            av.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_ai_no_current_command_priority(self):
        """AI is not commandable and has no Current_Command_Priority."""
        from bac_py.services.errors import BACnetError
        from bac_py.types.enums import ErrorCode

        ai = AnalogInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ai.read_property(PropertyIdentifier.CURRENT_COMMAND_PRIORITY)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY


class TestAnalogCommandablePropertyPresence:
    """Commandable properties only present when commandable (spec footnote)."""

    def test_av_non_commandable_no_relinquish_default(self):
        """Non-commandable AV should NOT have Relinquish_Default in properties."""
        av = AnalogValueObject(1)
        plist = av.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT not in plist
        assert PropertyIdentifier.PRIORITY_ARRAY not in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY not in plist

    def test_av_commandable_has_relinquish_default(self):
        """Commandable AV should have Relinquish_Default."""
        av = AnalogValueObject(1, commandable=True)
        assert av.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 0.0
        plist = av.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist

    def test_ao_always_has_commandable_properties(self):
        """AO is always commandable and always has these properties."""
        ao = AnalogOutputObject(1)
        plist = ao.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.RELINQUISH_DEFAULT in plist
        assert PropertyIdentifier.PRIORITY_ARRAY in plist
        assert PropertyIdentifier.CURRENT_COMMAND_PRIORITY in plist


class TestAnalogOutOfServiceWritable:
    """Present_Value writable when Out_Of_Service is TRUE (Clause 12)."""

    def test_ai_present_value_writable_when_oos(self):
        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert ai.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0

    def test_ai_present_value_read_only_when_in_service(self):
        from bac_py.services.errors import BACnetError
        from bac_py.types.enums import ErrorCode

        ai = AnalogInputObject(1)
        with pytest.raises(BACnetError) as exc_info:
            ai.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_ai_present_value_read_only_after_oos_cleared(self):
        from bac_py.services.errors import BACnetError
        from bac_py.types.enums import ErrorCode

        ai = AnalogInputObject(1)
        ai.write_property(PropertyIdentifier.OUT_OF_SERVICE, True)
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        ai.write_property(PropertyIdentifier.OUT_OF_SERVICE, False)
        with pytest.raises(BACnetError) as exc_info:
            ai.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED
        # Value should still be 42.0 from when OOS was TRUE
        assert ai.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0
