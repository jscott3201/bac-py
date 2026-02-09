"""Tests for Phase 2 constructed data types (C1-C13)."""

import pytest

from bac_py.types.constructed import (
    BACnetAddress,
    BACnetCalendarEntry,
    BACnetCOVSubscription,
    BACnetDateRange,
    BACnetDateTime,
    BACnetDestination,
    BACnetDeviceObjectPropertyReference,
    BACnetLogRecord,
    BACnetObjectPropertyReference,
    BACnetPrescale,
    BACnetPriorityArray,
    BACnetPriorityValue,
    BACnetRecipient,
    BACnetRecipientProcess,
    BACnetScale,
    BACnetSpecialEvent,
    BACnetTimeValue,
    BACnetWeekNDay,
    StatusFlags,
)
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier

# --- C1: BACnetDateTime ---


class TestBACnetDateTime:
    def test_construction(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 7, 15, 1),
            time=BACnetTime(14, 30, 0, 0),
        )
        assert dt.date.year == 2024
        assert dt.time.hour == 14

    def test_to_dict(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 1, 1, 2),
            time=BACnetTime(0, 0, 0, 0),
        )
        d = dt.to_dict()
        assert d["date"]["year"] == 2024
        assert d["time"]["hour"] == 0

    def test_from_dict_round_trip(self):
        original = BACnetDateTime(
            date=BACnetDate(2024, 12, 25, 3),
            time=BACnetTime(23, 59, 59, 99),
        )
        restored = BACnetDateTime.from_dict(original.to_dict())
        assert restored == original

    def test_frozen(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 1, 1, 1),
            time=BACnetTime(0, 0, 0, 0),
        )
        with pytest.raises(AttributeError):
            dt.date = BACnetDate(2025, 1, 1, 1)  # type: ignore[misc]


# --- C2: BACnetDateRange ---


class TestBACnetDateRange:
    def test_construction(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 2),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        assert dr.start_date.year == 2024
        assert dr.end_date.month == 12

    def test_round_trip(self):
        original = BACnetDateRange(
            start_date=BACnetDate(2024, 6, 1, 0xFF),
            end_date=BACnetDate(2024, 8, 31, 0xFF),
        )
        restored = BACnetDateRange.from_dict(original.to_dict())
        assert restored == original


# --- C3: BACnetWeekNDay ---


class TestBACnetWeekNDay:
    def test_construction(self):
        wnd = BACnetWeekNDay(month=1, week_of_month=2, day_of_week=3)
        assert wnd.month == 1
        assert wnd.week_of_month == 2
        assert wnd.day_of_week == 3

    def test_wildcards(self):
        wnd = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=0xFF)
        d = wnd.to_dict()
        assert d["month"] is None
        assert d["week_of_month"] is None
        assert d["day_of_week"] is None

    def test_round_trip(self):
        original = BACnetWeekNDay(month=6, week_of_month=0xFF, day_of_week=1)
        restored = BACnetWeekNDay.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_all_wildcards(self):
        original = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=0xFF)
        restored = BACnetWeekNDay.from_dict(original.to_dict())
        assert restored == original


# --- C4: BACnetCalendarEntry ---


class TestBACnetCalendarEntry:
    def test_date_choice(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 3))
        assert entry.choice == 0
        assert isinstance(entry.value, BACnetDate)

    def test_date_range_choice(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 2),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        entry = BACnetCalendarEntry(choice=1, value=dr)
        assert entry.choice == 1

    def test_week_n_day_choice(self):
        wnd = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=1)
        entry = BACnetCalendarEntry(choice=2, value=wnd)
        assert entry.choice == 2

    def test_round_trip_date(self):
        original = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 7, 4, 4))
        restored = BACnetCalendarEntry.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_date_range(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 6, 1, 0xFF),
            end_date=BACnetDate(2024, 8, 31, 0xFF),
        )
        original = BACnetCalendarEntry(choice=1, value=dr)
        restored = BACnetCalendarEntry.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_week_n_day(self):
        wnd = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=1)
        original = BACnetCalendarEntry(choice=2, value=wnd)
        restored = BACnetCalendarEntry.from_dict(original.to_dict())
        assert restored == original

    def test_invalid_choice_raises(self):
        with pytest.raises(ValueError, match="Invalid BACnetCalendarEntry choice"):
            BACnetCalendarEntry.from_dict({"choice": 99, "value": {}})


