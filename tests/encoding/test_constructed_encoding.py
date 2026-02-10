"""Tests for constructed type encoding in encode_property_value.

Verifies that all BACnet constructed types defined in types/constructed.py
can be encoded to wire format via encode_property_value without error,
and produce valid tag structures.
"""

import pytest

from bac_py.encoding.primitives import (
    decode_application_value,
    encode_property_value,
)
from bac_py.encoding.tags import TagClass, decode_tag
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
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


# ---------------------------------------------------------------------------
# StatusFlags (already supported, verify still works)
# ---------------------------------------------------------------------------
class TestStatusFlagsEncoding:
    def test_normal(self):
        sf = StatusFlags()
        result = encode_property_value(sf)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_all_flags_set(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        result = encode_property_value(sf)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetDateTime
# ---------------------------------------------------------------------------
class TestDateTimeEncoding:
    def test_basic(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 6, 15, 6),
            time=BACnetTime(14, 30, 0, 0),
        )
        result = encode_property_value(dt)
        assert isinstance(result, bytes)
        # Should contain a Date tag (10) followed by a Time tag (11)
        tag1, off1 = decode_tag(result, 0)
        assert tag1.cls == TagClass.APPLICATION
        assert tag1.number == 10  # Date
        tag2, _off2 = decode_tag(result, off1 + tag1.length)
        assert tag2.cls == TagClass.APPLICATION
        assert tag2.number == 11  # Time

    def test_wildcard(self):
        dt = BACnetDateTime(
            date=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF),
            time=BACnetTime(0xFF, 0xFF, 0xFF, 0xFF),
        )
        result = encode_property_value(dt)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetDateRange
# ---------------------------------------------------------------------------
class TestDateRangeEncoding:
    def test_basic(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 1),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        result = encode_property_value(dr)
        assert isinstance(result, bytes)
        # Two application-tagged dates
        tag1, off1 = decode_tag(result, 0)
        assert tag1.number == 10
        tag2, _off2 = decode_tag(result, off1 + tag1.length)
        assert tag2.number == 10


# ---------------------------------------------------------------------------
# BACnetWeekNDay
# ---------------------------------------------------------------------------
class TestWeekNDayEncoding:
    def test_basic(self):
        wnd = BACnetWeekNDay(month=6, week_of_month=2, day_of_week=3)
        result = encode_property_value(wnd)
        assert isinstance(result, bytes)
        # Should be an octet string (tag 6) with 3 bytes
        tag, _off = decode_tag(result, 0)
        assert tag.number == 6  # Octet String
        assert tag.length == 3

    def test_wildcards(self):
        wnd = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=0xFF)
        result = encode_property_value(wnd)
        content = result[-3:]
        assert content == bytes([0xFF, 0xFF, 0xFF])


# ---------------------------------------------------------------------------
# BACnetCalendarEntry
# ---------------------------------------------------------------------------
class TestCalendarEntryEncoding:
    def test_date_choice(self):
        entry = BACnetCalendarEntry(
            choice=0,
            value=BACnetDate(2024, 7, 4, 4),
        )
        result = encode_property_value(entry)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 0

    def test_date_range_choice(self):
        entry = BACnetCalendarEntry(
            choice=1,
            value=BACnetDateRange(
                start_date=BACnetDate(2024, 1, 1, 1),
                end_date=BACnetDate(2024, 12, 31, 2),
            ),
        )
        result = encode_property_value(entry)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 1
        assert tag.is_opening

    def test_week_n_day_choice(self):
        entry = BACnetCalendarEntry(
            choice=2,
            value=BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=1),
        )
        result = encode_property_value(entry)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 2


# ---------------------------------------------------------------------------
# BACnetTimeValue
# ---------------------------------------------------------------------------
class TestTimeValueEncoding:
    def test_basic(self):
        tv = BACnetTimeValue(
            time=BACnetTime(8, 0, 0, 0),
            value=72.5,
        )
        result = encode_property_value(tv)
        assert isinstance(result, bytes)
        # First should be Time tag (11)
        tag, _off = decode_tag(result, 0)
        assert tag.number == 11

    def test_with_null_value(self):
        tv = BACnetTimeValue(
            time=BACnetTime(17, 0, 0, 0),
            value=None,
        )
        result = encode_property_value(tv)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetSpecialEvent
# ---------------------------------------------------------------------------
class TestSpecialEventEncoding:
    def test_with_calendar_entry(self):
        se = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0,
                value=BACnetDate(2024, 12, 25, 3),
            ),
            list_of_time_values=(
                BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
                BACnetTimeValue(time=BACnetTime(17, 0, 0, 0), value=None),
            ),
            event_priority=1,
        )
        result = encode_property_value(se)
        assert isinstance(result, bytes)
        # First tag should be opening tag 0 (calendar entry)
        tag, _ = decode_tag(result, 0)
        assert tag.is_opening
        assert tag.number == 0

    def test_with_calendar_reference(self):
        se = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=68.0),),
            event_priority=5,
        )
        result = encode_property_value(se)
        assert isinstance(result, bytes)
        # First tag should be context 1 (calendar reference)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 1


