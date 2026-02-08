"""Tests for BACnet Loop object (Clause 12.17)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.loop import LoopObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import StatusFlags
from bac_py.types.enums import (
    Action,
    EngineeringUnits,
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestLoopObject:
    """Tests for LoopObject (Clause 12.17)."""

    def test_create_basic(self):
        loop = LoopObject(1)
        assert loop.object_identifier == ObjectIdentifier(ObjectType.LOOP, 1)

    def test_object_type(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.LOOP

    def test_present_value_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_present_value_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0)
        assert loop.read_property(PropertyIdentifier.PRESENT_VALUE) == 50.0

    def test_status_flags_initialized(self):
        loop = LoopObject(1)
        sf = loop.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_event_state_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_out_of_service_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_action_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.ACTION) == Action.DIRECT

    def test_action_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.ACTION, Action.REVERSE)
        assert loop.read_property(PropertyIdentifier.ACTION) == Action.REVERSE

    def test_proportional_constant_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.PROPORTIONAL_CONSTANT) == 0.0

    def test_pid_constants_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.PROPORTIONAL_CONSTANT, 1.5)
        loop.write_property(PropertyIdentifier.INTEGRAL_CONSTANT, 0.5)
        loop.write_property(PropertyIdentifier.DERIVATIVE_CONSTANT, 0.1)
        assert loop.read_property(PropertyIdentifier.PROPORTIONAL_CONSTANT) == 1.5
        assert loop.read_property(PropertyIdentifier.INTEGRAL_CONSTANT) == 0.5
        assert loop.read_property(PropertyIdentifier.DERIVATIVE_CONSTANT) == 0.1

    def test_setpoint_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.SETPOINT) == 0.0

    def test_setpoint_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.SETPOINT, 72.0)
        assert loop.read_property(PropertyIdentifier.SETPOINT) == 72.0

    def test_maximum_output_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.MAXIMUM_OUTPUT) == 100.0

    def test_minimum_output_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.MINIMUM_OUTPUT) == 0.0

    def test_priority_for_writing_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.PRIORITY_FOR_WRITING) == 16

    def test_update_interval_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.UPDATE_INTERVAL) == 100

    def test_controlled_variable_value_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.CONTROLLED_VARIABLE_VALUE) == 0.0

    def test_controlled_variable_value_read_only(self):
        loop = LoopObject(1)
        with pytest.raises(BACnetError) as exc_info:
            loop.write_property(PropertyIdentifier.CONTROLLED_VARIABLE_VALUE, 42.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_bias_optional(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.BIAS) is None

    def test_bias_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.BIAS, 5.0)
        assert loop.read_property(PropertyIdentifier.BIAS) == 5.0

    def test_not_commandable(self):
        loop = LoopObject(1)
        assert loop._priority_array is None

    def test_property_list(self):
        loop = LoopObject(1)
        plist = loop.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.ACTION in plist
        assert PropertyIdentifier.SETPOINT in plist
        assert PropertyIdentifier.OUTPUT_UNITS in plist
        assert PropertyIdentifier.PRIORITY_FOR_WRITING in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_output_units_default(self):
        loop = LoopObject(1)
        assert loop.read_property(PropertyIdentifier.OUTPUT_UNITS) == EngineeringUnits.NO_UNITS

    def test_output_units_writable(self):
        loop = LoopObject(1)
        loop.write_property(PropertyIdentifier.OUTPUT_UNITS, EngineeringUnits.DEGREES_FAHRENHEIT)
        assert (
            loop.read_property(PropertyIdentifier.OUTPUT_UNITS)
            == EngineeringUnits.DEGREES_FAHRENHEIT
        )

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.LOOP, 2)
        assert isinstance(obj, LoopObject)

    def test_initial_properties(self):
        loop = LoopObject(1, object_name="LOOP-1", setpoint=72.0)
        assert loop.read_property(PropertyIdentifier.OBJECT_NAME) == "LOOP-1"
        assert loop.read_property(PropertyIdentifier.SETPOINT) == 72.0
