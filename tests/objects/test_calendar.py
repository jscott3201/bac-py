"""Tests for BACnet Calendar object (Clause 12.9)."""

import pytest

from bac_py.objects.base import create_object
from bac_py.objects.calendar import CalendarObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import (
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier


class TestCalendarObject:
    """Tests for CalendarObject (Clause 12.9)."""

    def test_create_basic(self):
        cal = CalendarObject(1)
        assert cal.object_identifier == ObjectIdentifier(ObjectType.CALENDAR, 1)

    def test_object_type(self):
        cal = CalendarObject(1)
        assert cal.read_property(PropertyIdentifier.OBJECT_TYPE) == ObjectType.CALENDAR

    def test_present_value_default(self):
        cal = CalendarObject(1)
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is False

    def test_present_value_read_only(self):
        cal = CalendarObject(1)
        with pytest.raises(BACnetError) as exc_info:
            cal.write_property(PropertyIdentifier.PRESENT_VALUE, True)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_date_list_default_empty(self):
        cal = CalendarObject(1)
        assert cal.read_property(PropertyIdentifier.DATE_LIST) == []

    def test_date_list_writable(self):
        cal = CalendarObject(1)
        dates = [(2024, 12, 25), (2024, 1, 1)]
        cal.write_property(PropertyIdentifier.DATE_LIST, dates)
        assert cal.read_property(PropertyIdentifier.DATE_LIST) == dates

    def test_date_list_initial_property(self):
        dates = [(2024, 7, 4)]
        cal = CalendarObject(1, date_list=dates)
        assert cal.read_property(PropertyIdentifier.DATE_LIST) == dates

    def test_description_optional(self):
        cal = CalendarObject(1)
        assert cal.read_property(PropertyIdentifier.DESCRIPTION) is None

    def test_description_writable(self):
        cal = CalendarObject(1)
        cal.write_property(PropertyIdentifier.DESCRIPTION, "Holidays")
        assert cal.read_property(PropertyIdentifier.DESCRIPTION) == "Holidays"

    def test_property_list(self):
        cal = CalendarObject(1)
        plist = cal.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert PropertyIdentifier.PRESENT_VALUE in plist
        assert PropertyIdentifier.DATE_LIST in plist
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist
        assert PropertyIdentifier.OBJECT_NAME not in plist
        assert PropertyIdentifier.OBJECT_TYPE not in plist
        assert PropertyIdentifier.PROPERTY_LIST not in plist

    def test_not_commandable(self):
        cal = CalendarObject(1)
        assert cal._priority_array is None

    def test_no_status_flags(self):
        """Calendar has no Status_Flags per spec."""
        cal = CalendarObject(1)
        with pytest.raises(BACnetError) as exc_info:
            cal.read_property(PropertyIdentifier.STATUS_FLAGS)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_factory_creation(self):
        import bac_py.objects  # noqa: F401

        obj = create_object(ObjectType.CALENDAR, 10)
        assert isinstance(obj, CalendarObject)

    def test_initial_properties(self):
        cal = CalendarObject(1, object_name="CAL-1", description="Test calendar")
        assert cal.read_property(PropertyIdentifier.OBJECT_NAME) == "CAL-1"
        assert cal.read_property(PropertyIdentifier.DESCRIPTION) == "Test calendar"
