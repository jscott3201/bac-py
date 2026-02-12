"""Tests for Calendar evaluation logic (Clause 12.9)."""

import datetime

from bac_py.objects.calendar import (
    CalendarObject,
    matches_calendar_entry,
    matches_date_range,
)
from bac_py.types.constructed import (
    BACnetCalendarEntry,
    BACnetDateRange,
    BACnetWeekNDay,
)
from bac_py.types.enums import PropertyIdentifier
from bac_py.types.primitives import BACnetDate

# ---------------------------------------------------------------------------
# BACnetDate matching
# ---------------------------------------------------------------------------


class TestMatchesBACnetDate:
    def test_exact_match(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 3))
        assert matches_calendar_entry(entry, 2024, 12, 25, 3)

    def test_exact_no_match(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 3))
        assert not matches_calendar_entry(entry, 2024, 12, 26, 4)

    def test_wildcard_year(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 12, 25, 0xFF))
        assert matches_calendar_entry(entry, 2024, 12, 25, 3)
        assert matches_calendar_entry(entry, 2030, 12, 25, 4)

    def test_wildcard_all(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF))
        assert matches_calendar_entry(entry, 2024, 6, 15, 6)

    def test_month_odd(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 13, 0xFF, 0xFF))
        # January (odd) → match
        assert matches_calendar_entry(entry, 2024, 1, 15, 1)
        # February (even) → no match
        assert not matches_calendar_entry(entry, 2024, 2, 15, 4)
        # March (odd) → match
        assert matches_calendar_entry(entry, 2024, 3, 1, 5)

    def test_month_even(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 14, 0xFF, 0xFF))
        assert not matches_calendar_entry(entry, 2024, 1, 15, 1)
        assert matches_calendar_entry(entry, 2024, 2, 15, 4)

    def test_day_last_of_month(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 32, 0xFF))
        # Feb 29 in leap year
        assert matches_calendar_entry(entry, 2024, 2, 29, 4)
        # Feb 28 is NOT last day in leap year
        assert not matches_calendar_entry(entry, 2024, 2, 28, 3)
        # Feb 28 IS last day in non-leap year
        assert matches_calendar_entry(entry, 2023, 2, 28, 2)
        # Jan 31
        assert matches_calendar_entry(entry, 2024, 1, 31, 3)

    def test_day_odd(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 33, 0xFF))
        assert matches_calendar_entry(entry, 2024, 1, 1, 1)
        assert not matches_calendar_entry(entry, 2024, 1, 2, 2)
        assert matches_calendar_entry(entry, 2024, 1, 31, 3)

    def test_day_even(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 34, 0xFF))
        assert not matches_calendar_entry(entry, 2024, 1, 1, 1)
        assert matches_calendar_entry(entry, 2024, 1, 2, 2)
        assert matches_calendar_entry(entry, 2024, 1, 30, 2)

    def test_day_of_week_match(self):
        # 2024-02-12 is a Monday (isoweekday=1)
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 1))
        assert matches_calendar_entry(entry, 2024, 2, 12, 1)
        assert not matches_calendar_entry(entry, 2024, 2, 13, 2)


# ---------------------------------------------------------------------------
# BACnetDateRange matching
# ---------------------------------------------------------------------------


class TestMatchesDateRange:
    def test_within_range(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 0xFF),
            end_date=BACnetDate(2024, 12, 31, 0xFF),
        )
        assert matches_date_range(dr, 2024, 6, 15)

    def test_at_start(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 3, 1, 0xFF),
            end_date=BACnetDate(2024, 3, 31, 0xFF),
        )
        assert matches_date_range(dr, 2024, 3, 1)

    def test_at_end(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 3, 1, 0xFF),
            end_date=BACnetDate(2024, 3, 31, 0xFF),
        )
        assert matches_date_range(dr, 2024, 3, 31)

    def test_before_range(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 3, 1, 0xFF),
            end_date=BACnetDate(2024, 3, 31, 0xFF),
        )
        assert not matches_date_range(dr, 2024, 2, 28)

    def test_after_range(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 3, 1, 0xFF),
            end_date=BACnetDate(2024, 3, 31, 0xFF),
        )
        assert not matches_date_range(dr, 2024, 4, 1)

    def test_wildcard_start(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF),
            end_date=BACnetDate(2024, 12, 31, 0xFF),
        )
        assert matches_date_range(dr, 2024, 6, 15)
        assert matches_date_range(dr, 1900, 1, 1)

    def test_calendar_entry_date_range(self):
        entry = BACnetCalendarEntry(
            choice=1,
            value=BACnetDateRange(
                start_date=BACnetDate(2024, 6, 1, 0xFF),
                end_date=BACnetDate(2024, 6, 30, 0xFF),
            ),
        )
        assert matches_calendar_entry(entry, 2024, 6, 15, 6)
        assert not matches_calendar_entry(entry, 2024, 7, 1, 1)


