"""Phase 7 validation tests: Write-change hooks and intrinsic reporting infrastructure.

Tests cover:
  A2: Write-change notification hook (_on_property_written callback)
  P1: Intrinsic reporting properties on analog/binary/multistate objects
"""

import pytest

from bac_py.objects.analog import AnalogInputObject, AnalogOutputObject, AnalogValueObject
from bac_py.objects.base import PropertyAccess, intrinsic_reporting_properties
from bac_py.objects.binary import BinaryInputObject, BinaryOutputObject, BinaryValueObject
from bac_py.objects.multistate import (
    MultiStateInputObject,
    MultiStateOutputObject,
    MultiStateValueObject,
)
from bac_py.types.enums import (
    BinaryPV,
    NotifyType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BitString


# ---------------------------------------------------------------------------
# A2: Write-change notification hook
# ---------------------------------------------------------------------------
class TestWriteChangeHook:
    """Verify the _on_property_written callback mechanism (A2)."""

    def test_callback_fires_on_value_change(self):
        obj = AnalogValueObject(1)
        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert len(changes) == 1
        assert changes[0][0] == PropertyIdentifier.PRESENT_VALUE
        assert changes[0][1] == 0.0  # default
        assert changes[0][2] == 42.0

    def test_callback_not_fired_when_value_unchanged(self):
        obj = AnalogValueObject(1)
        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        # Write same default value
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 0.0)
        assert len(changes) == 0

    def test_callback_fires_on_name_change(self):
        obj = AnalogValueObject(1, object_name="original")
        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        obj.write_property(PropertyIdentifier.OBJECT_NAME, "renamed")
        assert len(changes) == 1
        assert changes[0] == (PropertyIdentifier.OBJECT_NAME, "original", "renamed")

    def test_callback_fires_on_commandable_write(self):
        obj = AnalogOutputObject(1)
        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 100.0, priority=8)
        assert len(changes) == 1
        assert changes[0][0] == PropertyIdentifier.PRESENT_VALUE
        assert changes[0][2] == 100.0

    def test_callback_fires_on_relinquish(self):
        obj = AnalogOutputObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0, priority=8)

        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        # Relinquish priority 8 -> falls back to relinquish default (0.0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        assert len(changes) == 1
        assert changes[0][0] == PropertyIdentifier.PRESENT_VALUE
        assert changes[0][1] == 50.0
        assert changes[0][2] == 0.0  # relinquish default

    def test_no_callback_when_not_registered(self):
        obj = AnalogValueObject(1)
        assert obj._on_property_written is None
        # Should not raise
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)

    def test_multiple_changes_tracked(self):
        obj = AnalogValueObject(1, object_name="start")
        changes = []
        obj._on_property_written = lambda pid, old, new: changes.append((pid, old, new))
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0)
        obj.write_property(PropertyIdentifier.OBJECT_NAME, "end")
        assert len(changes) == 3


# ---------------------------------------------------------------------------
# P1: Intrinsic reporting helper function
# ---------------------------------------------------------------------------
class TestIntrinsicReportingHelper:
    """Verify the intrinsic_reporting_properties() helper function."""

    def test_basic_properties_returned(self):
        props = intrinsic_reporting_properties()
        expected = {
            PropertyIdentifier.TIME_DELAY,
            PropertyIdentifier.NOTIFICATION_CLASS,
            PropertyIdentifier.EVENT_ENABLE,
            PropertyIdentifier.ACKED_TRANSITIONS,
            PropertyIdentifier.NOTIFY_TYPE,
            PropertyIdentifier.EVENT_TIME_STAMPS,
            PropertyIdentifier.EVENT_DETECTION_ENABLE,
            PropertyIdentifier.EVENT_MESSAGE_TEXTS,
            PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG,
        }
        assert set(props.keys()) == expected

    def test_all_optional(self):
        props = intrinsic_reporting_properties()
        for prop_def in props.values():
            assert prop_def.required is False

    def test_include_limit_adds_analog_properties(self):
        props = intrinsic_reporting_properties(include_limit=True)
        assert PropertyIdentifier.HIGH_LIMIT in props
        assert PropertyIdentifier.LOW_LIMIT in props
        assert PropertyIdentifier.DEADBAND in props
        assert PropertyIdentifier.LIMIT_ENABLE in props

    def test_without_limit_excludes_analog_properties(self):
        props = intrinsic_reporting_properties(include_limit=False)
        assert PropertyIdentifier.HIGH_LIMIT not in props
        assert PropertyIdentifier.LOW_LIMIT not in props
        assert PropertyIdentifier.DEADBAND not in props
        assert PropertyIdentifier.LIMIT_ENABLE not in props

    def test_notify_type_is_enum(self):
        props = intrinsic_reporting_properties()
        assert props[PropertyIdentifier.NOTIFY_TYPE].datatype is NotifyType

    def test_event_enable_is_bitstring(self):
        props = intrinsic_reporting_properties()
        assert props[PropertyIdentifier.EVENT_ENABLE].datatype is BitString

    def test_acked_transitions_read_only(self):
        props = intrinsic_reporting_properties()
        assert props[PropertyIdentifier.ACKED_TRANSITIONS].access == PropertyAccess.READ_ONLY

    def test_event_detection_enable_is_bool(self):
        props = intrinsic_reporting_properties()
        assert props[PropertyIdentifier.EVENT_DETECTION_ENABLE].datatype is bool

    def test_limit_properties_are_float(self):
        props = intrinsic_reporting_properties(include_limit=True)
        assert props[PropertyIdentifier.HIGH_LIMIT].datatype is float
        assert props[PropertyIdentifier.LOW_LIMIT].datatype is float
        assert props[PropertyIdentifier.DEADBAND].datatype is float

    def test_limit_enable_is_bitstring(self):
        props = intrinsic_reporting_properties(include_limit=True)
        assert props[PropertyIdentifier.LIMIT_ENABLE].datatype is BitString


