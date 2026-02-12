"""Tests for BACnetTimeStamp CHOICE type and event-related enums (Step 1.3)."""

import pytest

from bac_py.types.constructed import BACnetDateTime, BACnetTimeStamp
from bac_py.types.enums import AcknowledgmentFilter, EventTransitionBits
from bac_py.types.primitives import BACnetDate, BACnetTime


class TestBACnetTimeStampTime:
    """BACnetTimeStamp with choice=0 (Time)."""

    def test_round_trip_time(self):
        ts = BACnetTimeStamp(choice=0, value=BACnetTime(14, 30, 15, 50))
        encoded = ts.encode()
        decoded, offset = BACnetTimeStamp.decode(encoded)

        assert decoded.choice == 0
        assert isinstance(decoded.value, BACnetTime)
        assert decoded.value.hour == 14
        assert decoded.value.minute == 30
        assert decoded.value.second == 15
        assert decoded.value.hundredth == 50
        assert offset == len(encoded)

    def test_round_trip_midnight(self):
        ts = BACnetTimeStamp(choice=0, value=BACnetTime(0, 0, 0, 0))
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.choice == 0
        assert decoded.value == BACnetTime(0, 0, 0, 0)

    def test_round_trip_end_of_day(self):
        ts = BACnetTimeStamp(choice=0, value=BACnetTime(23, 59, 59, 99))
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.value == BACnetTime(23, 59, 59, 99)

    def test_round_trip_wildcard_time(self):
        """Time with unspecified (wildcard) fields."""
        ts = BACnetTimeStamp(choice=0, value=BACnetTime(0xFF, 0xFF, 0xFF, 0xFF))
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.value.hour == 0xFF
        assert decoded.value.minute == 0xFF
        assert decoded.value.second == 0xFF
        assert decoded.value.hundredth == 0xFF

    def test_to_dict_time(self):
        ts = BACnetTimeStamp(choice=0, value=BACnetTime(10, 0, 0, 0))
        d = ts.to_dict()

        assert d["choice"] == "time"
        assert d["value"]["hour"] == 10

    def test_from_dict_time(self):
        d = {"choice": "time", "value": {"hour": 10, "minute": 0, "second": 0, "hundredth": 0}}
        ts = BACnetTimeStamp.from_dict(d)

        assert ts.choice == 0
        assert isinstance(ts.value, BACnetTime)
        assert ts.value.hour == 10


class TestBACnetTimeStampSequenceNumber:
    """BACnetTimeStamp with choice=1 (Unsigned sequence number)."""

    def test_round_trip_sequence_number(self):
        ts = BACnetTimeStamp(choice=1, value=42)
        encoded = ts.encode()
        decoded, offset = BACnetTimeStamp.decode(encoded)

        assert decoded.choice == 1
        assert decoded.value == 42
        assert offset == len(encoded)

    def test_round_trip_zero(self):
        ts = BACnetTimeStamp(choice=1, value=0)
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.value == 0

    def test_round_trip_large_sequence(self):
        """Maximum 4-byte unsigned value."""
        ts = BACnetTimeStamp(choice=1, value=0xFFFFFFFF)
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.value == 0xFFFFFFFF

    def test_round_trip_small_values(self):
        """Single-byte and two-byte sequence numbers."""
        for val in [1, 127, 255, 256, 65535]:
            ts = BACnetTimeStamp(choice=1, value=val)
            encoded = ts.encode()
            decoded, _ = BACnetTimeStamp.decode(encoded)
            assert decoded.value == val

    def test_to_dict_sequence_number(self):
        ts = BACnetTimeStamp(choice=1, value=100)
        d = ts.to_dict()

        assert d["choice"] == "sequence_number"
        assert d["value"] == 100

    def test_from_dict_sequence_number(self):
        d = {"choice": "sequence_number", "value": 100}
        ts = BACnetTimeStamp.from_dict(d)

        assert ts.choice == 1
        assert ts.value == 100


