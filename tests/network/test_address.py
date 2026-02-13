import pytest

from bac_py.network.address import (
    GLOBAL_BROADCAST,
    LOCAL_BROADCAST,
    BACnetAddress,
    BIPAddress,
    EthernetAddress,
    parse_address,
    remote_broadcast,
    remote_station,
)


class TestBIPAddress:
    def test_encode_decode_round_trip(self):
        addr = BIPAddress(host="192.168.1.100", port=47808)
        encoded = addr.encode()
        decoded = BIPAddress.decode(encoded)
        assert decoded == addr

    def test_encode_produces_six_bytes(self):
        addr = BIPAddress(host="10.0.0.1", port=47808)
        encoded = addr.encode()
        assert len(encoded) == 6

    def test_encode_wire_format(self):
        addr = BIPAddress(host="192.168.1.100", port=0xBAC0)
        encoded = addr.encode()
        assert encoded == bytes([192, 168, 1, 100, 0xBA, 0xC0])

    def test_decode_from_bytes(self):
        raw = bytes([10, 20, 30, 40, 0x00, 0x50])
        addr = BIPAddress.decode(raw)
        assert addr.host == "10.20.30.40"
        assert addr.port == 80

    def test_decode_from_memoryview(self):
        raw = bytes([192, 168, 0, 1, 0xBA, 0xC0])
        addr = BIPAddress.decode(memoryview(raw))
        assert addr.host == "192.168.0.1"
        assert addr.port == 47808

    def test_to_dict(self):
        addr = BIPAddress(host="192.168.1.1", port=47808)
        d = addr.to_dict()
        assert d == {"host": "192.168.1.1", "port": 47808}

    def test_from_dict(self):
        d = {"host": "10.0.0.5", "port": 12345}
        addr = BIPAddress.from_dict(d)
        assert addr.host == "10.0.0.5"
        assert addr.port == 12345

    def test_to_dict_from_dict_round_trip(self):
        addr = BIPAddress(host="172.16.0.99", port=47808)
        restored = BIPAddress.from_dict(addr.to_dict())
        assert restored == addr

    def test_encode_decode_port_zero(self):
        addr = BIPAddress(host="0.0.0.0", port=0)
        assert BIPAddress.decode(addr.encode()) == addr

    def test_encode_decode_max_port(self):
        addr = BIPAddress(host="255.255.255.255", port=65535)
        assert BIPAddress.decode(addr.encode()) == addr


