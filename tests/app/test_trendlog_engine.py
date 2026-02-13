"""Tests for TrendLog recording engine (Clause 12.25)."""

import asyncio
import datetime
import time
from unittest.mock import patch

from bac_py.app.trendlog_engine import TrendLogEngine, _datetime_to_float, _now_datetime
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.trendlog import TrendLogObject
from bac_py.types.constructed import (
    BACnetDateTime,
    BACnetDeviceObjectPropertyReference,
    BACnetLogRecord,
)
from bac_py.types.enums import LoggingType, ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeObjectDB:
    def __init__(self) -> None:
        self._objects: dict[ObjectIdentifier, object] = {}

    def add(self, obj: object) -> None:
        self._objects[obj.object_identifier] = obj  # type: ignore[attr-defined]

    def get(self, oid: ObjectIdentifier) -> object | None:
        return self._objects.get(oid)

    def get_objects_of_type(self, obj_type: ObjectType) -> list[object]:
        return [o for o in self._objects.values() if getattr(o, "OBJECT_TYPE", None) == obj_type]


class _FakeApp:
    def __init__(self, db: _FakeObjectDB | ObjectDatabase) -> None:
        self.object_db = db


def _make_engine(db: _FakeObjectDB | ObjectDatabase) -> TrendLogEngine:
    app = _FakeApp(db)
    return TrendLogEngine(app, scan_interval=1.0)  # type: ignore[arg-type]


def _make_trendlog(
    instance: int = 1,
    *,
    target_oid: ObjectIdentifier | None = None,
    log_interval: int = 100,  # centiseconds → 1 second
    buffer_size: int = 100,
    stop_when_full: bool = False,
    logging_type: LoggingType = LoggingType.POLLED,
) -> TrendLogObject:
    tl = TrendLogObject(instance)
    tl._properties[PropertyIdentifier.LOG_ENABLE] = True
    tl._properties[PropertyIdentifier.LOG_INTERVAL] = log_interval
    tl._properties[PropertyIdentifier.BUFFER_SIZE] = buffer_size
    tl._properties[PropertyIdentifier.STOP_WHEN_FULL] = stop_when_full
    tl._properties[PropertyIdentifier.LOGGING_TYPE] = logging_type
    if target_oid is not None:
        tl._properties[PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY] = (
            BACnetDeviceObjectPropertyReference(
                object_identifier=target_oid,
                property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            )
        )
    return tl


# ---------------------------------------------------------------------------
# TrendLogObject.append_record()
# ---------------------------------------------------------------------------


class TestAppendRecord:
    def test_append_basic(self):
        tl = TrendLogObject(1)
        tl._properties[PropertyIdentifier.BUFFER_SIZE] = 100
        record = BACnetLogRecord(timestamp=_now_datetime(), log_datum=42.0)
        assert tl.append_record(record) is True
        assert tl.read_property(PropertyIdentifier.RECORD_COUNT) == 1
        assert tl.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 1

    def test_circular_overflow(self):
        tl = TrendLogObject(1)
        tl._properties[PropertyIdentifier.BUFFER_SIZE] = 3
        tl._properties[PropertyIdentifier.STOP_WHEN_FULL] = False

        for i in range(5):
            record = BACnetLogRecord(timestamp=_now_datetime(), log_datum=float(i))
            tl.append_record(record)

        # Buffer should have last 3 records
        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 3
        assert buf[0].log_datum == 2.0
        assert buf[1].log_datum == 3.0
        assert buf[2].log_datum == 4.0
        assert tl.read_property(PropertyIdentifier.RECORD_COUNT) == 3
        assert tl.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 5

    def test_stop_when_full(self):
        tl = TrendLogObject(1)
        tl._properties[PropertyIdentifier.BUFFER_SIZE] = 2
        tl._properties[PropertyIdentifier.STOP_WHEN_FULL] = True

        r1 = BACnetLogRecord(timestamp=_now_datetime(), log_datum=1.0)
        r2 = BACnetLogRecord(timestamp=_now_datetime(), log_datum=2.0)
        r3 = BACnetLogRecord(timestamp=_now_datetime(), log_datum=3.0)

        assert tl.append_record(r1) is True
        assert tl.append_record(r2) is True
        assert tl.append_record(r3) is False  # Buffer full

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 2
        assert tl.read_property(PropertyIdentifier.TOTAL_RECORD_COUNT) == 2


