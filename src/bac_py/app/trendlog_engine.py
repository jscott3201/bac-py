"""Trend Log recording engine per ASHRAE 135-2020 Clause 12.25.

The :class:`TrendLogEngine` follows the same async lifecycle pattern as
:class:`EventEngine`.  It manages polled, triggered, and COV-based
recording for all :class:`TrendLogObject` instances in the object database.

COV-based logging (Clause 12.25.13) uses property-change callbacks on
local objects to record values when the monitored property changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import time
from typing import TYPE_CHECKING, Any

from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord
from bac_py.types.enums import LoggingType, ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.objects.trendlog import TrendLogObject

logger = logging.getLogger(__name__)


def _now_datetime() -> BACnetDateTime:
    """Create a BACnetDateTime from the current wall-clock time."""
    n = datetime.datetime.now()
    return BACnetDateTime(
        date=BACnetDate(n.year, n.month, n.day, n.isoweekday()),
        time=BACnetTime(n.hour, n.minute, n.second, n.microsecond // 10000),
    )


def _datetime_to_float(dt: BACnetDateTime) -> float:
    """Convert a BACnetDateTime to a POSIX-ish float for comparison."""
    try:
        d = dt.date
        t = dt.time
        py_dt = datetime.datetime(
            d.year if d.year != 0xFF else 2000,
            d.month if d.month not in (0xFF, 13, 14) else 1,
            d.day if d.day not in (0xFF, 32, 33, 34) else 1,
            t.hour if t.hour != 0xFF else 0,
            t.minute if t.minute != 0xFF else 0,
            t.second if t.second != 0xFF else 0,
        )
        return py_dt.timestamp()
    except (ValueError, OSError):
        return 0.0


class TrendLogEngine:
    """Async engine that drives polled, triggered, and COV-based trend log recording."""

    def __init__(
        self,
        app: BACnetApplication,
        *,
        scan_interval: float = 1.0,
    ) -> None:
        self._app = app
        self._scan_interval = scan_interval
        self._task: asyncio.Task[None] | None = None
        # Track last poll time per TrendLog OID (monotonic seconds)
        self._last_poll: dict[Any, float] = {}
        # Track which TrendLog OIDs have active COV subscriptions
        self._cov_subscriptions: dict[Any, bool] = {}

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the periodic recording loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the recording loop and clean up COV subscriptions."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._last_poll.clear()
        self._unregister_all_cov()

    # --- Main loop ---

    async def _run_loop(self) -> None:
        """Periodically check all TrendLog objects."""
        try:
            while True:
                self._evaluate_cycle()
                await asyncio.sleep(self._scan_interval)
        except asyncio.CancelledError:
            return

    def _evaluate_cycle(self) -> None:
        """Run one evaluation cycle across all TrendLog objects."""
        db = self._app.object_db
        now_mono = time.monotonic()

        for tl_obj in db.get_objects_of_type(ObjectType.TREND_LOG):
            self._evaluate_trendlog(tl_obj, now_mono)  # type: ignore[arg-type]

    def _evaluate_trendlog(self, tl: TrendLogObject, now_mono: float) -> None:
        """Evaluate a single TrendLog object."""
        oid = tl.object_identifier
        log_enable = tl.read_property(PropertyIdentifier.LOG_ENABLE)
        if not log_enable:
            # If disabled, unsubscribe any COV callback
            if oid in self._cov_subscriptions:
                self._unregister_cov(tl)
            return

        # Check start_time / stop_time window
        if not self._within_time_window(tl):
            # Outside time window, unsubscribe COV
            if oid in self._cov_subscriptions:
                self._unregister_cov(tl)
            return

        logging_type = tl.read_property(PropertyIdentifier.LOGGING_TYPE)

        if logging_type == LoggingType.POLLED:
            # If switching away from COV, clean up
            if oid in self._cov_subscriptions:
                self._unregister_cov(tl)
            self._handle_polled(tl, now_mono)
        elif logging_type == LoggingType.TRIGGERED:
            if oid in self._cov_subscriptions:
                self._unregister_cov(tl)
            self._handle_triggered(tl)
        elif logging_type == LoggingType.COV:
            self._handle_cov(tl)

    def _within_time_window(self, tl: TrendLogObject) -> bool:
        """Check if we're within the TrendLog's start/stop time window."""
        now_ts = datetime.datetime.now().timestamp()

        start_time = tl._properties.get(PropertyIdentifier.START_TIME)
        if start_time is not None and _datetime_to_float(start_time) > now_ts:
            return False

        stop_time = tl._properties.get(PropertyIdentifier.STOP_TIME)
        return not (stop_time is not None and _datetime_to_float(stop_time) < now_ts)

    def _handle_polled(self, tl: TrendLogObject, now_mono: float) -> None:
        """Handle polled logging (Clause 12.25.12)."""
        log_interval = tl._properties.get(PropertyIdentifier.LOG_INTERVAL, 0)
        if log_interval <= 0:
            return

        # log_interval is in centiseconds per spec
        interval_secs = log_interval / 100.0

        oid = tl.object_identifier
        last = self._last_poll.get(oid, 0.0)

        # Handle align_intervals
        align = tl._properties.get(PropertyIdentifier.ALIGN_INTERVALS, False)
        offset = tl._properties.get(PropertyIdentifier.INTERVAL_OFFSET, 0)
        offset_secs = offset / 100.0

        if align and interval_secs > 0:
            # Align to wall-clock boundaries
            now_wall = datetime.datetime.now().timestamp()
            # Seconds since midnight
            midnight = (
                datetime.datetime.now()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            elapsed = now_wall - midnight + offset_secs
            # Check if we've crossed an interval boundary since last poll
            current_slot = int(elapsed / interval_secs)
            last_wall = self._last_poll.get(oid)
            if last_wall is not None:
                last_elapsed = (now_wall - (now_mono - last_wall)) - midnight + offset_secs
                last_slot = int(last_elapsed / interval_secs)
                if current_slot <= last_slot:
                    return
        else:
            if now_mono - last < interval_secs:
                return

        self._last_poll[oid] = now_mono
        self._record_value(tl)

    def _handle_triggered(self, tl: TrendLogObject) -> None:
        """Handle triggered logging (Clause 12.25.14)."""
        trigger = tl._properties.get(PropertyIdentifier.TRIGGER, False)
        if trigger:
            tl._properties[PropertyIdentifier.TRIGGER] = False
            self._record_value(tl)

    def _handle_cov(self, tl: TrendLogObject) -> None:
        """Handle COV-based logging (Clause 12.25.13).

        Registers a property-change callback on the monitored object
        so that values are recorded whenever the property changes.
        """
        oid = tl.object_identifier
        if oid in self._cov_subscriptions:
            return  # Already subscribed

        db = self._app.object_db
        ref = tl._properties.get(PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY)
        if ref is None:
            return

        target = db.get(ref.object_identifier)
        if target is None:
            return

        prop_id = PropertyIdentifier(ref.property_identifier)

        def _on_change(_prop_id: PropertyIdentifier, _old: Any, new_value: Any) -> None:
            """Record value when the monitored property changes."""
            if not tl.read_property(PropertyIdentifier.LOG_ENABLE):
                return
            if not self._within_time_window(tl):
                return
            status_flags = None
            with contextlib.suppress(Exception):
                status_flags = target.read_property(PropertyIdentifier.STATUS_FLAGS)
            record = BACnetLogRecord(
                timestamp=_now_datetime(),
                log_datum=new_value,
                status_flags=status_flags,
            )
            tl.append_record(record)

        # Store the callback reference for cleanup
        tl._cov_callback = _on_change  # type: ignore[attr-defined]
        db.register_change_callback(ref.object_identifier, prop_id, _on_change)
        self._cov_subscriptions[oid] = True

    def _unregister_cov(self, tl: TrendLogObject) -> None:
        """Remove COV subscription for a single TrendLog."""
        oid = tl.object_identifier
        if oid not in self._cov_subscriptions:
            return

        db = self._app.object_db
        ref = tl._properties.get(PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY)
        callback = getattr(tl, "_cov_callback", None)
        if ref is not None and callback is not None:
            prop_id = PropertyIdentifier(ref.property_identifier)
            db.unregister_change_callback(ref.object_identifier, prop_id, callback)
        del self._cov_subscriptions[oid]

    def _unregister_all_cov(self) -> None:
        """Remove all COV subscriptions."""
        db = self._app.object_db
        for tl_obj in db.get_objects_of_type(ObjectType.TREND_LOG):
            self._unregister_cov(tl_obj)  # type: ignore[arg-type]
        self._cov_subscriptions.clear()

    def _record_value(self, tl: TrendLogObject) -> None:
        """Read the monitored property and append a log record."""
        db = self._app.object_db
        ref = tl._properties.get(PropertyIdentifier.LOG_DEVICE_OBJECT_PROPERTY)
        if ref is None:
            return

        # Read the monitored property
        target = db.get(ref.object_identifier)
        if target is None:
            logger.warning(
                "TrendLog %s: monitored object %s not found",
                tl.object_identifier,
                ref.object_identifier,
            )
            return

        try:
            prop_id = PropertyIdentifier(ref.property_identifier)
            value: Any = target.read_property(
                prop_id,
                array_index=ref.property_array_index,
            )
        except Exception:
            logger.warning(
                "TrendLog %s: failed to read %s.%s",
                tl.object_identifier,
                ref.object_identifier,
                ref.property_identifier,
                exc_info=True,
            )
            return

        # Read status flags if available
        status_flags = None
        with contextlib.suppress(Exception):
            status_flags = target.read_property(PropertyIdentifier.STATUS_FLAGS)

        record = BACnetLogRecord(
            timestamp=_now_datetime(),
            log_datum=value,
            status_flags=status_flags,
        )
        tl.append_record(record)
