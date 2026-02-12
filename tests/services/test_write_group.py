"""Tests for WriteGroup service."""

from bac_py.encoding.primitives import encode_application_real, encode_application_unsigned
from bac_py.services.write_group import GroupChannelValue, WriteGroupRequest


class TestGroupChannelValue:
    def test_encode_decode_minimal(self):
        gcv = GroupChannelValue(
            channel=1,
            value=encode_application_unsigned(100),
        )
        encoded = gcv.encode()
        decoded, _ = GroupChannelValue.decode(memoryview(encoded), 0)
        assert decoded.channel == 1
        assert decoded.value == encode_application_unsigned(100)
        assert decoded.overriding_priority is None

    def test_encode_decode_with_priority(self):
        gcv = GroupChannelValue(
            channel=5,
            value=encode_application_real(72.5),
            overriding_priority=8,
        )
        encoded = gcv.encode()
        decoded, _ = GroupChannelValue.decode(memoryview(encoded), 0)
        assert decoded.channel == 5
        assert decoded.value == encode_application_real(72.5)
        assert decoded.overriding_priority == 8


class TestWriteGroupRequest:
    def test_round_trip_single_channel(self):
        request = WriteGroupRequest(
            group_number=1,
            write_priority=8,
            change_list=[
                GroupChannelValue(
                    channel=1,
                    value=encode_application_unsigned(50),
                ),
            ],
        )
        encoded = request.encode()
        decoded = WriteGroupRequest.decode(encoded)
        assert decoded.group_number == 1
        assert decoded.write_priority == 8
        assert len(decoded.change_list) == 1
        assert decoded.change_list[0].channel == 1

    def test_round_trip_multiple_channels(self):
        request = WriteGroupRequest(
            group_number=42,
            write_priority=10,
            change_list=[
                GroupChannelValue(
                    channel=1,
                    value=encode_application_real(72.5),
                ),
                GroupChannelValue(
                    channel=2,
                    value=encode_application_real(23.0),
                    overriding_priority=4,
                ),
                GroupChannelValue(
                    channel=3,
                    value=encode_application_unsigned(1),
                ),
            ],
        )
        encoded = request.encode()
        decoded = WriteGroupRequest.decode(encoded)
        assert decoded.group_number == 42
        assert decoded.write_priority == 10
        assert len(decoded.change_list) == 3
        assert decoded.change_list[0].channel == 1
        assert decoded.change_list[0].value == encode_application_real(72.5)
        assert decoded.change_list[1].channel == 2
        assert decoded.change_list[1].overriding_priority == 4
        assert decoded.change_list[2].channel == 3

    def test_round_trip_large_group_number(self):
        request = WriteGroupRequest(
            group_number=0xFFFFFFFF,
            write_priority=16,
            change_list=[
                GroupChannelValue(
                    channel=65535,
                    value=encode_application_unsigned(0),
                ),
            ],
        )
        encoded = request.encode()
        decoded = WriteGroupRequest.decode(encoded)
        assert decoded.group_number == 0xFFFFFFFF
        assert decoded.write_priority == 16
        assert decoded.change_list[0].channel == 65535