# ---------------------------------------------------------------------------
# BACnetDeviceObjectPropertyReference
# ---------------------------------------------------------------------------
class TestDeviceObjectPropertyReferenceEncoding:
    def test_basic(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        result = encode_property_value(ref)
        assert isinstance(result, bytes)
        # Context tag 0 (object id), then context tag 1 (property id)
        tag0, off0 = decode_tag(result, 0)
        assert tag0.cls == TagClass.CONTEXT
        assert tag0.number == 0
        tag1, _ = decode_tag(result, off0 + tag0.length)
        assert tag1.cls == TagClass.CONTEXT
        assert tag1.number == 1

    def test_with_array_index_and_device(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=3,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        result = encode_property_value(ref)
        assert isinstance(result, bytes)
        # Should have context tags 0, 1, 2, 3
        offset = 0
        for expected_tag_num in [0, 1, 2, 3]:
            tag, off = decode_tag(result, offset)
            assert tag.cls == TagClass.CONTEXT
            assert tag.number == expected_tag_num
            offset = off + tag.length


# ---------------------------------------------------------------------------
# BACnetObjectPropertyReference
# ---------------------------------------------------------------------------
class TestObjectPropertyReferenceEncoding:
    def test_basic(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 5),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        result = encode_property_value(ref)
        assert isinstance(result, bytes)

    def test_with_array_index(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 10),
            property_identifier=PropertyIdentifier.PRIORITY_ARRAY,
            property_array_index=8,
        )
        result = encode_property_value(ref)
        assert isinstance(result, bytes)
        # Should have context tags 0, 1, 2
        offset = 0
        for expected in [0, 1, 2]:
            tag, off = decode_tag(result, offset)
            assert tag.number == expected
            offset = off + tag.length


# ---------------------------------------------------------------------------
# BACnetAddress (constructed)
# ---------------------------------------------------------------------------
class TestBACnetAddressEncoding:
    def test_basic(self):
        addr = BACnetAddress(
            network_number=100,
            mac_address=bytes([192, 168, 1, 1, 0xBA, 0xC0]),
        )
        result = encode_property_value(addr)
        assert isinstance(result, bytes)
        tag0, _off0 = decode_tag(result, 0)
        assert tag0.cls == TagClass.CONTEXT
        assert tag0.number == 0


# ---------------------------------------------------------------------------
# BACnetRecipient
# ---------------------------------------------------------------------------
class TestRecipientEncoding:
    def test_device_choice(self):
        r = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 42))
        result = encode_property_value(r)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 0  # device choice

    def test_address_choice(self):
        r = BACnetRecipient(
            address=BACnetAddress(network_number=0, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        )
        result = encode_property_value(r)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.is_opening
        assert tag.number == 1  # address choice

    def test_empty_recipient(self):
        r = BACnetRecipient()
        result = encode_property_value(r)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetRecipientProcess
# ---------------------------------------------------------------------------
class TestRecipientProcessEncoding:
    def test_basic(self):
        rp = BACnetRecipientProcess(
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
            process_identifier=42,
        )
        result = encode_property_value(rp)
        assert isinstance(result, bytes)
        # Opening tag 0 for recipient, then context tag 1 for process_identifier
        tag0, _ = decode_tag(result, 0)
        assert tag0.is_opening
        assert tag0.number == 0


# ---------------------------------------------------------------------------
# BACnetDestination
# ---------------------------------------------------------------------------
class TestDestinationEncoding:
    def test_basic(self):
        dest = BACnetDestination(
            valid_days=BitString(b"\xfe", 1),  # Mon-Sun
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 5)),
            process_identifier=1,
            issue_confirmed_notifications=True,
            transitions=BitString(b"\xe0", 5),  # all 3 bits
        )
        result = encode_property_value(dest)
        assert isinstance(result, bytes)
        # First should be BitString (tag 8) for valid_days
        tag, _ = decode_tag(result, 0)
        assert tag.number == 8  # Bit String


# ---------------------------------------------------------------------------
# BACnetScale
# ---------------------------------------------------------------------------
class TestScaleEncoding:
    def test_float_scale(self):
        s = BACnetScale(float_scale=1.5)
        result = encode_property_value(s)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 0

    def test_integer_scale(self):
        s = BACnetScale(integer_scale=10)
        result = encode_property_value(s)
        assert isinstance(result, bytes)
        tag, _ = decode_tag(result, 0)
        assert tag.cls == TagClass.CONTEXT
        assert tag.number == 1

    def test_default_scale(self):
        s = BACnetScale()
        result = encode_property_value(s)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetPrescale
# ---------------------------------------------------------------------------
class TestPrescaleEncoding:
    def test_basic(self):
        ps = BACnetPrescale(multiplier=10, modulo_divide=100)
        result = encode_property_value(ps)
        assert isinstance(result, bytes)
        tag0, off0 = decode_tag(result, 0)
        assert tag0.cls == TagClass.CONTEXT
        assert tag0.number == 0
        tag1, _ = decode_tag(result, off0 + tag0.length)
        assert tag1.cls == TagClass.CONTEXT
        assert tag1.number == 1


