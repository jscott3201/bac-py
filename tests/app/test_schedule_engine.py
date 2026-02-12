"""Tests for Schedule evaluation engine (Clause 12.24)."""

import datetime

from bac_py.app.schedule_engine import ScheduleEngine, _now_tuple, _time_tuple
from bac_py.objects.calendar import CalendarObject
from bac_py.objects.schedule import ScheduleObject
from bac_py.types.constructed import (
    BACnetCalendarEntry,
    BACnetDateRange,
    BACnetObjectPropertyReference,
    BACnetSpecialEvent,
    BACnetTimeValue,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeObjectDB:
    """Minimal ObjectDatabase stand-in for tests."""

    def __init__(self) -> None:
        self._objects: dict[ObjectIdentifier, object] = {}

    def add(self, obj: object) -> None:
        self._objects[obj.object_identifier] = obj  # type: ignore[attr-defined]

    def get(self, oid: ObjectIdentifier) -> object | None:
        return self._objects.get(oid)

    def get_objects_of_type(self, obj_type: ObjectType) -> list[object]:
        return [
            o
            for o in self._objects.values()
            if getattr(o, "OBJECT_TYPE", None) == obj_type
        ]


class _FakeApp:
    def __init__(self, db: _FakeObjectDB) -> None:
        self.object_db = db


def _make_engine(db: _FakeObjectDB) -> ScheduleEngine:
    app = _FakeApp(db)
    return ScheduleEngine(app)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Time tuple helpers
# ---------------------------------------------------------------------------


class TestTimeTuples:
    def test_time_tuple_normal(self):
        t = BACnetTime(14, 30, 0, 0)
        assert _time_tuple(t) == (14, 30, 0, 0)

    def test_time_tuple_wildcards(self):
        t = BACnetTime(0xFF, 0xFF, 0xFF, 0xFF)
        assert _time_tuple(t) == (0, 0, 0, 0)

    def test_now_tuple(self):
        t = datetime.time(14, 30, 15, 500000)
        result = _now_tuple(t)
        assert result == (14, 30, 15, 50)


# ---------------------------------------------------------------------------
# Schedule evaluation -- weekly schedule
# ---------------------------------------------------------------------------


class TestWeeklySchedule:
    def test_resolves_from_weekly_schedule(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        # Monday schedule with one entry at 08:00 = 72.0
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 68.0
        db.add(sched)

        engine = _make_engine(db)
        # Monday at 10:00 → should resolve to 72.0
        today = datetime.date(2024, 2, 12)  # Monday
        now = datetime.time(10, 0, 0)
        engine._evaluate_schedule(sched, today, now, db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0

    def test_before_first_entry_uses_default(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 68.0
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)  # Monday
        now = datetime.time(6, 0, 0)  # Before 8:00
        engine._evaluate_schedule(sched, today, now, db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 68.0

    def test_multiple_time_values_takes_latest(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
            BACnetTimeValue(time=BACnetTime(12, 0, 0, 0), value=74.0),
            BACnetTimeValue(time=BACnetTime(17, 0, 0, 0), value=68.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 65.0
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)  # Monday

        # At 14:00 → latest is 12:00 → 74.0
        engine._evaluate_schedule(sched, today, datetime.time(14, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 74.0

        # At 18:00 → latest is 17:00 → 68.0
        engine._evaluate_schedule(sched, today, datetime.time(18, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 68.0


# ---------------------------------------------------------------------------
# Schedule evaluation -- effective period
# ---------------------------------------------------------------------------


class TestEffectivePeriod:
    def test_outside_effective_period_uses_default(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.EFFECTIVE_PERIOD] = BACnetDateRange(
            start_date=BACnetDate(2024, 6, 1, 0xFF),
            end_date=BACnetDate(2024, 8, 31, 0xFF),
        )
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0
        db.add(sched)

        engine = _make_engine(db)
        # February is outside June-August
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 60.0

    def test_within_effective_period_evaluates_weekly(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.EFFECTIVE_PERIOD] = BACnetDateRange(
            start_date=BACnetDate(2024, 6, 1, 0xFF),
            end_date=BACnetDate(2024, 8, 31, 0xFF),
        )
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0
        db.add(sched)

        engine = _make_engine(db)
        # Monday June 3 at 10:00 → within period and weekly matches
        today = datetime.date(2024, 6, 3)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0


# ---------------------------------------------------------------------------
# Schedule evaluation -- exception schedule
# ---------------------------------------------------------------------------


class TestExceptionSchedule:
    def test_exception_overrides_weekly(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # Exception for a specific date
        exc = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0, value=BACnetDate(2024, 2, 12, 0xFF)
            ),
            list_of_time_values=(
                BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=55.0),
            ),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 55.0

    def test_higher_priority_exception_wins(self):
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        exc_low = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
            ),
            list_of_time_values=(
                BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=50.0),
            ),
            event_priority=10,
        )
        exc_high = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
            ),
            list_of_time_values=(
                BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=45.0),
            ),
            event_priority=5,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [
            exc_low,
            exc_high,
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 45.0

    def test_exception_with_calendar_reference(self):
        db = _FakeObjectDB()

        # Create a calendar that matches today
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(
                choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
            ),
        ]
        cal.evaluate(datetime.date(2024, 2, 12))
        db.add(cal)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        exc = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(
                BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),
            ),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


class TestOutputWriting:
    def test_writes_to_target_on_change(self):
        from bac_py.objects.analog import AnalogValueObject

        db = _FakeObjectDB()
        target = AnalogValueObject(1, commandable=True)
        db.add(target)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 72.0
        sched._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 10
        sched._properties[
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES
        ] = [
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)

        # Target should have been written at priority 10
        assert target.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0

    def test_no_write_when_value_unchanged(self):
        from bac_py.objects.analog import AnalogValueObject

        db = _FakeObjectDB()
        target = AnalogValueObject(1, commandable=True)
        db.add(target)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 72.0
        sched._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 10
        sched._properties[
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES
        ] = [
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)

        # First evaluation → writes
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert target.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0

        # Override target at higher priority
        target.write_property(
            PropertyIdentifier.PRESENT_VALUE, 50.0, priority=1
        )
        assert target.read_property(PropertyIdentifier.PRESENT_VALUE) == 50.0

        # Second evaluation → same schedule value, no new write
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # Target still shows priority 1 value
        assert target.read_property(PropertyIdentifier.PRESENT_VALUE) == 50.0


# ---------------------------------------------------------------------------
# Calendar evaluation within cycle
# ---------------------------------------------------------------------------


class TestCalendarInCycle:
    def test_evaluate_cycle_updates_calendars(self):
        db = _FakeObjectDB()
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(
                choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)
            ),
        ]
        db.add(cal)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is True
