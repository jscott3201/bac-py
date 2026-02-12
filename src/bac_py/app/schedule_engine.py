"""Schedule and Calendar evaluation engine per ASHRAE 135-2020 Clause 12.24.

The :class:`ScheduleEngine` follows the same async lifecycle pattern as
:class:`EventEngine` (start/stop/periodic loop).  On each cycle it:

1. Evaluates all Calendar objects (updating ``present_value``).
2. Evaluates all Schedule objects following the resolution order in
   Clause 12.24.4--12.24.9: effective_period → exception_schedule →
   weekly_schedule → schedule_default.
3. On value change, writes the new value to each target listed in
   ``list_of_object_property_references`` at ``priority_for_writing``.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from typing import TYPE_CHECKING, Any

from bac_py.objects.calendar import matches_calendar_entry, matches_date_range
from bac_py.types.constructed import BACnetCalendarEntry, BACnetSpecialEvent
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetTime, ObjectIdentifier

if TYPE_CHECKING:
    from bac_py.app.application import BACnetApplication
    from bac_py.objects.base import ObjectDatabase

logger = logging.getLogger(__name__)

_SENTINEL = object()  # Marker for "no value resolved"


def _time_tuple(t: BACnetTime) -> tuple[int, int, int, int]:
    """Convert a BACnetTime to a comparable tuple, resolving wildcards to 0."""
    return (
        0 if t.hour == 0xFF else t.hour,
        0 if t.minute == 0xFF else t.minute,
        0 if t.second == 0xFF else t.second,
        0 if t.hundredth == 0xFF else t.hundredth,
    )


def _now_tuple(now: datetime.time) -> tuple[int, int, int, int]:
    """Convert a Python time to a comparable tuple matching BACnetTime layout."""
    return (now.hour, now.minute, now.second, now.microsecond // 10000)


class ScheduleEngine:
    """Async engine that evaluates Calendar and Schedule objects periodically."""

    def __init__(
        self,
        app: BACnetApplication,
        *,
        scan_interval: float = 10.0,
    ) -> None:
        self._app = app
        self._scan_interval = scan_interval
        self._task: asyncio.Task[None] | None = None
        # Track last written value per schedule OID to detect changes
        self._last_values: dict[ObjectIdentifier, Any] = {}

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the periodic evaluation loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the evaluation loop and clean up."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._last_values.clear()

    # --- Main loop ---

    async def _run_loop(self) -> None:
        """Periodically evaluate all calendars and schedules."""
        try:
            while True:
                self._evaluate_cycle()
                await asyncio.sleep(self._scan_interval)
        except asyncio.CancelledError:
            return

    def _evaluate_cycle(self) -> None:
        """Run one evaluation cycle."""
        db = self._app.object_db
        today = datetime.date.today()
        now = datetime.datetime.now().time()

        # 1. Evaluate all Calendar objects
        for cal_obj in db.get_objects_of_type(ObjectType.CALENDAR):
            cal_obj.evaluate(today)  # type: ignore[attr-defined]

        # 2. Evaluate all Schedule objects
        for sched_obj in db.get_objects_of_type(ObjectType.SCHEDULE):
            self._evaluate_schedule(sched_obj, today, now, db)

    # --- Schedule evaluation (Clause 12.24.4--12.24.9) ---

    def _evaluate_schedule(
        self,
        sched: Any,
        today: datetime.date,
        now: datetime.time,
        db: ObjectDatabase,
    ) -> None:
        """Evaluate a single Schedule object and apply the result."""
        year = today.year
        month = today.month
        day = today.day
        day_of_week = today.isoweekday()  # Mon=1..Sun=7

        schedule_default = sched.read_property(PropertyIdentifier.SCHEDULE_DEFAULT)

        # Step 1: Check effective_period (Clause 12.24.4)
        effective_period = sched.read_property(PropertyIdentifier.EFFECTIVE_PERIOD)
        if effective_period is not None and not matches_date_range(
            effective_period, year, month, day
        ):
            self._apply_value(sched, schedule_default, db)
            return

        # Step 2: Check exception_schedule (Clause 12.24.5--12.24.7)
        exception_schedule = sched.read_property(
            PropertyIdentifier.EXCEPTION_SCHEDULE
        )
        if exception_schedule:
            value = self._resolve_exception_schedule(
                exception_schedule, year, month, day, day_of_week, now, db
            )
            if value is not _SENTINEL:
                self._apply_value(sched, value, db)
                return

        # Step 3: Fall back to weekly_schedule (Clause 12.24.8)
        weekly_schedule = sched.read_property(PropertyIdentifier.WEEKLY_SCHEDULE)
        if weekly_schedule:
            # BACnet weekly_schedule: index 0=Monday..6=Sunday
            day_index = day_of_week - 1
            if 0 <= day_index < len(weekly_schedule):
                day_entries = weekly_schedule[day_index]
                value = self._resolve_time_values(day_entries, now)
                if value is not _SENTINEL:
                    self._apply_value(sched, value, db)
                    return

        # Step 4: Use schedule_default (Clause 12.24.9)
        self._apply_value(sched, schedule_default, db)

    def _resolve_exception_schedule(
        self,
        exceptions: list[BACnetSpecialEvent],
        year: int,
        month: int,
        day: int,
        day_of_week: int,
        now: datetime.time,
        db: ObjectDatabase,
    ) -> Any:
        """Find the highest-priority matching exception and resolve its value.

        Returns ``_SENTINEL`` if no exception matches today.
        """
        best_priority = 17  # Lower number = higher priority; 1--16 valid
        best_value: Any = _SENTINEL

        for exc in exceptions:
            if exc.event_priority >= best_priority:
                continue

            # Check if the exception's period matches today
            if isinstance(exc.period, ObjectIdentifier):
                # Reference to a Calendar object -- check its present_value
                cal_obj = db.get(exc.period)
                if cal_obj is None:
                    continue
                pv = cal_obj.read_property(PropertyIdentifier.PRESENT_VALUE)
                if not pv:
                    continue
            elif isinstance(exc.period, BACnetCalendarEntry):
                if not matches_calendar_entry(
                    exc.period, year, month, day, day_of_week
                ):
                    continue
            else:
                continue

            # Resolve time values within this exception
            value = self._resolve_time_values(exc.list_of_time_values, now)
            if value is not _SENTINEL:
                best_priority = exc.event_priority
                best_value = value

        return best_value

    @staticmethod
    def _resolve_time_values(
        time_values: tuple[Any, ...] | list[Any],
        now: datetime.time,
    ) -> Any:
        """Find the latest BACnetTimeValue with ``time <= now``.

        Returns ``_SENTINEL`` if no entry qualifies.
        """
        now_t = _now_tuple(now)
        best_time: tuple[int, int, int, int] | None = None
        best_value: Any = _SENTINEL

        for tv in time_values:
            tv_t = _time_tuple(tv.time)
            if tv_t <= now_t and (best_time is None or tv_t > best_time):
                best_time = tv_t
                best_value = tv.value

        return best_value

    # --- Output writing ---

    def _apply_value(
        self,
        sched: Any,
        value: Any,
        db: ObjectDatabase,
    ) -> None:
        """Update present_value and write to targets on change."""
        oid = sched.object_identifier
        prev = self._last_values.get(oid, _SENTINEL)

        # Always update present_value
        sched._properties[PropertyIdentifier.PRESENT_VALUE] = value

        # Only write to targets on change
        if value == prev:
            return
        self._last_values[oid] = value

        priority = sched.read_property(PropertyIdentifier.PRIORITY_FOR_WRITING)
        targets = sched.read_property(
            PropertyIdentifier.LIST_OF_OBJECT_PROPERTY_REFERENCES
        )
        if not targets:
            return

        for ref in targets:
            target_obj = db.get(ref.object_identifier)
            if target_obj is None:
                logger.warning(
                    "Schedule %s: target %s not found",
                    oid,
                    ref.object_identifier,
                )
                continue
            try:
                prop_id = PropertyIdentifier(ref.property_identifier)
                target_obj.write_property(
                    prop_id,
                    value,
                    priority=priority,
                    array_index=ref.property_array_index,
                )
            except Exception:
                logger.warning(
                    "Schedule %s: failed to write %s.%s",
                    oid,
                    ref.object_identifier,
                    ref.property_identifier,
                    exc_info=True,
                )
