"""Tests for BACnet Date/Time value objects."""

from bac_py.objects.base import create_object
from bac_py.objects.value_types import (
    DatePatternValueObject,
    DateTimePatternValueObject,
    DateValueObject,
    TimePatternValueObject,
    TimeValueObject,
)
from bac_py.types.enums import (
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BACnetDate, BACnetTime


class TestDateValueObject:
    """DateValue object (Clause 12.38)."""

    def test_object_type(self):
        obj = DateValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATE_VALUE

    def test_registry_creation(self):
        obj = create_object(ObjectType.DATE_VALUE, 1)
        assert isinstance(obj, DateValueObject)

    def test_present_value_write(self):
        obj = DateValueObject(1)
        date = BACnetDate(2024, 6, 15, 6)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, date)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == date

    def test_commandable(self):
        obj = DateValueObject(1, commandable=True)
        date = BACnetDate(2024, 1, 1, 1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, date, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == date


class TestDatePatternValueObject:
    """DatePatternValue object (Clause 12.39)."""

    def test_object_type(self):
        obj = DatePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATEPATTERN_VALUE

    def test_wildcard_date(self):
        obj = DatePatternValueObject(1)
        # Wildcard date pattern (any year, any month, day 1)
        pattern = BACnetDate(0xFF, 0xFF, 1, 0xFF)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, pattern)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == pattern


class TestTimeValueObject:
    """TimeValue object (Clause 12.46)."""

    def test_object_type(self):
        obj = TimeValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.TIME_VALUE

    def test_present_value_write(self):
        obj = TimeValueObject(1)
        time = BACnetTime(14, 30, 0, 0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, time)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == time

    def test_commandable(self):
        obj = TimeValueObject(1, commandable=True)
        time = BACnetTime(8, 0, 0, 0)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, time, priority=16)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == time


class TestTimePatternValueObject:
    """TimePatternValue object (Clause 12.47)."""

    def test_object_type(self):
        obj = TimePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.TIMEPATTERN_VALUE

    def test_wildcard_time(self):
        obj = TimePatternValueObject(1)
        pattern = BACnetTime(0xFF, 30, 0xFF, 0xFF)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, pattern)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == pattern


class TestDateTimePatternValueObject:
    """DateTimePatternValue object (Clause 12.41)."""

    def test_object_type(self):
        obj = DateTimePatternValueObject(1)
        assert obj.OBJECT_TYPE == ObjectType.DATETIMEPATTERN_VALUE

    def test_registry_creation(self):
        obj = create_object(ObjectType.DATETIMEPATTERN_VALUE, 1)
        assert isinstance(obj, DateTimePatternValueObject)
