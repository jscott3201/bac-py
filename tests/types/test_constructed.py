"""Tests for BACnet constructed data types."""

from bac_py.encoding.primitives import (
    decode_all_application_values,
    encode_property_value,
)
from bac_py.types.constructed import (
    BACnetAddress,
    BACnetCalendarEntry,
    BACnetDateRange,
    BACnetDateTime,
    BACnetDestination,
    BACnetLogRecord,
    BACnetObjectPropertyReference,
    BACnetPriorityArray,
    BACnetPriorityValue,
    BACnetRecipient,
    BACnetRecipientProcess,
    BACnetSpecialEvent,
    BACnetTimeValue,
    StatusFlags,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier


class TestStatusFlags:
    def test_default_all_false(self):
        sf = StatusFlags()
        assert sf.in_alarm is False
        assert sf.fault is False
        assert sf.overridden is False
        assert sf.out_of_service is False

    def test_constructor_kwargs(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        assert sf.in_alarm is True
        assert sf.fault is True
        assert sf.overridden is True
        assert sf.out_of_service is True

    def test_partial_flags(self):
        sf = StatusFlags(fault=True, out_of_service=True)
        assert sf.in_alarm is False
        assert sf.fault is True
        assert sf.overridden is False
        assert sf.out_of_service is True

    def test_to_bit_string(self):
        sf = StatusFlags(in_alarm=True)
        bs = sf.to_bit_string()
        assert isinstance(bs, BitString)
        assert len(bs) == 4
        assert bs[0] is True  # IN_ALARM
        assert bs[1] is False  # FAULT
        assert bs[2] is False  # OVERRIDDEN
        assert bs[3] is False  # OUT_OF_SERVICE

    def test_to_bit_string_all_set(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        bs = sf.to_bit_string()
        assert all(bs[i] for i in range(4))

    def test_from_bit_string_roundtrip(self):
        original = StatusFlags(fault=True, out_of_service=True)
        bs = original.to_bit_string()
        restored = StatusFlags.from_bit_string(bs)
        assert restored == original

    def test_to_dict(self):
        sf = StatusFlags(in_alarm=True)
        d = sf.to_dict()
        assert d == {
            "in_alarm": True,
            "fault": False,
            "overridden": False,
            "out_of_service": False,
        }

    def test_from_dict_roundtrip(self):
        original = StatusFlags(overridden=True, out_of_service=True)
        d = original.to_dict()
        restored = StatusFlags.from_dict(d)
        assert restored == original

    def test_equality(self):
        a = StatusFlags(fault=True)
        b = StatusFlags(fault=True)
        c = StatusFlags(in_alarm=True)
        assert a == b
        assert a != c

    def test_equality_not_implemented_for_other_types(self):
        sf = StatusFlags()
        assert sf != "not a status flags"

    def test_repr_normal(self):
        sf = StatusFlags()
        assert repr(sf) == "StatusFlags(NORMAL)"

    def test_repr_with_flags(self):
        sf = StatusFlags(in_alarm=True, fault=True)
        r = repr(sf)
        assert "IN_ALARM" in r
        assert "FAULT" in r


class TestBACnetDateTimeEncode:
    def test_encode_produces_bytes(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 1, 15, 1),
            time=BACnetTime(10, 30, 0, 0),
        )
        encoded = dt.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_round_trip_via_property_value(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 6, 15, 3),
            time=BACnetTime(14, 30, 0, 0),
        )
        encoded = dt.encode()
        via_pv = encode_property_value(dt)
        assert encoded == via_pv


class TestBACnetDateRangeEncode:
    def test_encode_produces_bytes(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 1),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        encoded = dr.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 1),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        assert dr.encode() == encode_property_value(dr)


class TestBACnetCalendarEntryEncode:
    def test_encode_date_choice(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 6, 15, 3))
        encoded = entry.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_date_range_choice(self):
        dr = BACnetDateRange(
            start_date=BACnetDate(2024, 1, 1, 1),
            end_date=BACnetDate(2024, 12, 31, 2),
        )
        entry = BACnetCalendarEntry(choice=1, value=dr)
        encoded = entry.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        from bac_py.types.constructed import BACnetWeekNDay

        entry = BACnetCalendarEntry(choice=2, value=BACnetWeekNDay(0xFF, 0xFF, 0xFF))
        assert entry.encode() == encode_property_value(entry)


