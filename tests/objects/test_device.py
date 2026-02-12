"""Tests for the BACnet Device object."""

import pytest

from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestDeviceObject:
    def test_create_device(self):
        dev = DeviceObject(1234)
        assert dev.object_identifier.object_type == ObjectType.DEVICE
        assert dev.object_identifier.instance_number == 1234

    def test_read_object_identifier(self):
        dev = DeviceObject(1)
        oid = dev.read_property(PropertyIdentifier.OBJECT_IDENTIFIER)
        assert isinstance(oid, ObjectIdentifier)
        assert oid.object_type == ObjectType.DEVICE
        assert oid.instance_number == 1

    def test_read_object_type(self):
        dev = DeviceObject(1)
        ot = dev.read_property(PropertyIdentifier.OBJECT_TYPE)
        assert ot == ObjectType.DEVICE

    def test_read_object_name_initial(self):
        dev = DeviceObject(1, object_name="my-device")
        name = dev.read_property(PropertyIdentifier.OBJECT_NAME)
        assert name == "my-device"

    def test_read_protocol_version(self):
        dev = DeviceObject(1)
        pv = dev.read_property(PropertyIdentifier.PROTOCOL_VERSION)
        assert pv == 1

    def test_read_protocol_revision(self):
        dev = DeviceObject(1)
        pr = dev.read_property(PropertyIdentifier.PROTOCOL_REVISION)
        assert pr == 22

    def test_read_max_apdu_length(self):
        dev = DeviceObject(1)
        assert dev.read_property(PropertyIdentifier.MAX_APDU_LENGTH_ACCEPTED) == 1476

    def test_read_unknown_property_raises(self):
        dev = DeviceObject(1)
        # PRESENT_VALUE is not defined on a Device object
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.PRESENT_VALUE)
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_PROPERTY

    def test_write_object_name(self):
        dev = DeviceObject(1, object_name="old-name")
        dev.write_property(PropertyIdentifier.OBJECT_NAME, "new-name")
        assert dev.read_property(PropertyIdentifier.OBJECT_NAME) == "new-name"

    def test_write_read_only_raises(self):
        dev = DeviceObject(1)
        with pytest.raises(BACnetError) as exc_info:
            dev.write_property(PropertyIdentifier.OBJECT_IDENTIFIER, ObjectIdentifier(8, 2))
        assert exc_info.value.error_code == ErrorCode.WRITE_ACCESS_DENIED

    def test_property_list(self):
        dev = DeviceObject(1)
        plist = dev.read_property(PropertyIdentifier.PROPERTY_LIST)
        assert isinstance(plist, list)
        # Per the spec, Property_List excludes these four properties
        assert PropertyIdentifier.OBJECT_IDENTIFIER not in plist
        assert PropertyIdentifier.OBJECT_NAME not in plist
        assert PropertyIdentifier.OBJECT_TYPE not in plist
        assert PropertyIdentifier.PROPERTY_LIST not in plist
        # But other required properties should be present
        assert PropertyIdentifier.SYSTEM_STATUS in plist

    def test_object_list_default_empty(self):
        dev = DeviceObject(1)
        olist = dev.read_property(PropertyIdentifier.OBJECT_LIST)
        assert olist == []


class TestDeviceExtendedDiscoveryProperties:
    """Device object supports profile_name, profile_location, and tags."""

    def test_profile_name_optional(self):
        """Device works without profile_name set -- returns None."""
        dev = DeviceObject(1000)
        assert dev.read_property(PropertyIdentifier.PROFILE_NAME) is None

    def test_profile_name_read_write(self):
        dev = DeviceObject(1000)
        dev.write_property(PropertyIdentifier.PROFILE_NAME, "BACnet-Profile-A")
        assert dev.read_property(PropertyIdentifier.PROFILE_NAME) == "BACnet-Profile-A"

    def test_profile_location_optional(self):
        """Device works without profile_location set -- returns None."""
        dev = DeviceObject(1000)
        assert dev.read_property(PropertyIdentifier.PROFILE_LOCATION) is None

    def test_profile_location_read_write(self):
        dev = DeviceObject(1000)
        dev.write_property(
            PropertyIdentifier.PROFILE_LOCATION,
            "https://example.com/profiles/hvac-controller",
        )
        assert (
            dev.read_property(PropertyIdentifier.PROFILE_LOCATION)
            == "https://example.com/profiles/hvac-controller"
        )

    def test_tags_optional(self):
        """Device works without tags set -- returns None."""
        dev = DeviceObject(1000)
        assert dev.read_property(PropertyIdentifier.TAGS) is None

    def test_tags_read_write(self):
        dev = DeviceObject(1000)
        tags = [{"name": "floor", "value": "3"}, {"name": "zone", "value": "north"}]
        dev.write_property(PropertyIdentifier.TAGS, tags)
        result = dev.read_property(PropertyIdentifier.TAGS)
        assert result == tags

    def test_device_works_without_extended_properties(self):
        """All extended properties are optional -- basic Device still works."""
        dev = DeviceObject(
            2000,
            vendor_name="Test",
            vendor_identifier=999,
            model_name="TestModel",
            firmware_revision="1.0",
            application_software_version="1.0",
        )
        assert dev.read_property(PropertyIdentifier.OBJECT_TYPE).value == 8

    def test_extended_properties_in_definitions(self):
        """PROPERTY_DEFINITIONS includes all three extended properties."""
        defs = DeviceObject.PROPERTY_DEFINITIONS
        assert PropertyIdentifier.PROFILE_NAME in defs
        assert PropertyIdentifier.PROFILE_LOCATION in defs
        assert PropertyIdentifier.TAGS in defs

    def test_extended_properties_not_required(self):
        defs = DeviceObject.PROPERTY_DEFINITIONS
        assert defs[PropertyIdentifier.PROFILE_NAME].required is False
        assert defs[PropertyIdentifier.PROFILE_LOCATION].required is False
        assert defs[PropertyIdentifier.TAGS].required is False
