"""Tests for JSON serialization module."""

from __future__ import annotations

import json

import pytest

from bac_py.serialization import Serializer, deserialize, get_serializer, serialize
from bac_py.serialization.json import JsonSerializer
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import (
    BACnetDate,
    BACnetTime,
    BitString,
    ObjectIdentifier,
)


class TestJsonSerializerRoundTrip:
    def test_encode_decode_plain_dict(self):
        s = JsonSerializer()
        data = {"name": "device-1", "value": 42, "active": True}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == data

    def test_encode_decode_nested_dict(self):
        s = JsonSerializer()
        data = {"outer": {"inner": [1, 2, 3]}, "flag": False}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == data


class TestJsonSerializerOptions:
    def test_pretty_produces_indented_output(self):
        s = JsonSerializer(pretty=True)
        data = {"a": 1}
        encoded = s.encode(data)
        text = encoded.decode("utf-8")
        assert "\n" in text
        assert "  " in text

    def test_sort_keys_produces_sorted_keys(self):
        s = JsonSerializer(sort_keys=True)
        data = {"z": 1, "a": 2, "m": 3}
        encoded = s.encode(data)
        text = encoded.decode("utf-8")
        keys = list(json.loads(text).keys())
        assert keys == sorted(keys)


class TestJsonSerializerDefault:
    def test_handles_object_with_to_dict(self):
        class Dummy:
            def to_dict(self):
                return {"key": "value"}

        s = JsonSerializer()
        data = {"obj": Dummy()}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == {"obj": {"key": "value"}}

    def test_handles_bytes_as_hex(self):
        s = JsonSerializer()
        data = {"raw": b"\xde\xad\xbe\xef"}
        encoded = s.encode(data)
        decoded = s.decode(encoded)
        assert decoded == {"raw": "deadbeef"}

    def test_default_raises_type_error_for_unknown_types(self):
        s = JsonSerializer()
        with pytest.raises(TypeError, match="Cannot serialize"):
            s._default(object())

    def test_encode_raises_type_error_for_unknown_types(self):
        s = JsonSerializer()
        data = {"bad": object()}
        with pytest.raises(TypeError):
            s.encode(data)


class TestConvenienceFunctions:
    def test_serialize_plain_dict(self):
        data = {"x": 10}
        raw = serialize(data)
        result = deserialize(raw)
        assert result == data

    def test_serialize_object_with_to_dict(self):
        oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        raw = serialize(oid)
        result = deserialize(raw)
        assert result == {"object_type": "device", "instance": 100}

    def test_serialize_passes_kwargs(self):
        data = {"z": 1, "a": 2}
        raw = serialize(data, sort_keys=True)
        text = raw.decode("utf-8")
        keys = list(json.loads(text).keys())
        assert keys == sorted(keys)


class TestGetSerializer:
    def test_json_returns_json_serializer(self):
        s = get_serializer("json")
        assert isinstance(s, JsonSerializer)

    def test_unknown_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported serialization format"):
            get_serializer("unknown")


class TestSerializerProtocol:
    def test_runtime_checkable(self):
        s = JsonSerializer()
        assert isinstance(s, Serializer)


class TestBACnetPrimitiveRoundTrips:
    def test_object_identifier_round_trip(self):
        original = ObjectIdentifier(ObjectType.ANALOG_INPUT, 7)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = ObjectIdentifier.from_dict(recovered_dict)
        assert restored == original

    def test_bacnet_date_with_wildcards(self):
        original = BACnetDate(year=0xFF, month=12, day=25, day_of_week=0xFF)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BACnetDate.from_dict(recovered_dict)
        assert restored == original
        assert recovered_dict["year"] is None
        assert recovered_dict["day_of_week"] is None
        assert recovered_dict["month"] == 12

    def test_bacnet_time_round_trip(self):
        original = BACnetTime(hour=14, minute=30, second=0, hundredth=50)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BACnetTime.from_dict(recovered_dict)
        assert restored == original

    def test_bitstring_round_trip(self):
        original = BitString(b"\xa4", unused_bits=2)
        raw = serialize(original)
        recovered_dict = deserialize(raw)
        restored = BitString.from_dict(recovered_dict)
        assert restored == original


