"""Tests for BACnet constructed data types."""

import pytest

from bac_py.encoding.primitives import (
    decode_all_application_values,
    encode_context_tagged,
    encode_property_value,
    encode_unsigned,
)
from bac_py.types.constructed import (
    BACnetAddress,
    BACnetCalendarEntry,
    BACnetDateRange,
    BACnetDateTime,
    BACnetDestination,
    BACnetDeviceObjectPropertyReference,
    BACnetLogRecord,
    BACnetObjectPropertyReference,
    BACnetPriorityArray,
    BACnetPriorityValue,
    BACnetRecipient,
    BACnetRecipientProcess,
    BACnetScale,
    BACnetSpecialEvent,
    BACnetTimeStamp,
    BACnetTimeValue,
    BACnetValueSource,
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


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestStatusFlagsReprCoverage:
    def test_repr_overridden_flag(self):
        """StatusFlags repr includes OVERRIDDEN when set."""
        sf = StatusFlags(overridden=True)
        r = repr(sf)
        assert "OVERRIDDEN" in r

    def test_repr_out_of_service_flag(self):
        """StatusFlags repr includes OUT_OF_SERVICE when set."""
        sf = StatusFlags(out_of_service=True)
        r = repr(sf)
        assert "OUT_OF_SERVICE" in r

    def test_repr_all_flags(self):
        """StatusFlags repr includes all flags when all set."""
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        r = repr(sf)
        assert "IN_ALARM" in r
        assert "FAULT" in r
        assert "OVERRIDDEN" in r
        assert "OUT_OF_SERVICE" in r


class TestBACnetTimeStampDecodeCoverage:
    def test_decode_sequence_number(self):
        """BACnetTimeStamp decode with choice=1 (sequence number)."""
        ts = BACnetTimeStamp(choice=1, value=42)
        encoded = ts.encode()
        decoded, offset = BACnetTimeStamp.decode(encoded)
        assert decoded.choice == 1
        assert decoded.value == 42
        assert offset == len(encoded)

    def test_decode_datetime(self):
        """BACnetTimeStamp decode with choice=2 (datetime)."""
        dt = BACnetDateTime(
            date=BACnetDate(year=2024, month=6, day=15, day_of_week=6),
            time=BACnetTime(hour=10, minute=30, second=0, hundredth=0),
        )
        ts = BACnetTimeStamp(choice=2, value=dt)
        encoded = ts.encode()
        decoded, offset = BACnetTimeStamp.decode(encoded)
        assert decoded.choice == 2
        assert isinstance(decoded.value, BACnetDateTime)
        assert decoded.value == dt
        assert offset == len(encoded)

    def test_decode_invalid_tag_raises(self):
        """BACnetTimeStamp decode with invalid context tag raises ValueError."""
        # Context tag 5 is not valid for BACnetTimeStamp
        data = encode_context_tagged(5, encode_unsigned(42))
        with pytest.raises(ValueError, match="Invalid BACnetTimeStamp context tag"):
            BACnetTimeStamp.decode(data)


class TestBACnetSpecialEventEncodeCoverage:
    def test_encode_with_object_identifier_period(self):
        """BACnetSpecialEvent encode with ObjectIdentifier period (calendar reference)."""
        event = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=72.0),),
            event_priority=5,
        )
        encoded = event.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_special_event_calendar_reference_dict_round_trip(self):
        """BACnetSpecialEvent to_dict/from_dict with calendar reference."""
        event = BACnetSpecialEvent(
            period=ObjectIdentifier(ObjectType.CALENDAR, 1),
            list_of_time_values=(BACnetTimeValue(time=BACnetTime(0, 0, 0, 0), value=72.0),),
            event_priority=5,
        )
        d = event.to_dict()
        assert d["period_type"] == "calendar_reference"
        restored = BACnetSpecialEvent.from_dict(d)
        assert isinstance(restored.period, ObjectIdentifier)
        assert restored.period == ObjectIdentifier(ObjectType.CALENDAR, 1)
        assert restored.event_priority == 5


class TestDeviceObjectPropertyReferenceCoverage:
    def test_encode_decode_with_device_identifier(self):
        """DeviceObjectPropertyReference encode/decode with optional device_identifier."""
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=None,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        encoded = ref.encode()
        decoded, _offset = BACnetDeviceObjectPropertyReference.decode(encoded)
        assert decoded.device_identifier is not None
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE


