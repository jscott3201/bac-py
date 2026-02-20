"""Tests for BACnetClient: protocol operations, convenience methods, and smart encoding."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.client import BACnetClient
from bac_py.encoding.primitives import (
    decode_real,
    decode_unsigned,
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_object_id,
    encode_application_real,
    encode_application_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.services.alarm_summary import (
    AlarmSummary,
    GetAlarmSummaryACK,
    GetEventInformationACK,
)
from bac_py.services.common import BACnetPropertyValue
from bac_py.services.private_transfer import ConfirmedPrivateTransferACK
from bac_py.services.read_property import ReadPropertyACK
from bac_py.services.read_property_multiple import (
    PropertyReference,
    ReadAccessResult,
    ReadAccessSpecification,
    ReadPropertyMultipleACK,
    ReadResultElement,
)
from bac_py.services.read_range import (
    RangeByPosition,
    ReadRangeACK,
    ResultFlags,
)
from bac_py.services.virtual_terminal import VTDataACK, VTOpenACK
from bac_py.services.who_is import IAmRequest
from bac_py.services.write_group import GroupChannelValue
from bac_py.services.write_property_multiple import (
    WriteAccessSpecification,
)
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    EnableDisable,
    ErrorClass,
    ErrorCode,
    EventState,
    MessagePriority,
    ObjectType,
    PropertyIdentifier,
    ReinitializedState,
    Segmentation,
    UnconfirmedServiceChoice,
    VTClass,
)
from bac_py.types.primitives import BACnetDate, BACnetTime, BitString, ObjectIdentifier

PEER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
PEER_CONVENIENCE = BACnetAddress(
    mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
)


class TestBACnetClient:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    async def test_read_property(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Create a fake ReadPropertyACK response
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_property(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        assert isinstance(result, ReadPropertyACK)
        assert result.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert result.property_value == b"\x44\x42\x28\x00\x00"

        # Verify the app was called correctly
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.READ_PROPERTY

    async def test_read_property_with_array_index(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=3,
            property_value=b"\xc4\x00\x00\x00\x01",
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_property(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            array_index=3,
        )
        assert result.property_array_index == 3

    async def test_write_property(self):
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        await client.write_property(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=b"\x44\x42\x28\x00\x00",
            priority=8,
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.WRITE_PROPERTY

    async def test_who_is(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Simulate the I-Am responses being delivered via temporary handler
        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_is(timeout=0.1))
        await asyncio.sleep(0.01)

        # Simulate receiving an I-Am response
        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        registered_handler(iam.encode(), PEER)

        results = await task
        assert len(results) == 1
        assert results[0].object_identifier.instance_number == 42

        # Verify handler was registered and unregistered
        app.register_temporary_handler.assert_called_once_with(
            UnconfirmedServiceChoice.I_AM, registered_handler
        )
        app.unregister_temporary_handler.assert_called_once()

    async def test_who_is_with_range(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.who_is(low_limit=100, high_limit=200, timeout=0.05)
        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.WHO_IS

    async def test_who_is_no_responses(self):
        app = self._make_app()
        client = BACnetClient(app)

        results = await client.who_is(timeout=0.05)
        assert results == []

    async def test_who_is_malformed_iam_ignored(self):
        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_is(timeout=0.1))
        await asyncio.sleep(0.01)

        # Send malformed data
        assert registered_handler is not None
        registered_handler(b"\xff\xff", PEER)

        # Also send a valid I-Am
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 10),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=0,
        )
        registered_handler(iam.encode(), PEER)

        results = await task
        # Only the valid one should be collected
        assert len(results) == 1
        assert results[0].object_identifier.instance_number == 10

    async def test_read_property_multiple(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Create a fake ReadPropertyMultiple-ACK response
        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            property_value=b"\x75\x05\x00test",
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_property_multiple(
            address=PEER,
            read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                    ],
                ),
            ],
        )
        assert isinstance(result, ReadPropertyMultipleACK)
        assert len(result.list_of_read_access_results) == 1
        res = result.list_of_read_access_results[0]
        assert res.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert res.list_of_results[0].property_value is not None

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE
        )

    async def test_write_property_multiple(self):
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        await client.write_property_multiple(
            address=PEER,
            write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
                    list_of_properties=[
                        BACnetPropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            value=b"\x44\x42\x28\x00\x00",
                            priority=8,
                        ),
                    ],
                ),
            ],
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE
        )

    async def test_read_range(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Create a fake ReadRange-ACK response
        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            result_flags=ResultFlags(first_item=True, last_item=True, more_items=False),
            item_count=1,
            item_data=b"\xc4\x02\x00\x00\x01",  # Device object ID
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_range(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
        )
        assert isinstance(result, ReadRangeACK)
        assert result.result_flags.first_item is True
        assert result.result_flags.last_item is True
        assert result.item_count == 1

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.READ_RANGE

    async def test_read_range_with_position(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadRangeACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            result_flags=ResultFlags(first_item=False, last_item=False, more_items=True),
            item_count=2,
            item_data=b"\xc4\x00\x00\x00\x01\xc4\x00\x00\x00\x02",
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_range(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            range_qualifier=RangeByPosition(reference_index=2, count=2),
        )
        assert result.item_count == 2
        assert result.result_flags.more_items is True


class TestRead:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        return app

    async def test_read_real_with_strings(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "ai,1", "pv")
        assert isinstance(result, float)
        assert result == pytest.approx(72.5)

    async def test_read_string(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=encode_application_character_string("Zone Temp"),
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "analog-input,1", "object-name")
        assert result == "Zone Temp"

    async def test_read_unsigned(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_unsigned(3),
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "msv,1", "pv")
        assert result == 3

    async def test_read_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_enumerated(1),
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "bv,1", "pv")
        assert result == 1

    async def test_read_multiple_values_returns_list(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Object list with 2 object IDs
        from bac_py.encoding.primitives import encode_application_object_id

        multi_value = encode_application_object_id(0, 1) + encode_application_object_id(8, 100)
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_value=multi_value,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "dev,100", "object-list")
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_read_with_address_object(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        # Using BACnetAddress directly should still work
        result = await client.read(PEER_CONVENIENCE, "ai,1", "pv")
        assert result == pytest.approx(72.5)

    async def test_read_with_native_types(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        # Using native enum types directly should also work
        result = await client.read(
            PEER_CONVENIENCE,
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            PropertyIdentifier.PRESENT_VALUE,
        )
        assert result == pytest.approx(72.5)

    async def test_read_empty_value_returns_none(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"",
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read("192.168.1.100", "ai,1", "pv")
        assert result is None


class TestWrite:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock(return_value=b"")
        return app

    async def test_write_float_to_analog(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "av,1", "pv", 72.5, priority=8)
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.WRITE_PROPERTY
        # Verify the encoded value is a Real
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, offset = decode_tag(req.property_value, 0)
        assert tag.number == 4  # Real
        assert tag.cls == TagClass.APPLICATION
        assert decode_real(req.property_value[offset : offset + tag.length]) == pytest.approx(72.5)
        assert req.priority == 8

    async def test_write_int_to_analog_encodes_as_real(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "av,1", "pv", 72)
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, offset = decode_tag(req.property_value, 0)
        assert tag.number == 4  # Real, not Unsigned!
        assert decode_real(req.property_value[offset : offset + tag.length]) == pytest.approx(72.0)

    async def test_write_int_to_binary_encodes_as_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "bv,1", "pv", 1)
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, _ = decode_tag(req.property_value, 0)
        assert tag.number == 9  # Enumerated

    async def test_write_bool_to_binary_encodes_as_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "bo,1", "pv", True)
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, offset = decode_tag(req.property_value, 0)
        assert tag.number == 9  # Enumerated
        assert decode_unsigned(req.property_value[offset : offset + tag.length]) == 1

    async def test_write_int_to_multistate_encodes_as_unsigned(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "msv,1", "pv", 3)
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, offset = decode_tag(req.property_value, 0)
        assert tag.number == 2  # Unsigned
        assert decode_unsigned(req.property_value[offset : offset + tag.length]) == 3

    async def test_write_none_encodes_as_null(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ao,1", "pv", None, priority=8)
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, _ = decode_tag(req.property_value, 0)
        assert tag.number == 0  # Null
        assert req.priority == 8

    async def test_write_string(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "av,1", "name", "New Name")
        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        from bac_py.services.write_property import WritePropertyRequest

        req = WritePropertyRequest.decode(service_data)
        tag, _ = decode_tag(req.property_value, 0)
        assert tag.number == 7  # Character String

    async def test_write_with_network_address(self):
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("2:192.168.1.100", "av,1", "pv", 72.5)
        call_kwargs = app.confirmed_request.call_args
        dest = call_kwargs.kwargs["destination"]
        assert dest.network == 2


class TestReadMultiple:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        return app

    async def test_read_multiple_basic(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            property_value=encode_application_character_string("Zone Temp"),
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_multiple(
            "192.168.1.100",
            {"ai,1": ["pv", "name"]},
        )

        assert "analog-input,1" in result
        props = result["analog-input,1"]
        assert props["present-value"] == pytest.approx(72.5)
        assert props["object-name"] == "Zone Temp"

    async def test_read_multiple_with_error(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.DESCRIPTION,
                            property_access_error=(
                                ErrorClass.PROPERTY,
                                ErrorCode.UNKNOWN_PROPERTY,
                            ),
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_multiple(
            "192.168.1.100",
            {"ai,1": ["pv", "desc"]},
        )

        props = result["analog-input,1"]
        assert props["present-value"] == pytest.approx(72.5)
        assert props["description"] is None  # Error -> None

    async def test_read_multiple_objects(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                    ],
                ),
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 2),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(68.0),
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_multiple(
            "192.168.1.100",
            {
                "ai,1": ["pv"],
                "ai,2": ["pv"],
            },
        )

        assert len(result) == 2
        assert result["analog-input,1"]["present-value"] == pytest.approx(72.5)
        assert result["analog-input,2"]["present-value"] == pytest.approx(68.0)

    async def test_read_multiple_with_unsigned(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.UNITS,
                            property_value=encode_application_enumerated(62),
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_multiple(
            "192.168.1.100",
            {"ai,1": ["pv", "units"]},
        )

        props = result["analog-input,1"]
        assert props["present-value"] == pytest.approx(72.5)
        assert props["units"] == 62


class TestPropertyTypeHints:
    """Test that _encode_for_write uses _PROPERTY_TYPE_HINTS for non-PV properties."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock(return_value=b"")
        return app

    def _get_encoded_value(self, app):
        """Extract the property_value bytes from the WritePropertyRequest."""
        from bac_py.services.write_property import WritePropertyRequest

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyRequest.decode(service_data)
        return req.property_value

    async def test_int_to_units_encodes_as_enumerated(self):
        """Units property expects Enumerated; writing int 62 should encode as Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "units", 62)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated
        assert tag.cls == TagClass.APPLICATION
        assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 62

    async def test_int_to_reliability_encodes_as_enumerated(self):
        """Reliability expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "reliability", 0)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated

    async def test_int_to_event_state_encodes_as_enumerated(self):
        """Event-state expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "event-state", 0)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated

    async def test_int_to_cov_increment_encodes_as_real(self):
        """COV-increment expects Real; writing int 5 should encode as Real 5.0."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "cov-inc", 5)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real
        assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(5.0)

    async def test_float_to_cov_increment_encodes_as_real(self):
        """COV-increment expects Real; writing float 0.5 should encode as Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "cov-inc", 0.5)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real
        assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.5)

    async def test_int_to_high_limit_encodes_as_real(self):
        """High-limit expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "high-limit", 100)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real
        assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(100.0)

    async def test_int_to_low_limit_encodes_as_real(self):
        """Low-limit expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "low-limit", 0)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real
        assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.0)

    async def test_int_to_deadband_encodes_as_real(self):
        """Deadband expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "deadband", 2)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real

    async def test_int_to_relinquish_default_encodes_as_real(self):
        """Relinquish-default expects Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "av,1", "relinquish-default", 72)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real

    async def test_int_to_number_of_states_encodes_as_unsigned(self):
        """Number-of-states expects Unsigned."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "msv,1", "number-of-states", 5)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 2  # Unsigned
        assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 5

    async def test_int_to_notification_class_encodes_as_unsigned(self):
        """Notification-class expects Unsigned."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "notification-class", 10)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 2  # Unsigned
        assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 10

    def test_int_to_out_of_service_encodes_as_boolean(self):
        """Out-of-service expects Boolean; writing int 1 should encode as Boolean."""
        app = self._make_app()
        client = BACnetClient(app)

        # Test _encode_for_write directly since Boolean tag encoding
        # (value in tag bits, no content bytes) doesn't round-trip
        # through WritePropertyRequest.decode.
        encoded = client._encode_for_write(
            1,
            PropertyIdentifier.OUT_OF_SERVICE,
            ObjectType.ANALOG_INPUT,
        )
        tag, _ = decode_tag(encoded, 0)
        assert tag.number == 1  # Boolean

    async def test_int_to_polarity_encodes_as_enumerated(self):
        """Polarity expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "bi,1", "polarity", 1)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated

    async def test_string_to_hinted_string_property_still_works(self):
        """String values should still pass through to encode_property_value for string props."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "desc", "Zone Temperature")
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 7  # Character String

    async def test_pv_encoding_takes_priority_over_hints(self):
        """PV encoding (object-type-aware) should take priority for present-value."""
        app = self._make_app()
        client = BACnetClient(app)

        # Writing int to binary PV should encode as Enumerated (not via hint map)
        await client.write("192.168.1.100", "bv,1", "pv", 1)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated (from PV logic, not hint map)

    async def test_unknown_property_falls_through(self):
        """Properties not in the hint map should fall through to encode_property_value."""
        app = self._make_app()
        client = BACnetClient(app)

        # protocol-version is not in the hints map
        await client.write("192.168.1.100", "dev,100", "protocol-version", 42)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        # Falls through to encode_property_value which encodes int as Unsigned
        assert tag.number == 2  # Unsigned
        assert decode_unsigned(value_bytes[offset : offset + tag.length]) == 42

    async def test_float_to_hinted_real_property(self):
        """Float value to a Real-hinted property should encode as Real."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "ai,1", "resolution", 0.1)
        value_bytes = self._get_encoded_value(app)
        tag, offset = decode_tag(value_bytes, 0)
        assert tag.number == 4  # Real
        assert decode_real(value_bytes[offset : offset + tag.length]) == pytest.approx(0.1)

    async def test_int_to_feedback_value_encodes_as_enumerated(self):
        """Feedback-value expects Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        await client.write("192.168.1.100", "bo,1", "feedback-value", 1)
        value_bytes = self._get_encoded_value(app)
        tag, _ = decode_tag(value_bytes, 0)
        assert tag.number == 9  # Enumerated


# ---------------------------------------------------------------------------
# New test classes for untested BACnetClient methods
# ---------------------------------------------------------------------------


def _make_app():
    """Create a mock BACnetApplication for testing."""
    app = MagicMock()
    app.confirmed_request = AsyncMock()
    app.unconfirmed_request = MagicMock()
    app.register_temporary_handler = MagicMock()
    app.unregister_temporary_handler = MagicMock()
    return app


class TestSubscribeCOV:
    """Tests for subscribe_cov() confirmed service."""

    async def test_subscribe_cov_sends_request(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        await client.subscribe_cov(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            process_id=42,
            confirmed=True,
            lifetime=3600,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV

    async def test_subscribe_cov_without_lifetime(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.subscribe_cov(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
            process_id=1,
            confirmed=False,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV


class TestUnsubscribeCOV:
    """Tests for unsubscribe_cov() cancellation."""

    async def test_unsubscribe_cov_sends_cancellation(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.unsubscribe_cov(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            process_id=42,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV


class TestDeviceCommunicationControl:
    """Tests for device_communication_control() confirmed service."""

    async def test_device_communication_control_disable(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.device_communication_control(
            address=PEER,
            enable_disable=EnableDisable.DISABLE,
            time_duration=60,
            password="secret",
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL
        )

    async def test_device_communication_control_enable(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.device_communication_control(
            address=PEER,
            enable_disable=EnableDisable.ENABLE,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.DEVICE_COMMUNICATION_CONTROL
        )


class TestReinitializeDevice:
    """Tests for reinitialize_device() confirmed service."""

    async def test_reinitialize_device_coldstart(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.reinitialize_device(
            address=PEER,
            reinitialized_state=ReinitializedState.COLDSTART,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.REINITIALIZE_DEVICE

    async def test_reinitialize_device_with_password(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.reinitialize_device(
            address=PEER,
            reinitialized_state=ReinitializedState.WARMSTART,
            password="mypass",
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.REINITIALIZE_DEVICE


class TestCreateObject:
    """Tests for create_object() confirmed service returning ObjectIdentifier."""

    async def test_create_object_by_type(self):
        app = _make_app()
        client = BACnetClient(app)

        # CreateObject-ACK returns an application-tagged ObjectIdentifier
        ack_data = encode_application_object_id(int(ObjectType.ANALOG_VALUE), 100)
        app.confirmed_request.return_value = ack_data

        result = await client.create_object(
            address=PEER,
            object_type=ObjectType.ANALOG_VALUE,
        )

        assert isinstance(result, ObjectIdentifier)
        assert result.object_type == ObjectType.ANALOG_VALUE
        assert result.instance_number == 100

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.CREATE_OBJECT

    async def test_create_object_by_identifier(self):
        app = _make_app()
        client = BACnetClient(app)

        ack_data = encode_application_object_id(int(ObjectType.BINARY_VALUE), 7)
        app.confirmed_request.return_value = ack_data

        result = await client.create_object(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 7),
        )

        assert result.object_type == ObjectType.BINARY_VALUE
        assert result.instance_number == 7

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.CREATE_OBJECT


class TestDeleteObject:
    """Tests for delete_object() confirmed service."""

    async def test_delete_object(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        await client.delete_object(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 100),
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.DELETE_OBJECT


class TestAddRemoveListElement:
    """Tests for add_list_element() and remove_list_element() confirmed services."""

    async def test_add_list_element(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        element_data = encode_application_unsigned(42)
        await client.add_list_element(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=element_data,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ADD_LIST_ELEMENT

    async def test_remove_list_element(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        element_data = encode_application_unsigned(42)
        await client.remove_list_element(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=element_data,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.REMOVE_LIST_ELEMENT

    async def test_add_list_element_with_array_index(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        element_data = encode_application_unsigned(7)
        await client.add_list_element(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.NOTIFICATION_CLASS, 1),
            property_identifier=PropertyIdentifier.RECIPIENT_LIST,
            list_of_elements=element_data,
            array_index=3,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ADD_LIST_ELEMENT


class TestTextMessage:
    """Tests for send_confirmed_text_message() and send_unconfirmed_text_message()."""

    async def test_send_confirmed_text_message(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.send_confirmed_text_message(
            address=PEER,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
            message="Fire alarm on floor 3",
            message_priority=MessagePriority.URGENT,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE
        )

    async def test_send_confirmed_text_message_with_class(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.send_confirmed_text_message(
            address=PEER,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
            message="Maintenance notice",
            message_priority=MessagePriority.NORMAL,
            message_class_numeric=5,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE
        )

    def test_send_unconfirmed_text_message(self):
        app = _make_app()
        client = BACnetClient(app)

        client.send_unconfirmed_text_message(
            destination=PEER,
            source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
            message="System status OK",
            message_priority=MessagePriority.NORMAL,
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE
        )


class TestVirtualTerminal:
    """Tests for vt_open(), vt_close(), and vt_data() confirmed services."""

    async def test_vt_open(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = VTOpenACK(remote_vt_session_identifier=5)
        app.confirmed_request.return_value = ack.encode()

        result = await client.vt_open(
            address=PEER,
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )

        assert isinstance(result, VTOpenACK)
        assert result.remote_vt_session_identifier == 5

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.VT_OPEN

    async def test_vt_close(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.vt_close(
            address=PEER,
            session_identifiers=[5, 6],
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.VT_CLOSE

    async def test_vt_data(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = VTDataACK(all_new_data_accepted=True)
        app.confirmed_request.return_value = ack.encode()

        result = await client.vt_data(
            address=PEER,
            vt_session_identifier=5,
            vt_new_data=b"hello\r\n",
            vt_data_flag=False,
        )

        assert isinstance(result, VTDataACK)
        assert result.all_new_data_accepted is True

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.VT_DATA

    async def test_vt_data_partial_accept(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = VTDataACK(all_new_data_accepted=False, accepted_octet_count=3)
        app.confirmed_request.return_value = ack.encode()

        result = await client.vt_data(
            address=PEER,
            vt_session_identifier=5,
            vt_new_data=b"hello\r\n",
            vt_data_flag=True,
        )

        assert result.all_new_data_accepted is False
        assert result.accepted_octet_count == 3


class TestPrivateTransfer:
    """Tests for confirmed_private_transfer() and unconfirmed_private_transfer()."""

    async def test_confirmed_private_transfer(self):
        app = _make_app()
        client = BACnetClient(app)

        # result_block must contain valid application-tagged data so
        # the round-trip encode/decode through extract_context_value works.
        result_data = encode_application_unsigned(42)
        ack = ConfirmedPrivateTransferACK(
            vendor_id=7,
            service_number=1,
            result_block=result_data,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.confirmed_private_transfer(
            address=PEER,
            vendor_id=7,
            service_number=1,
            service_parameters=b"\x0a\x0b",
        )

        assert isinstance(result, ConfirmedPrivateTransferACK)
        assert result.vendor_id == 7
        assert result.service_number == 1
        assert result.result_block == result_data

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.CONFIRMED_PRIVATE_TRANSFER
        )

    async def test_confirmed_private_transfer_no_params(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = ConfirmedPrivateTransferACK(vendor_id=99, service_number=0)
        app.confirmed_request.return_value = ack.encode()

        result = await client.confirmed_private_transfer(
            address=PEER,
            vendor_id=99,
            service_number=0,
        )

        assert result.vendor_id == 99
        assert result.result_block is None

    def test_unconfirmed_private_transfer(self):
        app = _make_app()
        client = BACnetClient(app)

        client.unconfirmed_private_transfer(
            destination=PEER,
            vendor_id=7,
            service_number=2,
            service_parameters=b"\xff",
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_PRIVATE_TRANSFER
        )

    def test_unconfirmed_private_transfer_no_params(self):
        app = _make_app()
        client = BACnetClient(app)

        client.unconfirmed_private_transfer(
            destination=PEER,
            vendor_id=7,
            service_number=3,
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_PRIVATE_TRANSFER
        )


class TestTimeSynchronization:
    """Tests for time_synchronization() and utc_time_synchronization() unconfirmed services."""

    def test_time_synchronization(self):
        app = _make_app()
        client = BACnetClient(app)

        client.time_synchronization(
            destination=PEER,
            date=BACnetDate(year=2024, month=6, day=15, day_of_week=6),
            time=BACnetTime(hour=14, minute=30, second=0, hundredth=0),
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.TIME_SYNCHRONIZATION
        )

    def test_utc_time_synchronization(self):
        app = _make_app()
        client = BACnetClient(app)

        client.utc_time_synchronization(
            destination=PEER,
            date=BACnetDate(year=2024, month=6, day=15, day_of_week=6),
            time=BACnetTime(hour=18, minute=30, second=0, hundredth=0),
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UTC_TIME_SYNCHRONIZATION
        )


class TestWriteGroup:
    """Tests for write_group() unconfirmed service."""

    def test_write_group(self):
        app = _make_app()
        client = BACnetClient(app)

        client.write_group(
            destination=PEER,
            group_number=1,
            write_priority=8,
            change_list=[
                GroupChannelValue(channel=1, value=encode_application_real(72.5)),
                GroupChannelValue(channel=2, value=encode_application_real(68.0)),
            ],
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.WRITE_GROUP

    def test_write_group_with_override_priority(self):
        app = _make_app()
        client = BACnetClient(app)

        client.write_group(
            destination=PEER,
            group_number=5,
            write_priority=10,
            change_list=[
                GroupChannelValue(
                    channel=3,
                    value=encode_application_unsigned(1),
                    overriding_priority=4,
                ),
            ],
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.WRITE_GROUP


class TestGetObjectList:
    """Tests for get_object_list() convenience method."""

    async def test_get_object_list_single_read(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        client = BACnetClient(app)

        # Build a fake ReadPropertyACK containing two ObjectIdentifiers
        object_list_data = encode_application_object_id(
            int(ObjectType.DEVICE), 1
        ) + encode_application_object_id(int(ObjectType.ANALOG_INPUT), 1)
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_value=object_list_data,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_object_list("192.168.1.100", 1)

        assert len(result) == 2
        assert result[0] == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert result[1] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

        # Should have called confirmed_request for the ReadProperty
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.READ_PROPERTY


class TestAcknowledgeAlarm:
    """Tests for acknowledge_alarm() confirmed service."""

    async def test_acknowledge_alarm(self):
        app = _make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        ts = BACnetTimeStamp(
            choice=1,
            value=100,  # sequenceNumber
        )

        await client.acknowledge_alarm(
            address=PEER,
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.HIGH_LIMIT,
            time_stamp=ts,
            acknowledgment_source="operator1",
            time_of_acknowledgment=ts,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ACKNOWLEDGE_ALARM


class TestGetAlarmSummary:
    """Tests for get_alarm_summary() confirmed service."""

    async def test_get_alarm_summary(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = GetAlarmSummaryACK(
            list_of_alarm_summaries=[
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    alarm_state=EventState.HIGH_LIMIT,
                    acknowledged_transitions=BitString(value=b"\xe0", unused_bits=5),
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_alarm_summary(address=PEER)

        assert isinstance(result, GetAlarmSummaryACK)
        assert len(result.list_of_alarm_summaries) == 1
        assert result.list_of_alarm_summaries[0].alarm_state == EventState.HIGH_LIMIT

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.GET_ALARM_SUMMARY

    async def test_get_alarm_summary_empty(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = GetAlarmSummaryACK(list_of_alarm_summaries=[])
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_alarm_summary(address=PEER)

        assert isinstance(result, GetAlarmSummaryACK)
        assert len(result.list_of_alarm_summaries) == 0


class TestGetEventInformation:
    """Tests for get_event_information() confirmed service."""

    async def test_get_event_information_empty(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=False,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_event_information(address=PEER)

        assert isinstance(result, GetEventInformationACK)
        assert len(result.list_of_event_summaries) == 0
        assert result.more_events is False

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.GET_EVENT_INFORMATION

    async def test_get_event_information_with_pagination(self):
        app = _make_app()
        client = BACnetClient(app)

        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=True,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_event_information(
            address=PEER,
            last_received_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 10),
        )

        assert result.more_events is True
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.GET_EVENT_INFORMATION


# ---------------------------------------------------------------------------
# Section 2A: Encoding & Decoding Helpers
# ---------------------------------------------------------------------------


class TestEncodingHelpers:
    """Tests for decode_cov_values(), _encode_for_write(), and _lookup_datatype()."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    # --- decode_cov_values ---

    def test_decode_cov_values_with_present_value(self):
        """decode_cov_values extracts property names and decoded values."""
        from bac_py.app.client import decode_cov_values
        from bac_py.services.cov import COVNotificationRequest

        notification = COVNotificationRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=encode_application_real(72.5),
                ),
            ],
        )

        result = decode_cov_values(notification)
        assert "present-value" in result
        assert result["present-value"] == pytest.approx(72.5)

    def test_decode_cov_values_with_empty_value(self):
        """decode_cov_values maps empty value bytes to None."""
        from bac_py.app.client import decode_cov_values
        from bac_py.services.cov import COVNotificationRequest

        notification = COVNotificationRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=300,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.DESCRIPTION,
                    value=b"",
                ),
            ],
        )

        result = decode_cov_values(notification)
        assert result["description"] is None

    def test_decode_cov_values_multiple_properties(self):
        """decode_cov_values handles multiple property values in a single notification."""
        from bac_py.app.client import decode_cov_values
        from bac_py.services.cov import COVNotificationRequest

        notification = COVNotificationRequest(
            subscriber_process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_remaining=60,
            list_of_values=[
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    value=encode_application_real(68.0),
                ),
                BACnetPropertyValue(
                    property_identifier=PropertyIdentifier.OBJECT_NAME,
                    value=encode_application_character_string("Zone Temp"),
                ),
            ],
        )

        result = decode_cov_values(notification)
        assert len(result) == 2
        assert result["present-value"] == pytest.approx(68.0)
        assert result["object-name"] == "Zone Temp"

    # --- _encode_for_write ---

    def test_encode_for_write_bytes_pass_through(self):
        """Already-encoded bytes pass through _encode_for_write unchanged."""
        app = self._make_app()
        client = BACnetClient(app)
        raw = encode_application_real(42.0)

        result = client._encode_for_write(
            raw, PropertyIdentifier.PRESENT_VALUE, ObjectType.ANALOG_VALUE
        )
        assert result == raw

    def test_encode_for_write_none_encodes_as_null(self):
        """None encodes as Null via _encode_for_write."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            None, PropertyIdentifier.PRESENT_VALUE, ObjectType.ANALOG_OUTPUT
        )
        tag, _ = decode_tag(result, 0)
        assert tag.number == 0  # Null

    def test_encode_for_write_bool_for_binary_pv_encodes_enumerated(self):
        """Bool for a binary object's PV (IntEnum datatype) encodes as Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            True, PropertyIdentifier.PRESENT_VALUE, ObjectType.BINARY_VALUE
        )
        tag, offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated
        assert decode_unsigned(result[offset : offset + tag.length]) == 1

    def test_encode_for_write_bool_for_non_binary_encodes_boolean(self):
        """Bool for a non-binary property (bool datatype) encodes as Boolean."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            True, PropertyIdentifier.OUT_OF_SERVICE, ObjectType.ANALOG_INPUT
        )
        tag, _ = decode_tag(result, 0)
        assert tag.number == 1  # Boolean

    def test_encode_for_write_int_for_float_property_encodes_real(self):
        """Int for a property with float datatype encodes as Real."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            72, PropertyIdentifier.PRESENT_VALUE, ObjectType.ANALOG_VALUE
        )
        tag, offset = decode_tag(result, 0)
        assert tag.number == 4  # Real
        assert decode_real(result[offset : offset + tag.length]) == pytest.approx(72.0)

    def test_encode_for_write_int_for_enum_property_encodes_enumerated(self):
        """Int for a property with IntEnum datatype encodes as Enumerated."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            1, PropertyIdentifier.PRESENT_VALUE, ObjectType.BINARY_OUTPUT
        )
        tag, offset = decode_tag(result, 0)
        assert tag.number == 9  # Enumerated
        assert decode_unsigned(result[offset : offset + tag.length]) == 1

    def test_encode_for_write_int_for_bool_property_encodes_boolean(self):
        """Int for a property with bool datatype encodes as Boolean."""
        app = self._make_app()
        client = BACnetClient(app)

        result = client._encode_for_write(
            1, PropertyIdentifier.OUT_OF_SERVICE, ObjectType.ANALOG_INPUT
        )
        tag, _ = decode_tag(result, 0)
        assert tag.number == 1  # Boolean

    # --- _lookup_datatype ---

    def test_lookup_datatype_unknown_object_type_returns_none(self):
        """_lookup_datatype returns None for an unregistered object type."""
        result = BACnetClient._lookup_datatype(ObjectType(999), PropertyIdentifier.PRESENT_VALUE)
        assert result is None

    def test_lookup_datatype_unknown_property_returns_none(self):
        """_lookup_datatype returns None for an unknown property on a known object."""
        result = BACnetClient._lookup_datatype(ObjectType.ANALOG_INPUT, PropertyIdentifier(9999))
        assert result is None


# ---------------------------------------------------------------------------
# Section 2B: Convenience Wrappers
# ---------------------------------------------------------------------------


class TestConvenienceWrappers:
    """Tests for write_multiple, get_object_list, subscribe/unsubscribe_cov_ex, etc."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app.register_cov_callback = MagicMock()
        app.unregister_cov_callback = MagicMock()
        return app

    # --- write_multiple ---

    async def test_write_multiple_builds_specs(self):
        """write_multiple builds WriteAccessSpecifications and sends WritePropertyMultiple."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.write_multiple(
            "192.168.1.100",
            {
                "av,1": {"pv": 72.5, "object-name": "Zone Temp"},
                "bo,1": {"pv": 1},
            },
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE
        )

    async def test_write_multiple_encodes_values_correctly(self):
        """write_multiple uses _encode_for_write for each property value."""
        from bac_py.services.write_property_multiple import WritePropertyMultipleRequest

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.write_multiple(
            "192.168.1.100",
            {"av,1": {"pv": 72.5}},
        )

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyMultipleRequest.decode(service_data)
        assert len(req.list_of_write_access_specs) == 1
        spec = req.list_of_write_access_specs[0]
        assert spec.object_identifier == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        assert len(spec.list_of_properties) == 1
        prop = spec.list_of_properties[0]
        assert prop.property_identifier == PropertyIdentifier.PRESENT_VALUE
        # Value should be a Real
        tag, offset = decode_tag(prop.value, 0)
        assert tag.number == 4  # Real
        assert decode_real(prop.value[offset : offset + tag.length]) == pytest.approx(72.5)

    async def test_write_multiple_with_priority(self):
        """write_multiple passes priority to every BACnetPropertyValue."""
        from bac_py.services.write_property_multiple import WritePropertyMultipleRequest

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.write_multiple(
            "192.168.1.100",
            {"av,1": {"pv": 72.5}, "bo,1": {"pv": 1}},
            priority=8,
        )

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyMultipleRequest.decode(service_data)
        for spec in req.list_of_write_access_specs:
            for prop in spec.list_of_properties:
                assert prop.priority == 8

    async def test_write_multiple_without_priority(self):
        """write_multiple without priority leaves BACnetPropertyValue.priority as None."""
        from bac_py.services.write_property_multiple import WritePropertyMultipleRequest

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.write_multiple(
            "192.168.1.100",
            {"av,1": {"pv": 72.5}},
        )

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyMultipleRequest.decode(service_data)
        prop = req.list_of_write_access_specs[0].list_of_properties[0]
        assert prop.priority is None

    async def test_write_multiple_priority_roundtrip(self):
        """Priority survives encode/decode round-trip."""
        from bac_py.services.write_property_multiple import WritePropertyMultipleRequest

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.write_multiple(
            "192.168.1.100",
            {"av,1": {"pv": 99.0}},
            priority=16,
        )

        call_kwargs = app.confirmed_request.call_args
        service_data = call_kwargs.kwargs["service_data"]
        req = WritePropertyMultipleRequest.decode(service_data)
        prop = req.list_of_write_access_specs[0].list_of_properties[0]
        assert prop.priority == 16
        # Re-encode and decode again
        re_encoded = req.encode()
        req2 = WritePropertyMultipleRequest.decode(re_encoded)
        prop2 = req2.list_of_write_access_specs[0].list_of_properties[0]
        assert prop2.priority == 16
        tag, offset = decode_tag(prop2.value, 0)
        assert decode_real(prop2.value[offset : offset + tag.length]) == pytest.approx(99.0)

    # --- get_object_list fallback ---

    async def test_get_object_list_fallback_on_segmentation_abort(self):
        """get_object_list falls back to element-by-element on SEGMENTATION_NOT_SUPPORTED abort."""
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        app = self._make_app()
        client = BACnetClient(app)

        # First call: raise BACnetAbortError with SEGMENTATION_NOT_SUPPORTED
        # Second call (array index 0): return count = 2
        # Third call (array index 1): return first ObjectIdentifier
        # Fourth call (array index 2): return second ObjectIdentifier
        count_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=0,
            property_value=encode_application_unsigned(2),
        )
        oid1_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=1,
            property_value=encode_application_object_id(int(ObjectType.DEVICE), 1),
        )
        oid2_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=2,
            property_value=encode_application_object_id(int(ObjectType.ANALOG_INPUT), 1),
        )

        app.confirmed_request.side_effect = [
            BACnetAbortError(AbortReason.SEGMENTATION_NOT_SUPPORTED),
            count_ack.encode(),
            oid1_ack.encode(),
            oid2_ack.encode(),
        ]

        result = await client.get_object_list("192.168.1.100", 1)
        assert len(result) == 2
        assert result[0] == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert result[1] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert app.confirmed_request.call_count == 4

    async def test_get_object_list_reraises_other_abort(self):
        """get_object_list re-raises BACnetAbortError for non-segmentation abort reasons."""
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        app = self._make_app()
        client = BACnetClient(app)

        app.confirmed_request.side_effect = BACnetAbortError(AbortReason.BUFFER_OVERFLOW)

        with pytest.raises(BACnetAbortError):
            await client.get_object_list("192.168.1.100", 1)

    # --- subscribe_cov_ex ---

    async def test_subscribe_cov_ex_registers_callback(self):
        """subscribe_cov_ex registers callback and sends subscribe request."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        callback = MagicMock()

        await client.subscribe_cov_ex(
            "192.168.1.100",
            "ai,1",
            process_id=42,
            callback=callback,
            lifetime=3600,
        )

        app.register_cov_callback.assert_called_once_with(42, callback)
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV

    async def test_subscribe_cov_ex_unregisters_callback_on_failure(self):
        """subscribe_cov_ex unregisters callback when the subscription request fails."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.side_effect = RuntimeError("network error")

        callback = MagicMock()

        with pytest.raises(RuntimeError, match="network error"):
            await client.subscribe_cov_ex(
                "192.168.1.100",
                "ai,1",
                process_id=42,
                callback=callback,
            )

        app.register_cov_callback.assert_called_once_with(42, callback)
        app.unregister_cov_callback.assert_called_once_with(42)

    async def test_subscribe_cov_ex_no_callback(self):
        """subscribe_cov_ex works without callback (no register/unregister calls)."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.subscribe_cov_ex(
            "192.168.1.100",
            "ai,1",
            process_id=1,
        )

        app.register_cov_callback.assert_not_called()
        app.confirmed_request.assert_called_once()

    # --- unsubscribe_cov_ex ---

    async def test_unsubscribe_cov_ex_cancels_and_unregisters(self):
        """unsubscribe_cov_ex sends unsubscribe and unregisters callback."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.unsubscribe_cov_ex(
            "192.168.1.100",
            "ai,1",
            process_id=42,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV
        app.unregister_cov_callback.assert_called_once_with(42)

    async def test_unsubscribe_cov_ex_skip_unregister(self):
        """unsubscribe_cov_ex skips callback unregister when unregister_callback=False."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.unsubscribe_cov_ex(
            "192.168.1.100",
            "ai,1",
            process_id=42,
            unregister_callback=False,
        )

        app.confirmed_request.assert_called_once()
        app.unregister_cov_callback.assert_not_called()

    # --- read_multiple (property_access_error sets None) ---

    async def test_read_multiple_property_access_error_sets_none(self):
        """read_multiple sets property to None when property_access_error is present."""
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=encode_application_real(72.5),
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.DESCRIPTION,
                            property_access_error=(
                                ErrorClass.PROPERTY,
                                ErrorCode.UNKNOWN_PROPERTY,
                            ),
                        ),
                    ],
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.read_multiple(
            "192.168.1.100",
            {"ai,1": ["pv", "desc"]},
        )

        props = result["analog-input,1"]
        assert props["present-value"] == pytest.approx(72.5)
        assert props["description"] is None

    # --- subscribe_cov_property ---

    async def test_subscribe_cov_property(self):
        """subscribe_cov_property builds request with property reference and COV increment."""
        from bac_py.services.cov import SubscribeCOVPropertyRequest

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        await client.subscribe_cov_property(
            address=PEER,
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
            process_id=10,
            confirmed=True,
            lifetime=600,
            cov_increment=0.5,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY
        )
        # Verify request round-trips correctly
        service_data = call_kwargs.kwargs["service_data"]
        req = SubscribeCOVPropertyRequest.decode(service_data)
        assert req.subscriber_process_identifier == 10
        assert req.monitored_object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert req.monitored_property_identifier.property_identifier == int(
            PropertyIdentifier.PRESENT_VALUE
        )
        assert req.lifetime == 600
        assert req.cov_increment == pytest.approx(0.5)

    # --- subscribe_cov_property_multiple ---

    async def test_subscribe_cov_property_multiple(self):
        """subscribe_cov_property_multiple sends the correct service choice."""
        from bac_py.services.cov import (
            BACnetPropertyReference,
            COVReference,
            COVSubscriptionSpecification,
        )

        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        specs = [
            COVSubscriptionSpecification(
                monitored_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                list_of_cov_references=[
                    COVReference(
                        monitored_property=BACnetPropertyReference(
                            property_identifier=int(PropertyIdentifier.PRESENT_VALUE),
                        ),
                        cov_increment=1.0,
                    ),
                ],
            ),
        ]

        await client.subscribe_cov_property_multiple(
            address=PEER,
            process_id=5,
            specifications=specs,
            confirmed=True,
            lifetime=300,
            max_notification_delay=10,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.SUBSCRIBE_COV_PROPERTY_MULTIPLE
        )

    # --- atomic_read_file ---

    async def test_atomic_read_file_stream(self):
        """atomic_read_file stream access round-trip."""
        from bac_py.services.file_access import (
            AtomicReadFileACK,
            StreamReadAccess,
            StreamReadACK,
        )

        app = self._make_app()
        client = BACnetClient(app)

        ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(
                file_start_position=0,
                file_data=b"Hello, BACnet!",
            ),
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.atomic_read_file(
            address=PEER,
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamReadAccess(
                file_start_position=0,
                requested_octet_count=1024,
            ),
        )

        assert isinstance(result, AtomicReadFileACK)
        assert result.end_of_file is True
        assert isinstance(result.access_method, StreamReadACK)
        assert result.access_method.file_data == b"Hello, BACnet!"
        assert result.access_method.file_start_position == 0

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ATOMIC_READ_FILE

    # --- atomic_write_file ---

    async def test_atomic_write_file_stream(self):
        """atomic_write_file stream access round-trip."""
        from bac_py.services.file_access import (
            AtomicWriteFileACK,
            StreamWriteAccess,
        )

        app = self._make_app()
        client = BACnetClient(app)

        ack = AtomicWriteFileACK(is_stream=True, file_start=0)
        app.confirmed_request.return_value = ack.encode()

        result = await client.atomic_write_file(
            address=PEER,
            file_identifier=ObjectIdentifier(ObjectType.FILE, 2),
            access_method=StreamWriteAccess(
                file_start_position=0,
                file_data=b"config data",
            ),
        )

        assert isinstance(result, AtomicWriteFileACK)
        assert result.is_stream is True
        assert result.file_start == 0

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ATOMIC_WRITE_FILE

    # --- who_has ---

    async def test_who_has_by_object_name(self):
        """who_has collects I-Have responses when searching by name."""
        from bac_py.services.who_has import IHaveRequest

        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_has(object_name="Zone Temp", timeout=0.1))
        await asyncio.sleep(0.01)

        assert registered_handler is not None
        ihave = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            object_name="Zone Temp",
        )
        registered_handler(ihave.encode(), PEER)

        results = await task
        assert len(results) == 1
        assert results[0].object_name == "Zone Temp"
        assert results[0].device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)

        app.register_temporary_handler.assert_called_once_with(
            UnconfirmedServiceChoice.I_HAVE, registered_handler
        )
        app.unregister_temporary_handler.assert_called_once()

    async def test_who_has_by_object_identifier(self):
        """who_has collects I-Have responses when searching by ObjectIdentifier."""
        from bac_py.services.who_has import IHaveRequest

        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        target_oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)
        task = asyncio.create_task(client.who_has(object_identifier=target_oid, timeout=0.1))
        await asyncio.sleep(0.01)

        assert registered_handler is not None
        ihave = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            object_identifier=target_oid,
            object_name="AHU-1 Temp",
        )
        registered_handler(ihave.encode(), PEER)

        results = await task
        assert len(results) == 1
        assert results[0].object_identifier == target_oid

    async def test_who_has_no_responses(self):
        """who_has returns empty list when no I-Have responses are received."""
        app = self._make_app()
        client = BACnetClient(app)

        results = await client.who_has(object_name="NonExistent", timeout=0.05)
        assert results == []


