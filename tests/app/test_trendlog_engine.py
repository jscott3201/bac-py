"""Tests for TrendLog recording engine (Clause 12.25)."""

import datetime

from bac_py.app.trendlog_engine import TrendLogEngine, _now_datetime
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.trendlog import TrendLogObject
from bac_py.types.constructed import (
    BACnetDeviceObjectPropertyReference,
    BACnetLogRecord,
)
from bac_py.types.enums import LoggingType, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier

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
        return [
            o
            for o in self._objects.values()
            if getattr(o, "OBJECT_TYPE", None) == obj_type
        ]


class _FakeApp:
    def __init__(self, db: _FakeObjectDB) -> None:
        self.object_db = db


def _make_engine(db: _FakeObjectDB) -> TrendLogEngine:
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
