import pytest

from bac_py.network.address import BACnetAddress
from bac_py.network.npdu import BACNET_PROTOCOL_VERSION, NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import NetworkMessageType, NetworkPriority


class TestEncodeDecodeRoundTrip:
    def test_simple_local_npdu(self):
        npdu = NPDU(apdu=b"\x01\x02\x03")
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.version == BACNET_PROTOCOL_VERSION
        assert decoded.is_network_message is False
        assert decoded.expecting_reply is False
        assert decoded.priority == NetworkPriority.NORMAL
        assert decoded.destination is None
        assert decoded.source is None
        assert decoded.apdu == b"\x01\x02\x03"

    def test_npdu_with_destination(self):
        dest = BACnetAddress(network=10, mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        npdu = NPDU(destination=dest, apdu=b"\xaa\xbb")
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.destination is not None
        assert decoded.destination.network == 10
        assert decoded.destination.mac_address == b"\xc0\xa8\x01\x01\xba\xc0"
        assert decoded.source is None
        assert decoded.apdu == b"\xaa\xbb"

    def test_npdu_with_source(self):
        src = BACnetAddress(network=5, mac_address=b"\x01\x02\x03")
        npdu = NPDU(source=src, apdu=b"\xdd")
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.source is not None
        assert decoded.source.network == 5
        assert decoded.source.mac_address == b"\x01\x02\x03"
        assert decoded.destination is None
        assert decoded.apdu == b"\xdd"

    def test_npdu_with_source_and_destination(self):
        src = BACnetAddress(network=1, mac_address=b"\x0a")
        dest = BACnetAddress(network=2, mac_address=b"\x0b\x0c")
        npdu = NPDU(source=src, destination=dest, hop_count=200, apdu=b"\xff")
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.source.network == 1
        assert decoded.source.mac_address == b"\x0a"
        assert decoded.destination.network == 2
        assert decoded.destination.mac_address == b"\x0b\x0c"
        assert decoded.hop_count == 200
        assert decoded.apdu == b"\xff"

    def test_network_layer_message(self):
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            network_message_data=b"\x00\x05",
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.is_network_message is True
        assert decoded.message_type == NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK
        assert decoded.network_message_data == b"\x00\x05"
        assert decoded.apdu == b""

    def test_network_layer_message_with_destination(self):
        dest = BACnetAddress(network=0xFFFF)
        npdu = NPDU(
            is_network_message=True,
            destination=dest,
            message_type=NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
            network_message_data=b"\x00\x01\x00\x02",
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.is_network_message is True
        assert decoded.destination.network == 0xFFFF
        assert decoded.destination.mac_address == b""
        assert decoded.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        assert decoded.network_message_data == b"\x00\x01\x00\x02"

    def test_priority_normal(self):
        npdu = NPDU(priority=NetworkPriority.NORMAL, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.priority == NetworkPriority.NORMAL

    def test_priority_urgent(self):
        npdu = NPDU(priority=NetworkPriority.URGENT, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.priority == NetworkPriority.URGENT

    def test_priority_critical_equipment(self):
        npdu = NPDU(priority=NetworkPriority.CRITICAL_EQUIPMENT, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.priority == NetworkPriority.CRITICAL_EQUIPMENT

    def test_priority_life_safety(self):
        npdu = NPDU(priority=NetworkPriority.LIFE_SAFETY, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.priority == NetworkPriority.LIFE_SAFETY

    def test_expecting_reply_true(self):
        npdu = NPDU(expecting_reply=True, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.expecting_reply is True

    def test_expecting_reply_false(self):
        npdu = NPDU(expecting_reply=False, apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.expecting_reply is False

    def test_global_broadcast_destination(self):
        dest = BACnetAddress(network=0xFFFF)
        npdu = NPDU(destination=dest, apdu=b"\x01\x02")
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.destination.network == 0xFFFF
        assert decoded.destination.mac_address == b""
        assert decoded.destination.is_global_broadcast is True

    def test_version_preserved(self):
        npdu = NPDU(apdu=b"\x01")
        decoded = decode_npdu(encode_npdu(npdu))
        assert decoded.version == BACNET_PROTOCOL_VERSION

    def test_empty_apdu(self):
        npdu = NPDU()
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.apdu == b""

    def test_all_flags_combined(self):
        src = BACnetAddress(network=3, mac_address=b"\xab")
        dest = BACnetAddress(network=7, mac_address=b"\xcd\xef")
        npdu = NPDU(
            expecting_reply=True,
            priority=NetworkPriority.LIFE_SAFETY,
            source=src,
            destination=dest,
            hop_count=128,
            apdu=b"\x10\x20\x30",
        )
        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)
        assert decoded.expecting_reply is True
        assert decoded.priority == NetworkPriority.LIFE_SAFETY
        assert decoded.source.network == 3
        assert decoded.source.mac_address == b"\xab"
        assert decoded.destination.network == 7
        assert decoded.destination.mac_address == b"\xcd\xef"
        assert decoded.hop_count == 128
        assert decoded.apdu == b"\x10\x20\x30"


class TestSourceValidation:
    def test_snet_global_broadcast_raises(self):
        src = BACnetAddress(network=0xFFFF, mac_address=b"\x01")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="SNET cannot be 0xFFFF"):
            encode_npdu(npdu)

    def test_snet_zero_raises(self):
        src = BACnetAddress(network=0, mac_address=b"\x01")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="SNET cannot be 0"):
            encode_npdu(npdu)

    def test_snet_none_raises(self):
        src = BACnetAddress(network=None, mac_address=b"\x01")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="SNET cannot be 0"):
            encode_npdu(npdu)

    def test_slen_zero_raises(self):
        src = BACnetAddress(network=5, mac_address=b"")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="SLEN cannot be 0"):
            encode_npdu(npdu)