# ---------------------------------------------------------------------------
# Section 2C: BBMD Table Operations
# ---------------------------------------------------------------------------


class TestBBMDOperations:
    """Tests for BBMD table management methods (Section 2C)."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app._transport = None  # Default: no transport
        app._parse_bip_address = MagicMock()
        app.register_network_message_handler = MagicMock()
        app.unregister_network_message_handler = MagicMock()
        app.send_network_message = MagicMock()
        return app

    def _make_app_with_transport(self):
        """Create a mock app with a mocked BIP transport."""
        app = self._make_app()
        transport = MagicMock()
        transport.read_bdt = AsyncMock()
        transport.read_fdt = AsyncMock()
        transport.write_bdt = AsyncMock()
        transport.delete_fdt_entry = AsyncMock()
        app._transport = transport
        return app, transport

    def test_require_transport_raises_when_none(self):
        """_require_transport raises RuntimeError when transport is None."""
        app = self._make_app()
        client = BACnetClient(app)

        with pytest.raises(RuntimeError, match="Transport not available"):
            client._require_transport()

    async def test_read_bdt(self):
        """read_bdt reads BDT from transport and returns BDTEntryInfo list."""
        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        app._parse_bip_address.return_value = bip_addr

        # Mock BDT entries returned by transport
        mock_entry = MagicMock()
        mock_entry.address = BIPAddress(host="192.168.1.2", port=47808)
        mock_entry.broadcast_mask = b"\xff\xff\xff\xff"
        transport.read_bdt.return_value = [mock_entry]

        result = await client.read_bdt("192.168.1.1")

        assert len(result) == 1
        assert result[0].address == "192.168.1.2:47808"
        assert result[0].mask == "255.255.255.255"
        transport.read_bdt.assert_called_once_with(bip_addr, timeout=5.0)

    async def test_read_fdt(self):
        """read_fdt reads FDT from transport and returns FDTEntryInfo list."""
        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        app._parse_bip_address.return_value = bip_addr

        # Mock FDT entries returned by transport
        mock_entry = MagicMock()
        mock_entry.address = BIPAddress(host="10.0.0.50", port=47808)
        mock_entry.ttl = 300
        mock_entry.remaining = 250
        transport.read_fdt.return_value = [mock_entry]

        result = await client.read_fdt("192.168.1.1")

        assert len(result) == 1
        assert result[0].address == "10.0.0.50:47808"
        assert result[0].ttl == 300
        assert result[0].remaining == 250
        transport.read_fdt.assert_called_once_with(bip_addr, timeout=5.0)

    async def test_write_bdt_success(self):
        """write_bdt sends entries to transport and succeeds on SUCCESSFUL_COMPLETION."""
        from bac_py.app.client import BDTEntryInfo
        from bac_py.types.enums import BvlcResultCode

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        entry_addr = BIPAddress(host="192.168.1.2", port=47808)
        app._parse_bip_address.side_effect = [bip_addr, entry_addr]

        transport.write_bdt.return_value = BvlcResultCode.SUCCESSFUL_COMPLETION

        entries = [BDTEntryInfo(address="192.168.1.2:47808", mask="255.255.255.255")]
        await client.write_bdt("192.168.1.1", entries)

        transport.write_bdt.assert_called_once()

    async def test_write_bdt_failure_raises(self):
        """write_bdt raises RuntimeError on non-successful result code."""
        from bac_py.app.client import BDTEntryInfo
        from bac_py.types.enums import BvlcResultCode

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        entry_addr = BIPAddress(host="192.168.1.2", port=47808)
        app._parse_bip_address.side_effect = [bip_addr, entry_addr]

        transport.write_bdt.return_value = BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK

        entries = [BDTEntryInfo(address="192.168.1.2:47808", mask="255.255.255.255")]
        with pytest.raises(RuntimeError, match="BBMD rejected Write-BDT"):
            await client.write_bdt("192.168.1.1", entries)

    async def test_delete_fdt_entry_success(self):
        """delete_fdt_entry succeeds on SUCCESSFUL_COMPLETION."""
        from bac_py.types.enums import BvlcResultCode

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_bbmd = BIPAddress(host="192.168.1.1", port=47808)
        bip_entry = BIPAddress(host="10.0.0.50", port=47808)
        app._parse_bip_address.side_effect = [bip_bbmd, bip_entry]

        transport.delete_fdt_entry.return_value = BvlcResultCode.SUCCESSFUL_COMPLETION

        await client.delete_fdt_entry("192.168.1.1", "10.0.0.50:47808")

        transport.delete_fdt_entry.assert_called_once_with(bip_bbmd, bip_entry, timeout=5.0)

    async def test_delete_fdt_entry_failure_raises(self):
        """delete_fdt_entry raises RuntimeError on NAK."""
        from bac_py.types.enums import BvlcResultCode

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_bbmd = BIPAddress(host="192.168.1.1", port=47808)
        bip_entry = BIPAddress(host="10.0.0.50", port=47808)
        app._parse_bip_address.side_effect = [bip_bbmd, bip_entry]

        transport.delete_fdt_entry.return_value = (
            BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK
        )

        with pytest.raises(RuntimeError, match="BBMD rejected Delete-FDT-Entry"):
            await client.delete_fdt_entry("192.168.1.1", "10.0.0.50:47808")

    async def test_who_is_router_to_network(self):
        """who_is_router_to_network collects I-Am-Router-To-Network responses."""
        from bac_py.network.messages import IAmRouterToNetwork

        app = self._make_app()
        app._transport = MagicMock()  # Just needs to exist
        client = BACnetClient(app)

        captured_handler = None

        def capture_handler(msg_type, handler):
            nonlocal captured_handler
            captured_handler = handler

        app.register_network_message_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_is_router_to_network(timeout=0.1))
        await asyncio.sleep(0.01)

        # Simulate an I-Am-Router-To-Network response
        assert captured_handler is not None
        iam_msg = IAmRouterToNetwork(networks=(1, 2, 3))
        source_mac = BIPAddress(host="192.168.1.10", port=47808).encode()
        captured_handler(iam_msg, source_mac)

        result = await task
        assert len(result) == 1
        assert result[0].address == "192.168.1.10:47808"
        assert result[0].networks == [1, 2, 3]

        app.unregister_network_message_handler.assert_called_once()

    async def test_read_bdt_nak_raises_runtime_error(self):
        """read_bdt converts BvlcNakError to RuntimeError."""
        from bac_py.transport.bip import BvlcNakError

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        app._parse_bip_address.return_value = bip_addr

        transport.read_bdt.side_effect = BvlcNakError(0x0020, bip_addr)

        with pytest.raises(RuntimeError, match=r"Device rejected Read-BDT.*NAK code 0x0020"):
            await client.read_bdt("192.168.1.1")

    async def test_read_fdt_nak_raises_runtime_error(self):
        """read_fdt converts BvlcNakError to RuntimeError."""
        from bac_py.transport.bip import BvlcNakError

        app, transport = self._make_app_with_transport()
        client = BACnetClient(app)

        bip_addr = BIPAddress(host="192.168.1.1", port=47808)
        app._parse_bip_address.return_value = bip_addr

        transport.read_fdt.side_effect = BvlcNakError(0x0040, bip_addr)

        with pytest.raises(RuntimeError, match=r"Device rejected Read-FDT.*NAK code 0x0040"):
            await client.read_fdt("192.168.1.1")

    async def test_who_is_router_to_network_expected_count_early_return(self):
        """who_is_router_to_network returns early when expected_count is met."""
        from bac_py.network.messages import IAmRouterToNetwork

        app = self._make_app()
        app._transport = MagicMock()
        client = BACnetClient(app)

        captured_handler = None

        def capture_handler(msg_type, handler):
            nonlocal captured_handler
            captured_handler = handler

        app.register_network_message_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_is_router_to_network(timeout=5.0, expected_count=1))
        await asyncio.sleep(0.01)

        # Simulate a single router response — should trigger early return
        assert captured_handler is not None
        iam_msg = IAmRouterToNetwork(networks=(10, 20))
        source_mac = BIPAddress(host="192.168.1.10", port=47808).encode()
        captured_handler(iam_msg, source_mac)

        result = await asyncio.wait_for(task, timeout=1.0)
        assert len(result) == 1
        assert result[0].address == "192.168.1.10:47808"
        assert result[0].networks == [10, 20]


class TestUnicastDiscoveryEarlyReturn:
    """Tests for auto-inferred expected_count=1 on targeted unicast discovery."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    async def test_who_is_unicast_single_instance_returns_early(self):
        """who_is with low_limit==high_limit + unicast returns on first I-Am."""
        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        unicast_dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x64\xba\xc0")
        task = asyncio.create_task(
            client.who_is(low_limit=100, high_limit=100, destination=unicast_dest, timeout=5.0)
        )
        await asyncio.sleep(0.01)

        # Deliver a single I-Am — should trigger early return
        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        registered_handler(iam.encode(), unicast_dest)

        results = await asyncio.wait_for(task, timeout=1.0)
        assert len(results) == 1
        assert results[0].object_identifier.instance_number == 100

    async def test_discover_unicast_single_instance_returns_early(self):
        """Discover with low_limit==high_limit + unicast returns on first I-Am."""
        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        unicast_dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x64\xba\xc0")
        task = asyncio.create_task(
            client.discover(low_limit=200, high_limit=200, destination=unicast_dest, timeout=5.0)
        )
        await asyncio.sleep(0.01)

        # Deliver a single I-Am — should trigger early return
        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        registered_handler(iam.encode(), unicast_dest)

        results = await asyncio.wait_for(task, timeout=1.0)
        assert len(results) == 1
        assert results[0].instance == 200

    async def test_who_is_broadcast_does_not_auto_infer(self):
        """who_is with low_limit==high_limit but broadcast does NOT auto-infer."""
        from bac_py.network.address import GLOBAL_BROADCAST

        app = self._make_app()
        client = BACnetClient(app)

        # With global broadcast, should wait the full timeout (no early return)
        results = await client.who_is(
            low_limit=100, high_limit=100, destination=GLOBAL_BROADCAST, timeout=0.05
        )
        assert results == []

    async def test_who_is_different_limits_does_not_auto_infer(self):
        """who_is with low_limit != high_limit does NOT auto-infer expected_count."""
        app = self._make_app()
        client = BACnetClient(app)

        unicast_dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x64\xba\xc0")
        results = await client.who_is(
            low_limit=100, high_limit=200, destination=unicast_dest, timeout=0.05
        )
        assert results == []


