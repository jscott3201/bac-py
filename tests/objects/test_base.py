"""Tests for BACnet object model base classes (PropertyDefinition, ObjectDatabase, factory)."""

import pytest

from bac_py.objects.base import (
    ObjectDatabase,
    PropertyAccess,
    PropertyDefinition,
    create_object,
)
from bac_py.objects.device import DeviceObject
from bac_py.services.errors import BACnetError
from bac_py.types.enums import ErrorCode, ObjectType, PropertyIdentifier
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
