"""Tests for Who-Has and I-Have services."""

from bac_py.services.who_has import IHaveRequest, WhoHasRequest
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestWhoHasRequest:
    def test_by_object_id_no_limits(self):
        obj_id = ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        request = WhoHasRequest(object_identifier=obj_id)
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier == obj_id
        assert decoded.object_name is None
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_by_object_name_no_limits(self):
        request = WhoHasRequest(object_name="Temperature-Sensor")
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier is None
        assert decoded.object_name == "Temperature-Sensor"
        assert decoded.low_limit is None
        assert decoded.high_limit is None

    def test_by_object_id_with_limits(self):
        obj_id = ObjectIdentifier(ObjectType.BINARY_INPUT, 5)
        request = WhoHasRequest(
            object_identifier=obj_id,
            low_limit=100,
            high_limit=500,
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_identifier == obj_id
        assert decoded.low_limit == 100
        assert decoded.high_limit == 500

    def test_by_object_name_with_limits(self):
        request = WhoHasRequest(
            object_name="Room-Temp",
            low_limit=0,
            high_limit=4194303,
        )
        encoded = request.encode()
        decoded = WhoHasRequest.decode(encoded)
        assert decoded.object_name == "Room-Temp"
        assert decoded.low_limit == 0
        assert decoded.high_limit == 4194303


class TestIHaveRequest:
    def test_round_trip(self):
        request = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1234),
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_VALUE, 1),
            object_name="Temperature",
        )
        encoded = request.encode()
        decoded = IHaveRequest.decode(encoded)
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 1234)
        assert decoded.object_identifier == ObjectIdentifier(ObjectType.ANALOG_VALUE, 1)
        assert decoded.object_name == "Temperature"

    def test_different_object_types(self):
        request = IHaveRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 42),
            object_identifier=ObjectIdentifier(ObjectType.BINARY_INPUT, 99),
            object_name="Alarm-Input",
        )
        encoded = request.encode()
        decoded = IHaveRequest.decode(encoded)
        assert decoded.object_identifier.object_type == ObjectType.BINARY_INPUT
        assert decoded.object_identifier.instance_number == 99