# ---------------------------------------------------------------------------
# P1: Intrinsic reporting on Analog objects
# ---------------------------------------------------------------------------
class TestAnalogIntrinsicReporting:
    """Verify intrinsic reporting properties on Analog I/O/V objects."""

    @pytest.mark.parametrize(
        "cls",
        [AnalogInputObject, AnalogOutputObject, AnalogValueObject],
        ids=["AI", "AO", "AV"],
    )
    def test_has_common_reporting_properties(self, cls):
        obj = cls(1) if cls != AnalogValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.TIME_DELAY in defs
        assert PropertyIdentifier.NOTIFICATION_CLASS in defs
        assert PropertyIdentifier.EVENT_ENABLE in defs
        assert PropertyIdentifier.ACKED_TRANSITIONS in defs
        assert PropertyIdentifier.NOTIFY_TYPE in defs
        assert PropertyIdentifier.EVENT_TIME_STAMPS in defs
        assert PropertyIdentifier.EVENT_DETECTION_ENABLE in defs
        assert PropertyIdentifier.EVENT_MESSAGE_TEXTS in defs
        assert PropertyIdentifier.EVENT_MESSAGE_TEXTS_CONFIG in defs

    @pytest.mark.parametrize(
        "cls",
        [AnalogInputObject, AnalogOutputObject, AnalogValueObject],
        ids=["AI", "AO", "AV"],
    )
    def test_has_limit_properties(self, cls):
        """Analog objects include limit detection properties."""
        obj = cls(1) if cls != AnalogValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.HIGH_LIMIT in defs
        assert PropertyIdentifier.LOW_LIMIT in defs
        assert PropertyIdentifier.DEADBAND in defs
        assert PropertyIdentifier.LIMIT_ENABLE in defs

    def test_high_limit_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.HIGH_LIMIT, 100.0)
        assert obj.read_property(PropertyIdentifier.HIGH_LIMIT) == 100.0

    def test_low_limit_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.LOW_LIMIT, -10.0)
        assert obj.read_property(PropertyIdentifier.LOW_LIMIT) == -10.0

    def test_deadband_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.DEADBAND, 2.5)
        assert obj.read_property(PropertyIdentifier.DEADBAND) == 2.5

    def test_notification_class_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 5)
        assert obj.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 5

    def test_time_delay_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.TIME_DELAY, 10)
        assert obj.read_property(PropertyIdentifier.TIME_DELAY) == 10

    def test_notify_type_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.NOTIFY_TYPE, NotifyType.EVENT)
        assert obj.read_property(PropertyIdentifier.NOTIFY_TYPE) == NotifyType.EVENT

    def test_event_detection_enable_writable(self):
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.EVENT_DETECTION_ENABLE, True)
        assert obj.read_property(PropertyIdentifier.EVENT_DETECTION_ENABLE) is True

    def test_limit_enable_writable(self):
        obj = AnalogInputObject(1)
        le = BitString(b"\xc0", 6)  # 2-bit: high=1, low=1
        obj.write_property(PropertyIdentifier.LIMIT_ENABLE, le)
        assert obj.read_property(PropertyIdentifier.LIMIT_ENABLE) == le

    def test_event_enable_writable(self):
        obj = AnalogInputObject(1)
        # 3-bit EventTransitionBits: to-offnormal, to-fault, to-normal
        ee = BitString(b"\xe0", 5)
        obj.write_property(PropertyIdentifier.EVENT_ENABLE, ee)
        assert obj.read_property(PropertyIdentifier.EVENT_ENABLE) == ee

    def test_reporting_props_not_in_property_list_when_unset(self):
        """Optional reporting properties don't appear in property list when not set."""
        obj = AnalogInputObject(1)
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        # TIME_DELAY is optional and not set, so should not appear
        assert PropertyIdentifier.TIME_DELAY not in prop_list

    def test_reporting_props_in_property_list_when_set(self):
        """Optional reporting properties appear in property list when set."""
        obj = AnalogInputObject(1)
        obj.write_property(PropertyIdentifier.TIME_DELAY, 5)
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.TIME_DELAY in prop_list


