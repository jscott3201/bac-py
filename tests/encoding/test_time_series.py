"""Tests for the time series data exchange module (Annex AA)."""

import pytest

from bac_py.encoding.time_series import (
    TimeSeriesExporter,
    TimeSeriesImporter,
    _bits_to_status_flags,
    _datetime_to_iso,
    _iso_to_datetime,
    _status_flags_to_bits,
)
from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord, StatusFlags
from bac_py.types.primitives import BACnetDate, BACnetTime


def _make_record(
    year: int = 2024,
    month: int = 1,
    day: int = 15,
    hour: int = 10,
    minute: int = 30,
    second: int = 0,
    hundredth: int = 0,
    value: object = 72.5,
    status: StatusFlags | None = None,
) -> BACnetLogRecord:
    return BACnetLogRecord(
        timestamp=BACnetDateTime(
            date=BACnetDate(year=year, month=month, day=day, day_of_week=0xFF),
            time=BACnetTime(hour=hour, minute=minute, second=second, hundredth=hundredth),
        ),
        log_datum=value,
        status_flags=status,
    )


class TestDateTimeConversion:
    def test_datetime_to_iso_basic(self):
        dt = BACnetDateTime(
            date=BACnetDate(year=2024, month=1, day=15, day_of_week=0xFF),
            time=BACnetTime(hour=10, minute=30, second=0, hundredth=0),
        )
        assert _datetime_to_iso(dt) == "2024-01-15T10:30:00.00"

    def test_datetime_to_iso_wildcards(self):
        dt = BACnetDateTime(
            date=BACnetDate(year=0xFF, month=0xFF, day=0xFF, day_of_week=0xFF),
            time=BACnetTime(hour=0xFF, minute=0xFF, second=0xFF, hundredth=0xFF),
        )
        assert _datetime_to_iso(dt) == "*-*-*T*:*:*.*"

    def test_iso_roundtrip(self):
        dt = BACnetDateTime(
            date=BACnetDate(year=2024, month=6, day=20, day_of_week=0xFF),
            time=BACnetTime(hour=14, minute=5, second=30, hundredth=50),
        )
        iso = _datetime_to_iso(dt)
        restored = _iso_to_datetime(iso)
        assert restored.date.year == dt.date.year
        assert restored.date.month == dt.date.month
        assert restored.date.day == dt.date.day
        assert restored.time.hour == dt.time.hour
        assert restored.time.minute == dt.time.minute
        assert restored.time.second == dt.time.second
        assert restored.time.hundredth == dt.time.hundredth

    def test_iso_wildcard_roundtrip(self):
        dt = BACnetDateTime(
            date=BACnetDate(year=0xFF, month=3, day=0xFF, day_of_week=0xFF),
            time=BACnetTime(hour=12, minute=0xFF, second=0, hundredth=0xFF),
        )
        iso = _datetime_to_iso(dt)
        restored = _iso_to_datetime(iso)
        assert restored.date.year == 0xFF
        assert restored.date.month == 3
        assert restored.date.day == 0xFF
        assert restored.time.hour == 12
        assert restored.time.minute == 0xFF
        assert restored.time.second == 0
        assert restored.time.hundredth == 0xFF


class TestStatusFlagsConversion:
    def test_normal_flags(self):
        sf = StatusFlags()
        assert _status_flags_to_bits(sf) == "0000"

    def test_all_flags(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        assert _status_flags_to_bits(sf) == "1111"

    def test_single_flag(self):
        sf = StatusFlags(fault=True)
        assert _status_flags_to_bits(sf) == "0100"

    def test_bits_roundtrip(self):
        sf = StatusFlags(in_alarm=True, out_of_service=True)
        bits = _status_flags_to_bits(sf)
        restored = _bits_to_status_flags(bits)
        assert restored == sf

    def test_invalid_bits_raises(self):
        with pytest.raises(ValueError):
            _bits_to_status_flags("abc")

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError):
            _bits_to_status_flags("00000")


class TestTimeSeriesExporterJSON:
    def test_json_export_basic(self):
        records = [_make_record(value=72.5)]
        result = TimeSeriesExporter.to_json(records)
        assert '"format": "bacnet-time-series-v1"' in result
        assert "72.5" in result

    def test_json_export_with_metadata(self):
        records = [_make_record()]
        result = TimeSeriesExporter.to_json(records, metadata={"object_name": "Zone Temp Log"})
        assert "Zone Temp Log" in result

    def test_json_empty_records(self):
        result = TimeSeriesExporter.to_json([])
        assert '"records": []' in result

    def test_json_pretty_formatting(self):
        records = [_make_record()]
        result = TimeSeriesExporter.to_json(records, pretty=True)
        # Pretty JSON has newlines and indentation
        assert "\n" in result
        assert "  " in result

    def test_json_multiple_datum_types(self):
        records = [
            _make_record(value=72.5, hour=10),
            _make_record(value=42, hour=11),
            _make_record(value="active", hour=12),
            _make_record(value=None, hour=13),
        ]
        result = TimeSeriesExporter.to_json(records)
        assert "72.5" in result
        assert "42" in result
        assert "active" in result
        assert "null" in result

    def test_json_with_status_flags(self):
        records = [
            _make_record(status=StatusFlags(in_alarm=True)),
        ]
        result = TimeSeriesExporter.to_json(records)
        assert '"in_alarm": true' in result