# --- C5: BACnetTimeValue ---


class TestBACnetTimeValue:
    def test_construction(self):
        tv = BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.5)
        assert tv.time.hour == 8
        assert tv.value == 72.5

    def test_round_trip_float(self):
        original = BACnetTimeValue(time=BACnetTime(9, 30, 0, 0), value=68.0)
        restored = BACnetTimeValue.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_int(self):
        original = BACnetTimeValue(time=BACnetTime(17, 0, 0, 0), value=1)
        restored = BACnetTimeValue.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_string(self):
        original = BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value="inactive")
        restored = BACnetTimeValue.from_dict(original.to_dict())
        assert restored == original

    def test_none_value(self):
        original = BACnetTimeValue(time=BACnetTime(23, 59, 59, 99), value=None)
        restored = BACnetTimeValue.from_dict(original.to_dict())
        assert restored.value is None


# --- C6: BACnetSpecialEvent ---


class TestBACnetSpecialEvent:
    def test_with_calendar_entry(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 3))
        tv = BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=55.0)
        se = BACnetSpecialEvent(period=entry, list_of_time_values=(tv,), event_priority=1)
        assert se.event_priority == 1
        assert len(se.list_of_time_values) == 1

    def test_with_calendar_reference(self):
        cal_ref = ObjectIdentifier(ObjectType.CALENDAR, 1)
        tv = BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0)
        se = BACnetSpecialEvent(period=cal_ref, list_of_time_values=(tv,), event_priority=5)
        d = se.to_dict()
        assert d["period_type"] == "calendar_reference"

    def test_round_trip_calendar_entry(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 1, 1, 2))
        tv1 = BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0)
        tv2 = BACnetTimeValue(time=BACnetTime(17, 0, 0, 0), value=65.0)
        original = BACnetSpecialEvent(
            period=entry, list_of_time_values=(tv1, tv2), event_priority=3
        )
        restored = BACnetSpecialEvent.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_calendar_reference(self):
        cal_ref = ObjectIdentifier(ObjectType.CALENDAR, 5)
        tv = BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=None)
        original = BACnetSpecialEvent(period=cal_ref, list_of_time_values=(tv,), event_priority=16)
        restored = BACnetSpecialEvent.from_dict(original.to_dict())
        assert restored == original


# --- C7: BACnetDeviceObjectPropertyReference ---


class TestBACnetDeviceObjectPropertyReference:
    def test_basic(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=85,  # PRESENT_VALUE
        )
        assert ref.property_array_index is None
        assert ref.device_identifier is None

    def test_with_array_index(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=87,  # PRIORITY_ARRAY
            property_array_index=8,
        )
        assert ref.property_array_index == 8

    def test_with_device(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=85,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        assert ref.device_identifier is not None

    def test_round_trip_minimal(self):
        original = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 5),
            property_identifier=85,
        )
        restored = BACnetDeviceObjectPropertyReference.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_full(self):
        original = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 10),
            property_identifier=87,
            property_array_index=1,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
        )
        restored = BACnetDeviceObjectPropertyReference.from_dict(original.to_dict())
        assert restored == original

    def test_to_dict_omits_none_fields(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=85,
        )
        d = ref.to_dict()
        assert "property_array_index" not in d
        assert "device_identifier" not in d


# --- C8: BACnetObjectPropertyReference ---


class TestBACnetObjectPropertyReference:
    def test_basic(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=85,
        )
        assert ref.property_array_index is None

    def test_round_trip(self):
        original = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.LOOP, 1),
            property_identifier=85,
            property_array_index=3,
        )
        restored = BACnetObjectPropertyReference.from_dict(original.to_dict())
        assert restored == original


# --- C9: BACnetRecipient and BACnetDestination ---