# ---------------------------------------------------------------------------
# Polled logging
# ---------------------------------------------------------------------------


class TestPolledLogging:
    def test_records_value_on_poll(self):
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 42.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,
        )
        db.add(tl)

        engine = _make_engine(db)
        # Force past the interval by setting last_poll far in the past
        engine._last_poll[tl.object_identifier] = 0.0
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 1
        assert buf[0].log_datum == 42.0

    def test_disabled_trendlog_not_recorded(self):
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 42.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        tl._properties[PropertyIdentifier.LOG_ENABLE] = False
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_missing_target_does_not_crash(self):
        db = _FakeObjectDB()
        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 99),
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._last_poll[tl.object_identifier] = 0.0
        # Should not raise
        engine._evaluate_cycle()
        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# Triggered logging
# ---------------------------------------------------------------------------


class TestTriggeredLogging:
    def test_trigger_records_and_resets(self):
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 99.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.TRIGGERED,
        )
        tl._properties[PropertyIdentifier.TRIGGER] = True
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 1
        assert buf[0].log_datum == 99.0
        # Trigger should be reset to False
        assert tl._properties[PropertyIdentifier.TRIGGER] is False

    def test_no_trigger_no_record(self):
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 99.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.TRIGGERED,
        )
        tl._properties[PropertyIdentifier.TRIGGER] = False
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# COV-based logging (Clause 12.25.13)
# ---------------------------------------------------------------------------


