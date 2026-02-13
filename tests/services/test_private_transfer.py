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


# ---------------------------------------------------------------------------
# Coverage: private_transfer.py branch partials 81->84, 140->143
# ---------------------------------------------------------------------------


class TestConfirmedPrivateTransferRequestTrailingNonMatchingTag:
    """Branch 81->84: optional serviceParameters check in PrivateTransfer.decode.

    When offset < len(data) is True but the tag is NOT opening tag 2,
    the code falls through to the return without setting service_parameters.
    """

    def test_trailing_non_opening_tag(self):
        """Extra data after serviceNumber with non-matching tag."""
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        request = ConfirmedPrivateTransferRequest(
            vendor_id=42,
            service_number=1,
        )
        encoded = bytearray(request.encode())
        # Append a non-opening context tag (primitive context tag 2)
        encoded.extend(encode_context_tagged(2, encode_unsigned(99)))

        decoded = ConfirmedPrivateTransferRequest.decode(bytes(encoded))
        assert decoded.vendor_id == 42
        assert decoded.service_number == 1
        # The non-opening context tag 2 is not treated as service_parameters
        # because the code checks for opening tag 2 specifically
        assert decoded.service_parameters is None


class TestConfirmedPrivateTransferACKTrailingNonMatchingTag:
    """Branch 140->143: optional result_block check in PrivateTransferACK.decode.

    Same pattern as 81->84 but for the result_block field.
    """

    def test_trailing_non_opening_tag(self):
        """Extra data after serviceNumber in ACK with non-matching tag."""
        from bac_py.encoding.primitives import encode_context_tagged, encode_unsigned

        ack = ConfirmedPrivateTransferACK(
            vendor_id=42,
            service_number=1,
        )
        encoded = bytearray(ack.encode())
        # Append a non-opening context tag (primitive context tag 2)
        encoded.extend(encode_context_tagged(2, encode_unsigned(99)))

        decoded = ConfirmedPrivateTransferACK.decode(bytes(encoded))
        assert decoded.vendor_id == 42
        assert decoded.service_number == 1
        assert decoded.result_block is None
