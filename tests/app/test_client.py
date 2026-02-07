import asyncio
from unittest.mock import AsyncMock, MagicMock

from bac_py.app.client import BACnetClient
from bac_py.network.address import BACnetAddress
from bac_py.services.read_property import ReadPropertyACK
from bac_py.services.who_is import IAmRequest
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ObjectType,
    PropertyIdentifier,
    Segmentation,
    UnconfirmedServiceChoice,
)
from bac_py.types.primitives import ObjectIdentifier

PEER = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")


class TestBACnetClient:
    def _make_app(self):
        app = MagicMock()
        app.confirmed_request = AsyncMock()
        app.unconfirmed_request = MagicMock()
        app.register_temporary_handler = MagicMock()
        app.unregister_temporary_handler = MagicMock()
        return app

    def test_read_property(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Create a fake ReadPropertyACK response
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_property_with_array_index(self):
        app = self._make_app()
        client = BACnetClient(app)

        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=3,
            property_value=b"\xc4\x00\x00\x00\x01",
        )
        app.confirmed_request.return_value = ack.encode()

        async def run():
            result = await client.read_property(
                address=PEER,
                object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                property_identifier=PropertyIdentifier.OBJECT_LIST,
                array_index=3,
            )
            assert result.property_array_index == 3

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_property(self):
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is(self):
        app = self._make_app()
        client = BACnetClient(app)

        # Simulate the I-Am responses being delivered via temporary handler
        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_with_range(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            await client.who_is(low_limit=100, high_limit=200, timeout=0.05)
            app.unconfirmed_request.assert_called_once()
            call_kwargs = app.unconfirmed_request.call_args
            assert call_kwargs.kwargs["service_choice"] == UnconfirmedServiceChoice.WHO_IS

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_no_responses(self):
        app = self._make_app()
        client = BACnetClient(app)

        async def run():
            results = await client.who_is(timeout=0.05)
            assert results == []

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_malformed_iam_ignored(self):
        app = self._make_app()
        client = BACnetClient(app)

        registered_handler = None

        def capture_handler(service_choice, handler):
            nonlocal registered_handler
            registered_handler = handler

        app.register_temporary_handler.side_effect = capture_handler

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())
