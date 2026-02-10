"""Phase 3 validation tests: Property definition corrections (P1-P10).

Tests verify that object property definitions use correct BACnet types,
proper enum types, and that default values are spec-compliant constructed
types rather than raw Python scalars.
"""

import pytest

from bac_py.objects.accumulator import AccumulatorObject
from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.device import DeviceObject
from bac_py.objects.event_enrollment import EventEnrollmentObject
from bac_py.objects.file import FileObject
from bac_py.objects.loop import LoopObject
from bac_py.objects.schedule import ScheduleObject
from bac_py.objects.trendlog import TrendLogObject
from bac_py.objects.value_types import DateTimeValueObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import (
    BACnetDateRange,
    BACnetDateTime,
    BACnetDeviceObjectPropertyReference,
    BACnetObjectPropertyReference,
    BACnetPrescale,
    BACnetScale,
)
from bac_py.types.enums import (
    ErrorCode,
    EventType,
    LoggingType,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
)


# ---------------------------------------------------------------------------
# P2: EventType enum on EventEnrollment
# ---------------------------------------------------------------------------
class TestP2EventTypeEnum:
    """P2: Event_Type should be EventType enum, not int."""

    def test_event_type_definition_uses_enum(self):
        defn = EventEnrollmentObject.PROPERTY_DEFINITIONS[PropertyIdentifier.EVENT_TYPE]
        assert defn.datatype is EventType

    def test_event_type_default_is_enum(self):
        obj = EventEnrollmentObject(1)
        val = obj.read_property(PropertyIdentifier.EVENT_TYPE)
        assert isinstance(val, EventType)
        assert val == EventType.CHANGE_OF_BITSTRING

    def test_event_type_enum_values(self):
        assert EventType.CHANGE_OF_BITSTRING == 0
        assert EventType.CHANGE_OF_STATE == 1
        assert EventType.CHANGE_OF_VALUE == 2
        assert EventType.COMMAND_FAILURE == 3
        assert EventType.FLOATING_LIMIT == 4
        assert EventType.OUT_OF_RANGE == 5
        assert EventType.CHANGE_OF_LIFE_SAFETY == 8
        assert EventType.EXTENDED == 9
        assert EventType.BUFFER_READY == 10
        assert EventType.UNSIGNED_RANGE == 11
        assert EventType.NONE == 20


# ---------------------------------------------------------------------------
# P3: LoggingType enum on TrendLog
# ---------------------------------------------------------------------------
class TestP3LoggingTypeEnum:
    """P3: Logging_Type should be LoggingType enum, not int."""

    def test_logging_type_definition_uses_enum(self):
        defn = TrendLogObject.PROPERTY_DEFINITIONS[PropertyIdentifier.LOGGING_TYPE]
        assert defn.datatype is LoggingType

    def test_logging_type_default_is_enum(self):
        obj = TrendLogObject(1)
        val = obj.read_property(PropertyIdentifier.LOGGING_TYPE)
        assert isinstance(val, LoggingType)
        assert val == LoggingType.POLLED

    def test_logging_type_enum_values(self):
        assert LoggingType.POLLED == 0
        assert LoggingType.COV == 1
        assert LoggingType.TRIGGERED == 2


# ---------------------------------------------------------------------------
# P4: NotifyType enum on EventEnrollment
# ---------------------------------------------------------------------------
class TestP4NotifyTypeEnum:
    """P4: Notify_Type should be NotifyType enum, not int."""

    def test_notify_type_definition_uses_enum(self):
        defn = EventEnrollmentObject.PROPERTY_DEFINITIONS[PropertyIdentifier.NOTIFY_TYPE]
        assert defn.datatype is NotifyType

    def test_notify_type_default_is_enum(self):
        obj = EventEnrollmentObject(1)
        val = obj.read_property(PropertyIdentifier.NOTIFY_TYPE)
        assert isinstance(val, NotifyType)
        assert val == NotifyType.ALARM

    def test_notify_type_enum_values(self):
        assert NotifyType.ALARM == 0
        assert NotifyType.EVENT == 1
        assert NotifyType.ACK_NOTIFICATION == 2