class TestBACnetRecipientEncodeCoverage:
    def test_encode_device_recipient(self):
        """BACnetRecipient.encode() with device set."""
        recip = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 10))
        encoded = recip.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_address_recipient(self):
        """BACnetRecipient.encode() with address set."""
        from bac_py.types.constructed import BACnetAddress

        addr = BACnetAddress(network_number=1, mac_address=b"\x0a")
        recip = BACnetRecipient(address=addr)
        encoded = recip.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_empty_recipient(self):
        """BACnetRecipient.encode() with neither device nor address set."""
        recip = BACnetRecipient()
        encoded = recip.encode()
        assert isinstance(encoded, bytes)


class TestBACnetScaleCoverage:
    def test_to_dict_float_scale(self):
        """BACnetScale to_dict with float_scale."""
        scale = BACnetScale(float_scale=1.5)
        d = scale.to_dict()
        assert d == {"type": "float", "value": 1.5}

    def test_to_dict_integer_scale(self):
        """BACnetScale to_dict with integer_scale."""
        scale = BACnetScale(integer_scale=10)
        d = scale.to_dict()
        assert d == {"type": "integer", "value": 10}

    def test_to_dict_neither_set(self):
        """BACnetScale to_dict with neither set."""
        scale = BACnetScale()
        d = scale.to_dict()
        assert d == {"type": "float", "value": None}

    def test_from_dict_float(self):
        """BACnetScale from_dict with float type."""
        d = {"type": "float", "value": 2.5}
        scale = BACnetScale.from_dict(d)
        assert scale.float_scale == 2.5
        assert scale.integer_scale is None

    def test_from_dict_integer(self):
        """BACnetScale from_dict with integer type."""
        d = {"type": "integer", "value": 10}
        scale = BACnetScale.from_dict(d)
        assert scale.integer_scale == 10
        assert scale.float_scale is None


class TestBACnetLogRecordCoverage:
    def test_log_record_without_status_flags(self):
        """BACnetLogRecord to_dict omits status_flags when None."""
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(124, 6, 15, 6),
                time=BACnetTime(10, 30, 0, 0),
            ),
            log_datum=42.5,
        )
        d = rec.to_dict()
        assert "status_flags" not in d

    def test_log_record_with_status_flags(self):
        """BACnetLogRecord to_dict includes status_flags when set."""
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(124, 6, 15, 6),
                time=BACnetTime(10, 30, 0, 0),
            ),
            log_datum=42.5,
            status_flags=StatusFlags(in_alarm=True),
        )
        d = rec.to_dict()
        assert "status_flags" in d
        assert d["status_flags"]["in_alarm"] is True

    def test_log_record_with_object_log_datum(self):
        """BACnetLogRecord to_dict with a log_datum that has to_dict."""
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        rec = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(124, 6, 15, 6),
                time=BACnetTime(10, 30, 0, 0),
            ),
            log_datum=oid,
        )
        d = rec.to_dict()
        assert d["log_datum"] == {"object_type": "analog-input", "instance": 1}


class TestBACnetValueSourceCoverage:
    def test_encode_invalid_choice_raises(self):
        """BACnetValueSource encode with invalid choice raises ValueError."""
        vs = BACnetValueSource(choice=99, value=None)
        with pytest.raises(ValueError, match="Invalid BACnetValueSource choice"):
            vs.encode()

    def test_decode_invalid_choice_tag_raises(self):
        """BACnetValueSource decode with invalid context tag raises ValueError."""
        data = encode_context_tagged(5, encode_unsigned(0))
        with pytest.raises(ValueError, match="Invalid BACnetValueSource choice tag"):
            BACnetValueSource.decode(data)

    def test_to_dict_invalid_choice_raises(self):
        """BACnetValueSource to_dict with invalid choice raises ValueError."""
        vs = BACnetValueSource(choice=99, value=None)
        with pytest.raises(ValueError, match="Invalid BACnetValueSource choice"):
            vs.to_dict()

    def test_from_dict_invalid_choice_raises(self):
        """BACnetValueSource from_dict with invalid choice raises ValueError."""
        with pytest.raises(ValueError, match="Invalid BACnetValueSource choice"):
            BACnetValueSource.from_dict({"choice": "unknown", "value": None})


# ---------------------------------------------------------------------------
# Coverage: constructed.py remaining lines
# ---------------------------------------------------------------------------


class TestBACnetTimeStampApplicationTag:
    """Line 218-219: BACnetTimeStamp.decode with application tag raises ValueError."""

    def test_decode_application_tag_raises(self):
        from bac_py.encoding.primitives import encode_application_unsigned

        # Application-tagged unsigned value (not a context tag)
        data = encode_application_unsigned(42)
        with pytest.raises(ValueError, match="Expected context tag for BACnetTimeStamp"):
            BACnetTimeStamp.decode(data)


