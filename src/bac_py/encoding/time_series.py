"""Time series data exchange for BACnet trend logs (Annex AA).

Provides JSON and CSV export/import of :class:`~bac_py.types.constructed.BACnetLogRecord`
lists following the standardized data exchange format.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord, StatusFlags
from bac_py.types.primitives import BACnetDate, BACnetTime


def _datetime_to_iso(dt: BACnetDateTime) -> str:
    """Convert a BACnetDateTime to an ISO 8601 string.

    Wildcard fields (``0xFF``) are rendered as ``*``.
    """
    d = dt.date
    t = dt.time

    year = "*" if d.year == 0xFF else f"{d.year:04d}"
    month = "*" if d.month == 0xFF else f"{d.month:02d}"
    day = "*" if d.day == 0xFF else f"{d.day:02d}"
    hour = "*" if t.hour == 0xFF else f"{t.hour:02d}"
    minute = "*" if t.minute == 0xFF else f"{t.minute:02d}"
    second = "*" if t.second == 0xFF else f"{t.second:02d}"
    hundredth = "*" if t.hundredth == 0xFF else f"{t.hundredth:02d}"

    return f"{year}-{month}-{day}T{hour}:{minute}:{second}.{hundredth}"


def _iso_to_datetime(s: str) -> BACnetDateTime:
    """Parse an ISO 8601-style string back to a BACnetDateTime.

    Wildcard ``*`` fields are restored to ``0xFF``.
    """
    # Expected format: YYYY-MM-DDTHH:MM:SS.HH
    date_part, time_part = s.split("T")
    year_s, month_s, day_s = date_part.split("-")
    time_main, hundredth_s = time_part.split(".")
    hour_s, minute_s, second_s = time_main.split(":")

    def _parse(val: str) -> int:
        return 0xFF if val == "*" else int(val)

    return BACnetDateTime(
        date=BACnetDate(
            year=_parse(year_s),
            month=_parse(month_s),
            day=_parse(day_s),
            day_of_week=0xFF,
        ),
        time=BACnetTime(
            hour=_parse(hour_s),
            minute=_parse(minute_s),
            second=_parse(second_s),
            hundredth=_parse(hundredth_s),
        ),
    )


def _status_flags_to_bits(sf: StatusFlags) -> str:
    """Convert StatusFlags to a 4-character bit string like ``"0000"``."""
    return f"{int(sf.in_alarm)}{int(sf.fault)}{int(sf.overridden)}{int(sf.out_of_service)}"


def _bits_to_status_flags(s: str) -> StatusFlags:
    """Parse a 4-character bit string back to StatusFlags."""
    if len(s) != 4 or not all(c in "01" for c in s):
        raise ValueError(f"Invalid status flags bit string: {s!r}")
    return StatusFlags(
        in_alarm=s[0] == "1",
        fault=s[1] == "1",
        overridden=s[2] == "1",
        out_of_service=s[3] == "1",
    )


class TimeSeriesExporter:
    """Export BACnetLogRecord lists to JSON and CSV formats (Annex AA)."""

    @staticmethod
    def to_json(
        records: list[BACnetLogRecord],
        *,
        metadata: dict[str, Any] | None = None,
        pretty: bool = False,
    ) -> str:
        """Export records to a JSON string.

        :param records: List of log records to export.
        :param metadata: Optional metadata dict included in the output.
        :param pretty: If ``True``, output indented JSON.
        :returns: JSON string in the ``bacnet-time-series-v1`` format.
        """
        payload: dict[str, Any] = {
            "format": "bacnet-time-series-v1",
            "metadata": metadata or {},
            "records": [r.to_dict() for r in records],
        }
        if pretty:
            return json.dumps(payload, indent=2)
        return json.dumps(payload)

    @staticmethod
    def to_csv(
        records: list[BACnetLogRecord],
        *,
        include_status: bool = True,
    ) -> str:
        """Export records to a CSV string.

        :param records: List of log records to export.
        :param include_status: Whether to include a ``status_flags`` column.
        :returns: CSV string with header row.
        """
        output = io.StringIO()
        fieldnames = ["timestamp", "value"]
        if include_status:
            fieldnames.append("status_flags")
        writer = csv.writer(output)
        writer.writerow(fieldnames)

        for rec in records:
            ts = _datetime_to_iso(rec.timestamp)
            value = str(rec.log_datum) if rec.log_datum is not None else ""
            row = [ts, value]
            if include_status:
                if rec.status_flags is not None:
                    row.append(_status_flags_to_bits(rec.status_flags))
                else:
                    row.append("")
            writer.writerow(row)

        return output.getvalue()


class TimeSeriesImporter:
    """Import BACnetLogRecord lists from JSON and CSV formats (Annex AA)."""

    @staticmethod
    def from_json(data: str) -> tuple[list[BACnetLogRecord], dict[str, Any]]:
        """Import records from a JSON string.

        :param data: JSON string in the ``bacnet-time-series-v1`` format.
        :returns: Tuple of (records, metadata).
        :raises ValueError: If the JSON is invalid or missing required fields.
        """
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        if payload.get("format") != "bacnet-time-series-v1":
            raise ValueError(f"Unsupported format: {payload.get('format')!r}")

        metadata = payload.get("metadata", {})
        raw_records = payload.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("Expected 'records' to be an array")

        records = [BACnetLogRecord.from_dict(r) for r in raw_records]
        return records, metadata

    @staticmethod
    def from_csv(data: str) -> list[BACnetLogRecord]:
        """Import records from a CSV string.

        :param data: CSV string with ``timestamp``, ``value``, and
            optionally ``status_flags`` columns.
        :returns: List of log records.
        :raises ValueError: If the CSV is malformed or has missing columns.
        """
        reader = csv.DictReader(io.StringIO(data))
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        if "timestamp" not in reader.fieldnames or "value" not in reader.fieldnames:
            raise ValueError("CSV must have 'timestamp' and 'value' columns")

        has_status = "status_flags" in reader.fieldnames
        records: list[BACnetLogRecord] = []

        for row_num, row in enumerate(reader, start=2):
            ts_str = row.get("timestamp", "")
            if not ts_str:
                raise ValueError(f"Row {row_num}: missing timestamp")

            try:
                timestamp = _iso_to_datetime(ts_str)
            except (ValueError, IndexError) as exc:
                raise ValueError(f"Row {row_num}: invalid timestamp {ts_str!r}: {exc}") from exc

            raw_value = row.get("value", "")
            log_datum: Any
            if raw_value == "":
                log_datum = None
            else:
                # Try numeric conversion
                try:
                    log_datum = int(raw_value)
                except ValueError:
                    try:
                        log_datum = float(raw_value)
                    except ValueError:
                        log_datum = raw_value

            status_flags: StatusFlags | None = None
            if has_status:
                sf_str = row.get("status_flags", "")
                if sf_str:
                    try:
                        status_flags = _bits_to_status_flags(sf_str)
                    except ValueError as exc:
                        raise ValueError(
                            f"Row {row_num}: invalid status_flags {sf_str!r}: {exc}"
                        ) from exc

            records.append(
                BACnetLogRecord(
                    timestamp=timestamp,
                    log_datum=log_datum,
                    status_flags=status_flags,
                )
            )

        return records