class TestCOVLogging:
    def _make_real_db(self):
        """Create a real ObjectDatabase for COV callback support."""
        return ObjectDatabase()

    def test_cov_records_when_property_changes(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        # First cycle registers the COV callback
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Now change the monitored property
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 1
        assert buf[0].log_datum == 42.0

    def test_cov_does_not_record_when_value_unchanged(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        # Write the same value -- no change notification fires
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_disabling_trendlog_removes_cov_subscription(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Disable the TrendLog
        tl._properties[PropertyIdentifier.LOG_ENABLE] = False
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions

        # Property change should NOT record (re-enable out-of-service for write)
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0)
        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_cov_respects_stop_time(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        # Set stop_time in the past
        tl._properties[PropertyIdentifier.STOP_TIME] = BACnetDateTime(
            date=BACnetDate(2000, 1, 1, 6),
            time=BACnetTime(0, 0, 0, 0),
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        # Should NOT subscribe because outside time window
        assert tl.object_identifier not in engine._cov_subscriptions

    def test_cov_multiple_changes_records_each(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
            buffer_size=10,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()

        # Multiple changes
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0)
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 30.0)
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 40.0)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 3
        assert buf[0].log_datum == 20.0
        assert buf[1].log_datum == 30.0
        assert buf[2].log_datum == 40.0

    async def test_stop_cleans_up_cov_subscriptions(self):
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        await engine.stop()
        assert len(engine._cov_subscriptions) == 0


# ---------------------------------------------------------------------------
# now_datetime helper
# ---------------------------------------------------------------------------


class TestNowDatetime:
    def test_now_datetime_structure(self):
        dt = _now_datetime()
        now = datetime.datetime.now()
        assert dt.date.year == now.year
        assert dt.date.month == now.month
        assert dt.date.day == now.day
        assert dt.time.hour == now.hour


# ---------------------------------------------------------------------------
# _datetime_to_float exception handling (lines 54-55)
# ---------------------------------------------------------------------------


class TestDatetimeToFloat:
    def test_invalid_date_returns_zero(self):
        """BACnetDateTime with out-of-range values triggers ValueError -> 0.0."""
        # month=0 is invalid for datetime.datetime (valid range 1-12)
        dt = BACnetDateTime(
            date=BACnetDate(2024, 0, 15, 1),
            time=BACnetTime(12, 0, 0, 0),
        )
        assert _datetime_to_float(dt) == 0.0

    def test_valid_date_returns_nonzero(self):
        """Sanity check: a valid BACnetDateTime returns a positive timestamp."""
        dt = BACnetDateTime(
            date=BACnetDate(2024, 6, 15, 6),
            time=BACnetTime(12, 0, 0, 0),
        )
        result = _datetime_to_float(dt)
        assert result > 0.0


# ---------------------------------------------------------------------------
# Engine lifecycle: start/stop (lines 79-81, 86-89, 97-102)
# ---------------------------------------------------------------------------


class TestEngineLifecycle:
    async def test_start_already_running(self):
        """Calling start() twice should be a no-op on the second call."""
        db = _FakeObjectDB()
        engine = _make_engine(db)
        await engine.start()
        first_task = engine._task
        assert first_task is not None

        # Second start should not replace the task
        await engine.start()
        assert engine._task is first_task
        await engine.stop()

    async def test_stop_cancels_task(self):
        """stop() should cancel the running task and set it to None."""
        db = _FakeObjectDB()
        engine = _make_engine(db)
        await engine.start()
        assert engine._task is not None

        await engine.stop()
        assert engine._task is None

    async def test_stop_when_not_started(self):
        """stop() on a never-started engine should be harmless."""
        db = _FakeObjectDB()
        engine = _make_engine(db)
        await engine.stop()  # Should not raise
        assert engine._task is None

    async def test_run_loop_executes_evaluate_cycle(self):
        """The _run_loop runs _evaluate_cycle at least once before cancel."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 7.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._last_poll[tl.object_identifier] = 0.0
        await engine.start()
        # Give the loop a chance to run
        await asyncio.sleep(0.05)
        await engine.stop()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) >= 1


# ---------------------------------------------------------------------------
# _within_time_window: start_time in future (line 149)
# ---------------------------------------------------------------------------


class TestWithinTimeWindow:
    def test_start_time_in_future_returns_false(self):
        """TrendLog with START_TIME in the future should not record."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 5.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,
        )
        # Set start_time far in the future
        tl._properties[PropertyIdentifier.START_TIME] = BACnetDateTime(
            date=BACnetDate(2099, 12, 31, 3),
            time=BACnetTime(23, 59, 59, 99),
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._last_poll[tl.object_identifier] = 0.0
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# Polled logging edge cases (lines 158, 173-188, 191)
# ---------------------------------------------------------------------------


class TestPolledEdgeCases:
    def test_log_interval_zero_skips(self):
        """log_interval <= 0 should cause _handle_polled to return early."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 1.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=0,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._last_poll[tl.object_identifier] = 0.0
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_polled_aligned_intervals_records_on_boundary(self):
        """With ALIGN_INTERVALS=True, crossing an interval boundary records."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 3.14
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,  # 1 second in centiseconds
        )
        tl._properties[PropertyIdentifier.ALIGN_INTERVALS] = True
        tl._properties[PropertyIdentifier.INTERVAL_OFFSET] = 0
        db.add(tl)

        engine = _make_engine(db)
        oid = tl.object_identifier

        # Set last_poll to a time that guarantees we have crossed at least
        # one 1-second boundary.  Setting it far in the past ensures
        # current_slot > last_slot.
        engine._last_poll[oid] = time.monotonic() - 5.0
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 1
        assert buf[0].log_datum == 3.14

    def test_polled_aligned_interval_not_due(self):
        """With ALIGN_INTERVALS=True, same slot means no recording."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 2.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=360000,  # 3600 seconds (1 hour) in centiseconds
        )
        tl._properties[PropertyIdentifier.ALIGN_INTERVALS] = True
        tl._properties[PropertyIdentifier.INTERVAL_OFFSET] = 0
        db.add(tl)

        engine = _make_engine(db)
        oid = tl.object_identifier

        # Set last_poll to just now -- still in the same 1-hour slot
        engine._last_poll[oid] = time.monotonic()
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_polled_non_aligned_not_due(self):
        """Non-aligned interval that hasn't elapsed yet skips recording."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 9.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=6000,  # 60 seconds
        )
        db.add(tl)

        engine = _make_engine(db)
        oid = tl.object_identifier

        # Set last_poll to just now -- less than 60s have passed
        engine._last_poll[oid] = time.monotonic()
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# COV edge cases (lines 211, 216, 220, 227, 229)
# ---------------------------------------------------------------------------


