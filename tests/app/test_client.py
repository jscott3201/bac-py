import asyncio
from unittest.mock import AsyncMock, MagicMock

from bac_py.app.client import BACnetClient
from bac_py.network.address import BACnetAddress
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
from bac_py.services.who_is import IAmRequest
from bac_py.services.write_property_multiple import (
    PropertyValue,
    WriteAccessSpecification,
)
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

    def test_read_property_multiple(self):
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

        async def run():
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
                call_kwargs.kwargs["service_choice"]
                == ConfirmedServiceChoice.READ_PROPERTY_MULTIPLE
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_property_multiple(self):
        app = self._make_app()
        client = BACnetClient(app)
        app.confirmed_request.return_value = b""  # SimpleACK

        async def run():
            await client.write_property_multiple(
                address=PEER,
                write_access_specs=[
                    WriteAccessSpecification(
                        object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
                        list_of_properties=[
                            PropertyValue(
                                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                                property_value=b"\x44\x42\x28\x00\x00",
                                priority=8,
                            ),
                        ],
                    ),
                ],
            )
            app.confirmed_request.assert_called_once()
            call_kwargs = app.confirmed_request.call_args
            assert (
                call_kwargs.kwargs["service_choice"]
                == ConfirmedServiceChoice.WRITE_PROPERTY_MULTIPLE
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_range(self):
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

        async def run():
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

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_range_with_position(self):
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

        async def run():
            result = await client.read_range(
                address=PEER,
                object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                property_identifier=PropertyIdentifier.OBJECT_LIST,
                range_qualifier=RangeByPosition(reference_index=2, count=2),
            )
            assert result.item_count == 2
            assert result.result_flags.more_items is True

        asyncio.get_event_loop().run_until_complete(run())