class TestBACnetAddress:
    def test_is_local_when_network_is_none(self):
        addr = BACnetAddress()
        assert addr.is_local is True

    def test_is_local_when_network_is_set(self):
        addr = BACnetAddress(network=1)
        assert addr.is_local is False

    def test_is_broadcast_when_global(self):
        addr = BACnetAddress(network=0xFFFF)
        assert addr.is_broadcast is True

    def test_is_broadcast_when_no_mac(self):
        addr = BACnetAddress(network=5, mac_address=b"")
        assert addr.is_broadcast is True

    def test_is_broadcast_when_local_with_mac(self):
        addr = BACnetAddress(mac_address=b"\x01")
        assert addr.is_broadcast is False

    def test_is_not_broadcast_with_network_and_mac(self):
        addr = BACnetAddress(network=10, mac_address=b"\x01\x02")
        assert addr.is_broadcast is False

    def test_is_global_broadcast(self):
        addr = BACnetAddress(network=0xFFFF)
        assert addr.is_global_broadcast is True

    def test_is_not_global_broadcast(self):
        addr = BACnetAddress(network=5)
        assert addr.is_global_broadcast is False

    def test_is_not_global_broadcast_when_local(self):
        addr = BACnetAddress()
        assert addr.is_global_broadcast is False

    def test_to_dict_with_network_and_mac(self):
        addr = BACnetAddress(network=7, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        d = addr.to_dict()
        assert d == {"network": 7, "mac_address": "c0a80101bac0"}

    def test_to_dict_local_no_mac(self):
        addr = BACnetAddress()
        d = addr.to_dict()
        assert d == {}

    def test_to_dict_network_only(self):
        addr = BACnetAddress(network=0xFFFF)
        d = addr.to_dict()
        assert d == {"network": 0xFFFF}

    def test_from_dict_with_network_and_mac(self):
        d = {"network": 3, "mac_address": "aabb"}
        addr = BACnetAddress.from_dict(d)
        assert addr.network == 3
        assert addr.mac_address == b"\xaa\xbb"

    def test_from_dict_empty(self):
        addr = BACnetAddress.from_dict({})
        assert addr.network is None
        assert addr.mac_address == b""

    def test_to_dict_from_dict_round_trip(self):
        addr = BACnetAddress(network=42, mac_address=b"\x01\x02\x03")
        restored = BACnetAddress.from_dict(addr.to_dict())
        assert restored == addr

    def test_to_dict_from_dict_round_trip_global_broadcast(self):
        addr = BACnetAddress(network=0xFFFF)
        restored = BACnetAddress.from_dict(addr.to_dict())
        assert restored == addr


class TestConstants:
    def test_local_broadcast(self):
        assert LOCAL_BROADCAST.network is None
        assert LOCAL_BROADCAST.mac_address == b""
        assert LOCAL_BROADCAST.is_local is True
        assert LOCAL_BROADCAST.is_broadcast is True

    def test_global_broadcast(self):
        assert GLOBAL_BROADCAST.network == 0xFFFF
        assert GLOBAL_BROADCAST.mac_address == b""
        assert GLOBAL_BROADCAST.is_global_broadcast is True
        assert GLOBAL_BROADCAST.is_broadcast is True


class TestHelpers:
    def test_remote_broadcast(self):
        addr = remote_broadcast(5)
        assert addr.network == 5
        assert addr.mac_address == b""
        assert addr.is_broadcast is True
        assert addr.is_global_broadcast is False

    def test_remote_station(self):
        mac = b"\x0a\x14\x1e\x28\xba\xc0"
        addr = remote_station(10, mac)
        assert addr.network == 10
        assert addr.mac_address == mac
        assert addr.is_broadcast is False
        assert addr.is_local is False


class TestIsRemoteBroadcast:
    def test_remote_broadcast_true(self):
        addr = BACnetAddress(network=20, mac_address=b"")
        assert addr.is_remote_broadcast is True

    def test_local_broadcast_false(self):
        addr = BACnetAddress()
        assert addr.is_remote_broadcast is False

    def test_global_broadcast_false(self):
        addr = BACnetAddress(network=0xFFFF)
        assert addr.is_remote_broadcast is False

    def test_remote_unicast_false(self):
        addr = BACnetAddress(network=20, mac_address=b"\x01")
        assert addr.is_remote_broadcast is False

    def test_local_unicast_false(self):
        addr = BACnetAddress(mac_address=b"\x01\x02\x03\x04\x05\x06")
        assert addr.is_remote_broadcast is False


class TestEthernetAddress:
    def test_encode_decode_round_trip(self):
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        addr = EthernetAddress(mac=mac)
        encoded = addr.encode()
        decoded = EthernetAddress.decode(encoded)
        assert decoded == addr

    def test_encode_produces_six_bytes(self):
        addr = EthernetAddress(mac=b"\x01\x02\x03\x04\x05\x06")
        assert len(addr.encode()) == 6

    def test_invalid_mac_length_raises(self):
        with pytest.raises(ValueError, match="6 bytes"):
            EthernetAddress(mac=b"\x01\x02\x03")

    def test_to_dict(self):
        addr = EthernetAddress(mac=b"\xaa\xbb\xcc\xdd\xee\xff")
        d = addr.to_dict()
        assert d == {"mac": "aa:bb:cc:dd:ee:ff"}

    def test_from_dict(self):
        d = {"mac": "aa:bb:cc:dd:ee:ff"}
        addr = EthernetAddress.from_dict(d)
        assert addr.mac == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_to_dict_from_dict_round_trip(self):
        addr = EthernetAddress(mac=b"\x01\x02\x03\x04\x05\x06")
        restored = EthernetAddress.from_dict(addr.to_dict())
        assert restored == addr

    def test_str(self):
        addr = EthernetAddress(mac=b"\xaa\xbb\xcc\xdd\xee\xff")
        assert str(addr) == "aa:bb:cc:dd:ee:ff"


class TestParseAddress:
    def test_parse_ipv4_default_port(self):
        addr = parse_address("192.168.1.100")
        assert addr.mac_address == b"\xc0\xa8\x01\x64\xba\xc0"

    def test_parse_ipv4_explicit_port(self):
        addr = parse_address("192.168.1.100:47809")
        assert addr.mac_address == b"\xc0\xa8\x01\x64\xba\xc1"

    def test_parse_remote_ipv4(self):
        addr = parse_address("2:192.168.1.100")
        assert addr.network == 2
        assert addr.mac_address == b"\xc0\xa8\x01\x64\xba\xc0"

    def test_parse_global_broadcast(self):
        addr = parse_address("*")
        assert addr == GLOBAL_BROADCAST

    def test_parse_remote_broadcast(self):
        addr = parse_address("2:*")
        assert addr.network == 2
        assert addr.mac_address == b""

    def test_parse_ethernet_mac(self):
        addr = parse_address("aa:bb:cc:dd:ee:ff")
        assert addr.mac_address == b"\xaa\xbb\xcc\xdd\xee\xff"
        assert addr.network is None

    def test_parse_ethernet_mac_uppercase(self):
        addr = parse_address("AA:BB:CC:DD:EE:FF")
        assert addr.mac_address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_parse_remote_ethernet_mac(self):
        addr = parse_address("5:aa:bb:cc:dd:ee:ff")
        assert addr.network == 5
        assert addr.mac_address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_parse_bacnet_address_passthrough(self):
        addr = BACnetAddress(mac_address=b"\x01\x02")
        assert parse_address(addr) is addr

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError):
            parse_address("")

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_address("not-an-address")

    def test_parse_ipv6(self):
        addr = parse_address("[::1]:47808")
        assert addr.network is None
        assert len(addr.mac_address) == 18