class TestBACnetTimeStampDateTime:
    """BACnetTimeStamp with choice=2 (BACnetDateTime)."""

    def test_round_trip_datetime(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 6, 15, 6),
            time=BACnetTime(9, 30, 0, 0),
        )
        ts = BACnetTimeStamp(choice=2, value=dt)
        encoded = ts.encode()
        decoded, offset = BACnetTimeStamp.decode(encoded)

        assert decoded.choice == 2
        assert isinstance(decoded.value, BACnetDateTime)
        assert decoded.value.date.year == 2024
        assert decoded.value.date.month == 6
        assert decoded.value.date.day == 15
        assert decoded.value.time.hour == 9
        assert decoded.value.time.minute == 30
        assert offset == len(encoded)

    def test_round_trip_date_wildcards(self):
        """DateTime with date wildcard fields."""
        dt = BACnetDateTime(
            date=BACnetDate(0xFF, 0xFF, 0xFF, 0xFF),
            time=BACnetTime(12, 0, 0, 0),
        )
        ts = BACnetTimeStamp(choice=2, value=dt)
        encoded = ts.encode()
        decoded, _ = BACnetTimeStamp.decode(encoded)

        assert decoded.value.date.year == 0xFF
        assert decoded.value.date.month == 0xFF
        assert decoded.value.time.hour == 12

    def test_to_dict_datetime(self):
        dt = BACnetDateTime(
            date=BACnetDate(2024, 1, 1, 1),
            time=BACnetTime(0, 0, 0, 0),
        )
        ts = BACnetTimeStamp(choice=2, value=dt)
        d = ts.to_dict()

        assert d["choice"] == "date_time"
        assert "date" in d["value"]
        assert "time" in d["value"]

    def test_from_dict_datetime(self):
        d = {
            "choice": "date_time",
            "value": {
                "date": {"year": 2024, "month": 1, "day": 1, "day_of_week": 1},
                "time": {"hour": 0, "minute": 0, "second": 0, "hundredth": 0},
            },
        }
        ts = BACnetTimeStamp.from_dict(d)

        assert ts.choice == 2
        assert isinstance(ts.value, BACnetDateTime)
        assert ts.value.date.year == 2024


class TestBACnetTimeStampErrors:
    """Error handling for BACnetTimeStamp."""

    def test_encode_invalid_choice(self):
        ts = BACnetTimeStamp(choice=3, value=0)
        with pytest.raises(ValueError, match="Invalid BACnetTimeStamp choice"):
            ts.encode()

    def test_from_dict_invalid_choice(self):
        with pytest.raises(ValueError, match="Invalid BACnetTimeStamp choice"):
            BACnetTimeStamp.from_dict({"choice": "invalid", "value": 0})


class TestBACnetTimeStampDictRoundTrip:
    """Full to_dict/from_dict round-trip for all variants."""

    def test_time_dict_round_trip(self):
        original = BACnetTimeStamp(choice=0, value=BACnetTime(8, 15, 30, 0))
        restored = BACnetTimeStamp.from_dict(original.to_dict())
        assert restored == original

    def test_sequence_dict_round_trip(self):
        original = BACnetTimeStamp(choice=1, value=500)
        restored = BACnetTimeStamp.from_dict(original.to_dict())
        assert restored == original

    def test_datetime_dict_round_trip(self):
        original = BACnetTimeStamp(
            choice=2,
            value=BACnetDateTime(
                date=BACnetDate(2024, 12, 25, 3),
                time=BACnetTime(18, 0, 0, 0),
            ),
        )
        restored = BACnetTimeStamp.from_dict(original.to_dict())
        assert restored == original


class TestBACnetTimeStampDecodeOffset:
    """Test decoding with non-zero starting offset."""

    def test_decode_with_offset(self):
        ts = BACnetTimeStamp(choice=1, value=42)
        encoded = ts.encode()
        # Prepend some garbage bytes and decode at offset
        padded = b"\x00\x00\x00" + encoded
        decoded, offset = BACnetTimeStamp.decode(padded, offset=3)

        assert decoded.choice == 1
        assert decoded.value == 42
        assert offset == len(padded)


class TestAcknowledgmentFilter:
    """Verify AcknowledgmentFilter enum values per Clause 13.7.1."""

    def test_values(self):
        assert AcknowledgmentFilter.ALL == 0
        assert AcknowledgmentFilter.ACKED == 1
        assert AcknowledgmentFilter.NOT_ACKED == 2

    def test_member_count(self):
        assert len(AcknowledgmentFilter) == 3


class TestEventTransitionBits:
    """Verify EventTransitionBits positional constants per Clause 12.11."""

    def test_values(self):
        assert EventTransitionBits.TO_OFFNORMAL == 0
        assert EventTransitionBits.TO_FAULT == 1
        assert EventTransitionBits.TO_NORMAL == 2

    def test_member_count(self):
        assert len(EventTransitionBits) == 3