# ---------------------------------------------------------------------------
# P5: Properties typed with proper constructed types
# ---------------------------------------------------------------------------
class TestP5AccumulatorTypes:
    """P5: Accumulator properties use BACnetScale/BACnetPrescale/BACnetDateTime."""

    def test_scale_definition_type(self):
        defn = AccumulatorObject.PROPERTY_DEFINITIONS[PropertyIdentifier.SCALE]
        assert defn.datatype is BACnetScale

    def test_scale_default_is_bacnet_scale(self):
        obj = AccumulatorObject(1)
        val = obj.read_property(PropertyIdentifier.SCALE)
        assert isinstance(val, BACnetScale)
        assert val.float_scale == 1.0

    def test_prescale_definition_type(self):
        defn = AccumulatorObject.PROPERTY_DEFINITIONS[PropertyIdentifier.PRESCALE]
        assert defn.datatype is BACnetPrescale

    def test_prescale_optional_no_default(self):
        obj = AccumulatorObject(1)
        val = obj.read_property(PropertyIdentifier.PRESCALE)
        assert val is None

    def test_value_change_time_definition_type(self):
        defn = AccumulatorObject.PROPERTY_DEFINITIONS[PropertyIdentifier.VALUE_CHANGE_TIME]
        assert defn.datatype is BACnetDateTime


class TestP5TrendLogTypes:
    """P5: TrendLog properties use proper types."""

    def test_start_time_definition_type(self):
        defn = TrendLogObject.PROPERTY_DEFINITIONS[PropertyIdentifier.START_TIME]
        assert defn.datatype is BACnetDateTime

    def test_stop_time_definition_type(self):
        defn = TrendLogObject.PROPERTY_DEFINITIONS[PropertyIdentifier.STOP_TIME]
        assert defn.datatype is BACnetDateTime

    def test_log_device_object_property_definition_type(self):
        defn = TrendLogObject.PROPERTY_DEFINITIONS[PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY]
        assert defn.datatype is BACnetDeviceObjectPropertyReference


class TestP5ScheduleTypes:
    """P5: Schedule.Effective_Period uses BACnetDateRange."""

    def test_effective_period_definition_type(self):
        defn = ScheduleObject.PROPERTY_DEFINITIONS[PropertyIdentifier.EFFECTIVE_PERIOD]
        assert defn.datatype is BACnetDateRange

    def test_effective_period_default_is_date_range(self):
        obj = ScheduleObject(1)
        val = obj.read_property(PropertyIdentifier.EFFECTIVE_PERIOD)
        assert isinstance(val, BACnetDateRange)
        assert val.start_date.year == 1900
        assert val.start_date.month == 1
        assert val.start_date.day == 1
        assert val.end_date.year == 2155
        assert val.end_date.month == 12
        assert val.end_date.day == 31