class TestParseAddressHexMac:
    """Tests for remote station addresses with arbitrary hex MACs (MS/TP, ARCNET, etc.)."""

    def test_parse_mstp_one_byte_mac(self):
        addr = parse_address("4352:01")
        assert addr.network == 4352
        assert addr.mac_address == b"\x01"

    def test_parse_mstp_high_address(self):
        addr = parse_address("1100:fe")
        assert addr.network == 1100
        assert addr.mac_address == b"\xfe"

    def test_parse_two_byte_mac(self):
        addr = parse_address("200:0a0b")
        assert addr.network == 200
        assert addr.mac_address == b"\x0a\x0b"

    def test_parse_three_byte_mac(self):
        addr = parse_address("300:aabbcc")
        assert addr.network == 300
        assert addr.mac_address == b"\xaa\xbb\xcc"

    def test_parse_four_byte_mac(self):
        addr = parse_address("400:deadbeef")
        assert addr.network == 400
        assert addr.mac_address == b"\xde\xad\xbe\xef"

    def test_parse_uppercase_hex(self):
        addr = parse_address("500:ABCDEF01")
        assert addr.network == 500
        assert addr.mac_address == b"\xab\xcd\xef\x01"

    def test_parse_mixed_case_hex(self):
        addr = parse_address("600:aAbBcC")
        assert addr.network == 600
        assert addr.mac_address == b"\xaa\xbb\xcc"

    def test_is_remote_not_local(self):
        addr = parse_address("4352:01")
        assert addr.is_local is False
        assert addr.is_broadcast is False

    def test_network_one(self):
        addr = parse_address("1:01")
        assert addr.network == 1
        assert addr.mac_address == b"\x01"

    def test_network_max(self):
        addr = parse_address("65534:ff")
        assert addr.network == 65534
        assert addr.mac_address == b"\xff"

    def test_round_trip_str_parse_one_byte(self):
        """BACnetAddress.__str__() -> parse_address() round trip for MS/TP."""
        original = BACnetAddress(network=4352, mac_address=b"\x01")
        s = str(original)
        assert s == "4352:01"
        restored = parse_address(s)
        assert restored == original

    def test_round_trip_str_parse_two_byte(self):
        original = BACnetAddress(network=200, mac_address=b"\x0a\x0b")
        s = str(original)
        assert s == "200:0a0b"
        restored = parse_address(s)
        assert restored == original

    def test_round_trip_str_parse_four_byte(self):
        original = BACnetAddress(network=100, mac_address=b"\xde\xad\xbe\xef")
        s = str(original)
        restored = parse_address(s)
        assert restored == original

    def test_ipv4_still_takes_priority(self):
        """Ensure '2:192.168.1.100' is still parsed as BACnet/IP, not hex MAC."""
        addr = parse_address("2:192.168.1.100")
        assert addr.network == 2
        # BACnet/IP: 6-byte MAC (4-byte IP + 2-byte port)
        assert len(addr.mac_address) == 6

    def test_ethernet_still_takes_priority(self):
        """Ensure 'aa:bb:cc:dd:ee:ff' is still parsed as Ethernet MAC."""
        addr = parse_address("aa:bb:cc:dd:ee:ff")
        assert addr.network is None
        assert addr.mac_address == b"\xaa\xbb\xcc\xdd\xee\xff"

    def test_broadcast_still_works(self):
        addr = parse_address("2:*")
        assert addr.network == 2
        assert addr.mac_address == b""

    def test_odd_length_hex_raises(self):
        """Odd-length hex string is not a valid MAC."""
        with pytest.raises(ValueError):
            parse_address("100:0")

    def test_non_hex_chars_raises(self):
        with pytest.raises(ValueError):
            parse_address("100:zz")


