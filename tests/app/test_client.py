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
