"""Tests for BACnet Schedule object (Clause 12.24)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.schedule import ScheduleObject
from bac_py.services.errors import BACnetError
from bac_py.types.constructed import BACnetDateRange, StatusFlags
from bac_py.types.enums import (
    ErrorCode,
    EventState,
    ObjectType,
    PropertyIdentifier,
    Reliability,
)
from bac_py.types.primitives import ObjectIdentifier


class TestScheduleObject:
    """Tests for ScheduleObject (Clause 12.24)."""

    def test_create_basic(self):
        sched = ScheduleObject(1)
        assert sched.object_identifier == ObjectIdentifier(ObjectType.SCHEDULE, 1)

    def test_object_type(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.SCHEDULE

    def test_present_value_read_only(self):
        sched = ScheduleObject(1)
        with pytest.raises(BACnetError) as exc_info:
            sched.write_property(PropertyIdentifier.PRESENT_VALUE, 42)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_effective_period_default(self):
        sched = ScheduleObject(1)
        period = sched.read_property(PropertyIdentifier.EFFECTIVE_PERIOD)
        assert isinstance(period, BACnetDateRange)
        assert period.start_date.year == 1900
        assert period.start_date.month == 1
        assert period.start_date.day == 1
        assert period.end_date.year == 2155
        assert period.end_date.month == 12
        assert period.end_date.day == 31

    def test_effective_period_writable(self):
        sched = ScheduleObject(1)
        new_period = ((2024, 1, 1), (2024, 12, 31))
        sched.write_property(PropertyIdentifier.EFFECTIVE_PERIOD, new_period)
        assert sched.read_property(PropertyIdentifier.EFFECTIVE_PERIOD) == new_period

    def test_weekly_schedule_optional(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.WEEKLY_SCHEDULE) is None

    def test_weekly_schedule_writable(self):
        sched = ScheduleObject(1)
        weekly = [[] for _ in range(7)]
        sched.write_property(PropertyIdentifier.WEEKLY_SCHEDULE, weekly)
        assert sched.read_property(PropertyIdentifier.WEEKLY_SCHEDULE) == weekly

    def test_exception_schedule_optional(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.EXCEPTION_SCHEDULE) is None

    def test_schedule_default_writable(self):
        sched = ScheduleObject(1)
        sched.write_property(PropertyIdentifier.SCHEDULE_DEFAULT, 72.0)
        assert sched.read_property(PropertyIdentifier.SCHEDULE_DEFAULT) == 72.0

    def test_list_of_object_property_references_default(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES) == []

    def test_priority_for_writing_default(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.PRIORITY_FOR_WRITING) == 16

    def test_status_flags_initialized(self):
        sched = ScheduleObject(1)
        sf = sched.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert isinstance(sf, StatusFlags)

    def test_event_state_default(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.EVENT_STATE) == EventState.NORMAL

    def test_reliability_default(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.RELIABILITY) == Reliability.NO_FAULT_DETECTED

    def test_out_of_service_default(self):
        sched = ScheduleObject(1)
        assert sched.read_property(PropertyIdentifier.OUT_OF_SERVICE) is False

    def test_not_commandable(self):
        sched = ScheduleObject(1)
        assert sched._priority_array is None

    def test_property_list(self):
        sched = ScheduleObject(1)
        plist = sched.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.EFFECTIVE_PERIOD in plist
        assert PropertyIdentifier.STATUS_FLAGS in plist
        assert PropertyIdentifier.RELIABILITY in plist
        assert PropertyIdentifier.SCHEDULE_DEFAULT in plist
        assert PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES in plist
        assert PropertyIdentifier.PRIORITY_FOR_WRITING in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.SCHEDULE, 3)
        assert isinstance(obj, ScheduleObject)

    def test_initial_properties(self):
        sched = ScheduleObject(1, object_name="SCHED-1", description="HVAC schedule")
        assert sched.read_property(PropertyIdentifier.OBJECT_NAME) == "SCHED-1"
        assert sched.read_property(PropertyIdentifier.DESCRIPTION) == "HVAC schedule"
