import asyncio
from unittest.mock import MagicMock

import pytest

from bac_py.app.server import DefaultServerHandlers, _encode_property_value
from bac_py.network.address import BACnetAddress
from bac_py.objects.base import ObjectDatabase
from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.services.who_is import WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.types.enums import (
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
    Segmentation,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

SOURCE = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")


def _make_app(device_instance: int = 1):
    """Create a mock application with a device for testing."""
    app = MagicMock()
    app.config = MagicMock()
    app.config.max_apdu_length = 1476
    app.config.vendor_id = 42
    app.service_registry = MagicMock()
    app.unconfirmed_request = MagicMock()

    db = ObjectDatabase()
    device = DeviceObject(
        device_instance,
        object_name="test-device",
        vendor_name="test-vendor",
        vendor_identifier=42,
        model_name="test-model",
        firmware_revision="1.0",
        application_software_version="1.0",
    )
    db.add(device)
    return app, db, device


class TestEncodePropertyValue:
    def test_encode_unsigned(self):
        result = _encode_property_value(42)
        # Application tag 2 (unsigned), length, value
        assert result[0] >> 4 == 2  # tag number

    def test_encode_string(self):
        result = _encode_property_value("hello")
        assert result[0] >> 4 == 7  # character string tag

    def test_encode_object_identifier(self):
        result = _encode_property_value(ObjectIdentifier(ObjectType.DEVICE, 1))
        assert result[0] == 0xC4  # application tag 12, length 4

    def test_encode_bitstring(self):
        result = _encode_property_value(BitString(b"\xff", 0))
        assert result[0] >> 4 == 8  # bit string tag

    def test_encode_segmentation(self):
        result = _encode_property_value(Segmentation.BOTH)
        assert result[0] >> 4 == 9  # enumerated tag

    def test_encode_list_of_object_ids(self):
        items = [
            ObjectIdentifier(ObjectType.DEVICE, 1),
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 2),
        ]
        result = _encode_property_value(items)
        # Should contain two object identifiers
        assert len(result) == 10  # 5 bytes each (1 tag + 4 data)

    def test_encode_empty_list(self):
        result = _encode_property_value([])
        assert result == b""


class TestHandleReadProperty:
    def test_read_object_name(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
        )

        async def run():
            result = await handlers.handle_read_property(12, request.encode(), SOURCE)
            ack = ReadPropertyACK.decode(result)
            assert ack.object_identifier.object_type == ObjectType.DEVICE
            assert ack.property_identifier == PropertyIdentifier.OBJECT_NAME
            assert len(ack.property_value) > 0

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_protocol_version(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.PROTOCOL_VERSION,
        )

        async def run():
            result = await handlers.handle_read_property(12, request.encode(), SOURCE)
            ack = ReadPropertyACK.decode(result)
            assert ack.property_identifier == PropertyIdentifier.PROTOCOL_VERSION

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_read_property(12, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_unknown_property_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        # PRESENT_VALUE is not defined on a Device object
        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_read_property(12, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_wildcard_device_instance(self):
        """Wildcard instance 4194303 resolves to local device (Clause 15.5.2)."""
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 4194303),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
        )

        async def run():
            result = await handlers.handle_read_property(12, request.encode(), SOURCE)
            ack = ReadPropertyACK.decode(result)
            # ACK should contain the actual device instance, not the wildcard
            assert ack.object_identifier.instance_number == 42
            assert ack.object_identifier.object_type == ObjectType.DEVICE

        asyncio.get_event_loop().run_until_complete(run())


class TestHandleWriteProperty:
    def test_write_object_name(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=b"\x75\x0a\x00new-name!",
        )

        async def run():
            result = await handlers.handle_write_property(15, request.encode(), SOURCE)
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_read_only_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_IDENTIFIER,
            property_value=b"\xc4\x02\x00\x00\x01",
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_write_property(15, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x00\x00\x00\x00",
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_write_property(15, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_write_wildcard_device_instance(self):
        """Wildcard instance 4194303 resolves to local device (Clause 15.9)."""
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 4194303),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=b"\x75\x0a\x00new-name!",
        )

        async def run():
            result = await handlers.handle_write_property(15, request.encode(), SOURCE)
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())


