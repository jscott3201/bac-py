"""Tests for BACnet/IPv6 BVLL encoding and decoding (bvll_ipv6.py)."""

import pytest

from bac_py.network.address import BIP6Address
from bac_py.transport.bvll_ipv6 import (
    BVLC_TYPE_BACNET_IPV6,
    BVLL6_HEADER_LENGTH,
    VMAC_LENGTH,
    decode_bvll6,
    encode_bvll6,
)
from bac_py.types.enums import Bvlc6Function


class TestConstants:
    def test_bvlc_type_bacnet_ipv6(self):
        assert BVLC_TYPE_BACNET_IPV6 == 0x82

    def test_bvll6_header_length(self):
        assert BVLL6_HEADER_LENGTH == 4

    def test_vmac_length(self):
        assert VMAC_LENGTH == 3


class TestEncodeDecodeRoundTrip:
    def test_bvlc_result(self):
        src = b"\x01\x02\x03"
        payload = b"\x00\x00"
        encoded = encode_bvll6(Bvlc6Function.BVLC_RESULT, payload, source_vmac=src)
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.BVLC_RESULT
        assert decoded.data == payload
        assert decoded.source_vmac == src
        assert decoded.dest_vmac is None

    def test_original_unicast_npdu(self):
        src = b"\x01\x02\x03"
        dst = b"\x04\x05\x06"
        payload = b"\x01\x00\x10"
        encoded = encode_bvll6(
            Bvlc6Function.ORIGINAL_UNICAST_NPDU,
            payload,
            source_vmac=src,
            dest_vmac=dst,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.ORIGINAL_UNICAST_NPDU
        assert decoded.data == payload
        assert decoded.source_vmac == src
        assert decoded.dest_vmac == dst
        assert decoded.originating_address is None

    def test_original_broadcast_npdu(self):
        src = b"\xaa\xbb\xcc"
        payload = b"\x01\x00\x10\x08"
        encoded = encode_bvll6(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            payload,
            source_vmac=src,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.ORIGINAL_BROADCAST_NPDU
        assert decoded.data == payload
        assert decoded.source_vmac == src
        assert decoded.dest_vmac is None

    def test_forwarded_npdu(self):
        src = b"\x11\x22\x33"
        orig = BIP6Address(host="::1", port=47808)
        payload = b"\x01\x00"
        encoded = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            payload,
            source_vmac=src,
            originating_address=orig,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.FORWARDED_NPDU
        assert decoded.data == payload
        assert decoded.source_vmac == src
        assert decoded.originating_address is not None
        assert decoded.originating_address.host == "::1"
        assert decoded.originating_address.port == 47808

    def test_address_resolution(self):
        src = b"\xaa\xbb\xcc"
        target_vmac = b"\xdd\xee\xff"
        encoded = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=src,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.ADDRESS_RESOLUTION
        assert decoded.data == target_vmac
        assert decoded.source_vmac == src

    def test_forwarded_address_resolution(self):
        src = b"\x01\x02\x03"
        orig = BIP6Address(host="fe80::1", port=47808)
        target_vmac = b"\xdd\xee\xff"
        encoded = encode_bvll6(
            Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=src,
            originating_address=orig,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION
        assert decoded.data == target_vmac
        assert decoded.source_vmac == src
        assert decoded.originating_address is not None
        assert decoded.originating_address.port == 47808

    def test_address_resolution_ack(self):
        src = b"\x01\x02\x03"
        dst = b"\x04\x05\x06"
        encoded = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=src,
            dest_vmac=dst,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.ADDRESS_RESOLUTION_ACK
        assert decoded.source_vmac == src
        assert decoded.dest_vmac == dst
        assert decoded.data == b""

    def test_virtual_address_resolution(self):
        src = b"\x0a\x0b\x0c"
        encoded = encode_bvll6(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION,
            b"",
            source_vmac=src,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION
        assert decoded.source_vmac == src

    def test_virtual_address_resolution_ack(self):
        src = b"\x0a\x0b\x0c"
        dst = b"\x0d\x0e\x0f"
        encoded = encode_bvll6(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=src,
            dest_vmac=dst,
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK
        assert decoded.source_vmac == src
        assert decoded.dest_vmac == dst

    def test_register_foreign_device(self):
        src = b"\x0a\x0b\x0c"
        payload = b"\x00\x3c"  # TTL = 60 seconds
        encoded = encode_bvll6(Bvlc6Function.REGISTER_FOREIGN_DEVICE, payload, source_vmac=src)
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.REGISTER_FOREIGN_DEVICE
        assert decoded.data == payload
        assert decoded.source_vmac == src

    def test_delete_foreign_device_table_entry(self):
        src = b"\x0a\x0b\x0c"
        payload = b"\x01\x02\x03\x04\x05\x06"
        encoded = encode_bvll6(
            Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY, payload, source_vmac=src
        )
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY
        assert decoded.data == payload
        assert decoded.source_vmac == src

    def test_distribute_broadcast_npdu(self):
        src = b"\x0a\x0b\x0c"
        payload = b"\x01\x00\x10\x08\x00"
        encoded = encode_bvll6(Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU, payload, source_vmac=src)
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU
        assert decoded.data == payload
        assert decoded.source_vmac == src

    def test_secure_bvll(self):
        payload = b"\x00\x01\x02\x03"
        encoded = encode_bvll6(Bvlc6Function.SECURE_BVLL, payload)
        decoded = decode_bvll6(encoded)
        assert decoded.function == Bvlc6Function.SECURE_BVLL
        assert decoded.data == payload


class TestEncodeFormat:
    def test_header_starts_with_bvlc6_type(self):
        encoded = encode_bvll6(Bvlc6Function.BVLC_RESULT, b"\x00\x00", source_vmac=b"\x01\x02\x03")
        assert encoded[0] == BVLC_TYPE_BACNET_IPV6

    def test_header_function_byte(self):
        encoded = encode_bvll6(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            b"\x01",
            source_vmac=b"\x01\x02\x03",
        )
        assert encoded[1] == Bvlc6Function.ORIGINAL_BROADCAST_NPDU

    def test_header_length_bvlc_result(self):
        payload = b"\x00\x00"
        encoded = encode_bvll6(Bvlc6Function.BVLC_RESULT, payload, source_vmac=b"\x01\x02\x03")
        length = (encoded[2] << 8) | encoded[3]
        # Header(4) + src_vmac(3) + payload(2)
        assert length == BVLL6_HEADER_LENGTH + VMAC_LENGTH + len(payload)

    def test_header_length_unicast(self):
        payload = b"\x01\x02\x03"
        encoded = encode_bvll6(
            Bvlc6Function.ORIGINAL_UNICAST_NPDU,
            payload,
            source_vmac=b"\x01\x02\x03",
            dest_vmac=b"\x04\x05\x06",
        )
        length = (encoded[2] << 8) | encoded[3]
        # Header(4) + src_vmac(3) + dst_vmac(3) + payload(3)
        assert length == BVLL6_HEADER_LENGTH + 3 + 3 + len(payload)

    def test_header_length_forwarded(self):
        payload = b"\x01\x02"
        orig = BIP6Address(host="::1", port=47808)
        encoded = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            payload,
            source_vmac=b"\x01\x02\x03",
            originating_address=orig,
        )
        length = (encoded[2] << 8) | encoded[3]
        # Header(4) + src_vmac(3) + originating(18) + payload(2)
        assert length == BVLL6_HEADER_LENGTH + 3 + 18 + len(payload)


class TestDecodeErrors:
    def test_data_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            decode_bvll6(b"\x82\x00\x00")

    def test_invalid_bvlc_type(self):
        with pytest.raises(ValueError, match="Invalid BVLC type"):
            decode_bvll6(b"\x81\x00\x00\x04")

    def test_invalid_length_too_small(self):
        with pytest.raises(ValueError, match="Invalid BVLL6 length"):
            decode_bvll6(b"\x82\x00\x00\x02\x00\x00")

    def test_invalid_length_too_large(self):
        with pytest.raises(ValueError, match="Invalid BVLL6 length"):
            decode_bvll6(b"\x82\x00\x00\xff\x00\x00")

    def test_truncated_source_vmac(self):
        # Original-Unicast requires source + dest VMAC but data is too short
        with pytest.raises(ValueError, match="truncated"):
            decode_bvll6(b"\x82\x01\x00\x06\x01\x02")

    def test_truncated_dest_vmac(self):
        # Original-Unicast with source but missing dest
        with pytest.raises(ValueError, match="truncated"):
            decode_bvll6(b"\x82\x01\x00\x07\x01\x02\x03")

    def test_truncated_originating_address(self):
        # Forwarded-NPDU with source VMAC but missing originating address
        data = b"\x82\x08\x00\x09\x01\x02\x03\x00\x00"
        with pytest.raises(ValueError, match="truncated"):
            decode_bvll6(data)

    def test_decode_from_memoryview(self):
        payload = b"\x01\x02"
        encoded = encode_bvll6(Bvlc6Function.BVLC_RESULT, payload, source_vmac=b"\x01\x02\x03")
        decoded = decode_bvll6(memoryview(encoded))
        assert decoded.function == Bvlc6Function.BVLC_RESULT
        assert decoded.data == payload
        assert decoded.source_vmac == b"\x01\x02\x03"


class TestEncodeErrors:
    def test_unicast_without_source_vmac(self):
        with pytest.raises(ValueError, match="source VMAC"):
            encode_bvll6(Bvlc6Function.ORIGINAL_UNICAST_NPDU, b"\x01")

    def test_unicast_without_dest_vmac(self):
        with pytest.raises(ValueError, match="destination VMAC"):
            encode_bvll6(
                Bvlc6Function.ORIGINAL_UNICAST_NPDU,
                b"\x01",
                source_vmac=b"\x01\x02\x03",
            )

    def test_broadcast_without_source_vmac(self):
        with pytest.raises(ValueError, match="source VMAC"):
            encode_bvll6(Bvlc6Function.ORIGINAL_BROADCAST_NPDU, b"\x01")

    def test_forwarded_without_originating(self):
        with pytest.raises(ValueError, match="originating_address"):
            encode_bvll6(
                Bvlc6Function.FORWARDED_NPDU,
                b"\x01",
                source_vmac=b"\x01\x02\x03",
            )

    def test_wrong_vmac_length(self):
        with pytest.raises(ValueError, match="source VMAC"):
            encode_bvll6(
                Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
                b"\x01",
                source_vmac=b"\x01\x02",  # 2 bytes instead of 3
            )

    def test_wrong_dest_vmac_length(self):
        with pytest.raises(ValueError, match="destination VMAC"):
            encode_bvll6(
                Bvlc6Function.ORIGINAL_UNICAST_NPDU,
                b"\x01",
                source_vmac=b"\x01\x02\x03",
                dest_vmac=b"\x04\x05",  # 2 bytes instead of 3
            )
