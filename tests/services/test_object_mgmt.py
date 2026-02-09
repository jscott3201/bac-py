"""Tests for object management services."""

from bac_py.encoding.primitives import encode_application_real
from bac_py.services.common import BACnetPropertyValue
from bac_py.services.object_mgmt import CreateObjectRequest, DeleteObjectRequest
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestCreateObjectRequest:
    def test_create_with_type_only(self):
        request = CreateObjectRequest(object_type=ObjectType.ANALOG_VALUE)
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.ANALOG_VALUE
        assert decoded.object_identifier is None
        assert decoded.list_of_initial_values is None

    def test_create_with_object_identifier(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 42)
        request = CreateObjectRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type is None
        assert decoded.object_identifier == obj_id

    def test_create_with_initial_values(self):
        pv = BACnetPropertyValue(
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            value=encode_application_real(25.5),
        )
        request = CreateObjectRequest(
            object_type=ObjectType.ANALOG_VALUE,
            list_of_initial_values=[pv],
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert decoded.object_type == ObjectType.ANALOG_VALUE
        assert decoded.list_of_initial_values is not None
        assert len(decoded.list_of_initial_values) == 1
        assert decoded.list_of_initial_values[0].property_identifier == (
            PropertyIdentifier.PRESENT_VALUE
        )

    def test_create_with_multiple_initial_values(self):
        pvs = [
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.PRESENT_VALUE,
                value=encode_application_real(10.0),
            ),
            BACnetPropertyValue(
                property_identifier=PropertyIdentifier.OBJECT_NAME,
                value=b"\x75\x05\x00test",
            ),
        ]
        request = CreateObjectRequest(
            object_type=ObjectType.ANALOG_VALUE,
            list_of_initial_values=pvs,
        )
        encoded = request.encode()
        decoded = CreateObjectRequest.decode(encoded)
        assert len(decoded.list_of_initial_values) == 2


class TestDeleteObjectRequest:
    def test_round_trip(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        request = DeleteObjectRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = DeleteObjectRequest.decode(encoded)
        assert decoded.object_identifier == obj_id

    def test_different_types(self):
        for obj_type in [ObjectType.BINARY_VALUE, ObjectType.MULTI_STATE_VALUE, ObjectType.FILE]:
            obj_id = ObjectIdentifier(obj_type, 99)
            request = DeleteObjectRequest(object_identifier=obj_id)
            encoded = request.encode()
            decoded = DeleteObjectRequest.decode(encoded)
            assert decoded.object_identifier == obj_id