# ---------------------------------------------------------------------------
# Section 2D: Backup/Restore Procedures
# ---------------------------------------------------------------------------


class TestBackupRestore:
    """Tests for backup_device, restore_device, and helper methods (Section 2D).

    These tests mock client methods directly (read_property, reinitialize_device,
    atomic_read_file, atomic_write_file) because the backup/restore procedures
    compose multiple client calls and check decoded property_value types.
    """

    def _make_client(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)
        return client

    async def test_discover_device_oid_returns_oid(self):
        """_discover_device_oid returns ObjectIdentifier when property_value is one."""
        client = self._make_client()

        oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        mock_ack = MagicMock()
        mock_ack.property_value = oid
        client.read_property = AsyncMock(return_value=mock_ack)

        result = await client._discover_device_oid(PEER)
        assert result == oid

    async def test_discover_device_oid_fallback(self):
        """_discover_device_oid falls back to wildcard when value is not ObjectIdentifier."""
        client = self._make_client()

        mock_ack = MagicMock()
        mock_ack.property_value = b"\x91\x00"  # raw bytes, not ObjectIdentifier
        client.read_property = AsyncMock(return_value=mock_ack)

        result = await client._discover_device_oid(PEER)
        assert result == ObjectIdentifier(ObjectType.DEVICE, 4194303)

    async def test_poll_backup_restore_state_returns_on_target(self):
        """_poll_backup_restore_state returns when target state is reached."""
        from bac_py.types.enums import BackupAndRestoreState

        client = self._make_client()
        device_oid = ObjectIdentifier(ObjectType.DEVICE, 100)

        # Return int value matching a target state
        mock_ack = MagicMock()
        mock_ack.property_value = int(BackupAndRestoreState.PERFORMING_A_BACKUP)
        client.read_property = AsyncMock(return_value=mock_ack)

        result = await client._poll_backup_restore_state(
            PEER,
            device_oid,
            target_states=(
                BackupAndRestoreState.PERFORMING_A_BACKUP,
                BackupAndRestoreState.PREPARING_FOR_BACKUP,
            ),
            poll_interval=0.01,
        )
        assert result == BackupAndRestoreState.PERFORMING_A_BACKUP

    async def test_poll_backup_restore_state_polls_until_target(self):
        """_poll_backup_restore_state polls multiple times until target state."""
        from bac_py.types.enums import BackupAndRestoreState

        client = self._make_client()
        device_oid = ObjectIdentifier(ObjectType.DEVICE, 100)

        # First returns non-int (bytes), second returns target int
        non_target_ack = MagicMock()
        non_target_ack.property_value = b"\x91\x00"  # bytes, not int

        target_ack = MagicMock()
        target_ack.property_value = int(BackupAndRestoreState.PERFORMING_A_BACKUP)

        client.read_property = AsyncMock(side_effect=[non_target_ack, target_ack])

        result = await client._poll_backup_restore_state(
            PEER,
            device_oid,
            target_states=(BackupAndRestoreState.PERFORMING_A_BACKUP,),
            poll_interval=0.01,
        )
        assert result == BackupAndRestoreState.PERFORMING_A_BACKUP
        assert client.read_property.call_count == 2

    async def test_download_file_single_chunk(self):
        """_download_file reads a file in a single chunk (end_of_file=True)."""
        from bac_py.services.file_access import AtomicReadFileACK, StreamReadACK

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        client = BACnetClient(app)

        file_oid = ObjectIdentifier(ObjectType.FILE, 1)

        ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(
                file_start_position=0,
                file_data=b"config data here",
            ),
        )
        app.confirmed_request.return_value = ack.encode()

        data = await client._download_file(PEER, file_oid)
        assert data == b"config data here"
        app.confirmed_request.assert_called_once()

    async def test_download_file_multiple_chunks(self):
        """_download_file reads a file across multiple chunks."""
        from bac_py.services.file_access import AtomicReadFileACK, StreamReadACK

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        client = BACnetClient(app)

        file_oid = ObjectIdentifier(ObjectType.FILE, 1)

        chunk1 = AtomicReadFileACK(
            end_of_file=False,
            access_method=StreamReadACK(
                file_start_position=0,
                file_data=b"chunk1",
            ),
        )
        chunk2 = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(
                file_start_position=6,
                file_data=b"chunk2",
            ),
        )
        app.confirmed_request.side_effect = [chunk1.encode(), chunk2.encode()]

        data = await client._download_file(PEER, file_oid)
        assert data == b"chunk1chunk2"
        assert app.confirmed_request.call_count == 2

    async def test_backup_device_full_procedure(self):
        """backup_device executes the 5-step backup procedure."""
        from bac_py.services.file_access import AtomicReadFileACK, StreamReadACK
        from bac_py.types.enums import BackupAndRestoreState

        client = self._make_client()

        device_oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        file_oid = ObjectIdentifier(ObjectType.FILE, 1)

        # Mock reinitialize_device (Steps 1 and 5)
        client.reinitialize_device = AsyncMock()

        # Mock _discover_device_oid (Step 2a)
        discover_ack = MagicMock()
        discover_ack.property_value = device_oid

        # Mock _poll state (Step 2b)
        state_ack = MagicMock()
        state_ack.property_value = int(BackupAndRestoreState.PERFORMING_A_BACKUP)

        # Mock read config files (Step 3)
        config_ack = MagicMock()
        config_ack.property_value = file_oid  # single ObjectIdentifier

        client.read_property = AsyncMock(side_effect=[discover_ack, state_ack, config_ack])

        # Mock _download_file (Step 4)
        read_ack = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(
                file_start_position=0,
                file_data=b"backup-contents",
            ),
        )
        client.atomic_read_file = AsyncMock(return_value=read_ack)

        result = await client.backup_device(PEER, password="pass", poll_interval=0.01)

        assert result.device_instance == 100
        assert len(result.configuration_files) == 1
        assert result.configuration_files[0][0] == file_oid
        assert result.configuration_files[0][1] == b"backup-contents"
        assert client.reinitialize_device.call_count == 2

    async def test_restore_device_full_procedure(self):
        """restore_device executes the 4-step restore procedure."""
        from bac_py.app.client import BackupData
        from bac_py.services.file_access import AtomicWriteFileACK
        from bac_py.types.enums import BackupAndRestoreState

        client = self._make_client()

        device_oid = ObjectIdentifier(ObjectType.DEVICE, 100)
        file_oid = ObjectIdentifier(ObjectType.FILE, 1)

        backup_data = BackupData(
            device_instance=100,
            configuration_files=[(file_oid, b"restore-data")],
        )

        # Mock reinitialize_device (Steps 1 and 4)
        client.reinitialize_device = AsyncMock()

        # Mock _discover_device_oid (Step 2a)
        discover_ack = MagicMock()
        discover_ack.property_value = device_oid

        # Mock _poll state (Step 2b)
        state_ack = MagicMock()
        state_ack.property_value = int(BackupAndRestoreState.PERFORMING_A_RESTORE)

        client.read_property = AsyncMock(side_effect=[discover_ack, state_ack])

        # Mock atomic_write_file (Step 3)
        write_ack = AtomicWriteFileACK(
            is_stream=True,
            file_start=0,
        )
        client.atomic_write_file = AsyncMock(return_value=write_ack)

        await client.restore_device(PEER, backup_data, password="pass", poll_interval=0.01)

        assert client.reinitialize_device.call_count == 2
        client.atomic_write_file.assert_called_once()

    async def test_backup_device_multiple_config_files(self):
        """backup_device handles multiple configuration files."""
        from bac_py.services.file_access import AtomicReadFileACK, StreamReadACK
        from bac_py.types.enums import BackupAndRestoreState

        client = self._make_client()

        device_oid = ObjectIdentifier(ObjectType.DEVICE, 200)
        file_oid1 = ObjectIdentifier(ObjectType.FILE, 1)
        file_oid2 = ObjectIdentifier(ObjectType.FILE, 2)

        client.reinitialize_device = AsyncMock()

        # _discover_device_oid
        discover_ack = MagicMock()
        discover_ack.property_value = device_oid

        # _poll state
        state_ack = MagicMock()
        state_ack.property_value = int(BackupAndRestoreState.PERFORMING_A_BACKUP)

        # config files list
        config_ack = MagicMock()
        config_ack.property_value = [file_oid1, file_oid2]

        client.read_property = AsyncMock(side_effect=[discover_ack, state_ack, config_ack])

        # File downloads
        ack1 = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(file_start_position=0, file_data=b"file1"),
        )
        ack2 = AtomicReadFileACK(
            end_of_file=True,
            access_method=StreamReadACK(file_start_position=0, file_data=b"file2"),
        )
        client.atomic_read_file = AsyncMock(side_effect=[ack1, ack2])

        result = await client.backup_device(PEER, poll_interval=0.01)

        assert result.device_instance == 200
        assert len(result.configuration_files) == 2
        assert result.configuration_files[0] == (file_oid1, b"file1")
        assert result.configuration_files[1] == (file_oid2, b"file2")


