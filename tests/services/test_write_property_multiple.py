"""Tests for WritePropertyMultiple service (Clause 15.10)."""

from bac_py.services.write_property_multiple import (
    PropertyValue,
    WriteAccessSpecification,
    WritePropertyMultipleRequest,
)
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestPropertyValue:
    def test_encode_decode_minimal(self):
        pv = PropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",
        )
        encoded = pv.encode()
        decoded, offset = PropertyValue.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.property_array_index is None
        assert decoded.priority is None
        assert offset == len(encoded)

    def test_encode_decode_with_priority(self):
        pv = PropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",
            priority=8,
        )
        encoded = pv.encode()
        decoded, offset = PropertyValue.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.priority == 8
        assert offset == len(encoded)

    def test_encode_decode_with_array_index(self):
        pv = PropertyValue(
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_value=b"\xc4\x00\x00\x00\x01",
            property_array_index=3,
        )
        encoded = pv.encode()
        decoded, offset = PropertyValue.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.property_array_index == 3
        assert decoded.property_value == b"\xc4\x00\x00\x00\x01"
        assert offset == len(encoded)

    def test_encode_decode_all_fields(self):
        pv = PropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",
            property_array_index=1,
            priority=4,
        )
        encoded = pv.encode()
        decoded, offset = PropertyValue.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index == 1
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.priority == 4
        assert offset == len(encoded)


class TestWriteAccessSpecification:
    def test_encode_decode_single_property(self):
        spec = WriteAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
            list_of_properties=[
                PropertyValue(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    property_value=b"\x44\x42\x28\x00\x00",
                ),
            ],
        )
        encoded = spec.encode()
        decoded, offset = WriteAccessSpecification.decode(encoded, 0)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)
        assert len(decoded.list_of_properties) == 1
        assert decoded.list_of_properties[0].property_identifier == (
            PropertyIdentifier.PRESENT_VALUE
        )
        assert offset == len(encoded)

    def test_encode_decode_multiple_properties(self):
        spec = WriteAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            list_of_properties=[
                PropertyValue(
                    property_identifier=PropertyIdentifier.OBJECT_NAME,
                    property_value=b"\x75\x05\x00test",
                ),
                PropertyValue(
                    property_identifier=PropertyIdentifier.DESCRIPTION,
                    property_value=b"\x75\x06\x00hello",
                ),
            ],
        )
        encoded = spec.encode()
        decoded, offset = WriteAccessSpecification.decode(encoded, 0)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 42)
        assert len(decoded.list_of_properties) == 2
        assert offset == len(encoded)


class TestWritePropertyMultipleRequest:
    def test_encode_decode_single_object(self):
        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
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
            ]
        )
        encoded = request.encode()
        decoded = WritePropertyMultipleRequest.decode(encoded)
        assert len(decoded.list_of_write_access_specs) == 1
        spec = decoded.list_of_write_access_specs[0]
        assert spec.object_identifier == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1)
        assert len(spec.list_of_properties) == 1
        assert spec.list_of_properties[0].priority == 8

    def test_encode_decode_multiple_objects(self):
        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 1),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x44\x42\x28\x00\x00",
                        ),
                    ],
                ),
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x44\x00\x00\x00\x00",
                            priority=4,
                        ),
                        PropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_NAME,
                            property_value=b"\x75\x05\x00test",
                        ),
                    ],
                ),
            ]
        )
        encoded = request.encode()
        decoded = WritePropertyMultipleRequest.decode(encoded)
        assert len(decoded.list_of_write_access_specs) == 2
        spec2 = decoded.list_of_write_access_specs[1]
        assert spec2.object_identifier == ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2)
        assert len(spec2.list_of_properties) == 2
        assert spec2.list_of_properties[0].priority == 4
        assert spec2.list_of_properties[1].priority is None

    def test_round_trip_with_array_index_and_priority(self):
        request = WritePropertyMultipleRequest(
            list_of_write_access_specs=[
                WriteAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
                    list_of_properties=[
                        PropertyValue(
                            property_identifier=PropertyIdentifier.OBJECT_LIST,
                            property_value=b"\xc4\x00\x00\x00\x05",
                            property_array_index=3,
                            priority=16,
                        ),
                    ],
                ),
            ]
        )
        encoded = request.encode()
        decoded = WritePropertyMultipleRequest.decode(encoded)
        pv = decoded.list_of_write_access_specs[0].list_of_properties[0]
        assert pv.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert pv.property_array_index == 3
        assert pv.priority == 16
        assert pv.property_value == b"\xc4\x00\x00\x00\x05"
