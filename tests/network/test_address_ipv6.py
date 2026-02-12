"""Tests for BACnet/IPv6 address types and IPv6 parse_address support."""

import pytest

from bac_py.network.address import (
    BACnetAddress,
    BIP6Address,
    parse_address,
)


class TestBIP6Address:
    def test_encode_decode_round_trip(self):
        addr = BIP6Address(host="::1", port=47808)
        encoded = addr.encode()
        decoded = BIP6Address.decode(encoded)
        assert decoded == addr

    def test_encode_produces_eighteen_bytes(self):
        addr = BIP6Address(host="::1", port=47808)
        encoded = addr.encode()
        assert len(encoded) == 18

    def test_encode_decode_full_address(self):
        addr = BIP6Address(host="2001:db8::1", port=47808)
        encoded = addr.encode()
        decoded = BIP6Address.decode(encoded)
        assert decoded.host == "2001:db8::1"
        assert decoded.port == 47808

    def test_encode_decode_link_local(self):
        addr = BIP6Address(host="fe80::1", port=47808)
        encoded = addr.encode()
        decoded = BIP6Address.decode(encoded)
        assert decoded.host == "fe80::1"
        assert decoded.port == 47808

    def test_decode_from_memoryview(self):
        addr = BIP6Address(host="::1", port=47808)
        encoded = addr.encode()
        decoded = BIP6Address.decode(memoryview(encoded))
        assert decoded == addr

    def test_to_dict(self):
        addr = BIP6Address(host="::1", port=47808)
        d = addr.to_dict()
        assert d == {"host": "::1", "port": 47808}

    def test_from_dict(self):
        d = {"host": "::1", "port": 12345}
        addr = BIP6Address.from_dict(d)
        assert addr.host == "::1"
        assert addr.port == 12345

    def test_to_dict_from_dict_round_trip(self):
        addr = BIP6Address(host="2001:db8::99", port=47808)
        restored = BIP6Address.from_dict(addr.to_dict())
        assert restored == addr

    def test_encode_decode_port_zero(self):
        addr = BIP6Address(host="::", port=0)
        assert BIP6Address.decode(addr.encode()) == addr

    def test_encode_decode_max_port(self):
        addr = BIP6Address(host="::ffff:192.168.1.1", port=65535)
        decoded = BIP6Address.decode(addr.encode())
        assert decoded.port == 65535

    def test_frozen(self):
        addr = BIP6Address(host="::1", port=47808)
        with pytest.raises(AttributeError):
            addr.host = "::2"  # type: ignore[misc]


class TestParseAddressIPv6:
    def test_parse_loopback(self):
        addr = parse_address("[::1]")
        assert len(addr.mac_address) == 18
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.host == "::1"
        assert decoded.port == 0xBAC0

    def test_parse_loopback_with_port(self):
        addr = parse_address("[::1]:47808")
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.host == "::1"
        assert decoded.port == 47808

    def test_parse_loopback_custom_port(self):
        addr = parse_address("[::1]:12345")
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.port == 12345

    def test_parse_with_network(self):
        addr = parse_address("2:[::1]:47808")
        assert addr.network == 2
        assert len(addr.mac_address) == 18
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.host == "::1"
        assert decoded.port == 47808

    def test_parse_with_network_default_port(self):
        addr = parse_address("5:[fe80::1]")
        assert addr.network == 5
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.host == "fe80::1"
        assert decoded.port == 0xBAC0

    def test_parse_full_ipv6(self):
        addr = parse_address("[2001:db8::1]:47808")
        decoded = BIP6Address.decode(addr.mac_address)
        assert decoded.host == "2001:db8::1"
        assert decoded.port == 47808

    def test_parse_invalid_ipv6_raises(self):
        with pytest.raises(ValueError, match="Invalid IPv6 address"):
            parse_address("[not-an-ipv6]")

    def test_parse_passthrough_bacnet_address(self):
        orig = BACnetAddress(mac_address=b"\x01\x02\x03")
        assert parse_address(orig) is orig

    def test_parse_ipv4_still_works(self):
        addr = parse_address("192.168.1.100:47808")
        assert len(addr.mac_address) == 6

    def test_parse_wildcard_still_works(self):
        addr = parse_address("*")
        assert addr.is_global_broadcast


class TestBACnetAddressStrIPv6:
    def test_str_18byte_mac_local(self):
        bip6 = BIP6Address(host="::1", port=47808)
        addr = BACnetAddress(mac_address=bip6.encode())
        s = str(addr)
        assert "[" in s
        assert "]" in s
        assert "47808" in s

    def test_str_18byte_mac_remote(self):
        bip6 = BIP6Address(host="::1", port=47808)
        addr = BACnetAddress(network=2, mac_address=bip6.encode())
        s = str(addr)
        assert s.startswith("2:")
        assert "[" in s

    def test_str_3byte_vmac_local(self):
        addr = BACnetAddress(mac_address=b"\xaa\xbb\xcc")
        s = str(addr)
        assert s == "aabbcc"

    def test_str_3byte_vmac_remote(self):
        addr = BACnetAddress(network=5, mac_address=b"\xaa\xbb\xcc")
        s = str(addr)
        assert s == "5:aabbcc"

    def test_str_round_trip_ipv6(self):
        """Verify that str(BACnetAddress) with 18-byte MAC produces a parseable string."""
        bip6 = BIP6Address(host="::1", port=47808)
        addr = BACnetAddress(mac_address=bip6.encode())
        s = str(addr)
        reparsed = parse_address(s)
        assert reparsed.mac_address == addr.mac_address

    def test_str_round_trip_ipv6_remote(self):
        bip6 = BIP6Address(host="2001:db8::1", port=47808)
        addr = BACnetAddress(network=3, mac_address=bip6.encode())
        s = str(addr)
        reparsed = parse_address(s)
        assert reparsed.network == 3
        assert reparsed.mac_address == addr.mac_address
