"""Tests for BACnetValueSource and BACnetDeviceObjectReference types."""

from bac_py.types.constructed import BACnetDeviceObjectReference, BACnetValueSource
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestBACnetDeviceObjectReference:
    def test_encode_decode_with_device(self):
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
        )
        encoded = ref.encode()
        decoded, length = BACnetDeviceObjectReference.decode(encoded)
        assert decoded.object_identifier == ref.object_identifier
        assert decoded.device_identifier == ref.device_identifier
        assert length == len(encoded)

    def test_encode_decode_without_device(self):
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 5),
        )
        encoded = ref.encode()
        decoded, length = BACnetDeviceObjectReference.decode(encoded)
        assert decoded.object_identifier == ref.object_identifier
        assert decoded.device_identifier is None
        assert length == len(encoded)

    def test_frozen(self):
        import pytest

        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
        )
        with pytest.raises(AttributeError):
            ref.object_identifier = ObjectIdentifier(ObjectType.ANALOG_INPUT, 2)  # type: ignore[misc]


class TestBACnetValueSourceNone:
    def test_none_source(self):
        vs = BACnetValueSource.none_source()
        assert vs.choice == 0
        assert vs.value is None

    def test_none_source_encode_decode(self):
        vs = BACnetValueSource.none_source()
        encoded = vs.encode()
        decoded, length = BACnetValueSource.decode(encoded)
        assert decoded.choice == 0
        assert decoded.value is None
        assert length == len(encoded)


class TestBACnetValueSourceObject:
    def test_from_object(self):
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
        )
        vs = BACnetValueSource.from_object(ref)
        assert vs.choice == 1
        assert vs.value == ref

    def test_from_object_encode_decode(self):
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 10),
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 200),
        )
        vs = BACnetValueSource.from_object(ref)
        encoded = vs.encode()
        decoded, length = BACnetValueSource.decode(encoded)
        assert decoded.choice == 1
        assert isinstance(decoded.value, BACnetDeviceObjectReference)
        assert decoded.value.object_identifier == ref.object_identifier
        assert decoded.value.device_identifier == ref.device_identifier
        assert length == len(encoded)

    def test_from_object_no_device(self):
        ref = BACnetDeviceObjectReference(
            object_identifier=ObjectIdentifier(ObjectType.BINARY_VALUE, 3),
        )
        vs = BACnetValueSource.from_object(ref)
        encoded = vs.encode()
        decoded, _length = BACnetValueSource.decode(encoded)
        assert decoded.choice == 1
        assert decoded.value.device_identifier is None
        assert decoded.value.object_identifier == ref.object_identifier


class TestBACnetValueSourceAddress:
    def test_from_address(self):
        addr = b"\xc0\xa8\x01\x64\xba\xc0"
        vs = BACnetValueSource.from_address(addr)
        assert vs.choice == 2
        assert vs.value == addr

    def test_from_address_encode_decode(self):
        addr = b"\x0a\x00\x00\x01"
        vs = BACnetValueSource.from_address(addr)
        encoded = vs.encode()
        decoded, length = BACnetValueSource.decode(encoded)
        assert decoded.choice == 2
        assert decoded.value == addr
        assert length == len(encoded)