# ---------------------------------------------------------------------------
# BACnetWeekNDay matching
# ---------------------------------------------------------------------------


class TestMatchesWeekNDay:
    def test_specific_week_and_day(self):
        # Second Monday of any month
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(0xFF, 2, 1))
        # 2024-02-12 is Monday, day 12 → week 2 ((12-1)//7+1=2)
        assert matches_calendar_entry(entry, 2024, 2, 12, 1)
        # 2024-02-05 is Monday, day 5 → week 1
        assert not matches_calendar_entry(entry, 2024, 2, 5, 1)

    def test_last_week(self):
        # Last Friday of any month (week_of_month=6, day_of_week=5)
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(0xFF, 6, 5))
        # Jan 2024: 31 days, last 7 days = 25-31
        # Jan 26 is Friday (isoweekday=5)
        assert matches_calendar_entry(entry, 2024, 1, 26, 5)
        # Jan 19 is Friday but not in last 7 days
        assert not matches_calendar_entry(entry, 2024, 1, 19, 5)

    def test_any_week_any_day(self):
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(0xFF, 0xFF, 0xFF))
        assert matches_calendar_entry(entry, 2024, 6, 15, 6)

    def test_odd_month(self):
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(13, 0xFF, 0xFF))
        assert matches_calendar_entry(entry, 2024, 1, 15, 1)
        assert not matches_calendar_entry(entry, 2024, 2, 15, 4)

    def test_even_month(self):
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(14, 0xFF, 0xFF))
        assert not matches_calendar_entry(entry, 2024, 1, 15, 1)
        assert matches_calendar_entry(entry, 2024, 2, 15, 4)

    def test_specific_month(self):
        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(3, 0xFF, 0xFF))
        assert matches_calendar_entry(entry, 2024, 3, 15, 5)
        assert not matches_calendar_entry(entry, 2024, 4, 15, 1)


# ---------------------------------------------------------------------------
# CalendarObject.evaluate()
# ---------------------------------------------------------------------------


class TestCalendarEvaluate:
    def test_empty_date_list(self):
        cal = CalendarObject(1)
        result = cal.evaluate(datetime.date(2024, 6, 15))
        assert result is False
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is False

    def test_matching_entry(self):
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 6, 15, 0xFF)),
        ]
        result = cal.evaluate(datetime.date(2024, 6, 15))
        assert result is True

    def test_no_matching_entry(self):
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 0xFF)),
        ]
        result = cal.evaluate(datetime.date(2024, 6, 15))
        assert result is False

    def test_multiple_entries_one_matches(self):
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 0xFF)),
            BACnetCalendarEntry(
                choice=1,
                value=BACnetDateRange(
                    start_date=BACnetDate(2024, 6, 1, 0xFF),
                    end_date=BACnetDate(2024, 6, 30, 0xFF),
                ),
            ),
        ]
        result = cal.evaluate(datetime.date(2024, 6, 15))
        assert result is True

    def test_evaluate_updates_present_value(self):
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
        ]
        cal.evaluate(datetime.date(2024, 1, 1))
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is True

        cal._properties[PropertyIdentifier.DATE_LIST] = []
        cal.evaluate(datetime.date(2024, 1, 1))
        assert cal.read_property(PropertyIdentifier.PRESENT_VALUE) is False

    def test_defaults_to_today(self):
        cal = CalendarObject(1)
        cal._properties[PropertyIdentifier.DATE_LIST] = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF)),
        ]
        # Should not raise (uses datetime.date.today())
        result = cal.evaluate()
        assert result is True
