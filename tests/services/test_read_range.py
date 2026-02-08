"""Tests for ReadRange service (Clause 15.8)."""

from bac_py.services.read_range import (
    RangeByPosition,
    RangeBySequenceNumber,
    RangeByTime,
    ReadRangeACK,
    ReadRangeRequest,
    ResultFlags,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import BACnetDate, BACnetTime, ObjectIdentifier


class TestResultFlags:
    def test_default_all_false(self):
        rf = ResultFlags()
        assert not rf.first_item
        assert not rf.last_item
        assert not rf.more_items

    def test_round_trip(self):
        rf = ResultFlags(first_item=True, last_item=True, more_items=False)
        bs = rf.to_bit_string()
        decoded = ResultFlags.from_bit_string(bs)
        assert decoded.first_item is True
        assert decoded.last_item is True
        assert decoded.more_items is False

    def test_round_trip_more_items(self):
        rf = ResultFlags(first_item=True, last_item=False, more_items=True)
        bs = rf.to_bit_string()
        decoded = ResultFlags.from_bit_string(bs)
        assert decoded.first_item is True
        assert decoded.last_item is False
        assert decoded.more_items is True


class TestReadRangeRequest:
    def test_encode_decode_no_range(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.property_array_index is None
        assert decoded.range is None

    def test_encode_decode_by_position(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            range=RangeByPosition(reference_index=5, count=10),
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert isinstance(decoded.range, RangeByPosition)
        assert decoded.range.reference_index == 5
        assert decoded.range.count == 10

    def test_encode_decode_by_position_negative_count(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            range=RangeByPosition(reference_index=10, count=-5),
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert isinstance(decoded.range, RangeByPosition)
        assert decoded.range.reference_index == 10
        assert decoded.range.count == -5

    def test_encode_decode_by_sequence_number(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.TREND_LOG, 1),
            property_identifier=PropertyIdentifier.LOG_BUFFER,
            range=RangeBySequenceNumber(reference_sequence_number=100, count=20),
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert isinstance(decoded.range, RangeBySequenceNumber)
        assert decoded.range.reference_sequence_number == 100
        assert decoded.range.count == 20

    def test_encode_decode_by_time(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.TREND_LOG, 1),
            property_identifier=PropertyIdentifier.LOG_BUFFER,
            range=RangeByTime(
                reference_date=BACnetDate(2024, 1, 15, 1),
                reference_time=BACnetTime(10, 30, 0, 0),
                count=50,
            ),
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert isinstance(decoded.range, RangeByTime)
        assert decoded.range.reference_date.year == 2024
        assert decoded.range.reference_date.month == 1
        assert decoded.range.reference_time.hour == 10
        assert decoded.range.reference_time.minute == 30
        assert decoded.range.count == 50

    def test_encode_decode_with_array_index(self):
        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=3,
            range=RangeByPosition(reference_index=1, count=5),
        )
        encoded = request.encode()
        decoded = ReadRangeRequest.decode(encoded)
        assert decoded.property_array_index == 3
        assert isinstance(decoded.range, RangeByPosition)


class TestReadRangeACK:
    def test_encode_decode_basic(self):
        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            result_flags=ResultFlags(first_item=True, last_item=True),
            item_count=2,
            item_data=b"\xc4\x00\x00\x00\x01\xc4\x02\x00\x00\x01",
        )
        encoded = ack.encode()
        decoded = ReadRangeACK.decode(encoded)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.result_flags.first_item is True
        assert decoded.result_flags.last_item is True
        assert decoded.result_flags.more_items is False
        assert decoded.item_count == 2
        assert decoded.item_data == b"\xc4\x00\x00\x00\x01\xc4\x02\x00\x00\x01"
        assert decoded.property_array_index is None
        assert decoded.first_sequence_number is None

    def test_encode_decode_with_sequence_number(self):
        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.TREND_LOG, 1),
            property_identifier=PropertyIdentifier.LOG_BUFFER,
            result_flags=ResultFlags(first_item=False, last_item=False, more_items=True),
            item_count=10,
            item_data=b"\x00" * 20,
            first_sequence_number=42,
        )
        encoded = ack.encode()
        decoded = ReadRangeACK.decode(encoded)
        assert decoded.result_flags.more_items is True
        assert decoded.item_count == 10
        assert decoded.first_sequence_number == 42

    def test_encode_decode_with_array_index(self):
        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 5),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            result_flags=ResultFlags(first_item=True, last_item=True),
            item_count=1,
            item_data=b"\xc4\x00\x00\x00\x01",
            property_array_index=2,
        )
        encoded = ack.encode()
        decoded = ReadRangeACK.decode(encoded)
        assert decoded.property_array_index == 2
        assert decoded.item_count == 1

    def test_encode_decode_empty_data(self):
        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            result_flags=ResultFlags(first_item=True, last_item=True),
            item_count=0,
            item_data=b"",
        )
        encoded = ack.encode()
        decoded = ReadRangeACK.decode(encoded)
        assert decoded.item_count == 0
        assert decoded.item_data == b""