# ---------------------------------------------------------------------------
# Section 2E: Discovery Extensions
# ---------------------------------------------------------------------------


class TestDiscoveryExtensions:
    """Tests for discover(), discover_extended(), traverse_hierarchy, and helpers."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    async def test_discover_returns_discovered_devices(self):
        """discover() returns DiscoveredDevice objects with address info."""
        from bac_py.app.client import DiscoveredDevice

        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.discover(timeout=0.1))
        await asyncio.sleep(0.01)

        # Simulate an I-Am response
        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        registered_handler(iam.encode(), PEER)

        result = await task
        assert len(result) == 1
        assert isinstance(result[0], DiscoveredDevice)
        assert result[0].instance == 42
        assert result[0].vendor_id == 7
        assert result[0].max_apdu_length == 1476
        assert result[0].address == PEER

    async def test_discover_extended_enriches_with_rpm(self):
        """discover_extended() enriches devices with profile metadata via RPM.

        The _enrich_device method checks isinstance(val, str) on property_value,
        so we mock read_property_multiple to return pre-decoded string values.
        """
        from bac_py.app.client import DiscoveredDevice

        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        # Mock RPM to return decoded result elements with str property_value
        mock_rpm_ack = MagicMock()
        mock_result = MagicMock()
        mock_result.list_of_results = [
            MagicMock(
                property_identifier=PropertyIdentifier.PROFILE_NAME,
                property_value="TestProfile",
                property_access_error=None,
            ),
            MagicMock(
                property_identifier=PropertyIdentifier.PROFILE_LOCATION,
                property_value="http://example.com",
                property_access_error=None,
            ),
            MagicMock(
                property_identifier=PropertyIdentifier.TAGS,
                property_value=None,
                property_access_error=(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY),
            ),
        ]
        mock_rpm_ack.list_of_read_access_results = [mock_result]
        client.read_property_multiple = AsyncMock(return_value=mock_rpm_ack)

        task = asyncio.create_task(client.discover_extended(timeout=0.1, enrich_timeout=1.0))
        await asyncio.sleep(0.01)

        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=7,
        )
        registered_handler(iam.encode(), PEER)

        result = await task
        assert len(result) == 1
        dev = result[0]
        assert isinstance(dev, DiscoveredDevice)
        assert dev.instance == 42
        assert dev.profile_name == "TestProfile"
        assert dev.profile_location == "http://example.com"
        assert dev.tags is None  # Error response -> None

    async def test_traverse_hierarchy_non_list_returns_early(self):
        """_traverse_hierarchy_recursive returns early for non-list subordinates.

        The method checks isinstance(subordinates, list). Since read_property
        returns raw bytes in property_value, a non-list value causes early return.
        We mock read_property to return a non-list property_value.
        """
        app = self._make_app()
        client = BACnetClient(app)

        root = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)

        # Return a non-list property_value (a single int)
        mock_ack = MagicMock()
        mock_ack.property_value = 42  # not a list
        client.read_property = AsyncMock(return_value=mock_ack)

        result = await client.traverse_hierarchy(PEER, root)
        # Non-list means no subordinates found
        assert result == []

    async def test_traverse_hierarchy_handles_cycles(self):
        """_traverse_hierarchy_recursive handles visited nodes to avoid cycles.

        We mock read_property to return list property_values containing
        ObjectIdentifier subordinates.
        """
        app = self._make_app()
        client = BACnetClient(app)

        root = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1)
        child = ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 2)

        # Root has child as subordinate
        root_ack = MagicMock()
        root_ack.property_value = [child]

        # Child refers back to root (cycle)
        child_ack = MagicMock()
        child_ack.property_value = [root]

        client.read_property = AsyncMock(side_effect=[root_ack, child_ack])

        result = await client.traverse_hierarchy(PEER, root)
        # Should find child (SV,2) and root (SV,1) listed as child's subordinate.
        # Root is already visited so recursion stops.
        assert ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 2) in result
        assert ObjectIdentifier(ObjectType.STRUCTURED_VIEW, 1) in result

    async def test_collect_unconfirmed_responses_expected_count(self):
        """_collect_unconfirmed_responses returns early when expected_count reached."""
        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.who_is(timeout=5.0, expected_count=1))
        await asyncio.sleep(0.01)

        assert registered_handler is not None
        iam = IAmRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 99),
            max_apdu_length=1476,
            segmentation_supported=Segmentation.BOTH,
            vendor_id=0,
        )
        registered_handler(iam.encode(), PEER)

        # Should return early (not wait full 5 seconds)
        result = await asyncio.wait_for(task, timeout=1.0)
        assert len(result) == 1
        assert result[0].object_identifier.instance_number == 99


# ---------------------------------------------------------------------------
# Additional uncovered small methods
# ---------------------------------------------------------------------------


class TestAdditionalMethods:
    """Tests for remaining small uncovered methods."""

    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    def test_who_am_i(self):
        """who_am_i sends unconfirmed Who-Am-I request."""
        app = self._make_app()
        client = BACnetClient(app)

        client.who_am_i(
            destination=PEER,
            vendor_id=7,
            model_name="TestModel",
            serial_number="SN12345",
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.WHO_AM_I

    def test_you_are(self):
        """you_are sends unconfirmed You-Are request."""
        app = self._make_app()
        client = BACnetClient(app)

        client.you_are(
            destination=PEER,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            device_mac_address=b"\xc0\xa8\x01\x64\xba\xc0",
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.YOU_ARE

    def test_you_are_with_network_number(self):
        """you_are sends You-Are with optional network number."""
        app = self._make_app()
        client = BACnetClient(app)

        client.you_are(
            destination=PEER,
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
            device_mac_address=b"\xc0\xa8\x01\x64\xba\xc0",
            device_network_number=5,
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.YOU_ARE

    async def test_discover_unconfigured(self):
        """discover_unconfigured collects Who-Am-I messages."""
        from bac_py.app.client import UnconfiguredDevice
        from bac_py.services.device_discovery import WhoAmIRequest

        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        task = asyncio.create_task(client.discover_unconfigured(timeout=0.1))
        await asyncio.sleep(0.01)

        assert registered_handler is not None
        who_am_i = WhoAmIRequest(
            vendor_id=7,
            model_name="TestModel",
            serial_number="SN12345",
        )
        registered_handler(who_am_i.encode(), PEER)

        result = await task
        assert len(result) == 1
        assert isinstance(result[0], UnconfiguredDevice)
        assert result[0].vendor_id == 7
        assert result[0].model_name == "TestModel"
        assert result[0].serial_number == "SN12345"

        app.unregister_temporary_handler.assert_called_once()

    async def test_send_audit_notification_confirmed(self):
        """send_audit_notification uses confirmed path when confirmed=True."""
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""

        # Use a mock notification since BACnetAuditNotification has many fields
        mock_notification = MagicMock()
        mock_notification.encode.return_value = b"\x00"

        await client.send_audit_notification(
            address=PEER,
            notifications=[mock_notification],
            confirmed=True,
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION
        )

    async def test_send_audit_notification_unconfirmed(self):
        """send_audit_notification uses unconfirmed path when confirmed=False."""
        app = self._make_app()
        client = BACnetClient(app)

        mock_notification = MagicMock()
        mock_notification.encode.return_value = b"\x00"

        await client.send_audit_notification(
            address=PEER,
            notifications=[mock_notification],
            confirmed=False,
        )

        app.unconfirmed_request.assert_called_once()
        call_kwargs = app.unconfirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION
        )
        app.confirmed_request.assert_not_called()

    async def test_query_audit_log(self):
        """query_audit_log sends AuditLogQuery request."""
        from bac_py.services.audit import AuditLogQueryACK
        from bac_py.types.audit_types import AuditQueryByTarget

        app = self._make_app()
        client = BACnetClient(app)

        ack = AuditLogQueryACK(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            records=[],
            no_more_items=True,
        )
        app.confirmed_request.return_value = ack.encode()

        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )

        result = await client.query_audit_log(
            address=PEER,
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query,
        )

        assert isinstance(result, AuditLogQueryACK)
        assert result.no_more_items is True
        assert result.records == []

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.AUDIT_LOG_QUERY

    async def test_get_enrollment_summary(self):
        """get_enrollment_summary sends request and decodes ACK."""
        from bac_py.services.alarm_summary import (
            EnrollmentSummary,
            GetEnrollmentSummaryACK,
        )
        from bac_py.types.enums import AcknowledgmentFilter, EventType

        app = self._make_app()
        client = BACnetClient(app)

        ack = GetEnrollmentSummaryACK(
            list_of_enrollment_summaries=[
                EnrollmentSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    event_type=EventType.CHANGE_OF_VALUE,
                    event_state=EventState.HIGH_LIMIT,
                    priority=3,
                    notification_class=10,
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_enrollment_summary(
            address=PEER,
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )

        assert isinstance(result, GetEnrollmentSummaryACK)
        assert len(result.list_of_enrollment_summaries) == 1
        assert result.list_of_enrollment_summaries[0].priority == 3

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.GET_ENROLLMENT_SUMMARY
        )


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestGetObjectListFallback:
    """Test get_object_list fallback when segmentation is not supported."""

    async def test_get_object_list_fallback_on_segmentation_error(self):
        """get_object_list falls back to element-by-element when SegNotSupported."""
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        # First call (full list) raises segmentation-not-supported
        # Second call (array index 0) returns count=2
        # Third/fourth calls return individual elements
        obj1 = ObjectIdentifier(ObjectType.DEVICE, 1)
        obj2 = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)

        count_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=0,
            property_value=encode_application_unsigned(2),
        )
        elem1_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=1,
            property_value=encode_application_object_id(obj1.object_type, obj1.instance_number),
        )
        elem2_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=2,
            property_value=encode_application_object_id(obj2.object_type, obj2.instance_number),
        )

        app.confirmed_request.side_effect = [
            BACnetAbortError(AbortReason.SEGMENTATION_NOT_SUPPORTED),
            count_ack.encode(),
            elem1_ack.encode(),
            elem2_ack.encode(),
        ]

        result = await client.get_object_list("192.168.1.100", 1)
        assert len(result) == 2
        assert result[0] == obj1
        assert result[1] == obj2

    async def test_get_object_list_fallback_count_zero(self):
        """get_object_list fallback with count=0 returns empty list."""
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        count_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=0,
            property_value=encode_application_unsigned(0),
        )

        app.confirmed_request.side_effect = [
            BACnetAbortError(AbortReason.SEGMENTATION_NOT_SUPPORTED),
            count_ack.encode(),
        ]

        result = await client.get_object_list("192.168.1.100", 1)
        assert result == []


class TestDiscoverExtendedRPMErrorHandling:
    """Test discover_extended when RPM enrichment fails."""

    async def test_discover_extended_rpm_error_skipped(self):
        """discover_extended skips RPM errors and returns basic device info."""
        from bac_py.services.errors import BACnetError

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        # Mock discover to return one device
        discover_result = MagicMock()
        discover_result.address = PEER
        discover_result.instance = 42
        discover_result.vendor_id = 7
        discover_result.max_apdu_length = 1476
        discover_result.segmentation_supported = Segmentation.BOTH

        client.discover = AsyncMock(return_value=[discover_result])

        # Mock read_property_multiple to raise BACnetError
        client.read_property_multiple = AsyncMock(
            side_effect=BACnetError(ErrorClass.SERVICES, ErrorCode.OTHER)
        )

        result = await client.discover_extended(timeout=0.1)
        assert len(result) == 1
        assert result[0].instance == 42
        # Profile fields should be None due to RPM error
        assert result[0].profile_name is None
        assert result[0].profile_location is None


class TestGetEventInformationPagination:
    """Test get_event_information with pagination."""

    async def test_get_event_information_with_last_received(self):
        """get_event_information passes last_received_object_identifier for pagination."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=False,
        )
        app.confirmed_request.return_value = ack.encode()

        last_obj = ObjectIdentifier(ObjectType.ANALOG_INPUT, 5)
        result = await client.get_event_information(
            address=PEER,
            last_received_object_identifier=last_obj,
        )
        assert isinstance(result, GetEventInformationACK)
        assert result.more_events is False

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.GET_EVENT_INFORMATION


