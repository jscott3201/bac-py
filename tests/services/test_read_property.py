from bac_py.services.read_property import ReadPropertyACK, ReadPropertyRequest
from bac_py.types.enums import ObjectType, PropertyIdentifier
from bac_py.types.primitives import ObjectIdentifier


class TestReadPropertyRequest:
    def test_round_trip_basic(self):
        req = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
        )
        decoded = ReadPropertyRequest.decode(req.encode())
        assert decoded.object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.object_identifier.instance_number == 1
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index is None

    def test_round_trip_with_array_index(self):
        req = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1234),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=5,
        )
        decoded = ReadPropertyRequest.decode(req.encode())
        assert decoded.object_identifier.object_type == ObjectType.DEVICE
        assert decoded.object_identifier.instance_number == 1234
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_LIST
        assert decoded.property_array_index == 5

    def test_round_trip_array_index_zero(self):
        req = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=0,
        )
        decoded = ReadPropertyRequest.decode(req.encode())
        assert decoded.property_array_index == 0

    def test_device_object_name(self):
        req = ReadPropertyRequest(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 99),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
        )
        decoded = ReadPropertyRequest.decode(req.encode())
        assert decoded.property_identifier == PropertyIdentifier.OBJECT_NAME


class TestReadPropertyACK:
    def test_round_trip_basic(self):
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.ANALOG_INPUT, 1),
            property_identifier=PropertyIdentifier.PRESENT_VALUE,
            property_value=b"\x44\x42\x28\x00\x00",  # REAL 42.0
        )
        decoded = ReadPropertyACK.decode(ack.encode())
        assert decoded.object_identifier.object_type == ObjectType.ANALOG_INPUT
        assert decoded.object_identifier.instance_number == 1
        assert decoded.property_identifier == PropertyIdentifier.PRESENT_VALUE
        assert decoded.property_array_index is None
        assert decoded.property_value == b"\x44\x42\x28\x00\x00"

    def test_round_trip_with_array_index(self):
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 100),
            property_identifier=PropertyIdentifier.OBJECT_LIST,
            property_array_index=3,
            property_value=b"\xc4\x00\x00\x00\x01",  # object-id
        )
        decoded = ReadPropertyACK.decode(ack.encode())
        assert decoded.property_array_index == 3
        assert decoded.property_value == b"\xc4\x00\x00\x00\x01"

    def test_round_trip_empty_value(self):
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            property_identifier=PropertyIdentifier.DESCRIPTION,
            property_value=b"",
        )
        decoded = ReadPropertyACK.decode(ack.encode())
        assert decoded.property_value == b""

    def test_round_trip_complex_value(self):
        # Simulate a multi-element value (e.g., a character string)
        value = b"\x75\x05\x00test"  # application-tagged char string "test"
        ack = ReadPropertyACK(
            object_identifier=ObjectIdentifier(ObjectType.DEVICE, 50),
            property_identifier=PropertyIdentifier.OBJECT_NAME,
            property_value=value,
        )
        decoded = ReadPropertyACK.decode(ack.encode())
        assert decoded.property_value == value