# ---------------------------------------------------------------------------
# BACnetLogRecord
# ---------------------------------------------------------------------------
class TestLogRecordEncoding:
    def test_basic(self):
        lr = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(2024, 6, 15, 6),
                time=BACnetTime(14, 30, 0, 0),
            ),
            log_datum=72.5,
        )
        result = encode_property_value(lr)
        assert isinstance(result, bytes)

    def test_with_status_flags(self):
        lr = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(2024, 6, 15, 6),
                time=BACnetTime(14, 30, 0, 0),
            ),
            log_datum=42,
            status_flags=StatusFlags(in_alarm=True),
        )
        result = encode_property_value(lr)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetCOVSubscription
# ---------------------------------------------------------------------------
class TestCOVSubscriptionEncoding:
    def test_basic(self):
        sub = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
                process_identifier=1,
            ),
            monitored_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            issue_confirmed_notifications=True,
            time_remaining=300,
        )
        result = encode_property_value(sub)
        assert isinstance(result, bytes)

    def test_with_cov_increment(self):
        sub = BACnetCOVSubscription(
            recipient=BACnetRecipientProcess(
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 2)),
                process_identifier=5,
            ),
            monitored_object=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            issue_confirmed_notifications=False,
            time_remaining=600,
            cov_increment=1.5,
        )
        result = encode_property_value(sub)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# BACnetPriorityValue
# ---------------------------------------------------------------------------
class TestPriorityValueEncoding:
    def test_null(self):
        pv = BACnetPriorityValue(value=None)
        result = encode_property_value(pv)
        tag, _ = decode_tag(result, 0)
        assert tag.number == 0  # Null

    def test_float(self):
        pv = BACnetPriorityValue(value=72.5)
        result = encode_property_value(pv)
        tag, _ = decode_tag(result, 0)
        assert tag.number == 4  # Real

    def test_unsigned(self):
        pv = BACnetPriorityValue(value=42)
        result = encode_property_value(pv)
        tag, _ = decode_tag(result, 0)
        assert tag.number == 2  # Unsigned


# ---------------------------------------------------------------------------
# BACnetPriorityArray
# ---------------------------------------------------------------------------
class TestPriorityArrayEncoding:
    def test_all_null(self):
        pa = BACnetPriorityArray()
        result = encode_property_value(pa)
        assert isinstance(result, bytes)
        # Should be 16 null tags
        offset = 0
        for _ in range(16):
            tag, off = decode_tag(result, offset)
            assert tag.number == 0  # Null
            offset = off + tag.length

    def test_mixed(self):
        slots = [BACnetPriorityValue() for _ in range(16)]
        slots[7] = BACnetPriorityValue(value=72.5)  # Priority 8
        slots[15] = BACnetPriorityValue(value=65.0)  # Priority 16
        pa = BACnetPriorityArray(slots=tuple(slots))
        result = encode_property_value(pa)
        assert isinstance(result, bytes)

        # Parse through, find the non-null values
        offset = 0
        values_found = []
        for _i in range(16):
            tag, off = decode_tag(result, offset)
            if tag.number == 0:  # Null
                values_found.append(None)
            else:
                val = decode_application_value(result[offset : off + tag.length])
                values_found.append(val)
            offset = off + tag.length

        assert values_found[7] == pytest.approx(72.5)
        assert values_found[15] == pytest.approx(65.0)
        assert all(v is None for i, v in enumerate(values_found) if i not in (7, 15))


# ---------------------------------------------------------------------------
# List of constructed types
# ---------------------------------------------------------------------------
class TestListOfConstructedTypes:
    def test_list_of_time_values(self):
        """Schedule Weekly_Schedule is a list of BACnetTimeValue."""
        tvs = [
            BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.0),
            BACnetTimeValue(time=BACnetTime(17, 0, 0, 0), value=None),
        ]
        result = encode_property_value(tvs)
        assert isinstance(result, bytes)

    def test_list_of_calendar_entries(self):
        """Calendar Date_List is a list of BACnetCalendarEntry."""
        entries = [
            BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 3)),
            BACnetCalendarEntry(
                choice=2,
                value=BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=1),
            ),
        ]
        result = encode_property_value(entries)
        assert isinstance(result, bytes)

    def test_list_of_destinations(self):
        """NotificationClass Recipient_List is a list of BACnetDestination."""
        dests = [
            BACnetDestination(
                valid_days=BitString(b"\xfe", 1),
                from_time=BACnetTime(0, 0, 0, 0),
                to_time=BACnetTime(23, 59, 59, 99),
                recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
                process_identifier=1,
                issue_confirmed_notifications=True,
                transitions=BitString(b"\xe0", 5),
            ),
        ]
        result = encode_property_value(dests)
        assert isinstance(result, bytes)

    def test_list_of_object_property_references(self):
        """Schedule List_Of_Object_Property_References."""
        refs = [
            BACnetDeviceObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
            ),
            BACnetDeviceObjectPropertyReference(
                object_identifier=ObjectIdentifier(ObjectType.BINARY_OUTPUT, 2),
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            ),
        ]
        result = encode_property_value(refs)
        assert isinstance(result, bytes)