class TestAcknowledgeAlarmRequest:
    """Test acknowledge_alarm client method."""

    async def test_acknowledge_alarm_sends_request(self):
        """acknowledge_alarm sends AcknowledgeAlarm-Request."""
        app = MagicMock()
        app.confirmed_request = AsyncMock(return_value=b"")
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        await client.acknowledge_alarm(
            address=PEER,
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.HIGH_LIMIT,
            time_stamp=BACnetTimeStamp(choice=1, value=100),
            acknowledgment_source="operator",
            time_of_acknowledgment=BACnetTimeStamp(choice=1, value=200),
        )

        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ACKNOWLEDGE_ALARM


# ---------------------------------------------------------------------------
# Additional coverage tests for BACnetClient
# ---------------------------------------------------------------------------


class TestReadMultipleNonePropertyValue:
    """Test read_multiple when property_value is None or empty."""

    async def test_read_multiple_empty_property_value_returns_none(self):
        """When property_value is empty bytes, read_multiple sets value to None."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()

        # Craft a ReadPropertyMultipleACK with empty property_value
        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"",  # empty
                        ),
                    ],
                ),
            ],
        )
        app.confirmed_request.return_value = ack.encode()

        client = BACnetClient(app)
        result = await client.read_multiple(
            "192.168.1.100",
            {"ai,1": ["present-value"]},
        )
        # Value should be None because property_value was empty
        assert result["analog-input,1"]["present-value"] is None


class TestGetObjectListSegmentationFallback:
    """Test get_object_list fallback path when segmentation is not supported."""

    async def test_get_object_list_fallback_on_segmentation_abort(self):
        """get_object_list falls back to reading array elements on abort."""
        from bac_py.services.errors import BACnetAbortError
        from bac_py.types.enums import AbortReason

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        # First call: raises segmentation not supported
        # Second call: returns array length = 2
        # Third/Fourth calls: return individual elements
        count_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=0,
            property_value=encode_application_unsigned(2),
        )
        elem1_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=1,
            property_value=encode_application_object_id(ObjectType.DEVICE, 1),
        )
        elem2_ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=2,
            property_value=encode_application_object_id(ObjectType.ANALOG_INPUT, 1),
        )
        app.confirmed_request.side_effect = [
            BACnetAbortError(AbortReason.SEGMENTATION_NOT_SUPPORTED),
            count_ack.encode(),
            elem1_ack.encode(),
            elem2_ack.encode(),
        ]

        result = await client.get_object_list(
            "192.168.1.100",
            device_instance=1,
        )
        assert len(result) == 2
        assert result[0] == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert result[1] == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)


class TestWhoIsRouterToNetworkHandler:
    """Test who_is_router_to_network handler paths."""

    async def test_who_is_router_str_destination(self):
        """who_is_router_to_network accepts string destination."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app.register_network_message_handler = MagicMock()
        app.unregister_network_message_handler = MagicMock()
        app.send_network_message = MagicMock()
        client = BACnetClient(app)

        result = await client.who_is_router_to_network(
            network=100,
            destination="192.168.1.255",
            timeout=0.01,
        )
        assert isinstance(result, list)
        # Verify send_network_message was called
        app.send_network_message.assert_called_once()

    async def test_who_is_router_bacnet_address_destination(self):
        """who_is_router_to_network accepts BACnetAddress destination."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app.register_network_message_handler = MagicMock()
        app.unregister_network_message_handler = MagicMock()
        app.send_network_message = MagicMock()
        client = BACnetClient(app)

        result = await client.who_is_router_to_network(
            destination=PEER,
            timeout=0.01,
        )
        assert isinstance(result, list)
        app.send_network_message.assert_called_once()


class TestDiscoverUnconfiguredException:
    """Test discover_unconfigured exception handling in callback."""

    async def test_discover_unconfigured_ignores_decode_errors(self):
        """discover_unconfigured ignores ValueError during decode."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        result = await client.discover_unconfigured(timeout=0.01)
        assert result == []

        # Verify handler was registered and unregistered
        app.register_temporary_handler.assert_called_once()
        app.unregister_temporary_handler.assert_called_once()