class TestTimeSeriesExporterCSV:
    def test_csv_export_basic(self):
        records = [_make_record(value=72.5)]
        result = TimeSeriesExporter.to_csv(records)
        lines = result.strip().splitlines()
        assert lines[0] == "timestamp,value,status_flags"
        assert "2024-01-15T10:30:00.00" in lines[1]
        assert "72.5" in lines[1]

    def test_csv_without_status(self):
        records = [_make_record(value=72.5)]
        result = TimeSeriesExporter.to_csv(records, include_status=False)
        lines = result.strip().splitlines()
        assert lines[0] == "timestamp,value"
        assert "status_flags" not in result

    def test_csv_with_status_flags(self):
        records = [
            _make_record(value=72.5, status=StatusFlags(in_alarm=True)),
        ]
        result = TimeSeriesExporter.to_csv(records)
        lines = result.strip().splitlines()
        assert "1000" in lines[1]

    def test_csv_empty_records(self):
        result = TimeSeriesExporter.to_csv([])
        lines = result.strip().splitlines()
        assert len(lines) == 1  # Header only

    def test_csv_wildcard_timestamps(self):
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(year=0xFF, month=0xFF, day=0xFF, day_of_week=0xFF),
                time=BACnetTime(hour=0xFF, minute=0xFF, second=0xFF, hundredth=0xFF),
            ),
            log_datum=42.0,
        )
        result = TimeSeriesExporter.to_csv([rec])
        assert "*-*-*T*:*:*.*" in result

    def test_csv_none_value(self):
        records = [_make_record(value=None)]
        result = TimeSeriesExporter.to_csv(records)
        lines = result.strip().splitlines()
        # Value should be empty string for None
        parts = lines[1].split(",")
        assert parts[1] == ""


class TestTimeSeriesImporterJSON:
    def test_json_roundtrip(self):
        records = [
            _make_record(value=72.5, status=StatusFlags()),
            _make_record(value=73.1, hour=11, minute=0, status=StatusFlags(fault=True)),
        ]
        json_str = TimeSeriesExporter.to_json(records, metadata={"name": "test"})
        restored, metadata = TimeSeriesImporter.from_json(json_str)

        assert len(restored) == 2
        assert restored[0].log_datum == 72.5
        assert restored[1].log_datum == 73.1
        assert metadata == {"name": "test"}

    def test_json_metadata_preserved(self):
        meta = {"object_name": "Zone Temp", "device": 1234}
        json_str = TimeSeriesExporter.to_json([], metadata=meta)
        _, restored_meta = TimeSeriesImporter.from_json(json_str)
        assert restored_meta == meta

    def test_json_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            TimeSeriesImporter.from_json("{not valid json")

    def test_json_wrong_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            TimeSeriesImporter.from_json('{"format": "unknown-v99", "records": []}')

    def test_json_not_object_raises(self):
        with pytest.raises(ValueError, match="Expected a JSON object"):
            TimeSeriesImporter.from_json("[1, 2, 3]")

    def test_json_empty_records(self):
        json_str = TimeSeriesExporter.to_json([])
        records, _ = TimeSeriesImporter.from_json(json_str)
        assert records == []


class TestTimeSeriesImporterCSV:
    def test_csv_roundtrip(self):
        records = [
            _make_record(value=72.5, status=StatusFlags()),
            _make_record(value=73.1, hour=11, status=StatusFlags()),
        ]
        csv_str = TimeSeriesExporter.to_csv(records)
        restored = TimeSeriesImporter.from_csv(csv_str)

        assert len(restored) == 2
        assert restored[0].log_datum == 72.5
        assert restored[1].log_datum == 73.1

    def test_csv_roundtrip_no_status(self):
        records = [_make_record(value=42.0)]
        csv_str = TimeSeriesExporter.to_csv(records, include_status=False)
        restored = TimeSeriesImporter.from_csv(csv_str)

        assert len(restored) == 1
        assert restored[0].log_datum == 42.0
        assert restored[0].status_flags is None

    def test_csv_integer_value(self):
        records = [_make_record(value=42)]
        csv_str = TimeSeriesExporter.to_csv(records, include_status=False)
        restored = TimeSeriesImporter.from_csv(csv_str)
        # CSV importer converts "42" to int
        assert restored[0].log_datum == 42
        assert isinstance(restored[0].log_datum, int)

    def test_csv_string_value(self):
        records = [_make_record(value="active")]
        csv_str = TimeSeriesExporter.to_csv(records, include_status=False)
        restored = TimeSeriesImporter.from_csv(csv_str)
        assert restored[0].log_datum == "active"

    def test_csv_none_value(self):
        records = [_make_record(value=None)]
        csv_str = TimeSeriesExporter.to_csv(records, include_status=False)
        restored = TimeSeriesImporter.from_csv(csv_str)
        assert restored[0].log_datum is None

    def test_csv_empty_records(self):
        csv_str = TimeSeriesExporter.to_csv([])
        restored = TimeSeriesImporter.from_csv(csv_str)
        assert restored == []

    def test_csv_malformed_raises(self):
        with pytest.raises(ValueError, match="must have"):
            TimeSeriesImporter.from_csv("bad_column\n123\n")

    def test_csv_no_header_raises(self):
        with pytest.raises(ValueError, match="no header"):
            TimeSeriesImporter.from_csv("")

    def test_csv_wildcard_timestamp_roundtrip(self):
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(year=0xFF, month=0xFF, day=0xFF, day_of_week=0xFF),
                time=BACnetTime(hour=0xFF, minute=0xFF, second=0xFF, hundredth=0xFF),
            ),
            log_datum=99.9,
        )
        csv_str = TimeSeriesExporter.to_csv([rec], include_status=False)
        restored = TimeSeriesImporter.from_csv(csv_str)
        assert restored[0].timestamp.date.year == 0xFF
        assert restored[0].timestamp.time.hour == 0xFF