class TestP5LoopTypes:
    """P5: Loop object references use BACnetObjectPropertyReference."""

    def test_controlled_variable_reference_type(self):
        defn = LoopObject.PROPERTY_DEFINITIONS[PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE]
        assert defn.datatype is BACnetObjectPropertyReference

    def test_manipulated_variable_reference_type(self):
        defn = LoopObject.PROPERTY_DEFINITIONS[PropertyIdentifier.MANIPULATED_VARIABLE_REFERENCE]
        assert defn.datatype is BACnetObjectPropertyReference

    def test_setpoint_reference_type(self):
        defn = LoopObject.PROPERTY_DEFINITIONS[PropertyIdentifier.SETPOINT_REFERENCE]
        assert defn.datatype is BACnetObjectPropertyReference

    def test_loop_references_uninitialized_raises(self):
        obj = LoopObject(1)
        # Required properties that are None raise VALUE_NOT_INITIALIZED
        with pytest.raises(BACnetError) as exc_info:
            obj.read_property(PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE)
        assert exc_info.value.error_code == ErrorCode.VALUE_NOT_INITIALIZED

    def test_loop_reference_writable(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        obj = LoopObject(1)
        obj.write_property(PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE, ref)
        assert obj.read_property(PropertyIdentifier.CONTROLLED_VARIABLE_REFERENCE) == ref


class TestP5EventEnrollmentTypes:
    """P5: EventEnrollment.Object_Property_Reference uses proper type."""

    def test_object_property_reference_type(self):
        defn = EventEnrollmentObject.PROPERTY_DEFINITIONS[
            PropertyIdentifier.OBJECT_PROPERTY_REFERENCE
        ]
        assert defn.datatype is BACnetDeviceObjectPropertyReference


class TestP5FileTypes:
    """P5: File.Modification_Date uses BACnetDateTime."""

    def test_modification_date_definition_type(self):
        defn = FileObject.PROPERTY_DEFINITIONS[PropertyIdentifier.MODIFICATION_DATE]
        assert defn.datatype is BACnetDateTime


class TestP5DateTimeValueTypes:
    """P5: DateTimeValue.Present_Value uses BACnetDateTime."""

    def test_present_value_definition_type(self):
        defn = DateTimeValueObject.PROPERTY_DEFINITIONS[PropertyIdentifier.PRESENT_VALUE]
        assert defn.datatype is BACnetDateTime


# ---------------------------------------------------------------------------
# P6: DeviceObject uses standard_properties()
# ---------------------------------------------------------------------------
class TestP6DeviceStandardProperties:
    """P6: DeviceObject uses standard_properties() helper."""

    def test_has_object_identifier(self):
        assert PropertyIdentifier.OBJECT_IDENTIFIER in DeviceObject.PROPERTY_DEFINITIONS

    def test_has_object_name(self):
        assert PropertyIdentifier.OBJECT_NAME in DeviceObject.PROPERTY_DEFINITIONS

    def test_has_object_type(self):
        assert PropertyIdentifier.OBJECT_TYPE in DeviceObject.PROPERTY_DEFINITIONS

    def test_has_property_list(self):
        assert PropertyIdentifier.PROPERTY_LIST in DeviceObject.PROPERTY_DEFINITIONS

    def test_has_description(self):
        assert PropertyIdentifier.DESCRIPTION in DeviceObject.PROPERTY_DEFINITIONS

    def test_object_type_value(self):
        obj = DeviceObject(
            1,
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )
        assert obj.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.DEVICE


# ---------------------------------------------------------------------------
# P7: AnalogInput has Update_Interval
# ---------------------------------------------------------------------------
class TestP7AnalogInputUpdateInterval:
    """P7: AnalogInputObject includes Update_Interval property."""

    def test_update_interval_in_definitions(self):
        assert PropertyIdentifier.UPDATE_INTERVAL in AnalogInputObject.PROPERTY_DEFINITIONS

    def test_update_interval_properties(self):
        defn = AnalogInputObject.PROPERTY_DEFINITIONS[PropertyIdentifier.UPDATE_INTERVAL]
        assert defn.datatype is int
        assert defn.required is False

    def test_update_interval_optional_default_none(self):
        obj = AnalogInputObject(1)
        assert obj.read_property(PropertyIdentifier.UPDATE_INTERVAL) is None

    def test_update_interval_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.UPDATE_INTERVAL, 1000)
        assert obj.read_property(PropertyIdentifier.UPDATE_INTERVAL) == 1000


# ---------------------------------------------------------------------------
# Cross-cutting: Verify no regressions on existing functionality
# ---------------------------------------------------------------------------
class TestPhase3NoRegressions:
    """Verify Phase 3 changes don't break existing object behavior."""

    def test_accumulator_still_has_status_flags(self):
        obj = AccumulatorObject(1)
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert sf is not None

    def test_trendlog_log_buffer_default(self):
        obj = TrendLogObject(1)
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []

    def test_event_enrollment_event_enable_default(self):
        obj = EventEnrollmentObject(1)
        assert obj.read_property(PropertyIdentifier.EVENT_ENABLE) == [True, True, True]

    def test_loop_pid_defaults(self):
        obj = LoopObject(1)
        assert obj.read_property(PropertyIdentifier.PROPORTIONAL_CONSTANT) == 0.0
        assert obj.read_property(PropertyIdentifier.INTEGRAL_CONSTANT) == 0.0
        assert obj.read_property(PropertyIdentifier.DERIVATIVE_CONSTANT) == 0.0

    def test_schedule_priority_for_writing_default(self):
        obj = ScheduleObject(1)
        assert obj.read_property(PropertyIdentifier.PRIORITY_FOR_WRITING) == 16

    def test_device_protocol_version(self):
        obj = DeviceObject(
            1,
            vendor_name="Test",
            vendor_identifier=999,
            model_name="Test",
            firmware_revision="1.0",
            application_software_version="1.0",
        )
        assert obj.read_property(PropertyIdentifier.PROTOCOL_VERSION) == 1

    def test_file_read_only_default(self):
        obj = FileObject(1)
        assert obj.read_property(PropertyIdentifier.READ_ONLY) is False

    def test_analog_input_present_value(self):
        obj = AnalogInputObject(1)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_analog_output_commandable(self):
        obj = AnalogOutputObject(1)
        assert obj._priority_array is not None

    def test_analog_value_optional_commandable(self):
        obj = AnalogValueObject(1, commandable=True)
        assert obj._priority_array is not None
        obj2 = AnalogValueObject(2)
        assert obj2._priority_array is None