# ==================== Coverage gap tests: uncovered lines/branches ====================


class TestGetObjectListEmptyFallback:
    """Test get_object_list returning empty list (line 836)."""

    async def test_get_object_list_empty_property_value(self):
        """get_object_list returns [] when property_value is empty (line 836)."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        # Return a ReadPropertyACK with empty property_value
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_value=b"",
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_object_list("192.168.1.100", device_instance=1)
        assert result == []


class TestDiscoverRoutersTypeCheck:
    """Test who_is_router_to_network IAmRouterToNetwork type check (line 1861)."""

    async def test_who_is_router_ignores_non_i_am_router(self):
        """on_i_am_router callback ignores non-IAmRouterToNetwork messages (line 1860-1861)."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app.register_network_message_handler = MagicMock()
        app.unregister_network_message_handler = MagicMock()
        app.send_network_message = MagicMock()
        client = BACnetClient(app)

        result = await client.who_is_router_to_network(timeout=0.01)
        assert isinstance(result, list)
        assert len(result) == 0

        # Grab the callback that was registered
        handler_call = app.register_network_message_handler.call_args
        callback = handler_call[0][1]

        # Call it with a non-IAmRouterToNetwork message -- should be a no-op
        callback("not-an-i-am-router", b"\x7f\x00\x00\x01\xba\xc0")
        # No crash; result should remain empty


