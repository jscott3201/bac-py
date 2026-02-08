from bac_py.network.address import (
    GLOBAL_BROADCAST,
    LOCAL_BROADCAST,
    BACnetAddress,
    BIPAddress,
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