class TestCOVEdgeCases:
    def _make_real_db(self):
        return ObjectDatabase()

    def test_cov_already_subscribed_skips(self):
        """If TrendLog is already in _cov_subscriptions, _handle_cov returns early."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        # First cycle subscribes
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Second cycle should hit the early return
        engine._evaluate_cycle()
        # Still subscribed (no error, no double registration)
        assert tl.object_identifier in engine._cov_subscriptions

    def test_cov_no_property_reference(self):
        """TrendLog without LOG_DEVICE_OBJECT_PROPERTY should not subscribe."""
        db = self._make_real_db()
        tl = _make_trendlog(
            logging_type=LoggingType.COV,
        )
        # Do NOT set LOG_DEVICE_OBJECT_PROPERTY (target_oid=None)
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions

    def test_cov_target_not_found(self):
        """TrendLog referencing nonexistent object should not subscribe."""
        db = self._make_real_db()
        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions

    def test_cov_callback_log_disabled_filters(self):
        """After COV subscription, disabling LOG_ENABLE filters out changes."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Disable logging (but do NOT run evaluate_cycle, so COV callback remains)
        tl._properties[PropertyIdentifier.LOG_ENABLE] = False

        # Change the monitored property -- callback should filter it out
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_cov_callback_outside_time_window_filters(self):
        """After COV subscription, being outside time window filters changes."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Now set stop_time to the past so time window check fails in the callback
        tl._properties[PropertyIdentifier.STOP_TIME] = BACnetDateTime(
            date=BACnetDate(2000, 1, 1, 6),
            time=BACnetTime(0, 0, 0, 0),
        )

        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 77.0)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# Switching from COV to other logging types (lines 134, 138)
# ---------------------------------------------------------------------------


class TestCOVSwitching:
    def _make_real_db(self):
        return ObjectDatabase()

    def test_switching_cov_to_polled_unsubscribes(self):
        """Changing LOGGING_TYPE from COV to POLLED should unregister COV."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Switch to POLLED
        tl._properties[PropertyIdentifier.LOGGING_TYPE] = LoggingType.POLLED
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions

    def test_switching_cov_to_triggered_unsubscribes(self):
        """Changing LOGGING_TYPE from COV to TRIGGERED should unregister COV."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Switch to TRIGGERED
        tl._properties[PropertyIdentifier.LOGGING_TYPE] = LoggingType.TRIGGERED
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions


# ---------------------------------------------------------------------------
# _unregister_cov edge case (line 249)
# ---------------------------------------------------------------------------


class TestUnregisterCOV:
    def test_unregister_cov_not_subscribed(self):
        """_unregister_cov on a TrendLog not in _cov_subscriptions is a no-op."""
        db = _FakeObjectDB()
        tl = _make_trendlog(logging_type=LoggingType.COV)
        db.add(tl)

        engine = _make_engine(db)
        # Should not raise even though TL is not subscribed
        engine._unregister_cov(tl)
        assert tl.object_identifier not in engine._cov_subscriptions


# ---------------------------------------------------------------------------
# _record_value edge cases (lines 271, 289-297)
# ---------------------------------------------------------------------------


class TestRecordValueEdgeCases:
    def test_record_value_no_property_reference(self):
        """_record_value returns early when LOG_DEVICE_OBJECT_PROPERTY is None."""
        db = _FakeObjectDB()
        tl = _make_trendlog()  # No target_oid → no LOG_DEVICE_OBJECT_PROPERTY
        db.add(tl)

        engine = _make_engine(db)
        engine._record_value(tl)

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0

    def test_record_value_exception_during_read(self):
        """Exception during read_property logs warning and returns gracefully."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,
        )
        db.add(tl)

        engine = _make_engine(db)

        # Patch read_property on the target to raise an exception
        with patch.object(ai, "read_property", side_effect=RuntimeError("boom")):
            engine._last_poll[tl.object_identifier] = 0.0
            engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


