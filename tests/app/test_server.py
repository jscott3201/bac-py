"""Tests for BACnet server handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.app.server import DefaultServerHandlers, _encode_property_value
from bac_py.encoding.primitives import encode_application_unsigned
from bac_py.network.address import BACnetAddress
from bac_py.objects.analog import AnalogInputObject
from bac_py.objects.base import ObjectDatabase, PropertyAccess, PropertyDefinition
from bac_py.objects.device import DeviceObject
from bac_py.objects.event_enrollment import EventEnrollmentObject
from bac_py.services.alarm_summary import (
    AlarmSummary,
    GetAlarmSummaryACK,
    GetAlarmSummaryRequest,
    GetEnrollmentSummaryACK,
    GetEnrollmentSummaryRequest,
    GetEventInformationACK,
    GetEventInformationRequest,
)
from bac_py.services.errors import BACnetError
from bac_py.services.event_notification import (
    AcknowledgeAlarmRequest,
    EventNotificationRequest,
)
from bac_py.services.list_element import AddListElementRequest, RemoveListElementRequest
from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.services.who_is import WhoIsRequest
from bac_py.services.write_property import WritePropertyRequest
from bac_py.types.constructed import BACnetTimeStamp
from bac_py.types.enums import (
    AcknowledgmentFilter,
    ConfirmedServiceChoice,
    ErrorCode,
    EventState,
    EventType,
    NotifyType,
    ObjectType,
    PropertyIdentifier,
    Segmentation,
)
from bac_py.types.primitives import BitString, ObjectIdentifier

SOURCE = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

# Use a writable list property that we'll add to the PROPERTY_DEFINITIONS
_LIST_PROP = PropertyIdentifier.TIME_SYNCHRONIZATION_RECIPIENTS


def _make_app(device_instance: int = 1):
    """Create a mock application with a device for testing."""
    app = MagicMock()
    app.config = MagicMock()
    app.config.max_apdu_length = 1476
    app.config.vendor_id = 42
    app.config.password = None
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


def _make_app_and_handlers(device_instance: int = 1):
    """Create a mock application, object database, and server handlers."""
    app = MagicMock()
    app.config = MagicMock()
    app.config.max_apdu_length = 1476
    app.config.vendor_id = 42
    app.config.password = None
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

    handlers = DefaultServerHandlers(app, db, device)
    return app, db, device, handlers


def _make_app_with_list_prop(device_instance: int = 1):
    """Create a mock application with a device that has a writable list property."""
    app = MagicMock()
    app.config = MagicMock()
    app.config.max_apdu_length = 1476
    app.config.vendor_id = 42
    app.config.password = None
    app.service_registry = MagicMock()
    app.unconfirmed_request = MagicMock()
    app.cov_manager = None

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
    # Add a writable list property to the device for testing
    device.PROPERTY_DEFINITIONS = {
        **device.PROPERTY_DEFINITIONS,
        _LIST_PROP: PropertyDefinition(
            _LIST_PROP,
            list,
            PropertyAccess.READ_WRITE,
            required=False,
        ),
    }
    db.add(device)
    return app, db, device


# ---------------------------------------------------------------------------
# _encode_property_value tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ReadProperty handler tests
# ---------------------------------------------------------------------------


class TestHandleReadProperty:
    async def test_read_object_name(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
        )

        result = await handlers.handle_read_property(12, request.encode(), SOURCE)
        ack = ReadPropertyACK.decode(result)
        assert ack.object_identifier.object_type == ObjectType.DEVICE
        assert ack.property_identifier == PropertyIdentifier.OBJECT_NAME
        assert len(ack.property_value) > 0

    async def test_read_protocol_version(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.PROTOCOL_VERSION,
        )

        result = await handlers.handle_read_property(12, request.encode(), SOURCE)
        ack = ReadPropertyACK.decode(result)
        assert ack.property_identifier == PropertyIdentifier.PROTOCOL_VERSION

    async def test_read_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_read_property(12, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_read_unknown_property_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        # PRESENT_VALUE is not defined on a Device object
        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_read_property(12, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    async def test_read_wildcard_device_instance(self):
        """Wildcard instance 4194303 resolves to local device (Clause 15.5.2)."""
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 4194303),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
        )

        result = await handlers.handle_read_property(12, request.encode(), SOURCE)
        ack = ReadPropertyACK.decode(result)
        # ACK should contain the actual device instance, not the wildcard
        assert ack.object_identifier.instance_number == 42
        assert ack.object_identifier.object_type == ObjectType.DEVICE


# ---------------------------------------------------------------------------
# WriteProperty handler tests
# ---------------------------------------------------------------------------


class TestHandleWriteProperty:
    async def test_write_object_name(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=b"\x75\x0a\x00new-name!",
        )

        result = await handlers.handle_write_property(15, request.encode(), SOURCE)
        assert result is None  # SimpleACK

    async def test_write_read_only_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_IDENTIFIER,
            property_value=b"\xc4\x02\x00\x00\x01",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_write_property(15, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    async def test_write_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x00\x00\x00\x00",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_write_property(15, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_write_wildcard_device_instance(self):
        """Wildcard instance 4194303 resolves to local device (Clause 15.9)."""
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = WritePropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 4194303),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=b"\x75\x0a\x00new-name!",
        )

        result = await handlers.handle_write_property(15, request.encode(), SOURCE)
        assert result is None  # SimpleACK


# ---------------------------------------------------------------------------
# WhoIs handler tests
# ---------------------------------------------------------------------------


class TestHandleWhoIs:
    async def test_who_is_no_range_responds(self):
        app, db, device = _make_app(device_instance=1234)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest()

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_is_in_range_responds(self):
        app, db, device = _make_app(device_instance=500)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=1000)

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_is_out_of_range_no_response(self):
        app, db, device = _make_app(device_instance=5000)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=1000)

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_not_called()

    async def test_who_is_exact_match(self):
        app, db, device = _make_app(device_instance=42)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=42, high_limit=42)

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_is_at_lower_bound(self):
        app, db, device = _make_app(device_instance=100)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=200)

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_is_at_upper_bound(self):
        app, db, device = _make_app(device_instance=200)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest(low_limit=100, high_limit=200)

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_is_iam_uses_device_segmentation(self):
        """I-Am response segmentation_supported must match device object."""
        from bac_py.services.who_is import IAmRequest

        app, db, device = _make_app(device_instance=1234)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoIsRequest()

        await handlers.handle_who_is(8, request.encode(), SOURCE)
        call_args = app.unconfirmed_request.call_args
        service_data = call_args.kwargs.get(
            "service_data", call_args[1].get("service_data") if len(call_args) > 1 else None
        )
        iam = IAmRequest.decode(service_data)
        # Device defaults to Segmentation.BOTH
        assert iam.segmentation_supported == Segmentation.BOTH


# ---------------------------------------------------------------------------
# DefaultServerHandlers.register tests
# ---------------------------------------------------------------------------


class TestDefaultServerHandlersRegister:
    def test_register_installs_handlers(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)
        handlers.register()

        registry = app.service_registry
        assert registry.register_confirmed.call_count == 28
        assert registry.register_unconfirmed.call_count == 11


# ---------------------------------------------------------------------------
# ReadPropertyMultiple handler tests
# ---------------------------------------------------------------------------


class TestHandleReadPropertyMultiple:
    async def test_rpm_read_multiple_properties(self):
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        assert len(ack.list_of_read_access_results) == 1
        res = ack.list_of_read_access_results[0]
        assert res.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert len(res.list_of_results) == 2
        assert res.list_of_results[0].property_value is not None
        assert res.list_of_results[0].property_access_error is None
        assert res.list_of_results[1].property_value is not None

    async def test_rpm_per_property_error(self):
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

    async def test_rpm_unknown_object(self):
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        res = ack.list_of_read_access_results[0]
        assert len(res.list_of_results) == 1
        assert res.list_of_results[0].property_access_error is not None
        assert res.list_of_results[0].property_access_error[1] == ErrorCode.UNKNOWN_OBJECT

    async def test_rpm_wildcard_device_instance(self):
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        res = ack.list_of_read_access_results[0]
        assert res.object_identifier.instance_number == 42
        assert res.list_of_results[0].property_value is not None

    async def test_rpm_multiple_objects(self):
        import bac_py.objects  # noqa: F401
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        assert len(ack.list_of_read_access_results) == 2
        assert ack.list_of_read_access_results[0].object_identifier == (
            ObjectIdentifier(ObjectType.DEVICE, 1)
        )
        assert ack.list_of_read_access_results[1].object_identifier == (
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        )

    async def test_rpm_all_properties(self):
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
                f"Property {elem.property_identifier} returned error {elem.property_access_error}"
            )

    async def test_rpm_required_properties(self):
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

    async def test_rpm_optional_properties(self):
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        res = ack.list_of_read_access_results[0]
        prop_ids = {elem.property_identifier for elem in res.list_of_results}
        # DESCRIPTION is optional and present
        assert PropertyIdentifier.DESCRIPTION in prop_ids
        # Required properties should NOT be included
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in prop_ids
        assert PropertyIdentifier.OBJECT_NAME not in prop_ids

    async def test_rpm_all_unknown_object(self):
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

        result = await handlers.handle_read_property_multiple(14, request.encode(), SOURCE)
        ack = ReadPropertyMultipleACK.decode(result)
        res = ack.list_of_read_access_results[0]
        # Should have one error result for the ALL reference
        assert len(res.list_of_results) == 1
        assert res.list_of_results[0].property_access_error is not None
        assert res.list_of_results[0].property_access_error[1] == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# WritePropertyMultiple handler tests
# ---------------------------------------------------------------------------


class TestHandleWritePropertyMultiple:
    async def test_wpm_write_success(self):
        from bac_py.services.common import BACnetPropertyValue
        from bac_py.services.write_property_multiple import (
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
                        BACnetPropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            value=b"\x75\x0a\x00new-name!",
                        ),
                    ],
                ),
            ]
        )

        result = await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
        assert result is None  # SimpleACK

    async def test_wpm_unknown_object_raises(self):
        from bac_py.services.common import BACnetPropertyValue
        from bac_py.services.write_property_multiple import (
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
                        BACnetPropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            value=b"\x44\x00\x00\x00\x00",
                        ),
                    ],
                ),
            ]
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_wpm_read_only_raises(self):
        from bac_py.services.common import BACnetPropertyValue
        from bac_py.services.write_property_multiple import (
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
                        BACnetPropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_IDENTIFIER,
                            value=b"\xc4\x02\x00\x00\x01",
                        ),
                    ],
                ),
            ]
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_write_property_multiple(16, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED


# ---------------------------------------------------------------------------
# ReadRange handler tests
# ---------------------------------------------------------------------------


class TestHandleReadRange:
    async def test_read_range_full_list(self):
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

        result = await handlers.handle_read_range(26, request.encode(), SOURCE)
        ack = ReadRangeACK.decode(result)
        assert ack.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert ack.result_flags.first_item is True
        assert ack.result_flags.last_item is True
        assert ack.result_flags.more_items is False

    async def test_read_range_by_position(self):
        import bac_py.objects  # noqa: F401
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

        result = await handlers.handle_read_range(26, request.encode(), SOURCE)
        ack = ReadRangeACK.decode(result)
        assert ack.item_count == 2
        assert ack.result_flags.first_item is False
        assert ack.result_flags.last_item is False
        assert ack.result_flags.more_items is True

    async def test_read_range_unknown_object_raises(self):
        from bac_py.services.read_range import ReadRangeRequest

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReadRangeRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_read_range(26, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# DeviceCommunicationControl handler tests
# ---------------------------------------------------------------------------


class TestHandleDeviceCommunicationControl:
    async def test_dcc_returns_simple_ack(self):
        from bac_py.services.device_mgmt import DeviceCommunicationControlRequest
        from bac_py.types.enums import EnableDisable

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.ENABLE,
        )

        result = await handlers.handle_device_communication_control(17, request.encode(), SOURCE)
        assert result is None

    async def test_dcc_with_duration_and_password(self):
        from bac_py.services.device_mgmt import DeviceCommunicationControlRequest
        from bac_py.types.enums import EnableDisable

        app, db, device = _make_app()
        app.config.password = "secret"
        handlers = DefaultServerHandlers(app, db, device)

        request = DeviceCommunicationControlRequest(
            enable_disable=EnableDisable.DISABLE,
            time_duration=60,
            password="secret",
        )

        result = await handlers.handle_device_communication_control(17, request.encode(), SOURCE)
        assert result is None


# ---------------------------------------------------------------------------
# ReinitializeDevice handler tests
# ---------------------------------------------------------------------------


class TestHandleReinitializeDevice:
    async def test_reinitialize_returns_simple_ack(self):
        from bac_py.services.device_mgmt import ReinitializeDeviceRequest
        from bac_py.types.enums import ReinitializedState

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.COLDSTART,
        )

        result = await handlers.handle_reinitialize_device(20, request.encode(), SOURCE)
        assert result is None

    async def test_reinitialize_warmstart(self):
        from bac_py.services.device_mgmt import ReinitializeDeviceRequest
        from bac_py.types.enums import ReinitializedState

        app, db, device = _make_app()
        app.config.password = "mypass"
        handlers = DefaultServerHandlers(app, db, device)

        request = ReinitializeDeviceRequest(
            reinitialized_state=ReinitializedState.WARMSTART,
            password="mypass",
        )

        result = await handlers.handle_reinitialize_device(20, request.encode(), SOURCE)
        assert result is None


# ---------------------------------------------------------------------------
# TimeSynchronization handler tests
# ---------------------------------------------------------------------------


class TestHandleTimeSynchronization:
    async def test_time_sync_processes(self):
        from bac_py.services.device_mgmt import TimeSynchronizationRequest
        from bac_py.types.primitives import BACnetDate, BACnetTime

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = TimeSynchronizationRequest(
            date=BACnetDate(2025, 1, 15, 3),
            time=BACnetTime(10, 30, 0, 0),
        )

        result = await handlers.handle_time_synchronization(6, request.encode(), SOURCE)
        assert result is None

    async def test_utc_time_sync_processes(self):
        from bac_py.services.device_mgmt import UTCTimeSynchronizationRequest
        from bac_py.types.primitives import BACnetDate, BACnetTime

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = UTCTimeSynchronizationRequest(
            date=BACnetDate(2025, 1, 15, 3),
            time=BACnetTime(18, 30, 0, 0),
        )

        result = await handlers.handle_utc_time_synchronization(9, request.encode(), SOURCE)
        assert result is None


# ---------------------------------------------------------------------------
# AtomicReadFile handler tests
# ---------------------------------------------------------------------------


class TestHandleAtomicReadFile:
    async def test_stream_read(self):
        from bac_py.objects.file import FileObject
        from bac_py.services.file_access import (
            AtomicReadFileACK,
            AtomicReadFileRequest,
            StreamReadAccess,
            StreamReadACK,
        )
        from bac_py.types.enums import FileAccessMethod

        app, db, device = _make_app()
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello BACnet")
        db.add(f)
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamReadAccess(
                file_start_position=0,
                requested_octet_count=100,
            ),
        )

        result = await handlers.handle_atomic_read_file(6, request.encode(), SOURCE)
        ack = AtomicReadFileACK.decode(result)
        assert ack.end_of_file is True
        assert isinstance(ack.access_method, StreamReadACK)
        assert ack.access_method.file_data == b"Hello BACnet"

    async def test_record_read(self):
        from bac_py.objects.file import FileObject
        from bac_py.services.file_access import (
            AtomicReadFileACK,
            AtomicReadFileRequest,
            RecordReadAccess,
            RecordReadACK,
        )
        from bac_py.types.enums import FileAccessMethod

        app, db, device = _make_app()
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        f.write_records(0, [b"rec1", b"rec2"])
        db.add(f)
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=RecordReadAccess(
                file_start_record=0,
                requested_record_count=10,
            ),
        )

        result = await handlers.handle_atomic_read_file(6, request.encode(), SOURCE)
        ack = AtomicReadFileACK.decode(result)
        assert ack.end_of_file is True
        assert isinstance(ack.access_method, RecordReadACK)
        assert ack.access_method.file_record_data == [b"rec1", b"rec2"]

    async def test_unknown_object_raises(self):
        from bac_py.services.file_access import AtomicReadFileRequest, StreamReadAccess

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 999),
            access_method=StreamReadAccess(
                file_start_position=0,
                requested_octet_count=10,
            ),
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_atomic_read_file(6, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_non_file_object_raises(self):
        from bac_py.services.file_access import AtomicReadFileRequest, StreamReadAccess

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicReadFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            access_method=StreamReadAccess(
                file_start_position=0,
                requested_octet_count=10,
            ),
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_atomic_read_file(6, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.INCONSISTENT_OBJECT_TYPE


# ---------------------------------------------------------------------------
# AtomicWriteFile handler tests
# ---------------------------------------------------------------------------


class TestHandleAtomicWriteFile:
    async def test_stream_write(self):
        from bac_py.objects.file import FileObject
        from bac_py.services.file_access import (
            AtomicWriteFileACK,
            AtomicWriteFileRequest,
            StreamWriteAccess,
        )
        from bac_py.types.enums import FileAccessMethod

        app, db, device = _make_app()
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        db.add(f)
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamWriteAccess(
                file_start_position=0,
                file_data=b"Hello",
            ),
        )

        result = await handlers.handle_atomic_write_file(7, request.encode(), SOURCE)
        ack = AtomicWriteFileACK.decode(result)
        assert ack.is_stream is True
        assert ack.file_start == 0
        data, _ = f.read_stream(0, 100)
        assert data == b"Hello"

    async def test_stream_append(self):
        from bac_py.objects.file import FileObject
        from bac_py.services.file_access import (
            AtomicWriteFileACK,
            AtomicWriteFileRequest,
            StreamWriteAccess,
        )
        from bac_py.types.enums import FileAccessMethod

        app, db, device = _make_app()
        f = FileObject(1, file_access_method=FileAccessMethod.STREAM_ACCESS)
        f.write_stream(0, b"Hello ")
        db.add(f)
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=StreamWriteAccess(
                file_start_position=-1,
                file_data=b"World",
            ),
        )

        result = await handlers.handle_atomic_write_file(7, request.encode(), SOURCE)
        ack = AtomicWriteFileACK.decode(result)
        assert ack.file_start == 6
        data, _ = f.read_stream(0, 100)
        assert data == b"Hello World"

    async def test_record_write(self):
        from bac_py.objects.file import FileObject
        from bac_py.services.file_access import (
            AtomicWriteFileACK,
            AtomicWriteFileRequest,
            RecordWriteAccess,
        )
        from bac_py.types.enums import FileAccessMethod

        app, db, device = _make_app()
        f = FileObject(1, file_access_method=FileAccessMethod.RECORD_ACCESS)
        db.add(f)
        handlers = DefaultServerHandlers(app, db, device)

        request = AtomicWriteFileRequest(
            file_identifier=ObjectIdentifier(ObjectType.FILE, 1),
            access_method=RecordWriteAccess(
                file_start_record=0,
                record_count=2,
                file_record_data=[b"rec1", b"rec2"],
            ),
        )

        result = await handlers.handle_atomic_write_file(7, request.encode(), SOURCE)
        ack = AtomicWriteFileACK.decode(result)
        assert ack.is_stream is False
        assert ack.file_start == 0
        records, _ = f.read_records(0, 10)
        assert records == [b"rec1", b"rec2"]


# ---------------------------------------------------------------------------
# CreateObject handler tests
# ---------------------------------------------------------------------------


class TestHandleCreateObject:
    async def test_create_by_type(self):
        import bac_py.objects  # noqa: F401
        from bac_py.encoding.primitives import decode_object_identifier
        from bac_py.encoding.tags import decode_tag

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import CreateObjectRequest

        request = CreateObjectRequest(object_type=ObjectType.ANALOG_INPUT)

        result = await handlers.handle_create_object(10, request.encode(), SOURCE)
        tag, offset = decode_tag(result, 0)
        obj_type, instance = decode_object_identifier(result[offset : offset + tag.length])
        assert obj_type == ObjectType.ANALOG_INPUT
        assert instance == 1
        oid = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert db.get(oid) is not None

    async def test_create_by_identifier(self):
        import bac_py.objects  # noqa: F401
        from bac_py.encoding.primitives import decode_object_identifier
        from bac_py.encoding.tags import decode_tag

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import CreateObjectRequest

        request = CreateObjectRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 42),
        )

        result = await handlers.handle_create_object(10, request.encode(), SOURCE)
        tag, offset = decode_tag(result, 0)
        obj_type, instance = decode_object_identifier(result[offset : offset + tag.length])
        assert obj_type == ObjectType.ANALOG_INPUT
        assert instance == 42

    async def test_create_duplicate_raises(self):
        import bac_py.objects  # noqa: F401

        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import CreateObjectRequest

        db.add(AnalogInputObject(1, object_name="AI-1"))

        request = CreateObjectRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_create_object(10, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS

    async def test_create_unsupported_type_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import CreateObjectRequest

        request = CreateObjectRequest(object_type=ObjectType.NETWORK_SECURITY)

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_create_object(10, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_OBJECT_TYPE


# ---------------------------------------------------------------------------
# DeleteObject handler tests
# ---------------------------------------------------------------------------


class TestHandleDeleteObject:
    async def test_delete_object(self):
        import bac_py.objects  # noqa: F401

        app, db, device = _make_app()
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import DeleteObjectRequest

        request = DeleteObjectRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        result = await handlers.handle_delete_object(11, request.encode(), SOURCE)
        assert result is None
        assert db.get(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)) is None

    async def test_delete_device_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import DeleteObjectRequest

        request = DeleteObjectRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_delete_object(11, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.OBJECT_DELETION_NOT_PERMITTED

    async def test_delete_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.object_mgmt import DeleteObjectRequest

        request = DeleteObjectRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_delete_object(11, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# ListElement handler tests (from original test_server.py)
# ---------------------------------------------------------------------------


class TestHandleListElement:
    async def test_add_list_element_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=b"\xc4\x00\x00\x00\x01",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(8, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_add_list_element_unknown_property_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            list_of_elements=b"\xc4\x00\x00\x00\x01",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(8, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    async def test_add_list_element_read_only_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=b"\xc4\x00\x00\x00\x01",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(8, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    async def test_remove_list_element_unknown_object_raises(self):
        app, db, device = _make_app()
        handlers = DefaultServerHandlers(app, db, device)

        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=b"\xc4\x00\x00\x00\x01",
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_remove_list_element(9, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# WhoHas handler tests
# ---------------------------------------------------------------------------


class TestHandleWhoHas:
    async def test_who_has_by_id_found(self):
        import bac_py.objects  # noqa: F401

        app, db, device = _make_app(device_instance=100)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.who_has import WhoHasRequest

        request = WhoHasRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        await handlers.handle_who_has(7, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_has_by_name_found(self):
        import bac_py.objects  # noqa: F401

        app, db, device = _make_app(device_instance=100)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.who_has import WhoHasRequest

        request = WhoHasRequest(object_name="AI-1")

        await handlers.handle_who_has(7, request.encode(), SOURCE)
        app.unconfirmed_request.assert_called_once()

    async def test_who_has_not_found(self):
        app, db, device = _make_app(device_instance=100)
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.who_has import WhoHasRequest

        request = WhoHasRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
        )

        await handlers.handle_who_has(7, request.encode(), SOURCE)
        app.unconfirmed_request.assert_not_called()

    async def test_who_has_out_of_range(self):
        import bac_py.objects  # noqa: F401

        app, db, device = _make_app(device_instance=5000)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        from bac_py.services.who_has import WhoHasRequest

        request = WhoHasRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            low_limit=1,
            high_limit=100,
        )

        await handlers.handle_who_has(7, request.encode(), SOURCE)
        app.unconfirmed_request.assert_not_called()

    async def test_who_has_i_have_response(self):
        import bac_py.objects  # noqa: F401
        from bac_py.services.who_has import IHaveRequest, WhoHasRequest

        app, db, device = _make_app(device_instance=100)
        ai = AnalogInputObject(1, object_name="AI-1")
        db.add(ai)
        handlers = DefaultServerHandlers(app, db, device)

        request = WhoHasRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )

        await handlers.handle_who_has(7, request.encode(), SOURCE)
        call_args = app.unconfirmed_request.call_args
        service_data = call_args.kwargs.get(
            "service_data", call_args[1].get("service_data") if len(call_args) > 1 else None
        )
        ihave = IHaveRequest.decode(service_data)
        assert ihave.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert ihave.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert ihave.object_name == "AI-1"


# ---------------------------------------------------------------------------
# GetAlarmSummary handler tests
# ---------------------------------------------------------------------------


class TestGetAlarmSummary:
    @pytest.mark.asyncio
    async def test_no_alarms_returns_empty(self):
        """No objects in alarm state -> empty summary list."""
        _, _, _, handlers = _make_app_and_handlers()
        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 0

    @pytest.mark.asyncio
    async def test_object_in_alarm_returned(self):
        """An analog input in OFFNORMAL event state is included."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 1
        summary = ack.list_of_alarm_summaries[0]
        assert summary.object_identifier == ai.object_identifier
        assert summary.alarm_state == EventState.OFFNORMAL

    @pytest.mark.asyncio
    async def test_normal_objects_excluded(self):
        """Objects in NORMAL event state are not included."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.NORMAL
        db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 0

    @pytest.mark.asyncio
    async def test_multiple_alarms(self):
        """Multiple alarmed objects are all returned."""
        _, db, _, handlers = _make_app_and_handlers()
        for i in range(3):
            ai = AnalogInputObject(i + 1)
            ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
            ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
            db.add(ai)

        request_data = GetAlarmSummaryRequest().encode()
        result = await handlers.handle_get_alarm_summary(0, request_data, SOURCE)
        ack = GetAlarmSummaryACK.decode(result)
        assert len(ack.list_of_alarm_summaries) == 3


# ---------------------------------------------------------------------------
# GetEnrollmentSummary handler tests
# ---------------------------------------------------------------------------


class TestGetEnrollmentSummary:
    def _make_enrollment(
        self,
        db,
        instance,
        *,
        event_type=EventType.CHANGE_OF_VALUE,
        event_state=EventState.NORMAL,
        notification_class=0,
    ):
        """Create an EventEnrollmentObject with given properties."""
        obj_ref = MagicMock()
        obj_ref.object_identifier = ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        obj_ref.property_identifier = PropertyIdentifier.PRESENT_VALUE
        ee = EventEnrollmentObject(
            instance,
            event_type=event_type,
            object_property_reference=obj_ref,
        )
        ee._properties[PropertyIdentifier.EVENT_STATE] = event_state
        ee._properties[PropertyIdentifier.NOTIFICATION_CLASS] = notification_class
        ee._properties[PropertyIdentifier.EVENT_TYPE] = event_type
        db.add(ee)
        return ee

    @pytest.mark.asyncio
    async def test_all_enrollments_returned(self):
        """With no extra filters, all enrollments match."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1)
        self._make_enrollment(db, 2)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 2

    @pytest.mark.asyncio
    async def test_event_state_filter(self):
        """Only enrollments matching the event state filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, event_state=EventState.NORMAL)
        self._make_enrollment(db, 2, event_state=EventState.OFFNORMAL)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            event_state_filter=EventState.OFFNORMAL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].event_state == EventState.OFFNORMAL

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        """Only enrollments matching the event type filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, event_type=EventType.CHANGE_OF_VALUE)
        self._make_enrollment(db, 2, event_type=EventType.OUT_OF_RANGE)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            event_type_filter=EventType.OUT_OF_RANGE,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].event_type == EventType.OUT_OF_RANGE

    @pytest.mark.asyncio
    async def test_notification_class_filter(self):
        """Only enrollments matching the notification class filter are returned."""
        _, db, _, handlers = _make_app_and_handlers()
        self._make_enrollment(db, 1, notification_class=5)
        self._make_enrollment(db, 2, notification_class=10)

        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
            notification_class_filter=10,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 1
        assert ack.list_of_enrollment_summaries[0].notification_class == 10

    @pytest.mark.asyncio
    async def test_no_enrollments(self):
        """Empty database returns empty list."""
        _, _, _, handlers = _make_app_and_handlers()
        request = GetEnrollmentSummaryRequest(
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        result = await handlers.handle_get_enrollment_summary(0, request.encode(), SOURCE)
        ack = GetEnrollmentSummaryACK.decode(result)
        assert len(ack.list_of_enrollment_summaries) == 0


# ---------------------------------------------------------------------------
# GetEventInformation handler tests
# ---------------------------------------------------------------------------


class TestGetEventInformation:
    @pytest.mark.asyncio
    async def test_no_events(self):
        """No objects in alarm -> empty event info list."""
        _, _, _, handlers = _make_app_and_handlers()
        request = GetEventInformationRequest()
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 0
        assert ack.more_events is False

    @pytest.mark.asyncio
    async def test_alarmed_object_included(self):
        """An object in alarm state appears in event information."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
        ai._properties[PropertyIdentifier.NOTIFY_TYPE] = NotifyType.ALARM
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, False]
        db.add(ai)

        request = GetEventInformationRequest()
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 1
        summary = ack.list_of_event_summaries[0]
        assert summary.object_identifier == ai.object_identifier
        assert summary.event_state == EventState.HIGH_LIMIT
        assert summary.notify_type == NotifyType.ALARM

    @pytest.mark.asyncio
    async def test_pagination_skip(self):
        """With last_received_object_identifier, skip until past that object."""
        _, db, _, handlers = _make_app_and_handlers()
        ai1 = AnalogInputObject(1)
        ai1._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai1._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai1)

        ai2 = AnalogInputObject(2)
        ai2._properties[PropertyIdentifier.EVENT_STATE] = EventState.HIGH_LIMIT
        ai2._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, True]
        db.add(ai2)

        # Request with last_received as ai1 -> should skip ai1, return ai2
        request = GetEventInformationRequest(
            last_received_object_identifier=ai1.object_identifier,
        )
        result = await handlers.handle_get_event_information(0, request.encode(), SOURCE)
        ack = GetEventInformationACK.decode(result)
        assert len(ack.list_of_event_summaries) == 1
        assert ack.list_of_event_summaries[0].object_identifier == ai2.object_identifier


# ---------------------------------------------------------------------------
# AcknowledgeAlarm handler tests
# ---------------------------------------------------------------------------


class TestAcknowledgeAlarm:
    @pytest.mark.asyncio
    async def test_acknowledge_offnormal(self):
        """Acknowledging an OFFNORMAL transition sets acked_transitions[0]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.OFFNORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [False, True, True]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None  # SimpleACK
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][0] is True

    @pytest.mark.asyncio
    async def test_acknowledge_fault(self):
        """Acknowledging a FAULT transition sets acked_transitions[1]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.FAULT
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, False, True]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.FAULT,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][1] is True

    @pytest.mark.asyncio
    async def test_acknowledge_normal(self):
        """Acknowledging a NORMAL transition sets acked_transitions[2]."""
        _, db, _, handlers = _make_app_and_handlers()
        ai = AnalogInputObject(1)
        ai._properties[PropertyIdentifier.EVENT_STATE] = EventState.NORMAL
        ai._properties[PropertyIdentifier.ACKED_TRANSITIONS] = [True, True, False]
        db.add(ai)

        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ai.object_identifier,
            event_state_acknowledged=EventState.NORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        result = await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert result is None
        assert ai._properties[PropertyIdentifier.ACKED_TRANSITIONS][2] is True

    @pytest.mark.asyncio
    async def test_unknown_object_raises_error(self):
        """Acknowledging a non-existent object raises BACnetError."""
        _, _, _, handlers = _make_app_and_handlers()
        ts = BACnetTimeStamp(choice=1, value=0)
        request = AcknowledgeAlarmRequest(
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="operator",
            time_of_acknowledgment=ts,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_acknowledge_alarm(0, request.encode(), SOURCE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT


# ---------------------------------------------------------------------------
# Event notification handler tests
# ---------------------------------------------------------------------------


class TestEventNotificationHandlers:
    def _make_notification(self) -> EventNotificationRequest:
        return EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=100,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.HIGH_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
        )

    @pytest.mark.asyncio
    async def test_confirmed_event_notification_returns_simple_ack(self):
        """Confirmed event notification handler returns None (SimpleACK)."""
        _, _, _, handlers = _make_app_and_handlers()
        notification = self._make_notification()
        result = await handlers.handle_confirmed_event_notification(
            0,
            notification.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unconfirmed_event_notification_returns_none(self):
        """Unconfirmed event notification handler returns None."""
        _, _, _, handlers = _make_app_and_handlers()
        notification = self._make_notification()
        result = await handlers.handle_unconfirmed_event_notification(
            0,
            notification.encode(),
            SOURCE,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Client alarm method tests
# ---------------------------------------------------------------------------


class TestClientAlarmMethods:
    """Test client methods build correct requests and decode responses."""

    def _make_client(self):
        """Create a BACnetClient with mocked application."""
        from bac_py.app.client import BACnetClient

        app = MagicMock()
        app.confirmed_request = AsyncMock()
        client = BACnetClient.__new__(BACnetClient)
        client._app = app
        client._default_timeout = 10.0
        return client, app

    @pytest.mark.asyncio
    async def test_acknowledge_alarm_sends_request(self):
        """acknowledge_alarm sends an AcknowledgeAlarm confirmed request."""
        client, app = self._make_client()
        app.confirmed_request.return_value = b""

        ts = BACnetTimeStamp(choice=1, value=0)
        await client.acknowledge_alarm(
            address=SOURCE,
            acknowledging_process_identifier=1,
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            event_state_acknowledged=EventState.OFFNORMAL,
            time_stamp=ts,
            acknowledgment_source="test",
            time_of_acknowledgment=ts,
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert call_kwargs.kwargs["service_choice"] == ConfirmedServiceChoice.ACKNOWLEDGE_ALARM

    @pytest.mark.asyncio
    async def test_get_alarm_summary_decodes_ack(self):
        """get_alarm_summary sends request and decodes response."""
        client, app = self._make_client()
        # Build a valid ACK response
        ack = GetAlarmSummaryACK(
            list_of_alarm_summaries=[
                AlarmSummary(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    alarm_state=EventState.HIGH_LIMIT,
                    acknowledged_transitions=BitString(b"\xe0", 5),
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_alarm_summary(address=SOURCE)
        assert len(result.list_of_alarm_summaries) == 1
        assert result.list_of_alarm_summaries[0].alarm_state == EventState.HIGH_LIMIT

    @pytest.mark.asyncio
    async def test_get_enrollment_summary_decodes_ack(self):
        """get_enrollment_summary sends request and decodes response."""
        client, app = self._make_client()
        from bac_py.services.alarm_summary import EnrollmentSummary

        ack = GetEnrollmentSummaryACK(
            list_of_enrollment_summaries=[
                EnrollmentSummary(
                    object_identifier=ObjectIdentifier(ObjectType.EVENT_ENROLLMENT, 1),
                    event_type=EventType.CHANGE_OF_VALUE,
                    event_state=EventState.NORMAL,
                    priority=0,
                    notification_class=1,
                ),
            ]
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_enrollment_summary(
            address=SOURCE,
            acknowledgment_filter=AcknowledgmentFilter.ALL,
        )
        assert len(result.list_of_enrollment_summaries) == 1

    @pytest.mark.asyncio
    async def test_get_event_information_decodes_ack(self):
        """get_event_information sends request and decodes response."""
        client, app = self._make_client()
        ack = GetEventInformationACK(
            list_of_event_summaries=[],
            more_events=False,
        )
        app.confirmed_request.return_value = ack.encode()

        result = await client.get_event_information(address=SOURCE)
        assert len(result.list_of_event_summaries) == 0
        assert result.more_events is False

    @pytest.mark.asyncio
    async def test_confirmed_event_notification_sends_request(self):
        """confirmed_event_notification sends the notification as confirmed request."""
        client, app = self._make_client()
        app.confirmed_request.return_value = b""

        notification = EventNotificationRequest(
            process_identifier=1,
            initiating_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            event_object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            time_stamp=BACnetTimeStamp(choice=1, value=0),
            notification_class=1,
            priority=100,
            event_type=EventType.OUT_OF_RANGE,
            notify_type=NotifyType.ALARM,
            to_state=EventState.HIGH_LIMIT,
            ack_required=True,
            from_state=EventState.NORMAL,
        )
        await client.confirmed_event_notification(
            address=SOURCE,
            notification=notification,
        )
        app.confirmed_request.assert_called_once()
        call_kwargs = app.confirmed_request.call_args
        assert (
            call_kwargs.kwargs["service_choice"]
            == ConfirmedServiceChoice.CONFIRMED_EVENT_NOTIFICATION
        )


# ---------------------------------------------------------------------------
# AddListElement integration tests (from test_list_element_handlers.py)
# ---------------------------------------------------------------------------


class TestAddListElement:
    async def test_add_elements_to_existing_list(self):
        """Test adding elements to an existing list property."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        # Set up a list property on the device
        device._properties[_LIST_PROP] = [10, 20]

        # Build the list_of_elements: two unsigned values
        elements = encode_application_unsigned(30) + encode_application_unsigned(40)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        result = await handlers.handle_add_list_element(
            ConfirmedServiceChoice.ADD_LIST_ELEMENT,
            request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK

        prop = device._properties[_LIST_PROP]
        assert 30 in prop
        assert 40 in prop
        assert len(prop) == 4

    async def test_add_to_none_creates_list(self):
        """Test adding to a property that is None but has list datatype."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        # Property exists in definitions but has no value yet
        elements = encode_application_unsigned(42)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        result = await handlers.handle_add_list_element(
            ConfirmedServiceChoice.ADD_LIST_ELEMENT,
            request.encode(),
            SOURCE,
        )
        assert result is None

        prop = device._properties[_LIST_PROP]
        assert prop == [42]

    async def test_add_to_unknown_object_raises(self):
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    async def test_add_to_read_only_property_raises(self):
        """Test that adding to a read-only list property raises WRITE_ACCESS_DENIED."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        # DEVICE_ADDRESS_BINDING is a read-only list property on Device
        elements = encode_application_unsigned(1)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.DEVICE_ADDRESS_BINDING,
            list_of_elements=elements,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    async def test_add_to_non_list_property_raises(self):
        """Test that adding to a non-list property raises PROPERTY_IS_NOT_A_LIST."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        # APDU_TIMEOUT is a writable int property (not a list)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.APDU_TIMEOUT,
            list_of_elements=elements,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_add_list_element(
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_A_LIST


# ---------------------------------------------------------------------------
# RemoveListElement integration tests (from test_list_element_handlers.py)
# ---------------------------------------------------------------------------


class TestRemoveListElement:
    async def test_remove_existing_elements(self):
        """Test removing elements from a list property."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        device._properties[_LIST_PROP] = [10, 20, 30, 40]

        elements = encode_application_unsigned(20) + encode_application_unsigned(40)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        result = await handlers.handle_remove_list_element(
            ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK

        prop = device._properties[_LIST_PROP]
        assert prop == [10, 30]

    async def test_remove_nonexistent_elements_silently_ignored(self):
        """Test that removing non-matching elements does not raise."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        device._properties[_LIST_PROP] = [10, 20]

        # Try to remove 99 which doesn't exist
        elements = encode_application_unsigned(99)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        result = await handlers.handle_remove_list_element(
            ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
            request.encode(),
            SOURCE,
        )
        assert result is None

        # Original list unchanged
        prop = device._properties[_LIST_PROP]
        assert prop == [10, 20]

    async def test_remove_from_non_list_raises(self):
        """Test removing from a non-list property raises error."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        # APDU_TIMEOUT is a writable int property, not a list
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.APDU_TIMEOUT,
            list_of_elements=elements,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_remove_list_element(
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_A_LIST

    async def test_remove_from_read_only_raises(self):
        """Test removing from a read-only list property raises WRITE_ACCESS_DENIED."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.DEVICE_ADDRESS_BINDING,
            list_of_elements=elements,
        )

        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_remove_list_element(
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED


# ---------------------------------------------------------------------------
# ConfirmedTextMessage handler tests
# ---------------------------------------------------------------------------


class TestHandleConfirmedTextMessage:
    @pytest.mark.asyncio
    async def test_basic_text_message_returns_simple_ack(self):
        """ConfirmedTextMessage handler returns None (SimpleACK)."""
        from bac_py.services.text_message import ConfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority

        _, _, _, handlers = _make_app_and_handlers()
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="Hello from device 100",
        )
        result = await handlers.handle_confirmed_text_message(
            ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK

    @pytest.mark.asyncio
    async def test_urgent_text_message(self):
        """ConfirmedTextMessage with urgent priority returns SimpleACK."""
        from bac_py.services.text_message import ConfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority

        _, _, _, handlers = _make_app_and_handlers()
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            message_priority=MessagePriority.URGENT,
            message="Emergency alert!",
        )
        result = await handlers.handle_confirmed_text_message(
            ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_text_message_with_numeric_class(self):
        """ConfirmedTextMessage with numeric message class returns SimpleACK."""
        from bac_py.services.text_message import ConfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority

        _, _, _, handlers = _make_app_and_handlers()
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="Classified message",
            message_class_numeric=42,
        )
        result = await handlers.handle_confirmed_text_message(
            ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_text_message_invokes_callback(self):
        """ConfirmedTextMessage invokes the text message callback if set."""
        from bac_py.services.text_message import ConfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority

        app, _, _, handlers = _make_app_and_handlers()
        callback = MagicMock()
        app._text_message_callback = callback

        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="callback test",
        )
        await handlers.handle_confirmed_text_message(
            ConfirmedServiceChoice.CONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0].message == "callback test"
        assert call_args[0][1] == SOURCE


# ---------------------------------------------------------------------------
# UnconfirmedTextMessage handler tests
# ---------------------------------------------------------------------------


class TestHandleUnconfirmedTextMessage:
    @pytest.mark.asyncio
    async def test_basic_unconfirmed_text_message(self):
        """UnconfirmedTextMessage handler returns None."""
        from bac_py.services.text_message import UnconfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority, UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        request = UnconfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="Unconfirmed hello",
        )
        result = await handlers.handle_unconfirmed_text_message(
            UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unconfirmed_text_message_invokes_callback(self):
        """UnconfirmedTextMessage invokes the text message callback if set."""
        from bac_py.services.text_message import UnconfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority, UnconfirmedServiceChoice

        app, _, _, handlers = _make_app_and_handlers()
        callback = MagicMock()
        app._text_message_callback = callback

        request = UnconfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            message_priority=MessagePriority.URGENT,
            message="urgent unconfirmed",
        )
        await handlers.handle_unconfirmed_text_message(
            UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        callback.assert_called_once()
        assert callback.call_args[0][0].message == "urgent unconfirmed"

    @pytest.mark.asyncio
    async def test_unconfirmed_text_message_with_character_class(self):
        """UnconfirmedTextMessage with character message class returns None."""
        from bac_py.services.text_message import UnconfirmedTextMessageRequest
        from bac_py.types.enums import MessagePriority, UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        request = UnconfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="classified by string",
            message_class_character="maintenance",
        )
        result = await handlers.handle_unconfirmed_text_message(
            UnconfirmedServiceChoice.UNCONFIRMED_TEXT_MESSAGE,
            request.encode(),
            SOURCE,
        )
        assert result is None


# ---------------------------------------------------------------------------
# WriteGroup handler tests
# ---------------------------------------------------------------------------


class TestHandleWriteGroup:
    @pytest.mark.asyncio
    async def test_write_group_basic(self):
        """WriteGroup handler processes request and returns None."""
        from bac_py.encoding.primitives import encode_application_unsigned
        from bac_py.services.write_group import GroupChannelValue, WriteGroupRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        # Encode a simple unsigned value as the channel value
        value_bytes = encode_application_unsigned(72)
        request = WriteGroupRequest(
            group_number=1,
            write_priority=8,
            change_list=[
                GroupChannelValue(channel=1, value=bytes(value_bytes)),
            ],
        )
        result = await handlers.handle_write_group(
            UnconfirmedServiceChoice.WRITE_GROUP,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_write_group_multiple_channels(self):
        """WriteGroup with multiple channel values processes without error."""
        from bac_py.encoding.primitives import encode_application_unsigned
        from bac_py.services.write_group import GroupChannelValue, WriteGroupRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        request = WriteGroupRequest(
            group_number=5,
            write_priority=10,
            change_list=[
                GroupChannelValue(
                    channel=1,
                    value=bytes(encode_application_unsigned(100)),
                ),
                GroupChannelValue(
                    channel=2,
                    value=bytes(encode_application_unsigned(200)),
                    overriding_priority=4,
                ),
            ],
        )
        result = await handlers.handle_write_group(
            UnconfirmedServiceChoice.WRITE_GROUP,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_write_group_empty_change_list(self):
        """WriteGroup with empty change list processes without error."""
        from bac_py.services.write_group import WriteGroupRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        request = WriteGroupRequest(
            group_number=1,
            write_priority=8,
            change_list=[],
        )
        result = await handlers.handle_write_group(
            UnconfirmedServiceChoice.WRITE_GROUP,
            request.encode(),
            SOURCE,
        )
        assert result is None


# ---------------------------------------------------------------------------
# WhoAmI handler tests
# ---------------------------------------------------------------------------


class TestHandleWhoAmI:
    @pytest.mark.asyncio
    async def test_who_am_i_logs_request(self):
        """Who-Am-I handler processes request and returns None."""
        from bac_py.services.device_discovery import WhoAmIRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        request = WhoAmIRequest(
            vendor_id=42,
            model_name="TestModel",
            serial_number="SN-12345",
        )
        result = await handlers.handle_who_am_i(
            UnconfirmedServiceChoice.WHO_AM_I,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_who_am_i_invokes_callback(self):
        """Who-Am-I invokes the callback if set on the app."""
        from bac_py.services.device_discovery import WhoAmIRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        app, _, _, handlers = _make_app_and_handlers()
        callback = MagicMock()
        app._who_am_i_callback = callback

        request = WhoAmIRequest(
            vendor_id=99,
            model_name="NewDevice",
            serial_number="SN-99999",
        )
        await handlers.handle_who_am_i(
            UnconfirmedServiceChoice.WHO_AM_I,
            request.encode(),
            SOURCE,
        )
        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0].vendor_id == 99
        assert call_args[0][0].model_name == "NewDevice"
        assert call_args[0][0].serial_number == "SN-99999"
        assert call_args[0][1] == SOURCE

    @pytest.mark.asyncio
    async def test_who_am_i_no_callback(self):
        """Who-Am-I without callback does not raise."""
        from bac_py.services.device_discovery import WhoAmIRequest
        from bac_py.types.enums import UnconfirmedServiceChoice

        app, _, _, handlers = _make_app_and_handlers()
        # Ensure no callback attribute
        if hasattr(app, "_who_am_i_callback"):
            delattr(app, "_who_am_i_callback")

        request = WhoAmIRequest(
            vendor_id=1,
            model_name="M",
            serial_number="S",
        )
        result = await handlers.handle_who_am_i(
            UnconfirmedServiceChoice.WHO_AM_I,
            request.encode(),
            SOURCE,
        )
        assert result is None


# ---------------------------------------------------------------------------
# VT-Open handler tests
# ---------------------------------------------------------------------------


class TestHandleVTOpen:
    def _make_vt_handlers(self):
        """Create handlers with VT-related app attributes properly initialized."""
        app, db, device, handlers = _make_app_and_handlers()
        # VT handlers use getattr() with defaults, but MagicMock auto-creates
        # attributes as MagicMock objects. Delete them so getattr falls through
        # to the default values used in the handler code.
        del app._vt_session_counter
        del app._vt_sessions
        return app, db, device, handlers

    @pytest.mark.asyncio
    async def test_vt_open_returns_session_id(self):
        """VT-Open handler returns VTOpenACK with a remote session ID."""
        from bac_py.services.virtual_terminal import VTOpenACK, VTOpenRequest
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()
        request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        result = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            request.encode(),
            SOURCE,
        )
        assert result is not None
        ack = VTOpenACK.decode(result)
        assert ack.remote_vt_session_identifier >= 1

    @pytest.mark.asyncio
    async def test_vt_open_increments_session_counter(self):
        """Multiple VT-Open calls produce different session IDs."""
        from bac_py.services.virtual_terminal import VTOpenACK, VTOpenRequest
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()
        request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        result1 = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            request.encode(),
            SOURCE,
        )
        result2 = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            request.encode(),
            SOURCE,
        )
        ack1 = VTOpenACK.decode(result1)
        ack2 = VTOpenACK.decode(result2)
        assert ack1.remote_vt_session_identifier != ack2.remote_vt_session_identifier

    @pytest.mark.asyncio
    async def test_vt_open_unknown_class_raises(self):
        """VT-Open with unsupported VT class raises UNKNOWN_VT_CLASS."""
        from bac_py.services.virtual_terminal import VTOpenRequest
        from bac_py.types.enums import VTClass

        _, _, device, handlers = self._make_vt_handlers()
        # Set VT classes supported to a specific list that excludes DEC_VT100
        device._properties[PropertyIdentifier.VT_CLASSES_SUPPORTED] = [
            VTClass.DEFAULT_TERMINAL,
        ]

        request = VTOpenRequest(
            vt_class=VTClass.DEC_VT100,
            local_vt_session_identifier=1,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_vt_open(
                ConfirmedServiceChoice.VT_OPEN,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_VT_CLASS


# ---------------------------------------------------------------------------
# VT-Close handler tests
# ---------------------------------------------------------------------------


class TestHandleVTClose:
    def _make_vt_handlers(self):
        """Create handlers with VT-related app attributes properly initialized."""
        app, db, device, handlers = _make_app_and_handlers()
        del app._vt_session_counter
        del app._vt_sessions
        return app, db, device, handlers

    @pytest.mark.asyncio
    async def test_vt_close_existing_session(self):
        """VT-Close on a valid session returns SimpleACK."""
        from bac_py.services.virtual_terminal import VTCloseRequest, VTOpenACK, VTOpenRequest
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()

        # First open a session
        open_request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        open_result = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            open_request.encode(),
            SOURCE,
        )
        ack = VTOpenACK.decode(open_result)
        session_id = ack.remote_vt_session_identifier

        # Now close it
        close_request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=[session_id],
        )
        result = await handlers.handle_vt_close(
            ConfirmedServiceChoice.VT_CLOSE,
            close_request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK

    @pytest.mark.asyncio
    async def test_vt_close_unknown_session_raises(self):
        """VT-Close with unknown session ID raises UNKNOWN_VT_SESSION."""
        from bac_py.services.virtual_terminal import VTCloseRequest

        _, _, _, handlers = self._make_vt_handlers()
        request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=[999],
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_vt_close(
                ConfirmedServiceChoice.VT_CLOSE,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_VT_SESSION

    @pytest.mark.asyncio
    async def test_vt_close_removes_session(self):
        """VT-Close removes the session; closing again raises error."""
        from bac_py.services.virtual_terminal import VTCloseRequest, VTOpenACK, VTOpenRequest
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()

        # Open a session
        open_request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        open_result = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            open_request.encode(),
            SOURCE,
        )
        ack = VTOpenACK.decode(open_result)
        session_id = ack.remote_vt_session_identifier

        # Close it
        close_request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=[session_id],
        )
        await handlers.handle_vt_close(
            ConfirmedServiceChoice.VT_CLOSE,
            close_request.encode(),
            SOURCE,
        )

        # Closing again should raise
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_vt_close(
                ConfirmedServiceChoice.VT_CLOSE,
                close_request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_VT_SESSION


# ---------------------------------------------------------------------------
# VT-Data handler tests
# ---------------------------------------------------------------------------


class TestHandleVTData:
    def _make_vt_handlers(self):
        """Create handlers with VT-related app attributes properly initialized."""
        app, db, device, handlers = _make_app_and_handlers()
        del app._vt_session_counter
        del app._vt_sessions
        return app, db, device, handlers

    @pytest.mark.asyncio
    async def test_vt_data_on_open_session(self):
        """VT-Data on a valid session returns VTDataACK with all_new_data_accepted."""
        from bac_py.services.virtual_terminal import (
            VTDataACK,
            VTDataRequest,
            VTOpenACK,
            VTOpenRequest,
        )
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()

        # Open a session first
        open_request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        open_result = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            open_request.encode(),
            SOURCE,
        )
        ack = VTOpenACK.decode(open_result)
        session_id = ack.remote_vt_session_identifier

        # Send data
        data_request = VTDataRequest(
            vt_session_identifier=session_id,
            vt_new_data=b"Hello VT\r\n",
            vt_data_flag=False,
        )
        result = await handlers.handle_vt_data(
            ConfirmedServiceChoice.VT_DATA,
            data_request.encode(),
            SOURCE,
        )
        assert result is not None
        data_ack = VTDataACK.decode(result)
        assert data_ack.all_new_data_accepted is True

    @pytest.mark.asyncio
    async def test_vt_data_unknown_session_raises(self):
        """VT-Data on unknown session raises UNKNOWN_VT_SESSION."""
        from bac_py.services.virtual_terminal import VTDataRequest

        _, _, _, handlers = self._make_vt_handlers()
        request = VTDataRequest(
            vt_session_identifier=999,
            vt_new_data=b"data",
            vt_data_flag=True,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_vt_data(
                ConfirmedServiceChoice.VT_DATA,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_VT_SESSION

    @pytest.mark.asyncio
    async def test_vt_data_with_flag_true(self):
        """VT-Data with vt_data_flag=True processes correctly."""
        from bac_py.services.virtual_terminal import (
            VTDataACK,
            VTDataRequest,
            VTOpenACK,
            VTOpenRequest,
        )
        from bac_py.types.enums import VTClass

        _, _, _, handlers = self._make_vt_handlers()

        # Open session
        open_request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=5,
        )
        open_result = await handlers.handle_vt_open(
            ConfirmedServiceChoice.VT_OPEN,
            open_request.encode(),
            SOURCE,
        )
        ack = VTOpenACK.decode(open_result)
        session_id = ack.remote_vt_session_identifier

        data_request = VTDataRequest(
            vt_session_identifier=session_id,
            vt_new_data=b"\x1b[2J",
            vt_data_flag=True,
        )
        result = await handlers.handle_vt_data(
            ConfirmedServiceChoice.VT_DATA,
            data_request.encode(),
            SOURCE,
        )
        data_ack = VTDataACK.decode(result)
        assert data_ack.all_new_data_accepted is True


# ---------------------------------------------------------------------------
# AuditLogQuery handler tests
# ---------------------------------------------------------------------------


class TestHandleAuditLogQuery:
    @pytest.mark.asyncio
    async def test_query_empty_audit_log(self):
        """AuditLogQuery on an empty log returns no records."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import AuditLogQueryACK, AuditLogQueryRequest
        from bac_py.types.audit_types import AuditQueryByTarget

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        query_params = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query_params,
            requested_count=10,
        )
        result = await handlers.handle_audit_log_query(
            ConfirmedServiceChoice.AUDIT_LOG_QUERY,
            request.encode(),
            SOURCE,
        )
        ack = AuditLogQueryACK.decode(result)
        assert len(ack.records) == 0
        assert ack.no_more_items is True

    @pytest.mark.asyncio
    async def test_query_audit_log_with_records(self):
        """AuditLogQuery returns records that have been appended."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import AuditLogQueryACK, AuditLogQueryRequest
        from bac_py.types.audit_types import AuditQueryByTarget, BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        # Append some records
        for i in range(3):
            notification = BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i + 1),
            )
            audit_log.append_record(notification)

        query_params = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query_params,
            requested_count=10,
        )
        result = await handlers.handle_audit_log_query(
            ConfirmedServiceChoice.AUDIT_LOG_QUERY,
            request.encode(),
            SOURCE,
        )
        ack = AuditLogQueryACK.decode(result)
        assert len(ack.records) == 3
        assert ack.no_more_items is True

    @pytest.mark.asyncio
    async def test_query_unknown_audit_log_raises(self):
        """AuditLogQuery on a non-existent audit log raises UNKNOWN_OBJECT."""
        from bac_py.services.audit import AuditLogQueryRequest
        from bac_py.types.audit_types import AuditQueryByTarget

        _, _, _, handlers = _make_app_and_handlers()
        query_params = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 999),
            query_parameters=query_params,
            requested_count=10,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_audit_log_query(
                ConfirmedServiceChoice.AUDIT_LOG_QUERY,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    @pytest.mark.asyncio
    async def test_query_non_audit_log_object_raises(self):
        """AuditLogQuery on a non-AuditLog object raises UNKNOWN_OBJECT."""
        from bac_py.services.audit import AuditLogQueryRequest
        from bac_py.types.audit_types import AuditQueryByTarget

        _, _, _, handlers = _make_app_and_handlers()
        # Device object exists but is not an AuditLogObject
        query_params = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.DEVICE, 1),
            query_parameters=query_params,
            requested_count=10,
        )
        with pytest.raises(BACnetError) as exc_info:
            await handlers.handle_audit_log_query(
                ConfirmedServiceChoice.AUDIT_LOG_QUERY,
                request.encode(),
                SOURCE,
            )
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    @pytest.mark.asyncio
    async def test_query_with_start_at_sequence(self):
        """AuditLogQuery with start_at_sequence_number filters records."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import AuditLogQueryACK, AuditLogQueryRequest
        from bac_py.types.audit_types import AuditQueryByTarget, BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        # Append 5 records (sequence numbers 1-5)
        for i in range(5):
            notification = BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, i + 1),
            )
            audit_log.append_record(notification)

        query_params = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
        )
        request = AuditLogQueryRequest(
            audit_log=ObjectIdentifier(ObjectType.AUDIT_LOG, 1),
            query_parameters=query_params,
            start_at_sequence_number=3,
            requested_count=10,
        )
        result = await handlers.handle_audit_log_query(
            ConfirmedServiceChoice.AUDIT_LOG_QUERY,
            request.encode(),
            SOURCE,
        )
        ack = AuditLogQueryACK.decode(result)
        # Should return records 3, 4, 5
        assert len(ack.records) == 3
        assert ack.no_more_items is True


