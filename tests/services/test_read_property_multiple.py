"""Tests for ReadPropertyMultiple service (Clause 15.7)."""

from bac_py.services.read_property_multiple import (
    PropertyReference,
    ReadAccessResult,
    ReadAccessSpecification,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
    ReadResultElement,
)
from bac_py.types.enums import ErrorClass, ErrorCode, ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestPropertyReference:
    def test_encode_decode_without_array_index(self):
        ref = PropertyReference(PropertyIdentifier.PRESENT_VALUE)
        encoded = ref.encode()
        decoded, offset = PropertyReference.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index is None
        assert offset == len(encoded)

    def test_encode_decode_with_array_index(self):
        ref = PropertyReference(PropertyIdentifier.OBJECT_LIST, property_array_index=3)
        encoded = ref.encode()
        decoded, offset = PropertyReference.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.property_array_index == 3
        assert offset == len(encoded)


class TestReadAccessSpecification:
    def test_encode_decode_single_property(self):
        spec = ReadAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_property_references=[
                PropertyReference(PropertyIdentifier.PRESENT_VALUE),
            ],
        )
        encoded = spec.encode()
        decoded, offset = ReadAccessSpecification.decode(encoded, 0)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert len(decoded.list_of_property_references) == 1
        assert decoded.list_of_property_references[0].property_identifier == (
            PropertyIdentifier.PRESENT_VALUE
        )
        assert offset == len(encoded)

    def test_encode_decode_multiple_properties(self):
        spec = ReadAccessSpecification(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            list_of_property_references=[
                PropertyReference(PropertyIdentifier.OBJECT_NAME),
                PropertyReference(PropertyIdentifier.OBJECT_TYPE),
                PropertyReference(PropertyIdentifier.OBJECT_LIST, property_array_index=0),
            ],
        )
        encoded = spec.encode()
        decoded, offset = ReadAccessSpecification.decode(encoded, 0)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 42)
        assert len(decoded.list_of_property_references) == 3
        assert decoded.list_of_property_references[2].property_array_index == 0
        assert offset == len(encoded)


class TestReadPropertyMultipleRequest:
    def test_encode_decode_single_object(self):
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                        PropertyReference(PropertyIdentifier.STATUS_FLAGS),
                    ],
                ),
            ]
        )
        encoded = request.encode()
        decoded = ReadPropertyMultipleRequest.decode(encoded)
        assert len(decoded.list_of_read_access_specs) == 1
        assert decoded.list_of_read_access_specs[0].object_identifier == (
            ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        )
        assert len(decoded.list_of_read_access_specs[0].list_of_property_references) == 2

    def test_encode_decode_multiple_objects(self):
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                    ],
                ),
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.PRESENT_VALUE),
                        PropertyReference(PropertyIdentifier.PRIORITY_ARRAY),
                    ],
                ),
            ]
        )
        encoded = request.encode()
        decoded = ReadPropertyMultipleRequest.decode(encoded)
        assert len(decoded.list_of_read_access_specs) == 2
        assert decoded.list_of_read_access_specs[1].object_identifier == (
            ObjectIdentifier(ObjectType.ANALOG_OUTPUT, 2)
        )
        assert len(decoded.list_of_read_access_specs[1].list_of_property_references) == 2

    def test_round_trip_with_array_index(self):
        request = ReadPropertyMultipleRequest(
            list_of_read_access_specs=[
                ReadAccessSpecification(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
                    list_of_property_references=[
                        PropertyReference(PropertyIdentifier.OBJECT_LIST, property_array_index=5),
                    ],
                ),
            ]
        )
        encoded = request.encode()
        decoded = ReadPropertyMultipleRequest.decode(encoded)
        ref = decoded.list_of_read_access_specs[0].list_of_property_references[0]
        assert ref.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert ref.property_array_index == 5


