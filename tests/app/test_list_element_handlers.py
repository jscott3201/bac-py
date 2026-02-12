"""Integration tests for AddListElement/RemoveListElement handlers."""

import asyncio
from unittest.mock import MagicMock

import pytest

from bac_py.app.server import DefaultServerHandlers
from bac_py.encoding.primitives import encode_application_unsigned
from bac_py.network.address import BACnetAddress
from bac_py.objects.base import ObjectDatabase, PropertyAccess, PropertyDefinition
from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.services.list_element import AddListElementRequest, RemoveListElementRequest
from bac_py.types.enums import (
    ConfirmedServiceChoice,
    ErrorCode,
    ObjectType,
    PropertyIdentifier,
)
from bac_py.types.primitives import ObjectIdentifier

SOURCE = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")

# Use a writable list property that we'll add to the PROPERTY_DEFINITIONS
_LIST_PROP = PropertyIdentifier.TIME_SYNCHRONIZATION_RECIPIENTS


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


class TestAddListElement:
    def test_add_elements_to_existing_list(self):
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

        async def run():
            result = await handlers.handle_add_list_element(
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())
        prop = device._properties[_LIST_PROP]
        assert 30 in prop
        assert 40 in prop
        assert len(prop) == 4

    def test_add_to_none_creates_list(self):
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

        async def run():
            result = await handlers.handle_add_list_element(
                ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
            assert result is None

        asyncio.get_event_loop().run_until_complete(run())
        prop = device._properties[_LIST_PROP]
        assert prop == [42]

    def test_add_to_unknown_object_raises(self):
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 999),
            property_identifier=_LIST_PROP,
            list_of_elements=elements,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_add_list_element(
                    ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                    request.encode(),
                    SOURCE,
                )
            assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

        asyncio.get_event_loop().run_until_complete(run())

    def test_add_to_read_only_property_raises(self):
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

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_add_list_element(
                    ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                    request.encode(),
                    SOURCE,
                )
            assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

        asyncio.get_event_loop().run_until_complete(run())

    def test_add_to_non_list_property_raises(self):
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

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_add_list_element(
                    ConfirmedServiceChoice.ADD_LIST_ELEMENT,
                    request.encode(),
                    SOURCE,
                )
            assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_A_LIST

        asyncio.get_event_loop().run_until_complete(run())


class TestRemoveListElement:
    def test_remove_existing_elements(self):
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

        async def run():
            result = await handlers.handle_remove_list_element(
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
            assert result is None  # SimpleACK

        asyncio.get_event_loop().run_until_complete(run())
        prop = device._properties[_LIST_PROP]
        assert prop == [10, 30]

    def test_remove_nonexistent_elements_silently_ignored(self):
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

        async def run():
            result = await handlers.handle_remove_list_element(
                ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                request.encode(),
                SOURCE,
            )
            assert result is None

        asyncio.get_event_loop().run_until_complete(run())
        # Original list unchanged
        prop = device._properties[_LIST_PROP]
        assert prop == [10, 20]

    def test_remove_from_non_list_raises(self):
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

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_remove_list_element(
                    ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                    request.encode(),
                    SOURCE,
                )
            assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_A_LIST

        asyncio.get_event_loop().run_until_complete(run())

    def test_remove_from_read_only_raises(self):
        """Test removing from a read-only list property raises WRITE_ACCESS_DENIED."""
        app, db, device = _make_app_with_list_prop()
        handlers = DefaultServerHandlers(app, db, device)

        elements = encode_application_unsigned(1)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.DEVICE_ADDRESS_BINDING,
            list_of_elements=elements,
        )

        async def run():
            with pytest.raises(BACnetError) as exc_info:
                await handlers.handle_remove_list_element(
                    ConfirmedServiceChoice.REMOVE_LIST_ELEMENT,
                    request.encode(),
                    SOURCE,
                )
            assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

        asyncio.get_event_loop().run_until_complete(run())