class TestHandleWhoIs:
    def test_who_is_no_range_responds(self):
        app, db, device = _make_app(device_instance=1234)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest()

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_in_range_responds(self):
        app, db, device = _make_app(device_instance=500)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=1000)

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_out_of_range_no_response(self):
        app, db, device = _make_app(device_instance=5000)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=1000)

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_not_called()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_exact_match(self):
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=42, high_limit=42)

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_at_lower_bound(self):
        app, db, device = _make_app(device_instance=100)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=200)

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_at_upper_bound(self):
        app, db, device = _make_app(device_instance=200)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=200)

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            app.unconfirmed_request.assert_called_once()

        asyncio.get_event_loop().run_until_complete(run())

    def test_who_is_iam_uses_device_segmentation(self):
        """I-Am response segmentation_supported must match device object."""
        from bac_py.services.who_is import IAmRequest

        app, db, device = _make_app(device_instance=1234)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest()

        async def run():
            await handlers.handle_who_is(8, request.encode(), SOURCE)
            call_args = app.unconfirmed_request.call_args
            service_data = call_args.kwargs.get(
                "service_data", call_args[1].get("service_data") if len(call_args) > 1 else None
            )
            iam = IAmRequest.decode(service_data)
            # Device defaults to Segmentation.BOTH
            assert iam.segmentation_supported == Segmentation.BOTH

        asyncio.get_event_loop().run_until_complete(run())


class TestDefaultServerHandlersRegister:
    def test_register_installs_handlers(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)
        handlers.register()

        registry = app.service_registry
        assert registry.register_confirmed.call_count == 6
        assert registry.register_unconfirmed.call_count == 1


class TestHandleReadPropertyMultiple:
    def test_rpm_read_multiple_properties(self):
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                        PropertyReference(PropertyIdentifier.PROTOCOL_VERSION),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            assert len(ack.list_of_read_access_results) == 1
            res = ack.list_of_read_access_results[0]
            assert res.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
            assert len(res.list_of_results) == 2
            assert res.list_of_results[0].property_value is not None
            assert res.list_of_results[0].property_access_error is None
            assert res.list_of_results[1].property_value is not None

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_per_property_error(self):
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                        PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            # Object_Name succeeds
            assert res.list_of_results[0].property_value is not None
            assert res.list_of_results[0].property_access_error is None
            # Present_Value fails (not on Device)
            assert res.list_of_results[1].property_value is None
            assert res.list_of_results[1].property_access_error is not None
            assert res.list_of_results[1].property_access_error[1] == ErrorCode.UNKNOWN_PROPERTY

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_unknown_object(self):
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            assert len(res.list_of_results) == 1
            assert res.list_of_results[0].property_access_error is not None
            assert res.list_of_results[0].property_access_error[1] == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_wildcard_device_instance(self):
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 4194303),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            assert res.object_identifier.instance_number == 42
            assert res.list_of_results[0].property_value is not None

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_multiple_objects(self):
        import bac_py.objects  # noqa: F401
        from bac_py.objects.analog import AnalogInputObject
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                    ],
                ),
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_NAME),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            assert len(ack.list_of_read_access_results) == 2
            assert ack.list_of_read_access_results[0].object_identifier == (
                ObjectIdentifier(ObjectType.DEVICE, 1)
            )
            assert ack.list_of_read_access_results[1].object_identifier == (
                ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_all_properties(self):
        """Property identifier ALL expands to all properties on the object."""
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.ALL),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            # Should have many properties, not just an error for "ALL"
            assert len(res.list_of_results) > 5
            # Verify key properties are present
            prop_ids = {elem.property_identifier for elem in res.list_of_results}
            assert PropertyIdentifier.OBJECT_IDENTIFIER in prop_ids
            assert PropertyIdentifier.OBJECT_NAME in prop_ids
            assert PropertyIdentifier.OBJECT_TYPE in prop_ids
            assert PropertyIdentifier.PROTOCOL_VERSION in prop_ids
            assert PropertyIdentifier.PROPERTY_LIST in prop_ids
            # All results should be successful (no errors)
            for elem in res.list_of_results:
                assert elem.property_value is not None, (
                    f"Property {elem.property_identifier} returned error "
                    f"{elem.property_access_error}"
                )

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_required_properties(self):
        """Property identifier REQUIRED expands to only required properties."""
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.REQUIRED),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            prop_ids = {elem.property_identifier for elem in res.list_of_results}
            # Should include required properties
            assert PropertyIdentifier.OBJECT_IDENTIFIER in prop_ids
            assert PropertyIdentifier.OBJECT_NAME in prop_ids
            assert PropertyIdentifier.PROTOCOL_VERSION in prop_ids
            # Should NOT include optional properties like DESCRIPTION
            assert PropertyIdentifier.DESCRIPTION not in prop_ids

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_optional_properties(self):
        """Property identifier OPTIONAL expands to only optional properties present."""
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        # Set an optional property so it shows up
        device._properties[PropertyIdentifier.DESCRIPTION] = "test description"
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OPTIONAL),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            prop_ids = {elem.property_identifier for elem in res.list_of_results}
            # DESCRIPTION is optional and present
            assert PropertyIdentifier.DESCRIPTION in prop_ids
            # Required properties should NOT be included
            assert PropertyIdentifier.OBJECT_IDENTIFIER not in prop_ids
            assert PropertyIdentifier.OBJECT_NAME not in prop_ids

        asyncio.get_event_loop().run_until_complete(run())

    def test_rpm_all_unknown_object(self):
        """ALL on an unknown object still returns UNKNOWN_OBJECT error."""
        from bac_py.services.read_property_multiple import (
            PropertyReference,
            ReadAccessSpecification,
            ReadPropertyMultipleACK,
            ReadPropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.ALL),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
            ack = ReadPropertyMultipleACK.decode(result)
            res = ack.list_of_read_access_results[0]
            # Should have one error result for the ALL reference
            assert len(res.list_of_results) == 1
            assert res.list_of_results[0].property_access_error is not None
            assert res.list_of_results[0].property_access_error[1] == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())