# ---------------------------------------------------------------------------
# AuditNotification handler tests
# ---------------------------------------------------------------------------


class TestHandleAuditNotification:
    @pytest.mark.asyncio
    async def test_confirmed_audit_notification_returns_simple_ack(self):
        """ConfirmedAuditNotification returns None (SimpleACK)."""
        from bac_py.services.audit import ConfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, _, _, handlers = _make_app_and_handlers()
        notification = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        request = ConfirmedAuditNotificationRequest(
            notifications=[notification],
        )
        result = await handlers.handle_confirmed_audit_notification(
            ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK

    @pytest.mark.asyncio
    async def test_confirmed_audit_notification_appends_to_log(self):
        """ConfirmedAuditNotification appends notifications to AuditLog objects."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import ConfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        notification = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        request = ConfirmedAuditNotificationRequest(
            notifications=[notification],
        )
        await handlers.handle_confirmed_audit_notification(
            ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        # The record should have been appended to the log
        buffer = audit_log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].notification.operation == AuditOperation.WRITE

    @pytest.mark.asyncio
    async def test_confirmed_audit_multiple_notifications(self):
        """ConfirmedAuditNotification with multiple notifications appends all."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import ConfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        notifications = [
            BACnetAuditNotification(
                operation=AuditOperation.WRITE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            ),
            BACnetAuditNotification(
                operation=AuditOperation.CREATE,
                target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 2),
            ),
        ]
        request = ConfirmedAuditNotificationRequest(notifications=notifications)
        await handlers.handle_confirmed_audit_notification(
            ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        buffer = audit_log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 2

    @pytest.mark.asyncio
    async def test_unconfirmed_audit_notification_returns_none(self):
        """UnconfirmedAuditNotification returns None."""
        from bac_py.services.audit import UnconfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation, UnconfirmedServiceChoice

        _, _, _, handlers = _make_app_and_handlers()
        notification = BACnetAuditNotification(
            operation=AuditOperation.GENERAL,
        )
        request = UnconfirmedAuditNotificationRequest(
            notifications=[notification],
        )
        result = await handlers.handle_unconfirmed_audit_notification(
            UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unconfirmed_audit_notification_appends_to_log(self):
        """UnconfirmedAuditNotification appends to AuditLog objects."""
        from bac_py.objects.audit_log import AuditLogObject
        from bac_py.services.audit import UnconfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation, UnconfirmedServiceChoice

        _, db, _, handlers = _make_app_and_handlers()
        audit_log = AuditLogObject(1)
        audit_log._properties[PropertyIdentifier.LOG_ENABLE] = True
        db.add(audit_log)

        notification = BACnetAuditNotification(
            operation=AuditOperation.DELETE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 5),
        )
        request = UnconfirmedAuditNotificationRequest(
            notifications=[notification],
        )
        await handlers.handle_unconfirmed_audit_notification(
            UnconfirmedServiceChoice.UNCONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        buffer = audit_log._properties[PropertyIdentifier.LOG_BUFFER]
        assert len(buffer) == 1
        assert buffer[0].notification.operation == AuditOperation.DELETE

    @pytest.mark.asyncio
    async def test_audit_notification_no_log_objects(self):
        """AuditNotification without AuditLog objects in db does not raise."""
        from bac_py.services.audit import ConfirmedAuditNotificationRequest
        from bac_py.types.audit_types import BACnetAuditNotification
        from bac_py.types.enums import AuditOperation

        _, _, _, handlers = _make_app_and_handlers()
        # No AuditLogObject in db
        notification = BACnetAuditNotification(
            operation=AuditOperation.WRITE,
            target_object=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        request = ConfirmedAuditNotificationRequest(
            notifications=[notification],
        )
        result = await handlers.handle_confirmed_audit_notification(
            ConfirmedServiceChoice.CONFIRMED_AUDIT_NOTIFICATION,
            request.encode(),
            SOURCE,
        )
        assert result is None  # SimpleACK, no error even without log objects
