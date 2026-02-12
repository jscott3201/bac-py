"""BACnet Calendar object per ASHRAE 135-2020 Clause 12.9."""

from __future__ import annotations

import calendar as _cal
import datetime
from typing import Any, ClassVar

from bac_py.objects.base import (
    BACnetObject,
    PropertyAccess,
    PropertyDefinition,
    register_object_type,
    standard_properties,
)
from bac_py.types.constructed import (
    BACnetCalendarEntry,
    BACnetDateRange,
    BACnetWeekNDay,
)
from bac_py.types.enums import (
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import BACnetDate

# ---------------------------------------------------------------------------
# Date matching helpers (reused by ScheduleEngine for exception_schedule)
# ---------------------------------------------------------------------------


def _matches_bacnet_date(
    entry: BACnetDate,
    year: int,
    month: int,
    day: int,
    day_of_week: int,
) -> bool:
    """Check if a concrete date matches a BACnetDate pattern.

    Wildcard rules per ASHRAE 135-2020 Clause 20.2.12:
    - 0xFF = any (unspecified)
    - month 13 = odd months, 14 = even months
    - day 32 = last day of month, 33 = odd days, 34 = even days
    """
    # Year
    if entry.year != 0xFF and entry.year != year:
        return False
    # Month
    if entry.month != 0xFF:
        if entry.month == 13:  # odd months
            if month % 2 == 0:
                return False
        elif entry.month == 14:  # even months
            if month % 2 != 0:
                return False
        elif entry.month != month:
            return False
    # Day
    if entry.day != 0xFF:
        if entry.day == 32:  # last day of month
            last_day = _cal.monthrange(year, month)[1]
            if day != last_day:
                return False
        elif entry.day == 33:  # odd days
            if day % 2 == 0:
                return False
        elif entry.day == 34:  # even days
            if day % 2 != 0:
                return False
        elif entry.day != day:
            return False
    # Day of week
    return entry.day_of_week == 0xFF or entry.day_of_week == day_of_week


def _date_tuple(d: BACnetDate, *, low: bool) -> tuple[int, int, int]:
    """Convert a BACnetDate to a comparable ``(year, month, day)`` tuple.

    For range comparisons: *low* resolves wildcards to minimum values,
    otherwise to maximum values.
    """
    if low:
        yr = 0 if d.year == 0xFF else d.year
        mo = 1 if d.month in (0xFF, 13, 14) else d.month
        dy = 1 if d.day in (0xFF, 32, 33, 34) else d.day
    else:
        yr = 9999 if d.year == 0xFF else d.year
        mo = 12 if d.month in (0xFF, 13, 14) else d.month
        dy = 31 if d.day in (0xFF, 32, 33, 34) else d.day
    return (yr, mo, dy)


def matches_date_range(
    entry: BACnetDateRange,
    year: int,
    month: int,
    day: int,
) -> bool:
    """Check if a concrete date falls within an inclusive BACnetDateRange."""
    current = (year, month, day)
    return (
        _date_tuple(entry.start_date, low=True)
        <= current
        <= _date_tuple(entry.end_date, low=False)
    )


def _week_of_month(day: int) -> int:
    """Return the week-of-month (1--5) for a given day of month."""
    return (day - 1) // 7 + 1


def _matches_week_n_day(
    entry: BACnetWeekNDay,
    year: int,
    month: int,
    day: int,
    day_of_week: int,
) -> bool:
    """Check if a concrete date matches a BACnetWeekNDay pattern.

    WeekNDay fields per ASHRAE 135-2020 Clause 21:
    - month: 1--12 specific, 13 = odd, 14 = even, 0xFF = any
    - week_of_month: 1--5 specific, 6 = last 7 days, 0xFF = any
    - day_of_week: 1--7 (Mon--Sun), 0xFF = any
    """
    # Month
    if entry.month != 0xFF:
        if entry.month == 13:
            if month % 2 == 0:
                return False
        elif entry.month == 14:
            if month % 2 != 0:
                return False
        elif entry.month != month:
            return False
    # Week of month
    if entry.week_of_month != 0xFF:
        if entry.week_of_month == 6:  # last 7 days
            last_day = _cal.monthrange(year, month)[1]
            if day < last_day - 6:
                return False
        elif entry.week_of_month != _week_of_month(day):
            return False
    # Day of week
    return entry.day_of_week == 0xFF or entry.day_of_week == day_of_week


def matches_calendar_entry(
    entry: BACnetCalendarEntry,
    year: int,
    month: int,
    day: int,
    day_of_week: int,
) -> bool:
    """Check if a concrete date matches a BACnetCalendarEntry.

    Public helper also used by :class:`ScheduleEngine` for exception_schedule
    evaluation.
    """
    if entry.choice == 0:
        assert isinstance(entry.value, BACnetDate)
        return _matches_bacnet_date(entry.value, year, month, day, day_of_week)
    if entry.choice == 1:
        assert isinstance(entry.value, BACnetDateRange)
        return matches_date_range(entry.value, year, month, day)
    if entry.choice == 2:
        assert isinstance(entry.value, BACnetWeekNDay)
        return _matches_week_n_day(entry.value, year, month, day, day_of_week)
    return False


# ---------------------------------------------------------------------------
# CalendarObject
# ---------------------------------------------------------------------------


@register_object_type
class CalendarObject(BACnetObject):
    """BACnet Calendar object (Clause 12.9).

    A Calendar object maintains a list of dates, date ranges, and
    date patterns.  Present_Value is TRUE when the current date
    matches any entry in Date_List.
    """

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.CALENDAR

    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        **standard_properties(),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            bool,
            PropertyAccess.READ_ONLY,
            required=True,
            default=False,
        ),
        PropertyIdentifier.DATE_LIST: PropertyDefinition(
            PropertyIdentifier.DATE_LIST,
            list,
            PropertyAccess.READ_WRITE,
            required=True,
        ),
    }

    def __init__(self, instance_number: int, **initial_properties: Any) -> None:
        super().__init__(instance_number, **initial_properties)
        self._set_default(PropertyIdentifier.DATE_LIST, [])

    def evaluate(self, today: datetime.date | None = None) -> bool:
        """Evaluate the calendar against *today* and update present_value.

        Iterates ``date_list`` and sets ``present_value`` to ``True`` if any
        entry matches, ``False`` otherwise.

        Args:
            today: Date to evaluate against.  Defaults to ``date.today()``.

        Returns:
            The resulting present_value.
        """
        if today is None:
            today = datetime.date.today()

        year = today.year
        month = today.month
        day = today.day
        # Python isoweekday(): Monday=1..Sunday=7 (matches BACnet convention)
        day_of_week = today.isoweekday()

        date_list = self.read_property(PropertyIdentifier.DATE_LIST)
        result = any(
            matches_calendar_entry(entry, year, month, day, day_of_week) for entry in date_list
        )

        self._properties[PropertyIdentifier.PRESENT_VALUE] = result
        return result
