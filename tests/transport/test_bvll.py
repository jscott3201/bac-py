import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bvll import (
    BVLC_TYPE_BACNET_IP,
    BVLL_HEADER_LENGTH,
    decode_bvll,
    encode_bvll,
)
from bac_py.types.enums import BvlcFunction


class TestConstants:
    def test_bvlc_type_bacnet_ip(self):
        assert BVLC_TYPE_BACNET_IP == 0x81

    def test_bvll_header_length(self):
        assert BVLL_HEADER_LENGTH == 4


class TestEncodeDecodeRoundTrip:
    def test_original_unicast_npdu(self):
        payload = b"\x01\x00\x10\x02\x00"
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, payload)
        decoded = decode_bvll(encoded)
        assert decoded.function == BvlcFunction.ORIGINAL_UNICAST_NPDU
        assert decoded.data == payload
        assert decoded.originating_address is None

    def test_original_broadcast_npdu(self):
        payload = b"\x01\x00\x10\x08\x00"
        encoded = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, payload)
        decoded = decode_bvll(encoded)
        assert decoded.function == BvlcFunction.ORIGINAL_BROADCAST_NPDU
        assert decoded.data == payload
        assert decoded.originating_address is None

    def test_forwarded_npdu(self):
        orig = BIPAddress(host="192.168.1.50", port=47808)
        payload = b"\x01\x00\x10"
        encoded = encode_bvll(BvlcFunction.FORWARDED_NPDU, payload, originating_address=orig)
        decoded = decode_bvll(encoded)
        assert decoded.function == BvlcFunction.FORWARDED_NPDU
        assert decoded.data == payload
        assert decoded.originating_address is not None
        assert decoded.originating_address.host == "192.168.1.50"
        assert decoded.originating_address.port == 47808

    def test_bvlc_result(self):
        result_data = b"\x00\x00"
        encoded = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        decoded = decode_bvll(encoded)
        assert decoded.function == BvlcFunction.BVLC_RESULT
        assert decoded.data == result_data
        assert decoded.originating_address is None

    def test_empty_payload(self):
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, b"")
        decoded = decode_bvll(encoded)
        assert decoded.function == BvlcFunction.ORIGINAL_UNICAST_NPDU
        assert decoded.data == b""

    def test_large_payload(self):
        payload = bytes(range(256)) * 4
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, payload)
        decoded = decode_bvll(encoded)
        assert decoded.data == payload


class TestEncodeFormat:
    def test_header_starts_with_bvlc_type(self):
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, b"\x01")
        assert encoded[0] == BVLC_TYPE_BACNET_IP

    def test_header_function_byte(self):
        encoded = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, b"\x01")
        assert encoded[1] == BvlcFunction.ORIGINAL_BROADCAST_NPDU

    def test_header_length_field(self):
        payload = b"\x01\x02\x03"
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, payload)
        length = (encoded[2] << 8) | encoded[3]
        assert length == BVLL_HEADER_LENGTH + len(payload)

    def test_forwarded_npdu_length_includes_address(self):
        orig = BIPAddress(host="10.0.0.1", port=47808)
        payload = b"\x01\x02"
        encoded = encode_bvll(BvlcFunction.FORWARDED_NPDU, payload, originating_address=orig)
        length = (encoded[2] << 8) | encoded[3]
        assert length == BVLL_HEADER_LENGTH + 6 + len(payload)


class TestDecodeErrors:
    def test_invalid_bvlc_type_raises(self):
        bad_data = bytes([0x82, 0x0A, 0x00, 0x05, 0x01])
        with pytest.raises(ValueError, match="Invalid BVLC type"):
            decode_bvll(bad_data)

    def test_invalid_bvlc_type_zero_raises(self):
        bad_data = bytes([0x00, 0x0A, 0x00, 0x05, 0x01])
        with pytest.raises(ValueError, match="Invalid BVLC type"):
            decode_bvll(bad_data)

    def test_decode_from_memoryview(self):
        payload = b"\x01\x02"
        encoded = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, payload)
        decoded = decode_bvll(memoryview(encoded))
        assert decoded.function == BvlcFunction.ORIGINAL_UNICAST_NPDU
        assert decoded.data == payload


class TestEncodeErrors:
    def test_forwarded_npdu_without_originating_address_raises(self):
        with pytest.raises(ValueError, match="Forwarded-NPDU requires originating_address"):
            encode_bvll(BvlcFunction.FORWARDED_NPDU, b"\x01")

    def test_forwarded_npdu_with_none_originating_address_raises(self):
        with pytest.raises(ValueError, match="Forwarded-NPDU requires originating_address"):
            encode_bvll(BvlcFunction.FORWARDED_NPDU, b"\x01", originating_address=None)
