"""Tests for BACnetClient convenience methods: read(), write(), read_multiple()."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.client import BACnetClient
from bac_py.encoding.primitives import (
    decode_real,
    decode_unsigned,
    encode_application_character_string,
    encode_application_enumerated,
    encode_application_real,
    encode_application_unsigned,
)
from bac_py.encoding.tags import TagClass, decode_tag
from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.services.read_property import ReadPropertyACK
from bac_py.services.read_property_multiple import (
    ReadAccessResult,
    ReadPropertyMultipleACK,
    ReadResultElement,
)
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorClass,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier

PEER = BACnetAddress(mac_address=BIPAddress(host="192.168.1.100", port=0xBAC0).encode())


class TestRead:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        return app

    def test_read_real_with_strings(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read("192.168.1.100", "ai,1", "pv")
            assert isinstance(result, float)
            assert result == pytest.approx(72.5)

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_string(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=encode_application_character_string("Zone Temp"),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read("192.168.1.100", "analog-input,1", "object-name")
            assert result == "Zone Temp"

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_unsigned(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.MULTI_STATE_VALUE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_unsigned(3),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read("192.168.1.100", "msv,1", "pv")
            assert result == 3

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_enumerated(1),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read("192.168.1.100", "bv,1", "pv")
            assert result == 1

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_multiple_values_returns_list(self):
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

        async def run():
            result = await client.read("192.168.1.100", "dev,100", "object-list")
            assert isinstance(result, list)
            assert len(result) == 2

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_with_address_object(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            # Using BACnetAddress directly should still work
            result = await client.read(PEER, "ai,1", "pv")
            assert result == pytest.approx(72.5)

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_with_native_types(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=encode_application_real(72.5),
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            # Using native enum types directly should also work
            result = await client.read(
                PEER,
                ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                PropertyIdentifier.PRESENT_VALUE,
            )
            assert result == pytest.approx(72.5)

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_empty_value_returns_none(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"",
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read("192.168.1.100", "ai,1", "pv")
            assert result is None

        asyncio.get_event_loop().run_until_complete(run())


class TestWrite:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock(return_value=b"")
        return app

    def test_write_float_to_analog(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
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
            assert decode_real(req.property_value[offset : offset + tag.length]) == pytest.approx(
                72.5
            )
            assert req.priority == 8

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_int_to_analog_encodes_as_real(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "av,1", "pv", 72)
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, offset = decode_tag(req.property_value, 0)
            assert tag.number == 4  # Real, not Unsigned!
            assert decode_real(req.property_value[offset : offset + tag.length]) == pytest.approx(
                72.0
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_int_to_binary_encodes_as_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "bv,1", "pv", 1)
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, _ = decode_tag(req.property_value, 0)
            assert tag.number == 9  # Enumerated

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_bool_to_binary_encodes_as_enumerated(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "bo,1", "pv", True)
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, offset = decode_tag(req.property_value, 0)
            assert tag.number == 9  # Enumerated
            assert decode_unsigned(req.property_value[offset : offset + tag.length]) == 1

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_int_to_multistate_encodes_as_unsigned(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "msv,1", "pv", 3)
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, offset = decode_tag(req.property_value, 0)
            assert tag.number == 2  # Unsigned
            assert decode_unsigned(req.property_value[offset : offset + tag.length]) == 3

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_none_encodes_as_null(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "ao,1", "pv", None, priority=8)
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, _ = decode_tag(req.property_value, 0)
            assert tag.number == 0  # Null
            assert req.priority == 8

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_string(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("192.168.1.100", "av,1", "name", "New Name")
            call_kwargs = app.confirmed_request.call_args
            service_data = call_kwargs.kwargs["service_data"]
            from bac_py.services.write_property import WritePropertyRequest

            req = WritePropertyRequest.decode(service_data)
            tag, _ = decode_tag(req.property_value, 0)
            assert tag.number == 7  # Character String

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_with_network_address(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.write("2:192.168.1.100", "av,1", "pv", 72.5)
            call_kwargs = app.confirmed_request.call_args
            dest = call_kwargs.kwargs["destination"]
            assert dest.network == 2

        asyncio.get_event_loop().run_until_complete(run())


class TestReadMultiple:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        return app

    def test_read_multiple_basic(self):
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

        async def run():
            result = await client.read_multiple(
                "192.168.1.100",
                {"ai,1": ["pv", "name"]},
            )

            assert "analog-input,1" in result
            props = result["analog-input,1"]
            assert props["present-value"] == pytest.approx(72.5)
            assert props["object-name"] == "Zone Temp"

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_multiple_with_error(self):
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

        async def run():
            result = await client.read_multiple(
                "192.168.1.100",
                {"ai,1": ["pv", "desc"]},
            )

            props = result["analog-input,1"]
            assert props["present-value"] == pytest.approx(72.5)
            assert props["description"] is None  # Error -> None

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_multiple_objects(self):
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

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_multiple_with_unsigned(self):
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

        async def run():
            result = await client.read_multiple(
                "192.168.1.100",
                {"ai,1": ["pv", "units"]},
            )

            props = result["analog-input,1"]
            assert props["present-value"] == pytest.approx(72.5)
            assert props["units"] == 62

        asyncio.get_event_loop().run_until_complete(run())
