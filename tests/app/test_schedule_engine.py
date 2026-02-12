"""Tests for Schedule evaluation engine (Clause 12.24)."""

import asyncio
import datetime

import pytest

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
        return [o for o in self._objects.values() if getattr(o, "OBJECT_TYPE", None) == obj_type]


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
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 2, 12, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=55.0),),
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
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=50.0),),
            event_priority=10,
        )
        exc_high = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=45.0),),
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
            BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
        ]
        cal.evaluate(datetime.date(2024, 2, 12))
        db.add(cal)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        exc = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),),
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
        sched._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = [
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
        sched._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = [
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
        target.write_property(PropertyIdentifier.PRESENT_VALUE, 50.0, priority=1)
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
            BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
        ]
        db.add(cal)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is True


# ---------------------------------------------------------------------------
# Lifecycle (async start/stop)
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Calling start() twice is a no-op -- the second call returns immediately."""
        db = _FakeObjectDB()
        engine = _make_engine(db)

        await engine.start()
        first_task = engine._task
        assert first_task is not None

        # Second start should be a no-op
        await engine.start()
        assert engine._task is first_task

        # Clean up
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self):
        """stop() cancels the task and clears _last_values."""
        db = _FakeObjectDB()
        engine = _make_engine(db)

        await engine.start()
        assert engine._task is not None

        # Seed _last_values so we can verify it gets cleared
        engine._last_values[ObjectIdentifier(ObjectType.SCHEDULE, 1)] = 42

        await engine.stop()
        assert engine._task is None
        assert engine._last_values == {}

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """stop() when never started is a safe no-op."""
        db = _FakeObjectDB()
        engine = _make_engine(db)
        await engine.stop()  # Should not raise
        assert engine._task is None

    @pytest.mark.asyncio
    async def test_run_loop_executes_cycle(self):
        """_run_loop() calls _evaluate_cycle at least once before being stopped."""
        db = _FakeObjectDB()
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
        ]
        db.add(cal)

        engine = _make_engine(db)
        engine._scan_interval = 0.01  # Speed up for test

        await engine.start()
        # Give the loop time to run at least one cycle
        await asyncio.sleep(0.05)
        await engine.stop()

        # Calendar should have been evaluated (all-wildcard matches any date)
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is True


# ---------------------------------------------------------------------------
# Evaluate cycle processes schedules
# ---------------------------------------------------------------------------


class TestEvaluateCycleSchedules:
    def test_evaluate_cycle_processes_schedules(self):
        """_evaluate_cycle evaluates Schedule objects (covering line 106)."""
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 99.0
        db.add(sched)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        # Schedule_default should be applied as present_value
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 99.0


# ---------------------------------------------------------------------------
# Exception schedule resolution -- additional branches
# ---------------------------------------------------------------------------


class TestExceptionScheduleBranches:
    def test_exception_schedule_resolves_value_and_returns(self):
        """When exception_schedule matches today, its value is applied.

        The weekly_schedule is never consulted (lines 139-141).
        """
        db = _FakeObjectDB()
        sched = ScheduleObject(1)

        # Weekly schedule: Monday 08:00 → 72.0
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # Exception: all-wildcard date, 00:00 → 55.0
        exc = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=55.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)  # Monday
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)

        # Exception value wins over weekly 72.0
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 55.0

    def test_exception_priority_comparison_skips_lower(self):
        """Exceptions with event_priority >= best_priority are skipped (line 177).

        When a high-priority (lower number) exception is listed first and a
        lower-priority one follows, the second one's priority check triggers
        the ``continue`` on line 177.
        """
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # First exception: priority 5 (higher priority = lower number)
        exc_high = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=45.0),),
            event_priority=5,
        )
        # Second exception: priority 10, same date -- should be skipped by line 177
        exc_low = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=99.0),),
            event_priority=10,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc_high, exc_low]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 45.0

    def test_exception_calendar_reference_not_in_db(self):
        """Calendar ObjectIdentifier reference not found in db → skipped (line 183-184)."""
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # Exception references calendar:1 which does NOT exist in db
        exc = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 99),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # Falls through to schedule_default since the calendar isn't found
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 60.0

    def test_exception_calendar_reference_present_value_false(self):
        """Calendar reference with present_value=False → skipped (line 186-187)."""
        db = _FakeObjectDB()

        # Calendar present_value = False (date doesn't match)
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = []
        cal.evaluate(datetime.date(2024, 2, 12))  # Empty list → False
        db.add(cal)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        exc = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # Calendar is False → exception skipped → falls to schedule_default
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 60.0

    def test_exception_calendar_entry_no_match(self):
        """BACnetCalendarEntry period that doesn't match today → skipped (line 189)."""
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # Exception for December 25 only -- won't match February 12
        exc = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # No exception match → falls to schedule_default
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 60.0

    def test_exception_unknown_period_type_skipped(self):
        """Exception with unrecognized period type → skipped (lines 191-192)."""
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0

        # Create an exception with a period that is neither ObjectIdentifier
        # nor BACnetCalendarEntry (use a plain string as unknown type)
        exc = BACnetSpecialEvent(
            period="some-unknown-period-type",  # type: ignore[arg-type]
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=42.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # Unknown period type → skipped → falls to schedule_default
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 60.0


# ---------------------------------------------------------------------------
# Weekly schedule fallback branch
# ---------------------------------------------------------------------------


class TestWeeklyScheduleFallback:
    def test_weekly_schedule_fallback_when_no_exception(self):
        """When exception_schedule has no matches, weekly_schedule is used.

        Covers lines 148-153 branch.
        """
        db = _FakeObjectDB()
        sched = ScheduleObject(1)

        # Exception that won't match (Christmas only)
        exc = BACnetSpecialEvent(
            period=BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 0xFF)),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=99.0),),
            event_priority=1,
        )
        sched._properties[PropertyIdentifier.EXCEPTION_SCHEDULE] = [exc]

        # Weekly schedule: Monday 08:00 → 72.0
        monday_entries = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
        ]
        weekly = [monday_entries] + [[] for _ in range(6)]
        sched._properties[PropertyIdentifier.WEEKLY_SCHEDULE] = weekly
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 60.0
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)  # Monday
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0