class TestAddressStrRoundTrip:
    """Comprehensive round-trip tests: BACnetAddress -> str() -> parse_address() -> BACnetAddress.

    Verifies that __str__() produces output that parse_address() can reconstruct
    to an equivalent address, covering all MAC lengths and address types.
    """

    # --- Variable-length MACs with network (non-IP, non-Ethernet) ---

    @pytest.mark.parametrize("mac_len", [1, 2, 3, 4, 5, 7, 8])
    def test_round_trip_variable_mac_with_network(self, mac_len):
        """Round-trip for arbitrary MAC lengths (1-8, excluding 6) with network number."""
        mac = bytes(range(1, mac_len + 1))
        addr = BACnetAddress(network=100, mac_address=mac)
        restored = parse_address(str(addr))
        assert restored == addr

    @pytest.mark.parametrize("mac_len", [1, 2, 3, 4, 5, 7, 8])
    def test_str_format_variable_mac_with_network(self, mac_len):
        """Verify __str__ format: 'NETWORK:HEXMAC' with zero-padded lowercase hex."""
        mac = bytes(range(1, mac_len + 1))
        addr = BACnetAddress(network=100, mac_address=mac)
        s = str(addr)
        # Must be "100:" followed by hex
        assert s.startswith("100:")
        hex_part = s.split(":", 1)[1]
        # Hex must be lowercase
        assert hex_part == hex_part.lower()
        # Hex must be even-length (zero-padded bytes)
        assert len(hex_part) == mac_len * 2
        # Each byte must be 2 hex chars (e.g., "01" not "1")
        assert hex_part == mac.hex()

    @pytest.mark.parametrize("mac_len", [1, 2, 3, 4, 5, 7, 8])
    def test_round_trip_variable_mac_without_network(self, mac_len):
        """Local addresses with non-IP MACs: str() produces plain hex, parse_address rejects it.

        parse_address() requires a network prefix for hex MACs (_REMOTE_HEX_RE),
        so local non-IP hex MACs cannot round-trip. This documents the limitation.
        """
        mac = bytes(range(1, mac_len + 1))
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        # __str__ produces bare hex for local non-IP MAC
        assert s == mac.hex()
        assert ":" not in s
        # parse_address cannot parse bare hex without a network prefix
        with pytest.raises(ValueError):
            parse_address(s)

    # --- 6-byte BACnet/IP MAC (interpreted as IPv4:port) ---

    def test_round_trip_6byte_ip_mac_local(self):
        """6-byte MAC local: str() produces 'IP:PORT', which round-trips through parse_address."""
        mac = bytes([192, 168, 1, 100, 0xBA, 0xC0])
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        assert s == "192.168.1.100:47808"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_6byte_ip_mac_with_network(self):
        """6-byte MAC remote: str() produces 'NET:IP:PORT', which round-trips."""
        mac = bytes([10, 0, 0, 1, 0xBA, 0xC1])
        addr = BACnetAddress(network=5, mac_address=mac)
        s = str(addr)
        assert s == "5:10.0.0.1:47809"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_6byte_ip_mac_port_zero(self):
        """6-byte MAC with port 0."""
        mac = bytes([10, 0, 0, 1, 0x00, 0x00])
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        assert s == "10.0.0.1:0"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_6byte_ip_mac_max_port(self):
        """6-byte MAC with port 65535."""
        mac = bytes([255, 255, 255, 255, 0xFF, 0xFF])
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        assert s == "255.255.255.255:65535"
        restored = parse_address(s)
        assert restored == addr

    # --- 18-byte BACnet/IPv6 MAC ---

    def test_round_trip_18byte_ipv6_mac_local(self):
        """18-byte MAC local: str() produces '[ipv6]:port', round-trips."""
        import socket

        ipv6_bytes = socket.inet_pton(socket.AF_INET6, "::1")
        port_bytes = (47808).to_bytes(2, "big")
        mac = ipv6_bytes + port_bytes
        assert len(mac) == 18
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        assert "[" in s and "]" in s
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_18byte_ipv6_mac_with_network(self):
        """18-byte MAC remote: str() produces 'NET:[ipv6]:port', round-trips."""
        import socket

        ipv6_bytes = socket.inet_pton(socket.AF_INET6, "fe80::1")
        port_bytes = (47808).to_bytes(2, "big")
        mac = ipv6_bytes + port_bytes
        addr = BACnetAddress(network=10, mac_address=mac)
        s = str(addr)
        assert s.startswith("10:")
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_18byte_ipv6_full_address(self):
        """18-byte MAC with a full IPv6 address (not compressed)."""
        import socket

        ipv6_bytes = socket.inet_pton(socket.AF_INET6, "2001:db8::1")
        port_bytes = (9999).to_bytes(2, "big")
        mac = ipv6_bytes + port_bytes
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        restored = parse_address(s)
        assert restored == addr

    # --- Empty MAC: broadcasts ---

    def test_round_trip_global_broadcast(self):
        """Global broadcast: str() -> '*' -> parse_address -> GLOBAL_BROADCAST."""
        assert str(GLOBAL_BROADCAST) == "*"
        restored = parse_address(str(GLOBAL_BROADCAST))
        assert restored == GLOBAL_BROADCAST

    def test_round_trip_remote_broadcast(self):
        """Remote broadcast: str() -> 'N:*' -> parse_address -> same address."""
        addr = remote_broadcast(42)
        s = str(addr)
        assert s == "42:*"
        restored = parse_address(s)
        assert restored == addr

    @pytest.mark.parametrize("network", [1, 100, 1000, 65534])
    def test_round_trip_remote_broadcast_various_networks(self, network):
        """Remote broadcast on various network numbers."""
        addr = remote_broadcast(network)
        s = str(addr)
        assert s == f"{network}:*"
        restored = parse_address(s)
        assert restored == addr

    def test_local_broadcast_str_empty(self):
        """Local broadcast: str() produces '', which parse_address rejects."""
        assert str(LOCAL_BROADCAST) == ""
        with pytest.raises(ValueError):
            parse_address(str(LOCAL_BROADCAST))

    def test_local_broadcast_empty_mac_no_network(self):
        """Empty MAC, no network: same as LOCAL_BROADCAST."""
        addr = BACnetAddress(network=None, mac_address=b"")
        assert str(addr) == ""
        assert addr == LOCAL_BROADCAST

    # --- __str__ output format verification ---

    def test_str_format_hex_is_lowercase(self):
        """Hex output in __str__ must be lowercase."""
        addr = BACnetAddress(network=1, mac_address=b"\xab\xcd\xef")
        s = str(addr)
        assert s == "1:abcdef"

    def test_str_format_hex_is_zero_padded(self):
        """Each byte must be zero-padded to 2 hex chars (e.g., '01' not '1')."""
        addr = BACnetAddress(network=1, mac_address=b"\x01")
        s = str(addr)
        assert s == "1:01"
        # Not "1:1"
        assert s != "1:1" or s == "1:01"

    def test_str_format_single_byte_zero(self):
        """Byte 0x00 should format as '00'."""
        addr = BACnetAddress(network=50, mac_address=b"\x00")
        s = str(addr)
        assert s == "50:00"

    def test_str_format_single_byte_max(self):
        """Byte 0xFF should format as 'ff'."""
        addr = BACnetAddress(network=50, mac_address=b"\xff")
        s = str(addr)
        assert s == "50:ff"

    def test_str_format_multi_byte_all_zeros(self):
        """All-zero MAC bytes should be zero-padded."""
        addr = BACnetAddress(network=1, mac_address=b"\x00\x00\x00")
        s = str(addr)
        assert s == "1:000000"

    def test_str_format_ip_colon_port(self):
        """6-byte MAC str format must include port after colon."""
        mac = bytes([192, 168, 0, 1, 0xBA, 0xC0])
        addr = BACnetAddress(mac_address=mac)
        s = str(addr)
        # Must have IP:PORT format (IP contains dots, port follows last colon)
        parts = s.rsplit(":", 1)
        assert len(parts) == 2
        assert "." in parts[0]  # IP portion contains dots
        assert parts[1].isdigit()  # port is numeric

    def test_str_format_remote_ip_has_network_prefix(self):
        """Remote BACnet/IP address must have 'NET:IP:PORT' format."""
        mac = bytes([10, 0, 0, 1, 0xBA, 0xC0])
        addr = BACnetAddress(network=7, mac_address=mac)
        s = str(addr)
        assert s == "7:10.0.0.1:47808"

    # --- Edge cases ---

    def test_round_trip_network_1(self):
        """Minimum valid network number (1)."""
        addr = BACnetAddress(network=1, mac_address=b"\x42")
        restored = parse_address(str(addr))
        assert restored == addr

    def test_round_trip_network_65534(self):
        """Maximum valid unicast network number (65534)."""
        addr = BACnetAddress(network=65534, mac_address=b"\x42")
        restored = parse_address(str(addr))
        assert restored == addr

    def test_round_trip_all_ff_mac(self):
        """MAC of all 0xFF bytes."""
        addr = BACnetAddress(network=1, mac_address=b"\xff\xff\xff")
        s = str(addr)
        assert s == "1:ffffff"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_all_zero_mac(self):
        """MAC of all 0x00 bytes."""
        addr = BACnetAddress(network=1, mac_address=b"\x00\x00")
        s = str(addr)
        assert s == "1:0000"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_8_byte_mac(self):
        """8-byte MAC (uncommon but valid)."""
        mac = bytes(range(0x10, 0x18))
        addr = BACnetAddress(network=200, mac_address=mac)
        s = str(addr)
        assert s == "200:1011121314151617"
        restored = parse_address(s)
        assert restored == addr

    @pytest.mark.parametrize(
        "network,mac,expected_str",
        [
            (100, b"\x01", "100:01"),
            (100, b"\x0a\x0b", "100:0a0b"),
            (100, b"\xaa\xbb\xcc", "100:aabbcc"),
            (100, b"\xde\xad\xbe\xef", "100:deadbeef"),
            (100, b"\x01\x02\x03\x04\x05", "100:0102030405"),
            (100, b"\x01\x02\x03\x04\x05\x06\x07", "100:01020304050607"),
            (100, b"\x01\x02\x03\x04\x05\x06\x07\x08", "100:0102030405060708"),
        ],
    )
    def test_str_output_exact(self, network, mac, expected_str):
        """Verify exact __str__ output for various MAC lengths with network 100."""
        addr = BACnetAddress(network=network, mac_address=mac)
        assert str(addr) == expected_str

    def test_global_broadcast_network_ffff(self):
        """Network 0xFFFF is global broadcast regardless of MAC."""
        addr = BACnetAddress(network=0xFFFF)
        assert str(addr) == "*"
        assert addr.is_global_broadcast

    def test_str_parse_consistency_with_constants(self):
        """Verify GLOBAL_BROADCAST round-trips, LOCAL_BROADCAST does not."""
        # GLOBAL_BROADCAST round-trips
        assert parse_address(str(GLOBAL_BROADCAST)) == GLOBAL_BROADCAST
        # LOCAL_BROADCAST str is empty, which is not parseable
        assert str(LOCAL_BROADCAST) == ""

    def test_round_trip_6byte_mac_default_port(self):
        """6-byte MAC with default BACnet port 0xBAC0."""
        from bac_py.network.address import BIPAddress

        bip = BIPAddress(host="172.16.0.1", port=0xBAC0)
        addr = BACnetAddress(mac_address=bip.encode())
        s = str(addr)
        assert s == "172.16.0.1:47808"
        restored = parse_address(s)
        assert restored == addr

    def test_round_trip_6byte_mac_non_default_port(self):
        """6-byte MAC with a non-default port."""
        from bac_py.network.address import BIPAddress

        bip = BIPAddress(host="10.1.2.3", port=12345)
        addr = BACnetAddress(mac_address=bip.encode())
        s = str(addr)
        assert s == "10.1.2.3:12345"
        restored = parse_address(s)
        assert restored == addr