# ---------------------------------------------------------------------------
# _evaluate_trendlog: COV unsubscribe outside time window (line 126)
# ---------------------------------------------------------------------------


class TestEvaluateOutsideTimeWindow:
    def _make_real_db(self):
        return ObjectDatabase()

    def test_cov_unsubscribe_outside_time_window(self):
        """COV subscription removed when TrendLog leaves time window."""
        db = self._make_real_db()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Set stop_time to the past to move outside time window
        tl._properties[PropertyIdentifier.STOP_TIME] = BACnetDateTime(
            date=BACnetDate(2000, 1, 1, 6),
            time=BACnetTime(0, 0, 0, 0),
        )
        engine._evaluate_cycle()
        assert tl.object_identifier not in engine._cov_subscriptions


# ---------------------------------------------------------------------------
# Coverage gap tests: uncovered branches
# ---------------------------------------------------------------------------


class TestOutsideTimeWindowSkips:
    """Test outside time window skips logging (branch 140->exit)."""

    def test_polled_outside_time_window_skips(self):
        """Polled logging outside time window does not record (branch 140->exit)."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 42.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=100,
            logging_type=LoggingType.POLLED,
        )
        # Set stop_time in the past (outside time window)
        tl._properties[PropertyIdentifier.STOP_TIME] = BACnetDateTime(
            date=BACnetDate(2000, 1, 1, 6),
            time=BACnetTime(0, 0, 0, 0),
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._last_poll[tl.object_identifier] = 0.0
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


class TestPolledSameSlotSuppression:
    """Test same slot suppression in polled logging (branch 184->193)."""

    def test_polled_aligned_same_slot_does_not_record(self):
        """Aligned polled logging in same slot does not record (branch 184->193)."""
        db = _FakeObjectDB()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 5.0
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            log_interval=360000,  # 1 hour in centiseconds
        )
        tl._properties[PropertyIdentifier.ALIGN_INTERVALS] = True
        tl._properties[PropertyIdentifier.INTERVAL_OFFSET] = 0
        db.add(tl)

        engine = _make_engine(db)
        oid = tl.object_identifier

        # Set last_poll to very recent -- same 1-hour slot
        engine._last_poll[oid] = time.monotonic() - 0.001
        engine._evaluate_cycle()

        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0


class TestCOVUnregisterOnDelete:
    """Test COV callback unregistration on delete (branch 254->257)."""

    def test_unregister_cov_removes_callback(self):
        """_unregister_cov unregisters the change callback (branch 254->257)."""
        db = ObjectDatabase()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.PRESENT_VALUE] = 10.0
        ai._properties[PropertyIdentifier.OUT_OF_SERVICE] = True
        db.add(ai)

        tl = _make_trendlog(
            target_oid=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            logging_type=LoggingType.COV,
        )
        db.add(tl)

        engine = _make_engine(db)
        engine._evaluate_cycle()
        assert tl.object_identifier in engine._cov_subscriptions

        # Ensure the COV callback attribute exists
        assert hasattr(tl, "_cov_callback")

        # Now unregister
        engine._unregister_cov(tl)
        assert tl.object_identifier not in engine._cov_subscriptions

        # After unregistration, property changes should not record
        ai.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0)
        buf = tl.read_property(PropertyIdentifier.LOG_BUFFER)
        assert len(buf) == 0
