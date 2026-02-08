"""Tests for list element services."""

from bac_py.encoding.primitives import encode_application_object_id
from bac_py.services.list_element import AddListElementRequest, RemoveListElementRequest
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestAddListElementRequest:
    def test_round_trip(self):
        elements = encode_application_object_id(ObjectType.ANALOG_INPUT, 1)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=elements,
        )
        encoded = request.encode()
        decoded = AddListElementRequest.decode(encoded)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.list_of_elements == elements
        assert decoded.property_array_index is None

    def test_round_trip_with_array_index(self):
        elements = encode_application_object_id(ObjectType.BINARY_VALUE, 5)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=elements,
            property_array_index=3,
        )
        encoded = request.encode()
        decoded = AddListElementRequest.decode(encoded)
        assert decoded.property_array_index == 3
        assert decoded.list_of_elements == elements

    def test_round_trip_multiple_elements(self):
        buf = bytearray()
        buf.extend(encode_application_object_id(ObjectType.ANALOG_INPUT, 1))
        buf.extend(encode_application_object_id(ObjectType.ANALOG_INPUT, 2))
        elements = bytes(buf)
        request = AddListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=elements,
        )
        encoded = request.encode()
        decoded = AddListElementRequest.decode(encoded)
        assert decoded.list_of_elements == elements


class TestRemoveListElementRequest:
    def test_round_trip(self):
        elements = encode_application_object_id(ObjectType.ANALOG_INPUT, 1)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=elements,
        )
        encoded = request.encode()
        decoded = RemoveListElementRequest.decode(encoded)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.DEVICE, 1)
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.list_of_elements == elements

    def test_round_trip_with_array_index(self):
        elements = encode_application_object_id(ObjectType.BINARY_VALUE, 5)
        request = RemoveListElementRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            list_of_elements=elements,
            property_array_index=7,
        )
        encoded = request.encode()
        decoded = RemoveListElementRequest.decode(encoded)
        assert decoded.property_array_index == 7
