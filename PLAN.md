# Phase 6 -- Operational Completeness Implementation Plan

## Scope Analysis

Phase 6 has 4 sub-phases making Schedule, Calendar, TrendLog, and Binary Output
objects operationally functional. Object shells and types already exist; we need
the evaluation engines and enforcement logic.

### Step 1. Calendar Evaluation Logic (Clause 12.9)

**File: `src/bac_py/objects/calendar.py`**

Add `evaluate(date)` method to `CalendarObject`:
- Iterate `date_list` (list of `BACnetCalendarEntry` items)
- For each entry, match against current date:
  - `choice=0` (BACnetDate): match year/month/day with wildcard support (0xFF=any,
    month 13=odd, 14=even, day 32=last, 33=odd, 34=even)
  - `choice=1` (BACnetDateRange): inclusive range check
  - `choice=2` (BACnetWeekNDay): match month/week-of-month/day-of-week patterns
- Set `present_value = True` if any entry matches, `False` otherwise

**Helper function**: `_matches_date()` for BACnetDate wildcard matching (reusable
by Schedule engine).

### Step 2. Schedule and Calendar Evaluation Engine (Clause 12.24)

**New file: `src/bac_py/app/schedule_engine.py`**

`ScheduleEngine` class following `EventEngine` lifecycle pattern (start/stop/async loop):

1. **Calendar evaluation**: On each cycle, update all CalendarObject `present_value`
2. **Schedule evaluation** per Clause 12.24.4-12.24.9:
   - Check `effective_period` -- outside → use `schedule_default`
   - Check `exception_schedule` -- highest-priority BACnetSpecialEvent that matches
     today; if entry's `period` is a CalendarEntry, match directly; if ObjectIdentifier
     (referencing a Calendar), check that Calendar's `present_value`
   - Fall back to `weekly_schedule[day_of_week]` (0=Monday..6=Sunday)
   - Within matching day: find latest `BACnetTimeValue` with `time <= current_time`
   - No match: use `schedule_default`
3. **Output writing**: On value change, write to each target in
   `list_of_object_property_references` at `priority_for_writing`

**Lifecycle**: `start()` → async loop → `stop()`. Default scan interval 10 seconds.

### Step 3. Trend Log Recording Engine (Clause 12.25)

**New file: `src/bac_py/app/trendlog_engine.py`**

`TrendLogEngine` class with async lifecycle:

1. **Polled logging** (Clause 12.25.12): Timer per TrendLog at `log_interval`. On
   tick: read monitored property from object DB, construct `BACnetLogRecord`, append
   to `log_buffer`. Support `align_intervals` and `interval_offset`.

2. **Triggered logging** (Clause 12.25.14): When `trigger` property written to True,
   record and reset to False.

3. **Buffer management**: Circular overwrite vs stop-when-full. Update `record_count`
   and `total_record_count`. Helper method on TrendLogObject for `append_record()`.

4. **Log control**: Honor `log_enable`, `start_time`/`stop_time`.

**COV-based logging** deferred to future work (requires cross-device subscriptions).

### Step 4. Minimum On/Off Time Enforcement (Clause 19.2)

**File: `src/bac_py/objects/binary.py`**

Add timer-based enforcement to `BinaryOutputObject`:
- On write changing present_value state: start a lock timer for `minimum_on_time`
  or `minimum_off_time` (in centiseconds per spec, stored as seconds)
- During lock: writes are accepted into priority array but present_value stays locked
- On timer expiry: re-evaluate priority array and update present_value
- Store lock state as `_min_time_lock_until: float | None` timestamp

### Step 5. Tests

**New test files:**
- `tests/objects/test_calendar_eval.py` -- date matching with wildcards, ranges, weekNDay
- `tests/app/test_schedule_engine.py` -- schedule evaluation, priority resolution, output writes
- `tests/app/test_trendlog_engine.py` -- polled logging, buffer management, triggered logging
- `tests/objects/test_min_on_off_time.py` -- minimum time enforcement

## Verification

1. `pytest tests/ --ignore=tests/serialization/test_json.py` -- all pass
2. `.venv/bin/ruff check src/ tests/` -- clean on new files
3. `.venv/bin/mypy --ignore-missing-imports src/` -- clean
4. Calendar wildcard matching for all date patterns
5. Schedule resolves exception > weekly > default correctly
6. TrendLog records polled and triggered data correctly
7. Min on/off time prevents rapid state changes
