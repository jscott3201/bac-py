"""Tests for device discovery services (Who-Am-I / You-Are)."""

from bac_py.services.device_discovery import WhoAmIRequest, YouAreRequest
from bac_py.types.enums import ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestWhoAmIRequest:
    def test_round_trip(self):
        request = WhoAmIRequest(
            vendor_id=42,
            model_name="TestController",
            serial_number="SN-12345",
        )
        encoded = request.encode()
        decoded = WhoAmIRequest.decode(encoded)
        assert decoded.vendor_id == 42
        assert decoded.model_name == "TestController"
        assert decoded.serial_number == "SN-12345"

    def test_round_trip_unicode(self):
        request = WhoAmIRequest(
            vendor_id=999,
            model_name="Contrlr-2000",
            serial_number="ABC-XYZ-789",
        )
        encoded = request.encode()
        decoded = WhoAmIRequest.decode(encoded)
        assert decoded.vendor_id == 999
        assert decoded.model_name == "Contrlr-2000"
        assert decoded.serial_number == "ABC-XYZ-789"

    def test_round_trip_max_vendor_id(self):
        request = WhoAmIRequest(
            vendor_id=65535,
            model_name="M",
            serial_number="S",
        )
        encoded = request.encode()
        decoded = WhoAmIRequest.decode(encoded)
        assert decoded.vendor_id == 65535


class TestYouAreRequest:
    def test_round_trip_minimal(self):
        request = YouAreRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1234),
            device_mac_address=b"\xc0\xa8\x01\x64\xba\xc0",
        )
        encoded = request.encode()
        decoded = YouAreRequest.decode(encoded)
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 1234)
        assert decoded.device_mac_address == b"\xc0\xa8\x01\x64\xba\xc0"
        assert decoded.device_network_number is None

    def test_round_trip_with_network_number(self):
        request = YouAreRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 5678),
            device_mac_address=b"\x0a\x00\x00\x01\xba\xc0",
            device_network_number=2001,
        )
        encoded = request.encode()
        decoded = YouAreRequest.decode(encoded)
        assert decoded.device_identifier == ObjectIdentifier(ObjectType.DEVICE, 5678)
        assert decoded.device_mac_address == b"\x0a\x00\x00\x01\xba\xc0"
        assert decoded.device_network_number == 2001

    def test_round_trip_empty_mac(self):
        request = YouAreRequest(
            device_identifier=ObjectIdentifier(ObjectType.DEVICE, 1),
            device_mac_address=b"\x01",
        )
        encoded = request.encode()
        decoded = YouAreRequest.decode(encoded)
        assert decoded.device_mac_address == b"\x01"
