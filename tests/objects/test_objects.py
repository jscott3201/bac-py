import asyncio
from typing import ClassVar

import pytest

from bac_py.objects.base import (
    BACnetObject,
    ObjectDatabase,
    PropertyAccess,
    PropertyDefinition,
    create_object,
)
from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import ErrorClass, ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestPropertyDefinition:
    def test_attributes(self):
        pd = PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        )
        assert pd.identifier == PropertyIdentifier.PRESENT_VALUE
        assert pd.datatype is float
        assert pd.access == PropertyAccess.READ_WRITE
        assert pd.required is True
        assert pd.default == 0.0

    def test_frozen(self):
        pd = PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_ONLY,
            required=False,
        )
        with pytest.raises(AttributeError):
            pd.required = True


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


class TestBACnetObjectArrayAccess:
    def test_read_array_index_zero_returns_length(self):
        dev = DeviceObject(1)
        obj_list = [ObjectIdentifier(8, 1), ObjectIdentifier(0, 1)]
        dev._properties[PropertyIdentifier.OBJECT_LIST] = obj_list
        length = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=0)
        assert length == 2

    def test_read_array_index_valid(self):
        dev = DeviceObject(1)
        obj_list = [ObjectIdentifier(8, 1), ObjectIdentifier(0, 2)]
        dev._properties[PropertyIdentifier.OBJECT_LIST] = obj_list
        elem = dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=1)
        assert elem == ObjectIdentifier(8, 1)

    def test_read_array_index_out_of_range(self):
        dev = DeviceObject(1)
        dev._properties[PropertyIdentifier.OBJECT_LIST] = [ObjectIdentifier(8, 1)]
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.OBJECT_LIST, array_index=5)
        assert exc_info.value.error_code == ErrorCode.INVALID_ARRAY_INDEX

    def test_read_array_index_on_non_array(self):
        dev = DeviceObject(1, object_name="test")
        with pytest.raises(BACnetError) as exc_info:
            dev.read_property(PropertyIdentifier.OBJECT_NAME, array_index=1)
        assert exc_info.value.error_code == ErrorCode.PROPERTY_IS_NOT_AN_ARRAY