class TestBACnetTimeValueEncode:
    def test_encode_produces_bytes(self):
        tv = BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.5)
        encoded = tv.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        tv = BACnetTimeValue(time=BACnetTime(8, 0, 0, 0), value=72.5)
        assert tv.encode() == encode_property_value(tv)


class TestBACnetSpecialEventEncode:
    def test_encode_with_calendar_entry(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 4))
        event = BACnetSpecialEvent(
            period=entry,
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=72.0),),
            event_priority=10,
        )
        encoded = event.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_matches_property_value(self):
        entry = BACnetCalendarEntry(choice=0, value=BACnetDate(2024, 12, 25, 4))
        event = BACnetSpecialEvent(
            period=entry,
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=72.0),),
            event_priority=10,
        )
        assert event.encode() == encode_property_value(event)


class TestBACnetObjectPropertyReferenceEncode:
    def test_encode_produces_bytes(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        encoded = ref.encode()
        assert isinstance(encoded, bytes)

    def test_encode_with_array_index(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=3,
        )
        encoded = ref.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        ref = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        assert ref.encode() == encode_property_value(ref)


class TestBACnetAddressEncode:
    def test_encode_produces_bytes(self):
        addr = BACnetAddress(network_number=0, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        encoded = addr.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        addr = BACnetAddress(network_number=1, mac_address=b"\x0a")
        assert addr.encode() == encode_property_value(addr)


class TestBACnetRecipientEncode:
    def test_encode_device(self):
        recip = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 100))
        encoded = recip.encode()
        assert isinstance(encoded, bytes)

    def test_encode_address(self):
        addr = BACnetAddress(network_number=0, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        recip = BACnetRecipient(address=addr)
        encoded = recip.encode()
        assert isinstance(encoded, bytes)


class TestBACnetDestinationEncode:
    def test_encode_produces_bytes(self):
        dest = BACnetDestination(
            valid_days=BitString(b"\xfe", 1),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
            process_identifier=0,
            issue_confirmed_notifications=True,
            transitions=BitString(b"\xe0", 5),
        )
        encoded = dest.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        dest = BACnetDestination(
            valid_days=BitString(b"\xfe", 1),
            from_time=BACnetTime(0, 0, 0, 0),
            to_time=BACnetTime(23, 59, 59, 99),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
            process_identifier=0,
            issue_confirmed_notifications=True,
            transitions=BitString(b"\xe0", 5),
        )
        assert dest.encode() == encode_property_value(dest)


class TestBACnetLogRecordEncode:
    def test_encode_produces_bytes(self):
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(2024, 6, 15, 3),
                time=BACnetTime(14, 30, 0, 0),
            ),
            log_datum=72.5,
        )
        encoded = rec.encode()
        assert isinstance(encoded, bytes)

    def test_encode_with_status_flags(self):
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(2024, 6, 15, 3),
                time=BACnetTime(14, 30, 0, 0),
            ),
            log_datum=72.5,
            status_flags=StatusFlags(in_alarm=True),
        )
        encoded = rec.encode()
        assert isinstance(encoded, bytes)


class TestBACnetRecipientProcessEncode:
    def test_encode_produces_bytes(self):
        rp = BACnetRecipientProcess(
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
            process_identifier=42,
        )
        encoded = rp.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        rp = BACnetRecipientProcess(
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 1)),
            process_identifier=42,
        )
        assert rp.encode() == encode_property_value(rp)


class TestBACnetPriorityArrayEncode:
    def test_encode_all_null(self):
        pa = BACnetPriorityArray()
        encoded = pa.encode()
        assert isinstance(encoded, bytes)
        values = decode_all_application_values(encoded)
        assert len(values) == 16
        assert all(v is None for v in values)

    def test_encode_with_value(self):
        slots = list(BACnetPriorityValue() for _ in range(16))
        slots[7] = BACnetPriorityValue(value=72.5)
        pa = BACnetPriorityArray(slots=tuple(slots))
        encoded = pa.encode()
        assert isinstance(encoded, bytes)

    def test_encode_matches_property_value(self):
        pa = BACnetPriorityArray()
        assert pa.encode() == encode_property_value(pa)
