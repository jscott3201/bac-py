"""Tests for parse_address and BACnetAddress.__str__."""

import pytest

from bac_py.network.address import (
    GLOBAL_BROADCAST,
    LOCAL_BROADCAST,
    BACnetAddress,
    BIPAddress,
    parse_address,
    remote_broadcast,
)


class TestParseAddress:
    def test_ip_only_default_port(self):
        addr = parse_address("192.168.1.100")
        expected_mac = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
        assert addr.network is None
        assert addr.mac_address == expected_mac

    def test_ip_with_port(self):
        addr = parse_address("192.168.1.100:47809")
        expected_mac = BIPAddress(host="192.168.1.100", port=47809).encode()
        assert addr.network is None
        assert addr.mac_address == expected_mac

    def test_ip_with_standard_port(self):
        addr = parse_address("10.0.0.1:47808")
        expected_mac = BIPAddress(host="10.0.0.1", port=47808).encode()
        assert addr.mac_address == expected_mac

    def test_network_and_ip(self):
        addr = parse_address("2:192.168.1.100")
        expected_mac = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
        assert addr.network == 2
        assert addr.mac_address == expected_mac

    def test_network_ip_and_port(self):
        addr = parse_address("5:10.0.0.1:47809")
        expected_mac = BIPAddress(host="10.0.0.1", port=47809).encode()
        assert addr.network == 5
        assert addr.mac_address == expected_mac

    def test_global_broadcast(self):
        addr = parse_address("*")
        assert addr == GLOBAL_BROADCAST

    def test_remote_broadcast(self):
        addr = parse_address("2:*")
        assert addr == remote_broadcast(2)
        assert addr.network == 2
        assert addr.mac_address == b""

    def test_passthrough_bacnet_address(self):
        original = BACnetAddress(mac_address=b"\x01\x02\x03\x04\x05\x06")
        result = parse_address(original)
        assert result is original

    def test_whitespace_stripped(self):
        addr = parse_address("  192.168.1.100  ")
        expected_mac = BIPAddress(host="192.168.1.100", port=0xBAC0).encode()
        assert addr.mac_address == expected_mac

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_address("")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Cannot parse address"):
            parse_address("not-an-address")

    def test_only_whitespace_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_address("   ")

    def test_missing_ip_raises(self):
        with pytest.raises(ValueError, match="Cannot parse address"):
            parse_address("2:")


class TestBACnetAddressStr:
    def test_local_ip_unicast(self):
        mac = BIPAddress(host="192.168.1.100", port=47808).encode()
        addr = BACnetAddress(mac_address=mac)
        assert str(addr) == "192.168.1.100:47808"

    def test_remote_ip_unicast(self):
        mac = BIPAddress(host="10.0.0.1", port=47808).encode()
        addr = BACnetAddress(network=2, mac_address=mac)
        assert str(addr) == "2:10.0.0.1:47808"

    def test_global_broadcast(self):
        assert str(GLOBAL_BROADCAST) == "*"

    def test_remote_broadcast(self):
        addr = remote_broadcast(5)
        assert str(addr) == "5:*"

    def test_local_broadcast(self):
        assert str(LOCAL_BROADCAST) == ""

    def test_non_ip_mac(self):
        addr = BACnetAddress(mac_address=b"\x05")
        assert str(addr) == "05"

    def test_non_ip_mac_with_network(self):
        addr = BACnetAddress(network=3, mac_address=b"\x0a")
        assert str(addr) == "3:0a"


class TestParseAddressStrRoundTrip:
    def test_ip_only(self):
        addr = parse_address("192.168.1.100")
        # Default port gets appended
        assert str(addr) == "192.168.1.100:47808"
        # And parsing that string gives the same address
        assert parse_address(str(addr)) == addr

    def test_ip_with_port(self):
        addr = parse_address("10.0.0.1:47809")
        assert parse_address(str(addr)) == addr

    def test_network_ip_port(self):
        addr = parse_address("2:192.168.1.100:47808")
        assert parse_address(str(addr)) == addr

    def test_global_broadcast(self):
        addr = parse_address("*")
        assert parse_address(str(addr)) == addr

    def test_remote_broadcast(self):
        addr = parse_address("3:*")
        assert parse_address(str(addr)) == addr