class TestBACnetTimeValueToDict:
    """Line 478: BACnetTimeValue.to_dict calls value.to_dict() when available."""

    def test_to_dict_with_complex_value(self):
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        tv = BACnetTimeValue(
            time=BACnetTime(hour=8, minute=0, second=0, hundredth=0),
            value=oid,
        )
        d = tv.to_dict()
        assert d["value"] == {"object_type": "analog-input", "instance": 1}


class TestBACnetDeviceObjectPropertyReferenceArrayIndex:
    """Line 627: encode optional propertyArrayIndex in DeviceObjectPropertyReference."""

    def test_encode_decode_with_array_index(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=5,
            device_identifier=None,
        )
        encoded = ref.encode()
        decoded, _offset = BACnetDeviceObjectPropertyReference.decode(encoded)
        assert decoded.property_array_index == 5
        assert decoded.device_identifier is None


class TestBACnetDeviceObjectPropertyReferenceArrayIndexDecode:
    """Lines 668-672: decode propertyArrayIndex when present."""

    def test_decode_with_array_index_and_device(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_OUTPUT, 10),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=3,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
        )
        encoded = ref.encode()
        decoded, _offset = BACnetDeviceObjectPropertyReference.decode(encoded)
        assert decoded.property_array_index == 3
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 50)


class TestBACnetRecipientToDict:
    """Line 883: BACnetRecipient.to_dict with neither device nor address."""

    def test_to_dict_empty_recipient(self):
        recip = BACnetRecipient()
        d = recip.to_dict()
        assert d == {"type": "device", "device": None}


class TestBACnetRecipientFromDictEmpty:
    """Line 896: BACnetRecipient.from_dict with device=None."""

    def test_from_dict_device_none(self):
        d = {"type": "device", "device": None}
        recip = BACnetRecipient.from_dict(d)
        assert recip.device is None
        assert recip.address is None


class TestBACnetPriorityValueToDict:
    """Line 1248: BACnetPriorityValue.to_dict calls value.to_dict() when available."""

    def test_to_dict_with_complex_value(self):
        oid = ObjectIdentifier(ObjectType.BINARY_INPUT, 5)
        pv = BACnetPriorityValue(value=oid)
        d = pv.to_dict()
        assert d["value"] == {"object_type": "binary-input", "instance": 5}


class TestBACnetValueSourceDecodeApplicationTag:
    """Lines 1513-1514: BACnetValueSource.decode with application tag raises ValueError."""

    def test_decode_application_tag_raises(self):
        from bac_py.encoding.primitives import encode_application_unsigned

        data = encode_application_unsigned(0)
        with pytest.raises(ValueError, match="Expected context tag for BACnetValueSource"):
            BACnetValueSource.decode(data)


# ---------------------------------------------------------------------------
# Coverage: constructed.py branch partials
# ---------------------------------------------------------------------------


class TestDeviceObjectPropertyReferenceNoOptionalFields:
    """Branch 668->675: decode with no propertyArrayIndex and no deviceIdentifier.

    When data ends right after the propertyIdentifier, the offset >= len(data)
    checks at line 668 and 676 both skip, leaving both optional fields as None.
    """

    def test_decode_only_required_fields(self):
        ref = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=None,
            device_identifier=None,
        )
        encoded = ref.encode()
        decoded, _offset = BACnetDeviceObjectPropertyReference.decode(encoded)
        assert decoded.property_array_index is None
        assert decoded.device_identifier is None
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE


class TestBACnetValueSourceDecodeMemoryview:
    """Branch 1507->1510: data is already a memoryview, skip bytes conversion."""

    def test_decode_with_memoryview_input(self):
        vs = BACnetValueSource.none_source()
        encoded = vs.encode()
        # Pass a memoryview directly (not bytes) to skip the isinstance check
        decoded, offset = BACnetValueSource.decode(memoryview(encoded))
        assert decoded.choice == 0
        assert offset == len(encoded)


class TestBACnetValueSourceDecodePrimitiveNull:
    """Branch 1518->1520: context tag [0] that is NOT opening (primitive null).

    When choice 0 is encoded as a primitive context tag instead of
    opening+closing, the is_opening check is False and we skip directly
    to returning none_source().
    """

    def test_decode_primitive_context_null(self):
        # Craft a primitive context tag [0] with length 0
        # Byte: (tag_number << 4) | (cls << 3) | lvt = (0 << 4) | (1 << 3) | 0 = 0x08
        data = bytes([0x08])
        decoded, offset = BACnetValueSource.decode(data)
        assert decoded.choice == 0
        assert offset == 1