class TestBACnetAddress:
    def test_construction(self):
        addr = BACnetAddress(network_number=1, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        assert addr.network_number == 1
        assert len(addr.mac_address) == 6

    def test_round_trip(self):
        original = BACnetAddress(network_number=0, mac_address=b"\x0a\x00\x00\x01\xba\xc0")
        restored = BACnetAddress.from_dict(original.to_dict())
        assert restored == original


class TestBACnetRecipient:
    def test_device_recipient(self):
        r = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100))
        d = r.to_dict()
        assert d["type"] == "device"

    def test_address_recipient(self):
        addr = BACnetAddress(network_number=1, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        r = BACnetRecipient(address=addr)
        d = r.to_dict()
        assert d["type"] == "address"

    def test_round_trip_device(self):
        original = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 50))
        restored = BACnetRecipient.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_address(self):
        addr = BACnetAddress(network_number=2, mac_address=b"\x01\x02\x03\x04\x05\x06")
        original = BACnetRecipient(address=addr)
        restored = BACnetRecipient.from_dict(original.to_dict())
        assert restored == original


class TestBACnetDestination:
    def test_construction(self):
        dest = BACnetDestination(
            valid_days=BitString(b"\xfe", 1),  # Mon-Sun, 7 bits
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100)),
            process_identifier=1,
            issue_confirmed_notifications=True,
            transitions=BitString(b"\xe0", 5),  # 3 bits
        )
        assert dest.issue_confirmed_notifications is True

    def test_round_trip(self):
        original = BACnetDestination(
            valid_days=BitString(b"\xfe", 1),
            from_time=BACnetTime(8, 0, 0, 0),
            to_time=BACnetTime(17, 0, 0, 0),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 200)),
            process_identifier=42,
            issue_confirmed_notifications=False,
            transitions=BitString(b"\xa0", 5),
        )
        restored = BACnetDestination.from_dict(original.to_dict())
        assert restored == original


# --- C10: BACnetScale and BACnetPrescale ---


class TestBACnetScale:
    def test_float_scale(self):
        s = BACnetScale(float_scale=1.5)
        d = s.to_dict()
        assert d["type"] == "float"
        assert d["value"] == 1.5

    def test_integer_scale(self):
        s = BACnetScale(integer_scale=10)
        d = s.to_dict()
        assert d["type"] == "integer"
        assert d["value"] == 10

    def test_round_trip_float(self):
        original = BACnetScale(float_scale=0.001)
        restored = BACnetScale.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_integer(self):
        original = BACnetScale(integer_scale=100)
        restored = BACnetScale.from_dict(original.to_dict())
        assert restored == original


class TestBACnetPrescale:
    def test_construction(self):
        ps = BACnetPrescale(multiplier=10, modulo_divide=100)
        assert ps.multiplier == 10
        assert ps.modulo_divide == 100

    def test_round_trip(self):
        original = BACnetPrescale(multiplier=5, modulo_divide=1000)
        restored = BACnetPrescale.from_dict(original.to_dict())
        assert restored == original


# --- C11: BACnetLogRecord ---


class TestBACnetLogRecord:
    def test_construction(self):
        ts = BACnetDateTime(
            date=BACnetDate(2024, 7, 15, 1),
            time=BACnetTime(14, 30, 0, 0),
        )
        lr = BACnetLogRecord(timestamp=ts, log_datum=72.5)
        assert lr.log_datum == 72.5
        assert lr.status_flags is None

    def test_with_status_flags(self):
        ts = BACnetDateTime(
            date=BACnetDate(2024, 7, 15, 1),
            time=BACnetTime(14, 30, 0, 0),
        )
        sf = StatusFlags(in_alarm=True)
        lr = BACnetLogRecord(timestamp=ts, log_datum=72.5, status_flags=sf)
        assert lr.status_flags.in_alarm is True

    def test_round_trip(self):
        ts = BACnetDateTime(
            date=BACnetDate(2024, 12, 25, 3),
            time=BACnetTime(0, 0, 0, 0),
        )
        original = BACnetLogRecord(timestamp=ts, log_datum=42.0)
        restored = BACnetLogRecord.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_with_status(self):
        ts = BACnetDateTime(
            date=BACnetDate(2024, 1, 1, 2),
            time=BACnetTime(12, 0, 0, 0),
        )
        sf = StatusFlags(fault=True, out_of_service=True)
        original = BACnetLogRecord(timestamp=ts, log_datum="error", status_flags=sf)
        restored = BACnetLogRecord.from_dict(original.to_dict())
        assert restored == original


