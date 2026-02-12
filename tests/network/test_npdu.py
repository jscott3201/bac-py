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
        with pytest.raises(ValueError, match="Network number must be 1-65534"):
            BACnetAddress(network=0, mac_address=b"\x01")

    def test_snet_none_raises(self):
        src = BACnetAddress(network=None, mac_address=b"\x01")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="Source network must be set"):
            encode_npdu(npdu)

    def test_slen_zero_raises(self):
        src = BACnetAddress(network=5, mac_address=b"")
        npdu = NPDU(source=src, apdu=b"\x01")
        with pytest.raises(ValueError, match="SLEN cannot be 0"):
            encode_npdu(npdu)


# ---------------------------------------------------------------------------
# Variable-length MAC address parametrized tests
# ---------------------------------------------------------------------------

# MAC lengths to test (skip 6 = BIP and 18 = BIP6 as already well-tested)
_MAC_LENGTHS = [1, 2, 3, 4, 5, 7, 8]


def _make_mac(length: int) -> bytes:
    """Generate a deterministic MAC of the given length."""
    return bytes(range(0x10, 0x10 + length))


class TestVariableMacLengths:
    """Parametrized tests for variable-length MAC addresses in NPDU encode/decode."""

    # -- SADR round-trips with variable MAC lengths --

    @pytest.mark.parametrize("mac_len", _MAC_LENGTHS, ids=[f"slen_{n}" for n in _MAC_LENGTHS])
    def test_sadr_round_trip(self, mac_len: int):
        """Source address with variable MAC length encodes and decodes correctly."""
        mac = _make_mac(mac_len)
        src = BACnetAddress(network=100, mac_address=mac)
        npdu = NPDU(source=src, apdu=b"\xfe\xed")

        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)

        assert decoded.source is not None
        assert decoded.source.network == 100
        assert decoded.source.mac_address == mac
        assert len(decoded.source.mac_address) == mac_len
        assert decoded.destination is None
        assert decoded.apdu == b"\xfe\xed"

    @pytest.mark.parametrize("mac_len", _MAC_LENGTHS, ids=[f"slen_{n}" for n in _MAC_LENGTHS])
    def test_sadr_slen_byte_in_wire(self, mac_len: int):
        """SLEN byte in the encoded output matches the actual source MAC length."""
        mac = _make_mac(mac_len)
        src = BACnetAddress(network=100, mac_address=mac)
        npdu = NPDU(source=src, apdu=b"\xaa")

        encoded = encode_npdu(npdu)
        # Wire layout (source only, no destination):
        #   [0] version
        #   [1] control (source bit 0x08 set)
        #   [2..3] SNET (2 bytes big-endian)
        #   [4] SLEN
        slen_byte = encoded[4]
        assert slen_byte == mac_len
        # Verify the MAC bytes follow immediately after SLEN
        assert encoded[5 : 5 + mac_len] == mac

    # -- DADR round-trips with variable MAC lengths --

    @pytest.mark.parametrize("mac_len", _MAC_LENGTHS, ids=[f"dlen_{n}" for n in _MAC_LENGTHS])
    def test_dadr_round_trip(self, mac_len: int):
        """Destination address with variable MAC length encodes and decodes correctly."""
        mac = _make_mac(mac_len)
        dest = BACnetAddress(network=200, mac_address=mac)
        npdu = NPDU(destination=dest, apdu=b"\xca\xfe")

        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)

        assert decoded.destination is not None
        assert decoded.destination.network == 200
        assert decoded.destination.mac_address == mac
        assert len(decoded.destination.mac_address) == mac_len
        assert decoded.source is None
        assert decoded.apdu == b"\xca\xfe"

    @pytest.mark.parametrize("mac_len", _MAC_LENGTHS, ids=[f"dlen_{n}" for n in _MAC_LENGTHS])
    def test_dadr_dlen_byte_in_wire(self, mac_len: int):
        """DLEN byte in the encoded output matches the actual destination MAC length."""
        mac = _make_mac(mac_len)
        dest = BACnetAddress(network=200, mac_address=mac)
        npdu = NPDU(destination=dest, apdu=b"\xbb")

        encoded = encode_npdu(npdu)
        # Wire layout (destination only, no source):
        #   [0] version
        #   [1] control (destination bit 0x20 set)
        #   [2..3] DNET (2 bytes big-endian)
        #   [4] DLEN
        dlen_byte = encoded[4]
        assert dlen_byte == mac_len
        # Verify the MAC bytes follow immediately after DLEN
        assert encoded[5 : 5 + mac_len] == mac

    # -- Combined SADR + DADR with different MAC lengths --

    @pytest.mark.parametrize(
        ("src_mac_len", "dst_mac_len"),
        [
            (1, 5),
            (5, 1),
            (2, 7),
            (7, 2),
            (3, 8),
            (8, 3),
            (4, 7),
            (1, 8),
        ],
        ids=[
            "src1_dst5",
            "src5_dst1",
            "src2_dst7",
            "src7_dst2",
            "src3_dst8",
            "src8_dst3",
            "src4_dst7",
            "src1_dst8",
        ],
    )
    def test_combined_sadr_dadr_round_trip(self, src_mac_len: int, dst_mac_len: int):
        """NPDU with both source and destination of different MAC lengths round-trips."""
        src_mac = _make_mac(src_mac_len)
        dst_mac = bytes(range(0xA0, 0xA0 + dst_mac_len))
        src = BACnetAddress(network=300, mac_address=src_mac)
        dest = BACnetAddress(network=400, mac_address=dst_mac)
        npdu = NPDU(source=src, destination=dest, hop_count=42, apdu=b"\xde\xad")

        encoded = encode_npdu(npdu)
        decoded = decode_npdu(encoded)

        assert decoded.source is not None
        assert decoded.source.network == 300
        assert decoded.source.mac_address == src_mac
        assert len(decoded.source.mac_address) == src_mac_len

        assert decoded.destination is not None
        assert decoded.destination.network == 400
        assert decoded.destination.mac_address == dst_mac
        assert len(decoded.destination.mac_address) == dst_mac_len

        assert decoded.hop_count == 42
        assert decoded.apdu == b"\xde\xad"

    @pytest.mark.parametrize(
        ("src_mac_len", "dst_mac_len"),
        [
            (1, 5),
            (5, 1),
            (2, 7),
            (7, 2),
            (3, 8),
            (8, 3),
            (4, 7),
            (1, 8),
        ],
        ids=[
            "src1_dst5",
            "src5_dst1",
            "src2_dst7",
            "src7_dst2",
            "src3_dst8",
            "src8_dst3",
            "src4_dst7",
            "src1_dst8",
        ],
    )
    def test_combined_dlen_slen_bytes_in_wire(self, src_mac_len: int, dst_mac_len: int):
        """DLEN and SLEN bytes in the wire format match actual MAC lengths when both present."""
        src_mac = _make_mac(src_mac_len)
        dst_mac = bytes(range(0xA0, 0xA0 + dst_mac_len))
        src = BACnetAddress(network=300, mac_address=src_mac)
        dest = BACnetAddress(network=400, mac_address=dst_mac)
        npdu = NPDU(source=src, destination=dest, hop_count=42, apdu=b"\x01")

        encoded = encode_npdu(npdu)
        # Wire layout (both destination and source):
        #   [0] version
        #   [1] control (destination 0x20 | source 0x08 set)
        #   [2..3] DNET
        #   [4] DLEN
        #   [5 .. 5+DLEN-1] DADR
        #   [5+DLEN .. 5+DLEN+1] SNET
        #   [5+DLEN+2] SLEN
        #   [5+DLEN+3 .. ] SADR
        #   then hop_count, then APDU

        # Verify DLEN
        dlen_offset = 4
        assert encoded[dlen_offset] == dst_mac_len
        assert encoded[dlen_offset + 1 : dlen_offset + 1 + dst_mac_len] == dst_mac

        # Verify SLEN
        slen_offset = 5 + dst_mac_len + 2  # after DADR + 2 bytes SNET
        assert encoded[slen_offset] == src_mac_len
        assert encoded[slen_offset + 1 : slen_offset + 1 + src_mac_len] == src_mac