class TestReadResultElement:
    def test_encode_decode_success(self):
        elem = ReadResultElement(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",  # REAL 42.0
        )
        encoded = elem.encode()
        decoded, offset = ReadResultElement.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.property_access_error is None
        assert offset == len(encoded)

    def test_encode_decode_error(self):
        elem = ReadResultElement(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_access_error=(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY),
        )
        encoded = elem.encode()
        decoded, offset = ReadResultElement.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_value is None
        assert decoded.property_access_error == (
            ErrorClass.PROPERTY,
            ErrorCode.UNKNOWN_PROPERTY,
        )
        assert offset == len(encoded)

    def test_encode_decode_with_array_index(self):
        elem = ReadResultElement(
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=2,
            property_value=b"\xc4\x00\x00\x00\x01",  # Object ID
        )
        encoded = elem.encode()
        decoded, offset = ReadResultElement.decode(encoded, 0)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.property_array_index == 2
        assert decoded.property_value == b"\xc4\x00\x00\x00\x01"
        assert offset == len(encoded)


class TestReadAccessResult:
    def test_encode_decode_all_success(self):
        result = ReadAccessResult(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            list_of_results=[
                ReadResultElement(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    property_value=b"\x44\x42\x28\x00\x00",
                ),
                ReadResultElement(
                    property_identifier=PropertyIdentifier.OBJECT_NAME,
                    property_value=b"\x75\x05\x00test",
                ),
            ],
        )
        encoded = result.encode()
        decoded, offset = ReadAccessResult.decode(encoded, 0)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert len(decoded.list_of_results) == 2
        assert decoded.list_of_results[0].property_value == b"\x44\x42\x28\x00\x00"
        assert decoded.list_of_results[1].property_value == b"\x75\x05\x00test"
        assert offset == len(encoded)

    def test_encode_decode_mixed_success_error(self):
        result = ReadAccessResult(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            list_of_results=[
                ReadResultElement(
                    property_identifier=PropertyIdentifier.OBJECT_NAME,
                    property_value=b"\x75\x05\x00test",
                ),
                ReadResultElement(
                    property_identifier=PropertyIdentifier.PRESENT_VALUE,
                    property_access_error=(ErrorClass.PROPERTY, ErrorCode.UNKNOWN_PROPERTY),
                ),
            ],
        )
        encoded = result.encode()
        decoded, offset = ReadAccessResult.decode(encoded, 0)
        assert len(decoded.list_of_results) == 2
        assert decoded.list_of_results[0].property_value is not None
        assert decoded.list_of_results[1].property_access_error is not None
        assert offset == len(encoded)


class TestReadPropertyMultipleACK:
    def test_encode_decode_single_object(self):
        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x44\x42\x28\x00\x00",
                        ),
                    ],
                ),
            ]
        )
        encoded = ack.encode()
        decoded = ReadPropertyMultipleACK.decode(encoded)
        assert len(decoded.list_of_read_access_results) == 1
        res = decoded.list_of_read_access_results[0]
        assert res.object_identifier == ObjectIdentifier(ObjectType.ANALOG_INPUT, 1)
        assert len(res.list_of_results) == 1
        assert res.list_of_results[0].property_value == b"\x44\x42\x28\x00\x00"

    def test_encode_decode_multiple_objects(self):
        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x44\x00\x00\x00\x00",
                        ),
                    ],
                ),
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 2),
                    list_of_results=[
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.PRESENT_VALUE,
                            property_value=b"\x91\x01",
                        ),
                        ReadResultElement(
                            property_identifier=PropertyIdentifier.POLARITY,
                            property_access_error=(
                                ErrorClass.PROPERTY,
                                ErrorCode.UNKNOWN_PROPERTY,
                            ),
                        ),
                    ],
                ),
            ]
        )
        encoded = ack.encode()
        decoded = ReadPropertyMultipleACK.decode(encoded)
        assert len(decoded.list_of_read_access_results) == 2
        res1 = decoded.list_of_read_access_results[1]
        assert res1.object_identifier == ObjectIdentifier(ObjectType.BINARY_INPUT, 2)
        assert len(res1.list_of_results) == 2
        assert res1.list_of_results[0].property_value is not None
        assert res1.list_of_results[1].property_access_error is not None

    def test_round_trip_empty_results(self):
        """ACK with an object but no result elements."""
        ack = ReadPropertyMultipleACK(
            list_of_read_access_results=[
                ReadAccessResult(
                    object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
                    list_of_results=[],
                ),
            ]
        )
        encoded = ack.encode()
        decoded = ReadPropertyMultipleACK.decode(encoded)
        assert len(decoded.list_of_read_access_results) == 1
        assert len(decoded.list_of_read_access_results[0].list_of_results) == 0