# --- C12: BACnetCOVSubscription ---


class TestBACnetRecipientProcess:
    def test_construction(self):
        rp = BACnetRecipientProcess(
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100)),
            process_identifier=1,
        )
        assert rp.process_identifier == 1

    def test_round_trip(self):
        original = BACnetRecipientProcess(
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 50)),
            process_identifier=42,
        )
        restored = BACnetRecipientProcess.from_dict(original.to_dict())
        assert restored == original


class TestBACnetCOVSubscription:
    def test_construction(self):
        sub = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100)),
                process_identifier=1,
            ),
            monitored_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            issue_confirmed_notifications=True,
            time_remaining=300,
        )
        assert sub.time_remaining == 300
        assert sub.cov_increment is None

    def test_with_cov_increment(self):
        sub = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100)),
                process_identifier=1,
            ),
            monitored_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            issue_confirmed_notifications=False,
            time_remaining=600,
            cov_increment=0.5,
        )
        assert sub.cov_increment == 0.5

    def test_round_trip(self):
        original = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 200)),
                process_identifier=42,
            ),
            monitored_object=ObjectIdentifier(ObjectType.BINARY_VALUE, 5),
            issue_confirmed_notifications=True,
            time_remaining=120,
            cov_increment=1.0,
        )
        restored = BACnetCOVSubscription.from_dict(original.to_dict())
        assert restored == original

    def test_to_dict_omits_none_cov_increment(self):
        sub = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100)),
                process_identifier=1,
            ),
            monitored_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            issue_confirmed_notifications=True,
            time_remaining=300,
        )
        d = sub.to_dict()
        assert "cov_increment" not in d


# --- C13: BACnetPriorityValue and BACnetPriorityArray ---


class TestBACnetPriorityValue:
    def test_default_none(self):
        pv = BACnetPriorityValue()
        assert pv.value is None

    def test_with_value(self):
        pv = BACnetPriorityValue(value=72.5)
        assert pv.value == 72.5

    def test_round_trip_none(self):
        original = BACnetPriorityValue()
        restored = BACnetPriorityValue.from_dict(original.to_dict())
        assert restored.value is None

    def test_round_trip_float(self):
        original = BACnetPriorityValue(value=42.0)
        restored = BACnetPriorityValue.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_int(self):
        original = BACnetPriorityValue(value=1)
        restored = BACnetPriorityValue.from_dict(original.to_dict())
        assert restored == original


class TestBACnetPriorityArray:
    def test_default_16_none_slots(self):
        pa = BACnetPriorityArray()
        assert len(pa.slots) == 16
        for i in range(16):
            assert pa[i].value is None

    def test_indexed_access(self):
        slots = tuple(BACnetPriorityValue() for _ in range(16))
        slots_list = list(slots)
        slots_list[7] = BACnetPriorityValue(value=72.5)
        pa = BACnetPriorityArray(slots=tuple(slots_list))
        assert pa[7].value == 72.5
        assert pa[0].value is None

    def test_wrong_size_raises(self):
        with pytest.raises(ValueError, match="exactly 16 entries"):
            BACnetPriorityArray(slots=tuple(BACnetPriorityValue() for _ in range(10)))

    def test_round_trip(self):
        slots_list = [BACnetPriorityValue() for _ in range(16)]
        slots_list[0] = BACnetPriorityValue(value=100.0)
        slots_list[7] = BACnetPriorityValue(value=72.5)
        slots_list[15] = BACnetPriorityValue(value=55.0)
        original = BACnetPriorityArray(slots=tuple(slots_list))
        restored = BACnetPriorityArray.from_dict(original.to_dict())
        assert restored[0].value == 100.0
        assert restored[7].value == 72.5
        assert restored[15].value == 55.0
        for i in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14]:
            assert restored[i].value is None