class TestContentType:
    def test_content_type_returns_application_json(self):
        s = JsonSerializer()
        assert s.content_type == "application/json"


# ---------------------------------------------------------------------------
# Step 2a: Constructed Type Round-Trips
# ---------------------------------------------------------------------------


class TestConstructedTypeRoundTrips:
    """Test serialize -> deserialize -> from_dict for all major constructed types."""

    def test_status_flags_round_trip(self):
        from bac_py.types.constructed import StatusFlags

        original = StatusFlags(in_alarm=True, fault=False, overridden=True, out_of_service=False)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = StatusFlags.from_dict(d)
        assert restored == original

    def test_bacnet_date_time_round_trip(self):
        from bac_py.types.constructed import BACnetDateTime

        original = BACnetDateTime(
            date=BACnetDate(year=124, month=6, day=15, day_of_week=6),
            time=BACnetTime(hour=14, minute=30, second=0, hundredth=0),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetDateTime.from_dict(d)
        assert restored == original

    def test_bacnet_timestamp_time_choice(self):
        from bac_py.types.constructed import BACnetTimeStamp

        original = BACnetTimeStamp(choice=0, value=BACnetTime(hour=8, minute=0, second=0, hundredth=0))
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetTimeStamp.from_dict(d)
        assert restored == original

    def test_bacnet_timestamp_sequence_number_choice(self):
        from bac_py.types.constructed import BACnetTimeStamp

        original = BACnetTimeStamp(choice=1, value=42)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetTimeStamp.from_dict(d)
        assert restored == original

    def test_bacnet_timestamp_datetime_choice(self):
        from bac_py.types.constructed import BACnetDateTime, BACnetTimeStamp

        dt = BACnetDateTime(
            date=BACnetDate(year=124, month=1, day=1, day_of_week=1),
            time=BACnetTime(hour=0, minute=0, second=0, hundredth=0),
        )
        original = BACnetTimeStamp(choice=2, value=dt)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetTimeStamp.from_dict(d)
        assert restored == original

    def test_bacnet_date_range_round_trip(self):
        from bac_py.types.constructed import BACnetDateRange

        original = BACnetDateRange(
            start_date=BACnetDate(year=124, month=1, day=1, day_of_week=0xFF),
            end_date=BACnetDate(year=124, month=12, day=31, day_of_week=0xFF),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetDateRange.from_dict(d)
        assert restored == original

    def test_bacnet_weeknday_round_trip(self):
        from bac_py.types.constructed import BACnetWeekNDay

        original = BACnetWeekNDay(month=0xFF, week_of_month=2, day_of_week=1)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetWeekNDay.from_dict(d)
        assert restored == original

    def test_bacnet_weeknday_all_wildcards(self):
        from bac_py.types.constructed import BACnetWeekNDay

        original = BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=0xFF)
        d = original.to_dict()
        assert d["month"] is None
        assert d["week_of_month"] is None
        assert d["day_of_week"] is None
        restored = BACnetWeekNDay.from_dict(d)
        assert restored == original

    def test_bacnet_calendar_entry_date(self):
        from bac_py.types.constructed import BACnetCalendarEntry

        original = BACnetCalendarEntry(
            choice=0,
            value=BACnetDate(year=124, month=12, day=25, day_of_week=0xFF),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetCalendarEntry.from_dict(d)
        assert restored == original

    def test_bacnet_calendar_entry_date_range(self):
        from bac_py.types.constructed import BACnetCalendarEntry, BACnetDateRange

        original = BACnetCalendarEntry(
            choice=1,
            value=BACnetDateRange(
                start_date=BACnetDate(year=124, month=6, day=1, day_of_week=0xFF),
                end_date=BACnetDate(year=124, month=6, day=30, day_of_week=0xFF),
            ),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetCalendarEntry.from_dict(d)
        assert restored == original

    def test_bacnet_calendar_entry_weeknday(self):
        from bac_py.types.constructed import BACnetCalendarEntry, BACnetWeekNDay

        original = BACnetCalendarEntry(
            choice=2,
            value=BACnetWeekNDay(month=0xFF, week_of_month=0xFF, day_of_week=1),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetCalendarEntry.from_dict(d)
        assert restored == original

    def test_bacnet_time_value_round_trip(self):
        from bac_py.types.constructed import BACnetTimeValue

        original = BACnetTimeValue(
            time=BACnetTime(hour=8, minute=0, second=0, hundredth=0),
            value=72.5,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetTimeValue.from_dict(d)
        assert restored == original

    def test_bacnet_special_event_round_trip(self):
        from bac_py.types.constructed import (
            BACnetCalendarEntry,
            BACnetSpecialEvent,
            BACnetTimeValue,
        )

        original = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0,
                value=BACnetDate(year=124, month=12, day=25, day_of_week=0xFF),
            ),
            list_of_time_values=(
                BACnetTimeValue(
                    time=BACnetTime(hour=0, minute=0, second=0, hundredth=0),
                    value=65.0,
                ),
                BACnetTimeValue(
                    time=BACnetTime(hour=18, minute=0, second=0, hundredth=0),
                    value=60.0,
                ),
            ),
            event_priority=10,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetSpecialEvent.from_dict(d)
        assert restored == original

    def test_bacnet_object_property_reference_round_trip(self):
        from bac_py.types.constructed import BACnetObjectPropertyReference
        from bac_py.types.enums import PropertyIdentifier

        original = BACnetObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=None,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetObjectPropertyReference.from_dict(d)
        assert restored == original

    def test_bacnet_device_object_property_reference_round_trip(self):
        from bac_py.types.constructed import BACnetDeviceObjectPropertyReference
        from bac_py.types.enums import PropertyIdentifier

        original = BACnetDeviceObjectPropertyReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_array_index=3,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetDeviceObjectPropertyReference.from_dict(d)
        assert restored == original

    def test_bacnet_device_object_reference_round_trip(self):
        from bac_py.types.constructed import BACnetDeviceObjectReference

        original = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 5),
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetDeviceObjectReference.from_dict(d)
        assert restored == original

    def test_bacnet_device_object_reference_local(self):
        from bac_py.types.constructed import BACnetDeviceObjectReference

        original = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 3),
        )
        d = original.to_dict()
        assert "device_identifier" not in d
        restored = BACnetDeviceObjectReference.from_dict(d)
        assert restored == original

    def test_bacnet_value_source_none(self):
        from bac_py.types.constructed import BACnetValueSource

        original = BACnetValueSource.none_source()
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetValueSource.from_dict(d)
        assert restored == original
        assert d["choice"] == "none"

    def test_bacnet_value_source_object(self):
        from bac_py.types.constructed import BACnetDeviceObjectReference, BACnetValueSource

        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
        )
        original = BACnetValueSource.from_object(ref)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetValueSource.from_dict(d)
        assert restored == original
        assert d["choice"] == "object"

    def test_bacnet_value_source_address(self):
        from bac_py.types.constructed import BACnetValueSource

        original = BACnetValueSource.from_address(b"\xc0\xa8\x01\x64\xba\xc0")
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetValueSource.from_dict(d)
        assert restored == original
        assert d["choice"] == "address"

    def test_bacnet_log_record_round_trip(self):
        from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord, StatusFlags

        original = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(year=124, month=6, day=15, day_of_week=6),
                time=BACnetTime(hour=10, minute=30, second=0, hundredth=0),
            ),
            log_datum=72.5,
            status_flags=StatusFlags(in_alarm=False, fault=False, overridden=False, out_of_service=False),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetLogRecord.from_dict(d)
        assert restored == original

    def test_bacnet_priority_array_round_trip(self):
        from bac_py.types.constructed import BACnetPriorityArray, BACnetPriorityValue

        slots = [BACnetPriorityValue() for _ in range(16)]
        slots[7] = BACnetPriorityValue(value=72.5)  # Priority 8 = manual
        slots[15] = BACnetPriorityValue(value=55.0)  # Priority 16
        original = BACnetPriorityArray(slots=tuple(slots))
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetPriorityArray.from_dict(d)
        assert restored == original

    def test_bacnet_recipient_device_round_trip(self):
        from bac_py.types.constructed import BACnetRecipient

        original = BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 10))
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetRecipient.from_dict(d)
        assert restored == original

    def test_bacnet_recipient_address_round_trip(self):
        from bac_py.types.constructed import BACnetAddress, BACnetRecipient

        original = BACnetRecipient(
            address=BACnetAddress(network_number=1, mac_address=b"\xc0\xa8\x01\x01"),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetRecipient.from_dict(d)
        assert restored == original

    def test_bacnet_destination_round_trip(self):
        from bac_py.types.constructed import BACnetDestination, BACnetRecipient

        original = BACnetDestination(
            valid_days=BitString(b"\xfe", unused_bits=1),  # Mon-Sun
            from_time=BACnetTime(hour=0, minute=0, second=0, hundredth=0),
            to_time=BACnetTime(hour=23, minute=59, second=59, hundredth=99),
            recipient=BACnetRecipient(device=ObjectIdentifier(ObjectType.DEVICE, 10)),
            process_identifier=1,
            issue_confirmed_notifications=True,
            transitions=BitString(b"\xe0", unused_bits=5),  # all 3 transitions
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetDestination.from_dict(d)
        assert restored == original


# ---------------------------------------------------------------------------
# Step 2b: Schedule Configuration Export/Import
# ---------------------------------------------------------------------------


class TestScheduleConfigExportImport:
    """Test the config export/import use case: full schedule to JSON and back."""

    def test_weekly_schedule_round_trip(self):
        from bac_py.types.constructed import BACnetTimeValue

        monday = [
            BACnetTimeValue(time=BACnetTime(hour=8, minute=0, second=0, hundredth=0), value=72.0),
            BACnetTimeValue(time=BACnetTime(hour=17, minute=0, second=0, hundredth=0), value=65.0),
        ]
        weekend = [
            BACnetTimeValue(time=BACnetTime(hour=0, minute=0, second=0, hundredth=0), value=60.0),
        ]

        weekly_schedule = {
            "monday": [tv.to_dict() for tv in monday],
            "saturday": [tv.to_dict() for tv in weekend],
            "sunday": [tv.to_dict() for tv in weekend],
        }

        raw = serialize(weekly_schedule)
        d = deserialize(raw)

        # Reconstruct
        restored_monday = [BACnetTimeValue.from_dict(tv) for tv in d["monday"]]
        assert restored_monday == monday

    def test_exception_schedule_round_trip(self):
        from bac_py.types.constructed import (
            BACnetCalendarEntry,
            BACnetDateRange,
            BACnetSpecialEvent,
            BACnetTimeValue,
        )

        exceptions = [
            BACnetSpecialEvent(
                period=BACnetCalendarEntry(
                    choice=1,
                    value=BACnetDateRange(
                        start_date=BACnetDate(year=124, month=12, day=24, day_of_week=0xFF),
                        end_date=BACnetDate(year=125, month=1, day=2, day_of_week=0xFF),
                    ),
                ),
                list_of_time_values=(
                    BACnetTimeValue(
                        time=BACnetTime(hour=0, minute=0, second=0, hundredth=0),
                        value=60.0,
                    ),
                ),
                event_priority=5,
            ),
        ]

        config = {
            "exception_schedule": [se.to_dict() for se in exceptions],
        }

        raw = serialize(config)
        d = deserialize(raw)
        restored = [BACnetSpecialEvent.from_dict(se) for se in d["exception_schedule"]]
        assert restored == exceptions

    def test_full_schedule_config_round_trip(self):
        """Simulate exporting and importing a complete schedule configuration."""
        from bac_py.types.constructed import (
            BACnetCalendarEntry,
            BACnetDateRange,
            BACnetSpecialEvent,
            BACnetTimeValue,
        )

        weekly = {
            str(day): [
                BACnetTimeValue(
                    time=BACnetTime(hour=8, minute=0, second=0, hundredth=0),
                    value=72.0,
                ).to_dict(),
                BACnetTimeValue(
                    time=BACnetTime(hour=17, minute=0, second=0, hundredth=0),
                    value=65.0,
                ).to_dict(),
            ]
            for day in range(7)
        }

        exception = BACnetSpecialEvent(
            period=BACnetCalendarEntry(
                choice=0,
                value=BACnetDate(year=124, month=7, day=4, day_of_week=0xFF),
            ),
            list_of_time_values=(
                BACnetTimeValue(
                    time=BACnetTime(hour=0, minute=0, second=0, hundredth=0),
                    value=60.0,
                ),
            ),
            event_priority=8,
        )

        config = {
            "object_name": "HVAC-Schedule-1",
            "weekly_schedule": weekly,
            "exception_schedule": [exception.to_dict()],
            "effective_period": BACnetDateRange(
                start_date=BACnetDate(year=124, month=1, day=1, day_of_week=0xFF),
                end_date=BACnetDate(year=124, month=12, day=31, day_of_week=0xFF),
            ).to_dict(),
        }

        raw = serialize(config)
        d = deserialize(raw)

        # Verify we can reconstruct all parts
        assert d["object_name"] == "HVAC-Schedule-1"
        restored_period = BACnetDateRange.from_dict(d["effective_period"])
        assert restored_period.start_date.month == 1
        assert restored_period.end_date.month == 12

        restored_exceptions = [BACnetSpecialEvent.from_dict(se) for se in d["exception_schedule"]]
        assert len(restored_exceptions) == 1
        assert restored_exceptions[0] == exception

        for day_tvs in d["weekly_schedule"].values():
            restored_tvs = [BACnetTimeValue.from_dict(tv) for tv in day_tvs]
            assert len(restored_tvs) == 2
            assert restored_tvs[0].value == 72.0
            assert restored_tvs[1].value == 65.0


# ---------------------------------------------------------------------------
# Step 2c: Event Notification Payloads
# ---------------------------------------------------------------------------


class TestEventNotificationPayloads:
    """Test the webhook/event delivery use case: notification params to JSON."""

    def test_change_of_state_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            ChangeOfState,
            notification_parameters_from_dict,
        )

        original = ChangeOfState(
            new_state=b"\x09\x01",  # BinaryPV.ACTIVE encoded
            status_flags=StatusFlags(in_alarm=True, fault=False, overridden=False, out_of_service=False),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_out_of_range_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            OutOfRange,
            notification_parameters_from_dict,
        )

        original = OutOfRange(
            exceeding_value=105.5,
            status_flags=StatusFlags(in_alarm=True, fault=False, overridden=False, out_of_service=False),
            deadband=2.0,
            exceeded_limit=100.0,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_change_of_value_bits_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            ChangeOfValue,
            notification_parameters_from_dict,
        )

        original = ChangeOfValue(
            new_value_choice=0,
            new_value=BitString(b"\xa0", unused_bits=5),
            status_flags=StatusFlags(),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_change_of_value_real_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            ChangeOfValue,
            notification_parameters_from_dict,
        )

        original = ChangeOfValue(
            new_value_choice=1,
            new_value=72.5,
            status_flags=StatusFlags(),
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_floating_limit_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            FloatingLimit,
            notification_parameters_from_dict,
        )

        original = FloatingLimit(
            reference_value=85.3,
            status_flags=StatusFlags(in_alarm=True),
            setpoint_value=80.0,
            error_limit=5.0,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_unsigned_range_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            UnsignedRange,
            notification_parameters_from_dict,
        )

        original = UnsignedRange(
            exceeding_value=256,
            status_flags=StatusFlags(in_alarm=True),
            exceeded_limit=255,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_change_of_characterstring_round_trip(self):
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            ChangeOfCharacterstring,
            notification_parameters_from_dict,
        )

        original = ChangeOfCharacterstring(
            changed_value="CRITICAL",
            status_flags=StatusFlags(in_alarm=True),
            alarm_value="CRITICAL",
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_none_params_round_trip(self):
        from bac_py.types.notification_params import (
            NoneParams,
            notification_parameters_from_dict,
        )

        original = NoneParams()
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = notification_parameters_from_dict(d)
        assert restored == original

    def test_notification_as_webhook_payload(self):
        """Simulate wrapping a notification in a webhook envelope."""
        from bac_py.types.constructed import StatusFlags
        from bac_py.types.notification_params import (
            OutOfRange,
            notification_parameters_from_dict,
        )

        params = OutOfRange(
            exceeding_value=105.5,
            status_flags=StatusFlags(in_alarm=True),
            deadband=2.0,
            exceeded_limit=100.0,
        )

        payload = {
            "event_type": "out-of-range",
            "source_object": ObjectIdentifier(ObjectType.ANALOG_INPUT, 1).to_dict(),
            "notification_class": 5,
            "parameters": params.to_dict(),
        }

        raw = serialize(payload)
        d = deserialize(raw)

        assert d["event_type"] == "out-of-range"
        restored_source = ObjectIdentifier.from_dict(d["source_object"])
        assert restored_source == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        restored_params = notification_parameters_from_dict(d["parameters"])
        assert restored_params == params


# ---------------------------------------------------------------------------
# Step 2d: Audit Trail Records
# ---------------------------------------------------------------------------


class TestAuditTrailRecords:
    """Test the audit logging use case: audit notifications to JSON."""

    def test_audit_notification_minimal_round_trip(self):
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        original = BACnetAuditNotification(operation=AuditOperation.WRITE)
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetAuditNotification.from_dict(d)
        assert restored == original

    def test_audit_notification_full_round_trip(self):
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        original = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            source_object=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            source_comment="Operator override",
            target_comment="Temperature setpoint changed",
            invoke_id=42,
            source_user_id=1001,
            source_user_role=3,
            target_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            target_object=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            target_property=85,  # PRESENT_VALUE
            target_array_index=None,
            target_priority=8,
            target_value=b"\x44\x91\x00\x00",
            current_value=b"\x44\x87\x00\x00",
            result_error_class=None,
            result_error_code=None,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetAuditNotification.from_dict(d)
        assert restored == original

    def test_audit_notification_with_error(self):
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        original = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
            target_property=85,
            result_error_class=2,  # PROPERTY
            result_error_code=42,  # VALUE_OUT_OF_RANGE
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetAuditNotification.from_dict(d)
        assert restored == original

    def test_audit_log_record_round_trip(self):
        from bac_py.types.audit_types import BACnetAuditLogRecord, BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        notification = BACnetAuditNotification(
            operation=AuditOperation.CREATE,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 5),
        )
        original = BACnetAuditLogRecord(
            sequence_number=12345,
            notification=notification,
        )
        raw = serialize(original.to_dict())
        d = deserialize(raw)
        restored = BACnetAuditLogRecord.from_dict(d)
        assert restored == original
        assert d["sequence_number"] == 12345

    def test_audit_trail_as_list(self):
        """Simulate exporting a list of audit records (audit trail export)."""
        from bac_py.types.audit_types import BACnetAuditLogRecord, BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        records = [
            BACnetAuditLogRecord(
                sequence_number=i,
                notification=BACnetAuditNotification(
                    operation=AuditOperation.WRITE,
                    target_object=ObjectIdentifier(ObjectType.ANALOG_VALUE, 10),
                    target_property=85,
                ),
            )
            for i in range(5)
        ]

        trail = {"records": [r.to_dict() for r in records]}
        raw = serialize(trail)
        d = deserialize(raw)
        restored = [BACnetAuditLogRecord.from_dict(r) for r in d["records"]]
        assert restored == records


# ---------------------------------------------------------------------------
# Step 2e: Object Property Snapshots
# ---------------------------------------------------------------------------


class TestObjectPropertySnapshots:
    """Test the REST API response use case: object properties to JSON."""

    def test_binary_input_snapshot(self):
        from bac_py.objects.binary import BinaryInputObject
        from bac_py.types.enums import BinaryPV

        obj = BinaryInputObject(1, object_name="BI-1")
        snapshot = {}
        for prop_id in obj.PROPERTY_DEFINITIONS:
            try:
                val = obj.read_property(prop_id)
            except Exception:
                continue
            if val is None:
                continue
            if hasattr(val, "to_dict"):
                snapshot[prop_id.name.lower()] = val.to_dict()
            elif isinstance(val, int) and not isinstance(val, bool):
                snapshot[prop_id.name.lower()] = int(val)
            else:
                snapshot[prop_id.name.lower()] = val

        raw = serialize(snapshot)
        d = deserialize(raw)

        assert d["object_name"] == "BI-1"
        assert d["present_value"] == int(BinaryPV.INACTIVE)
        restored_oid = ObjectIdentifier.from_dict(d["object_identifier"])
        assert restored_oid.object_type == ObjectType.BINARY_INPUT
        assert restored_oid.instance_number == 1

    def test_analog_input_snapshot(self):
        from bac_py.objects.analog import AnalogInputObject

        obj = AnalogInputObject(42, object_name="Temp-Sensor-42")
        snapshot = {}
        for prop_id in obj.PROPERTY_DEFINITIONS:
            try:
                val = obj.read_property(prop_id)
            except Exception:
                continue
            if val is None:
                continue
            if hasattr(val, "to_dict"):
                snapshot[prop_id.name.lower()] = val.to_dict()
            elif isinstance(val, int) and not isinstance(val, bool):
                snapshot[prop_id.name.lower()] = int(val)
            elif isinstance(val, float):
                snapshot[prop_id.name.lower()] = val
            else:
                snapshot[prop_id.name.lower()] = val

        raw = serialize(snapshot)
        d = deserialize(raw)

        assert d["object_name"] == "Temp-Sensor-42"
        restored_oid = ObjectIdentifier.from_dict(d["object_identifier"])
        assert restored_oid.instance_number == 42


# ---------------------------------------------------------------------------
# Step 2f: TrendLog Data Export
# ---------------------------------------------------------------------------


class TestTrendLogDataExport:
    """Test the data export use case: log records list to JSON."""

    def test_log_records_list_round_trip(self):
        from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord, StatusFlags

        records = []
        for i in range(10):
            records.append(
                BACnetLogRecord(
                    timestamp=BACnetDateTime(
                        date=BACnetDate(year=124, month=6, day=15, day_of_week=6),
                        time=BACnetTime(hour=10, minute=i, second=0, hundredth=0),
                    ),
                    log_datum=20.0 + i * 0.5,
                    status_flags=StatusFlags(),
                )
            )

        export = {"records": [r.to_dict() for r in records]}
        raw = serialize(export)
        d = deserialize(raw)
        restored = [BACnetLogRecord.from_dict(r) for r in d["records"]]
        assert restored == records

    def test_log_records_without_status_flags(self):
        from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord

        original = BACnetLogRecord(
            timestamp=BACnetDateTime(
                date=BACnetDate(year=124, month=1, day=1, day_of_week=1),
                time=BACnetTime(hour=12, minute=0, second=0, hundredth=0),
            ),
            log_datum=42,
        )
        d = original.to_dict()
        assert "status_flags" not in d
        raw = serialize(d)
        restored = BACnetLogRecord.from_dict(deserialize(raw))
        assert restored == original

    def test_log_records_as_csv_friendly_dicts(self):
        """Test flattening log records for tabular export."""
        from bac_py.types.constructed import BACnetDateTime, BACnetLogRecord

        records = [
            BACnetLogRecord(
                timestamp=BACnetDateTime(
                    date=BACnetDate(year=124, month=6, day=15, day_of_week=6),
                    time=BACnetTime(hour=h, minute=0, second=0, hundredth=0),
                ),
                log_datum=70.0 + h,
            )
            for h in range(8, 18)
        ]

        flat = []
        for r in records:
            rd = r.to_dict()
            flat.append({
                "date": rd["timestamp"]["date"],
                "time": rd["timestamp"]["time"],
                "value": rd["log_datum"],
            })

        raw = serialize({"rows": flat})
        d = deserialize(raw)
        assert len(d["rows"]) == 10
        assert d["rows"][0]["value"] == 78.0
        assert d["rows"][9]["value"] == 87.0


# ---------------------------------------------------------------------------
# Step 2g: IntEnum Handling
# ---------------------------------------------------------------------------


class TestIntEnumHandling:
    """Test that BACnet enums serialize correctly as integers."""

    def test_object_type_serializes_as_int(self):
        raw = serialize({"type": ObjectType.ANALOG_INPUT})
        d = deserialize(raw)
        assert d["type"] == 0
        assert ObjectType(d["type"]) == ObjectType.ANALOG_INPUT

    def test_binary_pv_serializes_as_int(self):
        from bac_py.types.enums import BinaryPV

        raw = serialize({"active": BinaryPV.ACTIVE, "inactive": BinaryPV.INACTIVE})
        d = deserialize(raw)
        assert d["active"] == 1
        assert d["inactive"] == 0
        assert BinaryPV(d["active"]) == BinaryPV.ACTIVE

    def test_property_identifier_serializes_as_int(self):
        from bac_py.types.enums import PropertyIdentifier

        raw = serialize({"prop": PropertyIdentifier.PRESENT_VALUE})
        d = deserialize(raw)
        assert d["prop"] == 85
        assert PropertyIdentifier(d["prop"]) == PropertyIdentifier.PRESENT_VALUE

    def test_event_type_serializes_as_int(self):
        from bac_py.types.enums import EventType

        raw = serialize({"event": EventType.OUT_OF_RANGE})
        d = deserialize(raw)
        assert d["event"] == 5
        assert EventType(d["event"]) == EventType.OUT_OF_RANGE

    def test_reliability_serializes_as_int(self):
        from bac_py.types.enums import Reliability

        raw = serialize({"reliability": Reliability.NO_FAULT_DETECTED})
        d = deserialize(raw)
        assert d["reliability"] == 0
        assert Reliability(d["reliability"]) == Reliability.NO_FAULT_DETECTED

    def test_audit_operation_serializes_as_int(self):
        from bac_py.types.enums import AuditOperation

        raw = serialize({"op": AuditOperation.WRITE})
        d = deserialize(raw)
        assert isinstance(d["op"], int)
        assert AuditOperation(d["op"]) == AuditOperation.WRITE

    def test_mixed_enum_dict(self):
        """Test a dict with multiple enum types, simulating a REST response."""
        from bac_py.types.enums import BinaryPV, EventType, PropertyIdentifier

        data = {
            "object_type": ObjectType.BINARY_INPUT,
            "property": PropertyIdentifier.PRESENT_VALUE,
            "value": BinaryPV.ACTIVE,
            "event_type": EventType.CHANGE_OF_STATE,
        }
        raw = serialize(data)
        d = deserialize(raw)
        assert ObjectType(d["object_type"]) == ObjectType.BINARY_INPUT
        assert PropertyIdentifier(d["property"]) == PropertyIdentifier.PRESENT_VALUE
        assert BinaryPV(d["value"]) == BinaryPV.ACTIVE
        assert EventType(d["event_type"]) == EventType.CHANGE_OF_STATE