class TestHandleWritePropertyMultiple:
    def test_wpm_write_success(self):
        from bac_py.services.write_property_multiple import (
            PropertyValue,
            WriteAccessSpecification,
            WritePropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            property_value=b"\x75\x0a\x00new-name!",
                        ),
                    ],
                ),
            ]
        )

        async def run():
            result = await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())

    def test_wpm_unknown_object_raises(self):
        from bac_py.services.write_property_multiple import (
            PropertyValue,
            WriteAccessSpecification,
            WritePropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x44\x00\x00\x00\x00",
                        ),
                    ],
                ),
            ]
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_wpm_read_only_raises(self):
        from bac_py.services.write_property_multiple import (
            PropertyValue,
            WriteAccessSpecification,
            WritePropertyMultipleRequest,
        )

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_IDENTIFIER,
                            property_value=b"\xc4\x02\x00\x00\x01",
                        ),
                    ],
                ),
            ]
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

        asyncio.get_event_loop().run_until_complete(run())


class TestHandleReadRange:
    def test_read_range_full_list(self):
        from bac_py.services.read_range import (
            ReadRangeACK,
            ReadRangeRequest,
        )

        app, db, device = _make_app()
        # Populate object list with the device
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
        )

        async def run():
            result = await handlers.handle_read_range(26, request.encode(), SOURCE)
            ack = ReadRangeACK.decode(result)
            assert ack.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
            assert ack.result_flags.first_item is True
            assert ack.result_flags.last_item is True
            assert ack.result_flags.more_items is False

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_range_by_position(self):
        import bac_py.objects  # noqa: F401
        from bac_py.objects.analog import AnalogInputObject
        from bac_py.services.read_range import (
            RangeByPosition,
            ReadRangeACK,
            ReadRangeRequest,
        )

        app, db, device = _make_app()
        for i in range(1, 6):
            db.add(AnalogInputObject(i, object_name=f"AI-{i}"))
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            range=RangeByPosition(reference_index=2, count=2),
        )

        async def run():
            result = await handlers.handle_read_range(26, request.encode(), SOURCE)
            ack = ReadRangeACK.decode(result)
            assert ack.item_count == 2
            assert ack.result_flags.first_item is False
            assert ack.result_flags.last_item is False
            assert ack.result_flags.more_items is True

        asyncio.get_event_loop().run_until_complete(run())

    def test_read_range_unknown_object_raises(self):
        from bac_py.services.read_range import ReadRangeRequest

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_read_range(26, request.encode(), SOURCE)
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())