class TestObjectDatabase:
    def test_add_and_get(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        result = db.get(ObjectIdentifier(ObjectType.DEVICE, 1))
        assert result is dev

    def test_add_duplicate_raises(self):
        db = ObjectDatabase()
        dev1 = DeviceObject(1)
        db.add(dev1)
        dev2 = DeviceObject(1)
        with pytest.raises(BACnetError) as exc_info:
            db.add(dev2)
        assert exc_info.value.error_code == ErrorCode.OBJECT_IDENTIFIER_ALREADY_EXISTS

    def test_get_nonexistent_returns_none(self):
        db = ObjectDatabase()
        result = db.get(ObjectIdentifier(ObjectType.DEVICE, 999))
        assert result is None

    def test_remove_object(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        # Cannot remove Device object
        with pytest.raises(BACnetError) as exc_info:
            db.remove(ObjectIdentifier(ObjectType.DEVICE, 1))
        assert exc_info.value.error_code == ErrorCode.OBJECT_DELETION_NOT_PERMITTED

    def test_remove_nonexistent_raises(self):
        db = ObjectDatabase()
        with pytest.raises(BACnetError) as exc_info:
            db.remove(ObjectIdentifier(ObjectType.ANALOG_INPUT, 1))
        assert exc_info.value.error_code == ErrorCode.UNKNOWN_OBJECT

    def test_object_list(self):
        db = ObjectDatabase()
        dev = DeviceObject(1)
        db.add(dev)
        olist = db.object_list
        assert ObjectIdentifier(ObjectType.DEVICE, 1) in olist

    def test_len(self):
        db = ObjectDatabase()
        assert len(db) == 0
        db.add(DeviceObject(1))
        assert len(db) == 1

    def test_get_objects_of_type(self):
        db = ObjectDatabase()
        db.add(DeviceObject(1))
        devices = db.get_objects_of_type(ObjectType.DEVICE)
        assert len(devices) == 1
        ais = db.get_objects_of_type(ObjectType.ANALOG_INPUT)
        assert len(ais) == 0


class TestObjectFactory:
    def test_create_device_via_factory(self):
        dev = create_object(ObjectType.DEVICE, 42)
        assert isinstance(dev, DeviceObject)
        assert dev.object_identifier.instance_number == 42

    def test_create_unsupported_type_raises(self):
        # NETWORK_SECURITY is deprecated and not registered
        with pytest.raises(BACnetError) as exc_info:
            create_object(ObjectType.NETWORK_SECURITY, 1)
        assert exc_info.value.error_code == ErrorCode.UNSUPPORTED_OBJECT_TYPE


class _CommandableObject(BACnetObject):
    """Test object with commandable Present Value."""

    OBJECT_TYPE: ClassVar[ObjectType] = ObjectType.ANALOG_OUTPUT
    PROPERTY_DEFINITIONS: ClassVar[dict[PropertyIdentifier, PropertyDefinition]] = {
        PropertyIdentifier.OBJECT_IDENTIFIER: PropertyDefinition(
            PropertyIdentifier.OBJECT_IDENTIFIER,
            ObjectIdentifier,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.OBJECT_TYPE: PropertyDefinition(
            PropertyIdentifier.OBJECT_TYPE,
            ObjectType,
            PropertyAccess.READ_ONLY,
            required=True,
        ),
        PropertyIdentifier.PRESENT_VALUE: PropertyDefinition(
            PropertyIdentifier.PRESENT_VALUE,
            float,
            PropertyAccess.READ_WRITE,
            required=True,
            default=0.0,
        ),
        PropertyIdentifier.RELINQUISH_DEFAULT: PropertyDefinition(
            PropertyIdentifier.RELINQUISH_DEFAULT,
            float,
            PropertyAccess.READ_WRITE,
            required=False,
            default=0.0,
        ),
    }

    def __init__(self, instance_number: int, **kwargs):
        super().__init__(instance_number, **kwargs)
        self._priority_array = [None] * 16


class TestCommandPriority:
    def test_write_defaults_to_priority_16(self):
        """Commandable writes without explicit priority default to 16 (Clause 19.2)."""
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0)
        assert obj._priority_array[15] == 42.0  # priority 16 = index 15
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 42.0

    def test_write_with_explicit_priority(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 99.0, priority=8)
        assert obj._priority_array[7] == 99.0  # priority 8 = index 7
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 99.0

    def test_higher_priority_wins(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 10.0, priority=16)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 20.0, priority=8)
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 20.0

    def test_priority_out_of_range_error(self):
        """Priority out of range must use SERVICES/PARAMETER_OUT_OF_RANGE."""
        obj = _CommandableObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0, priority=0)
        assert exc_info.value.error_class == ErrorClass.SERVICES
        assert exc_info.value.error_code == ErrorCode.PARAMETER_OUT_OF_RANGE

    def test_priority_17_out_of_range(self):
        obj = _CommandableObject(1)
        with pytest.raises(BACnetError) as exc_info:
            obj.write_property(PropertyIdentifier.PRESENT_VALUE, 1.0, priority=17)
        assert exc_info.value.error_class == ErrorClass.SERVICES
        assert exc_info.value.error_code == ErrorCode.PARAMETER_OUT_OF_RANGE

    def test_relinquish_via_none(self):
        obj = _CommandableObject(1)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, 42.0, priority=8)
        obj.write_property(PropertyIdentifier.PRESENT_VALUE, None, priority=8)
        # Should fall back to relinquish default
        assert obj.read_property(PropertyIdentifier.PRESENT_VALUE) == 0.0

    def test_async_write_defaults_priority_16(self):
        """async_write_property also defaults to priority 16 for commandable."""
        obj = _CommandableObject(1)

        async def run():
            await obj.async_write_property(PropertyIdentifier.PRESENT_VALUE, 55.0)

        asyncio.get_event_loop().run_until_complete(run())
        assert obj._priority_array[15] == 55.0