# ---------------------------------------------------------------------------
# Additional coverage tests for address validation edge cases
# ---------------------------------------------------------------------------


class TestEthernetAddressBadMac:
    """EthernetAddress with wrong MAC length."""

    def test_too_short(self):
        with pytest.raises(ValueError, match="6 bytes"):
            EthernetAddress(mac=b"\x01\x02\x03\x04\x05")

    def test_too_long(self):
        with pytest.raises(ValueError, match="6 bytes"):
            EthernetAddress(mac=b"\x01\x02\x03\x04\x05\x06\x07")

    def test_empty(self):
        with pytest.raises(ValueError, match="6 bytes"):
            EthernetAddress(mac=b"")

    def test_one_byte(self):
        with pytest.raises(ValueError, match="6 bytes"):
            EthernetAddress(mac=b"\x01")


class TestBACnetAddressNetworkRange:
    """BACnetAddress network number validation."""

    def test_network_zero_raises(self):
        with pytest.raises(ValueError, match="Network number must be 1-65534"):
            BACnetAddress(network=0, mac_address=b"\x01")

    def test_network_negative_raises(self):
        with pytest.raises(ValueError, match="Network number must be 1-65534"):
            BACnetAddress(network=-1, mac_address=b"\x01")

    def test_network_65535_is_valid_global_broadcast(self):
        """0xFFFF (65535) is the special global broadcast value, allowed."""
        addr = BACnetAddress(network=0xFFFF)
        assert addr.is_global_broadcast is True

    def test_network_65535_with_mac_allowed(self):
        addr = BACnetAddress(network=0xFFFF, mac_address=b"\x01")
        assert addr.network == 0xFFFF

    def test_network_1_valid(self):
        addr = BACnetAddress(network=1, mac_address=b"\x01")
        assert addr.network == 1

    def test_network_65534_valid(self):
        addr = BACnetAddress(network=65534, mac_address=b"\x01")
        assert addr.network == 65534


class TestParseAddressPortRange:
    """Port number out-of-range validation in parse_address."""

    def test_ipv6_port_out_of_range(self):
        """IPv6 address with port > 65535 should raise ValueError."""
        with pytest.raises(ValueError, match="Port number out of range"):
            parse_address("[::1]:70000")

    def test_ipv4_port_out_of_range(self):
        """IPv4 address with port > 65535 should raise ValueError."""
        with pytest.raises(ValueError, match="Port number out of range"):
            parse_address("192.168.1.1:70000")

    def test_ipv6_port_negative_implicit(self):
        """Negative port number cannot be parsed (regex won't match negative)."""
        with pytest.raises(ValueError, match="Cannot parse address"):
            parse_address("[::1]:-1")

    def test_ipv6_invalid_address(self):
        """Invalid IPv6 address in brackets should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid IPv6 address"):
            parse_address("[not-valid-ipv6]")
