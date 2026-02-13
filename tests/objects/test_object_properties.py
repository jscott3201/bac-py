"""Expanded property-level coverage for undertested BACnet object types.

Tests instantiation, default values, read access, write access, and
read-only enforcement across 15 object types.
"""

from __future__ import annotations

import pytest

from bac_py.services.errors import BACnetError
from bac_py.types.constructed import BACnetShedLevel, StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    EventState,
    EventType,
    LightingInProgress,
    LoggingType,
    NodeType,
    ObjectType,
    PropertyIdentifier,
    ShedState,
    StagingState,
    TimerState,
    TimerTransition,
    WriteStatus,
)

# ---------------------------------------------------------------------------
# 1. LightingOutputObject
# ---------------------------------------------------------------------------


class TestLightingOutputObject:
    """Property-level tests for Lighting Output (Clause 12.54)."""

    def test_instantiation_with_required_properties(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-test")
        assert obj.OBJECT_TYPE == ObjectType.LIGHTING_OUTPUT
        assert obj.object_identifier.instance_number == 1
        assert obj.read_property(PropertyIdentifier.OBJECT_NAME) == "lo-test"

    def test_present_value_default(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_tracking_value_default(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.TRACKING_VALUE) == 0.0

    def test_tracking_value_is_read_only(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.TRACKING_VALUE, 50.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_in_progress_default(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.IN_PROGRESS) == LightingInProgress.IDLE

    def test_in_progress_is_read_only(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.IN_PROGRESS, LightingInProgress.FADE_ACTIVE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_write_present_value_via_priority(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 85.0, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 85.0

    def test_default_fade_time(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.DEFAULT_FADE_TIME) == 0

    def test_default_ramp_rate(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.DEFAULT_RAMP_RATE) == 100.0

    def test_default_step_increment(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.DEFAULT_STEP_INCREMENT) == 1.0

    def test_write_default_fade_time(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        obj.write_property(PropertyIdentifier.DEFAULT_FADE_TIME, 500)
        assert obj.read_property(PropertyIdentifier.DEFAULT_FADE_TIME) == 500

    def test_lighting_command_default_priority(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.LIGHTING_COMMAND_DEFAULT_PRIORITY) == 16

    def test_blink_warn_enable_default(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.BLINK_WARN_ENABLE) is False

    def test_intrinsic_event_algorithm(self):
        from bac_py.objects.lighting import LightingOutputObject

        assert LightingOutputObject.INTRINSIC_EVENT_ALGORITHM == EventType.OUT_OF_RANGE

    def test_object_type_read(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.LIGHTING_OUTPUT

    def test_status_flags_initialized(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)
        assert sf.in_alarm is False

    def test_relinquish_default(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        assert obj.read_property(PropertyIdentifier.RELINQUISH_DEFAULT) == 0.0

    def test_priority_array_initialized(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-1")
        pa = obj.read_property(PropertyIdentifier.PRIORITY_ARRAY)
        assert isinstance(pa, list)
        assert len(pa) == 16
        assert all(v is None for v in pa)


# ---------------------------------------------------------------------------
# 2. TimerObject
# ---------------------------------------------------------------------------


class TestTimerObject:
    """Property-level tests for Timer (Clause 12.57)."""

    def test_instantiation(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.OBJECT_TYPE == ObjectType.TIMER
        assert obj.object_identifier.instance_number == 1

    def test_present_value_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_write_present_value(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 120)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 120

    def test_timer_state_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.TIMER_STATE) == TimerState.IDLE

    def test_timer_state_is_read_only(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.TIMER_STATE, TimerState.RUNNING)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_timer_running_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.TIMER_RUNNING) is False

    def test_write_timer_running(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        obj.write_property(PropertyIdentifier.TIMER_RUNNING, True)
        assert obj.read_property(PropertyIdentifier.TIMER_RUNNING) is True

    def test_last_state_change_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.LAST_STATE_CHANGE) == TimerTransition.NONE

    def test_last_state_change_is_read_only(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.LAST_STATE_CHANGE, TimerTransition.IDLE_TO_RUNNING
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_initial_timeout_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.INITIAL_TIMEOUT) == 0

    def test_write_initial_timeout(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        obj.write_property(PropertyIdentifier.INITIAL_TIMEOUT, 300)
        assert obj.read_property(PropertyIdentifier.INITIAL_TIMEOUT) == 300

    def test_intrinsic_event_algorithm(self):
        from bac_py.objects.timer import TimerObject

        assert TimerObject.INTRINSIC_EVENT_ALGORITHM == EventType.CHANGE_OF_TIMER

    def test_event_state_default(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        assert obj.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_property_list_includes_required(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in prop_list
        assert PropertyIdentifier.TIMER_STATE in prop_list
        assert PropertyIdentifier.TIMER_RUNNING in prop_list
        assert PropertyIdentifier.INITIAL_TIMEOUT in prop_list


# ---------------------------------------------------------------------------
# 3. ChannelObject
# ---------------------------------------------------------------------------


class TestChannelObject:
    """Property-level tests for Channel (Clause 12.53)."""

    def test_instantiation(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        assert obj.OBJECT_TYPE == ObjectType.CHANNEL
        assert obj.object_identifier.instance_number == 1

    def test_channel_number_default(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        assert obj.read_property(PropertyIdentifier.CHANNEL_NUMBER) == 0

    def test_channel_number_custom(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1, channel_number=7)
        assert obj.read_property(PropertyIdentifier.CHANNEL_NUMBER) == 7

    def test_write_channel_number(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1, channel_number=5)
        obj.write_property(PropertyIdentifier.CHANNEL_NUMBER, 10)
        assert obj.read_property(PropertyIdentifier.CHANNEL_NUMBER) == 10

    def test_present_value_writable(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42

    def test_present_value_accepts_various_types(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, "hello")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == "hello"
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 3.14)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 3.14

    def test_write_status_default(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        assert obj.read_property(PropertyIdentifier.WRITE_STATUS) == WriteStatus.IDLE

    def test_write_status_is_read_only(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.WRITE_STATUS, WriteStatus.IN_PROGRESS)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_control_groups_default_empty(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        assert obj.read_property(PropertyIdentifier.CONTROL_GROUPS) == []

    def test_write_control_groups(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        obj.write_property(PropertyIdentifier.CONTROL_GROUPS, [1, 2, 3])
        assert obj.read_property(PropertyIdentifier.CONTROL_GROUPS) == [1, 2, 3]

    def test_list_of_object_property_references_default(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        refs = obj.read_property(PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES)
        assert refs == []

    def test_last_priority_is_read_only(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.LAST_PRIORITY, 5)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED


# ---------------------------------------------------------------------------
# 4. AveragingObject
# ---------------------------------------------------------------------------


class TestAveragingObject:
    """Property-level tests for Averaging (Clause 12.5)."""

    def test_instantiation(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.OBJECT_TYPE == ObjectType.AVERAGING

    def test_minimum_value_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.MINIMUM_VALUE) == 0.0

    def test_minimum_value_is_read_only(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.MINIMUM_VALUE, 10.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_maximum_value_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.MAXIMUM_VALUE) == 0.0

    def test_maximum_value_is_read_only(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.MAXIMUM_VALUE, 99.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_average_value_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.AVERAGE_VALUE) == 0.0

    def test_average_value_is_read_only(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.AVERAGE_VALUE, 50.0)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_window_interval_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.WINDOW_INTERVAL) == 60

    def test_write_window_interval(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        obj.write_property(PropertyIdentifier.WINDOW_INTERVAL, 120)
        assert obj.read_property(PropertyIdentifier.WINDOW_INTERVAL) == 120

    def test_window_samples_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.WINDOW_SAMPLES) == 10

    def test_write_window_samples(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        obj.write_property(PropertyIdentifier.WINDOW_SAMPLES, 20)
        assert obj.read_property(PropertyIdentifier.WINDOW_SAMPLES) == 20

    def test_attempted_samples_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.ATTEMPTED_SAMPLES) == 0

    def test_attempted_samples_is_read_only(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.ATTEMPTED_SAMPLES, 5)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_valid_samples_default(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        assert obj.read_property(PropertyIdentifier.VALID_SAMPLES) == 0

    def test_property_list_includes_required(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.AVERAGE_VALUE in prop_list
        assert PropertyIdentifier.MINIMUM_VALUE in prop_list
        assert PropertyIdentifier.MAXIMUM_VALUE in prop_list
        assert PropertyIdentifier.UNITS in prop_list
        assert PropertyIdentifier.WINDOW_INTERVAL in prop_list
        assert PropertyIdentifier.WINDOW_SAMPLES in prop_list


# ---------------------------------------------------------------------------
# 5. CommandObject
# ---------------------------------------------------------------------------


class TestCommandObject:
    """Property-level tests for Command (Clause 12.10)."""

    def test_instantiation(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.OBJECT_TYPE == ObjectType.COMMAND

    def test_present_value_default(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0

    def test_write_present_value(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 3)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 3

    def test_in_process_default(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.read_property(PropertyIdentifier.IN_PROCESS) is False

    def test_in_process_is_read_only(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.IN_PROCESS, True)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_all_writes_successful_default(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.read_property(PropertyIdentifier.ALL_WRITES_SUCCESSFUL) is True

    def test_all_writes_successful_is_read_only(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.ALL_WRITES_SUCCESSFUL, False)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_action_list_default(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        assert obj.read_property(PropertyIdentifier.ACTION) == []

    def test_write_action_list(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        actions = [{"target": "ai-1", "property": "present-value", "value": 42}]
        obj.write_property(PropertyIdentifier.ACTION, actions)
        assert obj.read_property(PropertyIdentifier.ACTION) == actions

    def test_property_list_includes_required(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in prop_list
        assert PropertyIdentifier.IN_PROCESS in prop_list
        assert PropertyIdentifier.ALL_WRITES_SUCCESSFUL in prop_list
        assert PropertyIdentifier.ACTION in prop_list


# ---------------------------------------------------------------------------
# 6. TrendLogMultipleObject
# ---------------------------------------------------------------------------


class TestTrendLogMultipleObject:
    """Property-level tests for Trend Log Multiple (Clause 12.30)."""

    def test_instantiation(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.OBJECT_TYPE == ObjectType.TREND_LOG_MULTIPLE

    def test_log_enable_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False

    def test_write_log_enable(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        obj.write_property(PropertyIdentifier.LOG_ENABLE, True)
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is True

    def test_buffer_size_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.BUFFER_SIZE) == 0

    def test_write_buffer_size(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        obj.write_property(PropertyIdentifier.BUFFER_SIZE, 1000)
        assert obj.read_property(PropertyIdentifier.BUFFER_SIZE) == 1000

    def test_log_buffer_default_empty(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []

    def test_log_buffer_is_read_only(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.LOG_BUFFER, [{"record": 1}])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_logging_type_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.POLLED

    def test_record_count_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.RECORD_COUNT) == 0

    def test_total_record_count_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 0

    def test_total_record_count_is_read_only(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.TOTAL_RECORD_COUNT, 42)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_stop_when_full_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.STOP_WHEN_FULL) is False

    def test_write_stop_when_full(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        obj.write_property(PropertyIdentifier.STOP_WHEN_FULL, True)
        assert obj.read_property(PropertyIdentifier.STOP_WHEN_FULL) is True

    def test_log_device_object_property_default(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-1")
        assert obj.read_property(PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY) == []


# ---------------------------------------------------------------------------
# 7. EventLogObject
# ---------------------------------------------------------------------------


class TestEventLogObject:
    """Property-level tests for Event Log (Clause 12.27)."""

    def test_instantiation(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.OBJECT_TYPE == ObjectType.EVENT_LOG

    def test_log_enable_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is False

    def test_write_log_enable(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        obj.write_property(PropertyIdentifier.LOG_ENABLE, True)
        assert obj.read_property(PropertyIdentifier.LOG_ENABLE) is True

    def test_buffer_size_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.BUFFER_SIZE) == 0

    def test_write_buffer_size(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        obj.write_property(PropertyIdentifier.BUFFER_SIZE, 500)
        assert obj.read_property(PropertyIdentifier.BUFFER_SIZE) == 500

    def test_log_buffer_default_empty(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.LOG_BUFFER) == []

    def test_log_buffer_is_read_only(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.LOG_BUFFER, [{"event": "test"}])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_logging_type_default_triggered(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.LOGGING_TYPE) == LoggingType.TRIGGERED

    def test_logging_type_is_read_only(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.LOGGING_TYPE, LoggingType.POLLED)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_record_count_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.RECORD_COUNT) == 0

    def test_total_record_count_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 0

    def test_total_record_count_is_read_only(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.TOTAL_RECORD_COUNT, 10)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_stop_when_full_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.STOP_WHEN_FULL) is False

    def test_records_since_notification_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.RECORDS_SINCE_NOTIFICATION) == 0

    def test_last_notify_record_default(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-1")
        assert obj.read_property(PropertyIdentifier.LAST_NOTIFY_RECORD) == 0


# ---------------------------------------------------------------------------
# 8. StagingObject
# ---------------------------------------------------------------------------


class TestStagingObject:
    """Property-level tests for Staging (Clause 12.62)."""

    def test_instantiation(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        assert obj.OBJECT_TYPE == ObjectType.STAGING
        assert obj.object_identifier.instance_number == 1

    def test_present_stage_default(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_STAGE) == StagingState.NOT_STAGED

    def test_present_stage_is_read_only(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_STAGE, StagingState.STAGED)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_write_present_value(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0

    def test_write_stages(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        stages = [{"name": "stage1"}, {"name": "stage2"}]
        obj.write_property(PropertyIdentifier.STAGES, stages)
        assert obj.read_property(PropertyIdentifier.STAGES) == stages

    def test_write_target_references(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        refs = [{"object": "analog-input:1", "property": "present-value"}]
        obj.write_property(PropertyIdentifier.TARGET_REFERENCES, refs)
        assert obj.read_property(PropertyIdentifier.TARGET_REFERENCES) == refs

    def test_out_of_service_default(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        assert obj.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_event_state_default(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        assert obj.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_status_flags_initialized(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="staging-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)


# ---------------------------------------------------------------------------
# 9. LoadControlObject
# ---------------------------------------------------------------------------


class TestLoadControlObject:
    """Property-level tests for Load Control (Clause 12.28)."""

    def test_instantiation(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.OBJECT_TYPE == ObjectType.LOAD_CONTROL

    def test_present_value_default(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == ShedState.SHED_INACTIVE

    def test_present_value_is_read_only(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, ShedState.SHED_REQUEST_PENDING)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_requested_shed_level_writable(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        shed = BACnetShedLevel(percent=50)
        obj.write_property(PropertyIdentifier.REQUESTED_SHED_LEVEL, shed)
        assert obj.read_property(PropertyIdentifier.REQUESTED_SHED_LEVEL) == shed

    def test_expected_shed_level_is_read_only(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        shed = BACnetShedLevel(level=3)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.EXPECTED_SHED_LEVEL, shed)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_actual_shed_level_is_read_only(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        shed = BACnetShedLevel(percent=25)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.ACTUAL_SHED_LEVEL, shed)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_shed_duration_default(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.read_property(PropertyIdentifier.SHED_DURATION) == 0

    def test_write_shed_duration(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        obj.write_property(PropertyIdentifier.SHED_DURATION, 3600)
        assert obj.read_property(PropertyIdentifier.SHED_DURATION) == 3600

    def test_duty_window_default(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.read_property(PropertyIdentifier.DUTY_WINDOW) == 0

    def test_shed_levels_default(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.read_property(PropertyIdentifier.SHED_LEVELS) == []

    def test_shed_level_descriptions_default(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        assert obj.read_property(PropertyIdentifier.SHED_LEVEL_DESCRIPTIONS) == []

    def test_start_time_is_read_only(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.START_TIME, "anything")
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_initialized(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)


# ---------------------------------------------------------------------------
# 10. GroupObject
# ---------------------------------------------------------------------------


class TestGroupObject:
    """Property-level tests for Group (Clause 12.14)."""

    def test_instantiation(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        assert obj.OBJECT_TYPE == ObjectType.GROUP

    def test_list_of_group_members_default(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        assert obj.read_property(PropertyIdentifier.LIST_OF_GROUP_MEMBERS) == []

    def test_write_list_of_group_members(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        members = [{"object": "ai-1", "property": "present-value"}]
        obj.write_property(PropertyIdentifier.LIST_OF_GROUP_MEMBERS, members)
        assert obj.read_property(PropertyIdentifier.LIST_OF_GROUP_MEMBERS) == members

    def test_present_value_default_empty(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == []

    def test_present_value_is_read_only(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, [1, 2, 3])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_property_list_includes_required(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.LIST_OF_GROUP_MEMBERS in prop_list
        assert PropertyIdentifier.PRESENT_VALUE in prop_list

    def test_object_type_read(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="group-1")
        assert obj.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.GROUP


# ---------------------------------------------------------------------------
# 11. GlobalGroupObject
# ---------------------------------------------------------------------------


class TestGlobalGroupObject:
    """Property-level tests for Global Group (Clause 12.50)."""

    def test_instantiation(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        assert obj.OBJECT_TYPE == ObjectType.GLOBAL_GROUP

    def test_group_members_default(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        assert obj.read_property(PropertyIdentifier.GROUP_MEMBERS) == []

    def test_write_group_members(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        members = [{"device": 1, "object": "ai-1", "property": "pv"}]
        obj.write_property(PropertyIdentifier.GROUP_MEMBERS, members)
        assert obj.read_property(PropertyIdentifier.GROUP_MEMBERS) == members

    def test_present_value_default_empty(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == []

    def test_present_value_is_read_only(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, [42])
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_event_state_default(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        assert obj.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_status_flags_initialized(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_property_list_includes_group_members(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.GROUP_MEMBERS in prop_list
        assert PropertyIdentifier.PRESENT_VALUE in prop_list


# ---------------------------------------------------------------------------
# 12. StructuredViewObject
# ---------------------------------------------------------------------------


class TestStructuredViewObject:
    """Property-level tests for Structured View (Clause 12.29)."""

    def test_instantiation(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.OBJECT_TYPE == ObjectType.STRUCTURED_VIEW

    def test_node_type_default(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.read_property(PropertyIdentifier.NODE_TYPE) == NodeType.UNKNOWN

    def test_write_node_type(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        obj.write_property(PropertyIdentifier.NODE_TYPE, NodeType.AREA)
        assert obj.read_property(PropertyIdentifier.NODE_TYPE) == NodeType.AREA

    def test_subordinate_list_default_empty(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.read_property(PropertyIdentifier.SUBORDINATE_LIST) == []

    def test_write_subordinate_list(self):
        from bac_py.objects.structured_view import StructuredViewObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = StructuredViewObject(1, object_name="sv-1")
        subs = [ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)]
        obj.write_property(PropertyIdentifier.SUBORDINATE_LIST, subs)
        assert obj.read_property(PropertyIdentifier.SUBORDINATE_LIST) == subs

    def test_object_type_read(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        assert obj.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.STRUCTURED_VIEW

    def test_property_list_includes_required(self):
        from bac_py.objects.structured_view import StructuredViewObject

        obj = StructuredViewObject(1, object_name="sv-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.NODE_TYPE in prop_list
        assert PropertyIdentifier.SUBORDINATE_LIST in prop_list


# ---------------------------------------------------------------------------
# 13. NotificationForwarderObject
# ---------------------------------------------------------------------------


class TestNotificationForwarderObject:
    """Property-level tests for Notification Forwarder (Clause 12.51)."""

    def test_instantiation(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.OBJECT_TYPE == ObjectType.NOTIFICATION_FORWARDER

    def test_subscribed_recipients_default(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.read_property(PropertyIdentifier.SUBSCRIBED_RECIPIENTS) == []

    def test_write_subscribed_recipients(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        recipients = [{"address": "192.168.1.100"}]
        obj.write_property(PropertyIdentifier.SUBSCRIBED_RECIPIENTS, recipients)
        assert obj.read_property(PropertyIdentifier.SUBSCRIBED_RECIPIENTS) == recipients

    def test_local_forwarding_only_default(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.read_property(PropertyIdentifier.LOCAL_FORWARDING_ONLY) is True

    def test_write_local_forwarding_only(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        obj.write_property(PropertyIdentifier.LOCAL_FORWARDING_ONLY, False)
        assert obj.read_property(PropertyIdentifier.LOCAL_FORWARDING_ONLY) is False

    def test_event_state_default(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        assert obj.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_status_flags_initialized(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_property_list_includes_required(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-1")
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.SUBSCRIBED_RECIPIENTS in prop_list
        assert PropertyIdentifier.LOCAL_FORWARDING_ONLY in prop_list


# ---------------------------------------------------------------------------
# 14. AlertEnrollmentObject
# ---------------------------------------------------------------------------


class TestAlertEnrollmentObject:
    """Property-level tests for Alert Enrollment (Clause 12.52)."""

    def test_instantiation(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.OBJECT_TYPE == ObjectType.ALERT_ENROLLMENT

    def test_present_value_is_read_only(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, "test")
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_notification_class_writable(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1", notification_class=5)
        assert obj.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 5
        obj.write_property(PropertyIdentifier.NOTIFICATION_CLASS, 10)
        assert obj.read_property(PropertyIdentifier.NOTIFICATION_CLASS) == 10

    def test_event_enable_writable(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1", event_enable=[True, True, True])
        result = obj.read_property(PropertyIdentifier.EVENT_ENABLE)
        assert result == [True, True, True]

    def test_event_detection_enable_default(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.read_property(PropertyIdentifier.EVENT_DETECTION_ENABLE) is True

    def test_write_event_detection_enable(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        obj.write_property(PropertyIdentifier.EVENT_DETECTION_ENABLE, False)
        assert obj.read_property(PropertyIdentifier.EVENT_DETECTION_ENABLE) is False

    def test_event_state_default(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_status_flags_initialized(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        sf = obj.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_object_type_read(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1")
        assert obj.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.ALERT_ENROLLMENT

    def test_property_list_includes_required(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-1", notification_class=1, event_enable=[])
        prop_list = obj.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in prop_list
        assert PropertyIdentifier.NOTIFICATION_CLASS in prop_list
        assert PropertyIdentifier.EVENT_ENABLE in prop_list


# ---------------------------------------------------------------------------
# 15. TestReadOnlyEnforcement - cross-object read-only property checks
# ---------------------------------------------------------------------------


class TestReadOnlyEnforcement:
    """Verify read-only properties cannot be written across multiple object types."""

    # -- object_type is read-only on all types --

    def test_object_type_read_only_on_lighting_output(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_timer(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_channel(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_averaging(self):
        from bac_py.objects.averaging import AveragingObject

        obj = AveragingObject(1, object_name="avg-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_command(self):
        from bac_py.objects.command import CommandObject

        obj = CommandObject(1, object_name="cmd-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_group(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="grp-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_global_group(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_load_control(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_notification_forwarder(self):
        from bac_py.objects.notification_forwarder import NotificationForwarderObject

        obj = NotificationForwarderObject(1, object_name="nf-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_event_log(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_trend_log_multiple(self):
        from bac_py.objects.trendlog_multiple import TrendLogMultipleObject

        obj = TrendLogMultipleObject(1, object_name="tlm-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_staging(self):
        from bac_py.objects.staging import StagingObject

        obj = StagingObject(1, object_name="stg-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_type_read_only_on_alert_enrollment(self):
        from bac_py.objects.alert_enrollment import AlertEnrollmentObject

        obj = AlertEnrollmentObject(1, object_name="ae-ro")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.OBJECT_TYPE, ObjectType.ANALOG_INPUT)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    # -- object_identifier is read-only on all types --

    def test_object_identifier_read_only_on_lighting_output(self):
        from bac_py.objects.lighting import LightingOutputObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = LightingOutputObject(1, object_name="lo-oid")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.OBJECT_IDENTIFIER,
                ObjectIdentifier(ObjectType.LIGHTING_OUTPUT, 99),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_identifier_read_only_on_timer(self):
        from bac_py.objects.timer import TimerObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = TimerObject(1, object_name="timer-oid")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.OBJECT_IDENTIFIER,
                ObjectIdentifier(ObjectType.TIMER, 99),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_identifier_read_only_on_command(self):
        from bac_py.objects.command import CommandObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = CommandObject(1, object_name="cmd-oid")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.OBJECT_IDENTIFIER,
                ObjectIdentifier(ObjectType.COMMAND, 99),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_identifier_read_only_on_group(self):
        from bac_py.objects.group import GroupObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = GroupObject(1, object_name="grp-oid")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.OBJECT_IDENTIFIER,
                ObjectIdentifier(ObjectType.GROUP, 99),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_object_identifier_read_only_on_load_control(self):
        from bac_py.objects.load_control import LoadControlObject
        from bac_py.types.primitives import ObjectIdentifier

        obj = LoadControlObject(1, object_name="lc-oid")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.OBJECT_IDENTIFIER,
                ObjectIdentifier(ObjectType.LOAD_CONTROL, 99),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    # -- status_flags is read-only on input-style objects --

    def test_status_flags_read_only_on_analog_input(self):
        from bac_py.objects.analog import AnalogInputObject

        obj = AnalogInputObject(1, object_name="ai-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(in_alarm=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_timer(self):
        from bac_py.objects.timer import TimerObject

        obj = TimerObject(1, object_name="timer-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(in_alarm=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_lighting_output(self):
        from bac_py.objects.lighting import LightingOutputObject

        obj = LightingOutputObject(1, object_name="lo-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(fault=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_event_log(self):
        from bac_py.objects.event_log import EventLogObject

        obj = EventLogObject(1, object_name="el-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(out_of_service=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_load_control(self):
        from bac_py.objects.load_control import LoadControlObject

        obj = LoadControlObject(1, object_name="lc-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(overridden=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_channel(self):
        from bac_py.objects.channel import ChannelObject

        obj = ChannelObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(in_alarm=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_status_flags_read_only_on_global_group(self):
        from bac_py.objects.global_group import GlobalGroupObject

        obj = GlobalGroupObject(1, object_name="gg-sf")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(
                PropertyIdentifier.STATUS_FLAGS,
                StatusFlags(in_alarm=True),
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    # -- unknown property raises UNKNOWN_PROPERTY --

    def test_unknown_property_read_raises(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="grp-unk")
        with pytest.raises(BACnetError) as exc_info:
            obj.read_property(PropertyIdentifier.LOGGING_TYPE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_unknown_property_write_raises(self):
        from bac_py.objects.group import GroupObject

        obj = GroupObject(1, object_name="grp-unk2")
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.LOG_ENABLE, True)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY
