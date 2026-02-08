"""Tests for private transfer services."""

from bac_py.encoding.primitives import encode_application_unsigned
from bac_py.services.private_transfer import (
    ConfirmedPrivateTransferACK,
    ConfirmedPrivateTransferRequest,
    UnconfirmedPrivateTransferRequest,
)


class TestConfirmedPrivateTransferRequest:
    def test_round_trip_no_params(self):
        request = ConfirmedPrivateTransferRequest(
            vendor_id=42,
            service_number=1,
        )
        encoded = request.encode()
        decoded = ConfirmedPrivateTransferRequest.decode(encoded)
        assert decoded.vendor_id == 42
        assert decoded.service_number == 1
        assert decoded.service_parameters is None

    def test_round_trip_with_params(self):
        params = encode_application_unsigned(12345)
        request = ConfirmedPrivateTransferRequest(
            vendor_id=99,
            service_number=5,
            service_parameters=params,
        )
        encoded = request.encode()
        decoded = ConfirmedPrivateTransferRequest.decode(encoded)
        assert decoded.vendor_id == 99
        assert decoded.service_number == 5
        assert decoded.service_parameters == params


class TestConfirmedPrivateTransferACK:
    def test_round_trip_no_result(self):
        ack = ConfirmedPrivateTransferACK(
            vendor_id=42,
            service_number=1,
        )
        encoded = ack.encode()
        decoded = ConfirmedPrivateTransferACK.decode(encoded)
        assert decoded.vendor_id == 42
        assert decoded.service_number == 1
        assert decoded.result_block is None

    def test_round_trip_with_result(self):
        result = encode_application_unsigned(999)
        ack = ConfirmedPrivateTransferACK(
            vendor_id=42,
            service_number=1,
            result_block=result,
        )
        encoded = ack.encode()
        decoded = ConfirmedPrivateTransferACK.decode(encoded)
        assert decoded.result_block == result


class TestUnconfirmedPrivateTransferRequest:
    def test_round_trip_no_params(self):
        request = UnconfirmedPrivateTransferRequest(
            vendor_id=10,
            service_number=3,
        )
        encoded = request.encode()
        decoded = UnconfirmedPrivateTransferRequest.decode(encoded)
        assert decoded.vendor_id == 10
        assert decoded.service_number == 3
        assert decoded.service_parameters is None

    def test_round_trip_with_params(self):
        params = encode_application_unsigned(42)
        request = UnconfirmedPrivateTransferRequest(
            vendor_id=10,
            service_number=3,
            service_parameters=params,
        )
        encoded = request.encode()
        decoded = UnconfirmedPrivateTransferRequest.decode(encoded)
        assert decoded.service_parameters == params