# ---------------------------------------------------------------------------
# Apply value -- error paths
# ---------------------------------------------------------------------------


class TestApplyValueErrors:
    def test_apply_value_target_not_found(self):
        """Target object not in db → logs warning, doesn't crash (lines 251-256)."""
        db = _FakeObjectDB()
        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 72.0
        sched._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 10
        sched._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = [
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 999),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        # Should not raise -- just logs a warning
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0

    def test_apply_value_write_failure(self):
        """write_property raises an exception → logs warning, continues (lines 265-266)."""

        class _ExplodingTarget:
            """Target that raises on write_property."""

            OBJECT_TYPE = ObjectType.ANALOG_VALUE
            object_identifier = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)

            def read_property(self, prop):
                return None

            def write_property(self, prop, value, *, priority=None, array_index=None):
                raise RuntimeError("simulated write failure")

        db = _FakeObjectDB()
        target = _ExplodingTarget()
        db.add(target)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 72.0
        sched._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 10
        sched._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = [
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        # Should not raise -- logs warning and continues
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        assert sched.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0

    def test_apply_value_target_not_found_with_valid_target(self):
        """Mix of missing and valid targets.

        Missing logs warning, valid target still gets written.
        """
        from bac_py.objects.analog import AnalogValueObject

        db = _FakeObjectDB()
        target = AnalogValueObject(2, commandable=True)
        db.add(target)

        sched = ScheduleObject(1)
        sched._properties[PropertyIdentifier.SCHEDULE_DEFAULT] = 72.0
        sched._properties[PropertyIdentifier.PRIORITY_FOR_WRITING] = 10
        sched._properties[PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES] = [
            # Missing target
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 999),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
            # Valid target
            BACnetObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 2),
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            ),
        ]
        db.add(sched)

        engine = _make_engine(db)
        today = datetime.date(2024, 2, 12)
        engine._evaluate_schedule(sched, today, datetime.time(10, 0), db)
        # Valid target should still be written despite the missing one
        assert target.read_property(PropertyIdentifier.PRESENT_VALUE) == 72.0