# ---------------------------------------------------------------------------
# P1: Intrinsic reporting on Binary objects
# ---------------------------------------------------------------------------
class TestBinaryIntrinsicReporting:
    """Verify intrinsic reporting properties on Binary I/O/V objects."""

    @pytest.mark.parametrize(
        "cls",
        [BinaryInputObject, BinaryOutputObject, BinaryValueObject],
        ids=["BI", "BO", "BV"],
    )
    def test_has_common_reporting_properties(self, cls):
        obj = cls(1) if cls != BinaryValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.TIME_DELAY in defs
        assert PropertyIdentifier.NOTIFICATION_CLASS in defs
        assert PropertyIdentifier.EVENT_ENABLE in defs
        assert PropertyIdentifier.NOTIFY_TYPE in defs
        assert PropertyIdentifier.EVENT_DETECTION_ENABLE in defs

    @pytest.mark.parametrize(
        "cls",
        [BinaryInputObject, BinaryOutputObject, BinaryValueObject],
        ids=["BI", "BO", "BV"],
    )
    def test_no_limit_properties(self, cls):
        """Binary objects do not include limit detection properties."""
        obj = cls(1) if cls != BinaryValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.HIGH_LIMIT not in defs
        assert PropertyIdentifier.LOW_LIMIT not in defs
        assert PropertyIdentifier.DEADBAND not in defs
        assert PropertyIdentifier.LIMIT_ENABLE not in defs

    def test_binary_input_has_alarm_value(self):
        obj = BinaryInputObject(1)
        assert PropertyIdentifier.ALARM_VALUE in obj.PROPERTY_DEFINITIONS
        obj.write_property(PropertyIdentifier.ALARM_VALUE, BinaryPV.ACTIVE)
        assert obj.read_property(PropertyIdentifier.ALARM_VALUE) == BinaryPV.ACTIVE

    def test_binary_value_has_alarm_value(self):
        obj = BinaryValueObject(1)
        assert PropertyIdentifier.ALARM_VALUE in obj.PROPERTY_DEFINITIONS

    def test_notification_class_writable(self):
        obj = BinaryInputObject(1)
        obj.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 3)
        assert obj.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 3


# ---------------------------------------------------------------------------
# P1: Intrinsic reporting on Multi-State objects
# ---------------------------------------------------------------------------
class TestMultiStateIntrinsicReporting:
    """Verify intrinsic reporting properties on Multi-State I/O/V objects."""

    @pytest.mark.parametrize(
        "cls",
        [MultiStateInputObject, MultiStateOutputObject, MultiStateValueObject],
        ids=["MSI", "MSO", "MSV"],
    )
    def test_has_common_reporting_properties(self, cls):
        obj = cls(1) if cls != MultiStateValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.TIME_DELAY in defs
        assert PropertyIdentifier.NOTIFICATION_CLASS in defs
        assert PropertyIdentifier.EVENT_ENABLE in defs
        assert PropertyIdentifier.NOTIFY_TYPE in defs
        assert PropertyIdentifier.EVENT_DETECTION_ENABLE in defs

    @pytest.mark.parametrize(
        "cls",
        [MultiStateInputObject, MultiStateOutputObject, MultiStateValueObject],
        ids=["MSI", "MSO", "MSV"],
    )
    def test_no_limit_properties(self, cls):
        """Multi-state objects do not include limit detection properties."""
        obj = cls(1) if cls != MultiStateValueObject else cls(1)
        defs = obj.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.HIGH_LIMIT not in defs
        assert PropertyIdentifier.LOW_LIMIT not in defs

    def test_msi_has_fault_values(self):
        obj = MultiStateInputObject(1, number_of_states=4)
        assert PropertyIdentifier.FAULT_VALUES in obj.PROPERTY_DEFINITIONS
        obj.write_property(PropertyIdentifier.FAULT_VALUES, [2, 3])
        assert obj.read_property(PropertyIdentifier.FAULT_VALUES) == [2, 3]

    def test_msi_has_alarm_values(self):
        obj = MultiStateInputObject(1, number_of_states=4)
        assert PropertyIdentifier.ALARM_VALUES in obj.PROPERTY_DEFINITIONS
        obj.write_property(PropertyIdentifier.ALARM_VALUES, [4])
        assert obj.read_property(PropertyIdentifier.ALARM_VALUES) == [4]

    def test_msv_has_fault_values(self):
        obj = MultiStateValueObject(1, number_of_states=3)
        assert PropertyIdentifier.FAULT_VALUES in obj.PROPERTY_DEFINITIONS

    def test_msv_has_alarm_values(self):
        obj = MultiStateValueObject(1, number_of_states=3)
        assert PropertyIdentifier.ALARM_VALUES in obj.PROPERTY_DEFINITIONS

    def test_notification_class_writable(self):
        obj = MultiStateInputObject(1, number_of_states=3)
        obj.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 7)
        assert obj.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 7

    def test_notify_type_enum_coercion(self):
        """Raw int from wire should be coerced to NotifyType."""
        obj = MultiStateInputObject(1, number_of_states=3)
        obj.write_property(PropertyIdentifier.NOTIFY_TYPE, 1)  # raw int for EVENT
        val = obj.read_property(PropertyIdentifier.NOTIFY_TYPE)
        assert isinstance(val, NotifyType)
        assert val == NotifyType.EVENT