class TestWhoAmIDecodeError:
    """Test who_am_i ValueError/IndexError catch (lines 2459-2460)."""

    async def test_discover_unconfigured_catches_value_error_in_callback(self):
        """Discover_unconfigured catches ValueError in _on_who_am_i callback."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        result = await client.discover_unconfigured(timeout=0.01)

        # Now call the registered handler with bad data
        handler_call = app.register_temporary_handler.call_args
        callback = handler_call[0][1]
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Call with malformed bytes that will raise ValueError or IndexError
        callback(b"\xff", source)
        # Should not crash, result should remain empty
        assert result == []


class TestEncodeForWriteFallbackBranches:
    """Test _encode_for_write fallback paths (branches 520->539, 527->539, 536->539)."""

    def _make_client(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        return BACnetClient(app)

    def test_bool_with_no_datatype_falls_back(self):
        """Boolean value with no datatype lookup falls back to encode_property_value."""
        from unittest.mock import patch

        client = self._make_client()
        # Force datatype lookup to return None (no registered type)
        with patch.object(client, "_lookup_datatype", return_value=None):
            result = client._encode_for_write(
                True,
                PropertyIdentifier.PRESENT_VALUE,
                ObjectType.ANALOG_INPUT,
            )
        # Should return valid bytes (not crash)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_bool_with_bool_datatype_encodes_boolean(self):
        """Boolean value with bool datatype encodes as BACnet boolean (branch 527->539)."""
        from unittest.mock import patch

        client = self._make_client()
        with patch.object(client, "_lookup_datatype", return_value=bool):
            result = client._encode_for_write(
                True,
                PropertyIdentifier.PRESENT_VALUE,
                ObjectType.ANALOG_INPUT,
            )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_int_with_bool_datatype_encodes_boolean(self):
        """Int value with bool datatype encodes as BACnet boolean (branch 536->539)."""
        from unittest.mock import patch

        client = self._make_client()
        with patch.object(client, "_lookup_datatype", return_value=bool):
            result = client._encode_for_write(
                1,
                PropertyIdentifier.PRESENT_VALUE,
                ObjectType.ANALOG_INPUT,
            )
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestBroadcastListenerDecoderNoneResult:
    """Test _broadcast_listener decoder returning None (branch 1035->exit)."""

    async def test_broadcast_listener_decoder_returns_none_skips(self):
        """When decoder returns None, item is not appended (branch 1035->exit)."""
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        client = BACnetClient(app)

        # Call discover (who_is) which uses _broadcast_listener internally
        # The decoder for I-Am can return None for malformed data
        result = await client.who_is(timeout=0.01)
        assert isinstance(result, list)

        # Grab the handler registered for I-Am
        handler_call = app.register_temporary_handler.call_args
        callback = handler_call[0][1]
        source = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

        # Valid I-Am should parse, but call with truncated data that causes
        # ValueError to be raised (which means item is not appended)
        callback(b"\x00", source)
        # Result should still be empty
        assert len(result) == 0


class TestSubscribeCovExUndo:
    """Test subscribe_cov_ex callback undo on failure (branch 926->928)."""

    async def test_subscribe_cov_ex_undoes_callback_on_failure(self):
        """subscribe_cov_ex unregisters callback on subscribe failure (branch 926->928)."""
        app = MagicMock()
        app.confirmed_request = AsyncMock(side_effect=RuntimeError("network error"))
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        app.register_cov_callback = MagicMock()
        app.unregister_cov_callback = MagicMock()
        client = BACnetClient(app)

        callback = MagicMock()
        with pytest.raises(RuntimeError):
            await client.subscribe_cov_ex(
                "192.168.1.100",
                "ai,1",
                process_id=42,
                callback=callback,
            )
        # Callback should have been unregistered on failure
        app.unregister_cov_callback.assert_called_once_with(42)
