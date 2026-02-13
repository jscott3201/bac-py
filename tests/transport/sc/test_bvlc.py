import struct

import pytest

from bac_py.transport.sc.bvlc import (
    AddressResolutionAckPayload,
    AdvertisementPayload,
    BvlcResultPayload,
    ConnectAcceptPayload,
    ConnectRequestPayload,
    ProprietaryMessagePayload,
    SCHeaderOption,
    SCMessage,
    build_secure_path_option,
)
from bac_py.transport.sc.types import (
    SC_HEADER_MIN_LENGTH,
    BvlcSCFunction,
    SCControlFlag,
    SCHeaderOptionType,
    SCHubConnectionStatus,
    SCResultCode,
)
from bac_py.transport.sc.vmac import SCVMAC, DeviceUUID

# ---------------------------------------------------------------------------
# SCMessage encode/decode round-trips for all 13 message types
# ---------------------------------------------------------------------------


class TestSCMessageMinimal:
    """Minimal messages (no VMACs, no options, no payload)."""

    def test_minimal_header_length(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0x1234)
        encoded = msg.encode()
        assert len(encoded) == SC_HEADER_MIN_LENGTH

    def test_minimal_roundtrip(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0x1234)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.HEARTBEAT_REQUEST
        assert decoded.message_id == 0x1234
        assert decoded.originating is None
        assert decoded.destination is None
        assert decoded.dest_options == ()
        assert decoded.data_options == ()
        assert decoded.payload == b""


class TestSCMessageRoundTrips:
    """Round-trip encode/decode for each of the 13 BVLC-SC message types."""

    def test_bvlc_result_ack(self):
        payload = BvlcResultPayload(BvlcSCFunction.ENCAPSULATED_NPDU, SCResultCode.ACK).encode()
        msg = SCMessage(BvlcSCFunction.BVLC_RESULT, message_id=1, payload=payload)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.BVLC_RESULT
        result = BvlcResultPayload.decode(decoded.payload)
        assert result.for_function == BvlcSCFunction.ENCAPSULATED_NPDU
        assert result.result_code == SCResultCode.ACK

    def test_bvlc_result_nak(self):
        payload = BvlcResultPayload(
            BvlcSCFunction.CONNECT_REQUEST,
            SCResultCode.NAK,
            error_header_marker=0x00,
            error_class=7,  # COMMUNICATION
            error_code=0x000E,  # NODE_DUPLICATE_VMAC
            error_details="Duplicate VMAC detected",
        ).encode()
        orig = SCVMAC.from_hex("AA:BB:CC:DD:EE:FF")
        msg = SCMessage(
            BvlcSCFunction.BVLC_RESULT, message_id=2, originating=orig, payload=payload
        )
        decoded = SCMessage.decode(msg.encode())
        assert decoded.originating == orig
        result = BvlcResultPayload.decode(decoded.payload)
        assert result.result_code == SCResultCode.NAK
        assert result.error_class == 7
        assert result.error_code == 0x000E
        assert result.error_details == "Duplicate VMAC detected"

    def test_encapsulated_npdu(self):
        npdu = b"\x01\x04\x00\x00\x00\x10\x0c\x00"
        orig = SCVMAC.from_hex("020000000001")
        dest = SCVMAC.from_hex("020000000002")
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0xB5EC,
            originating=orig,
            destination=dest,
            payload=npdu,
        )
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.ENCAPSULATED_NPDU
        assert decoded.originating == orig
        assert decoded.destination == dest
        assert decoded.payload == npdu

    def test_address_resolution(self):
        orig = SCVMAC.from_hex("020000000001")
        dest = SCVMAC.from_hex("020000000002")
        msg = SCMessage(
            BvlcSCFunction.ADDRESS_RESOLUTION,
            message_id=100,
            originating=orig,
            destination=dest,
        )
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.ADDRESS_RESOLUTION
        assert decoded.originating == orig
        assert decoded.destination == dest
        assert decoded.payload == b""

    def test_address_resolution_ack(self):
        uris = ("wss://192.168.1.10:4444", "wss://10.0.0.5:4444")
        payload = AddressResolutionAckPayload(uris).encode()
        orig = SCVMAC.from_hex("020000000002")
        dest = SCVMAC.from_hex("020000000001")
        msg = SCMessage(
            BvlcSCFunction.ADDRESS_RESOLUTION_ACK,
            message_id=100,
            originating=orig,
            destination=dest,
            payload=payload,
        )
        decoded = SCMessage.decode(msg.encode())
        ack = AddressResolutionAckPayload.decode(decoded.payload)
        assert ack.websocket_uris == uris

    def test_advertisement(self):
        payload = AdvertisementPayload(
            SCHubConnectionStatus.CONNECTED_TO_PRIMARY, True, 1600, 1497
        ).encode()
        orig = SCVMAC.from_hex("020000000001")
        msg = SCMessage(
            BvlcSCFunction.ADVERTISEMENT,
            message_id=50,
            originating=orig,
            payload=payload,
        )
        decoded = SCMessage.decode(msg.encode())
        adv = AdvertisementPayload.decode(decoded.payload)
        assert adv.hub_connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY
        assert adv.accept_direct_connections is True
        assert adv.max_bvlc_length == 1600
        assert adv.max_npdu_length == 1497

    def test_advertisement_solicitation(self):
        orig = SCVMAC.from_hex("020000000001")
        dest = SCVMAC.from_hex("020000000002")
        msg = SCMessage(
            BvlcSCFunction.ADVERTISEMENT_SOLICITATION,
            message_id=51,
            originating=orig,
            destination=dest,
        )
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.ADVERTISEMENT_SOLICITATION
        assert decoded.payload == b""

    def test_connect_request(self):
        vmac = SCVMAC.from_hex("020000000001")
        device_uuid = DeviceUUID(b"\x55\x0e\x84\x00" + b"\x00" * 12)
        payload = ConnectRequestPayload(vmac, device_uuid, 1600, 1497).encode()
        msg = SCMessage(BvlcSCFunction.CONNECT_REQUEST, message_id=1, payload=payload)
        decoded = SCMessage.decode(msg.encode())
        req = ConnectRequestPayload.decode(decoded.payload)
        assert req.vmac == vmac
        assert req.uuid == device_uuid
        assert req.max_bvlc_length == 1600
        assert req.max_npdu_length == 1497

    def test_connect_accept(self):
        vmac = SCVMAC.from_hex("020000000099")
        device_uuid = DeviceUUID(b"\xaa" * 16)
        payload = ConnectAcceptPayload(vmac, device_uuid, 4096, 1497).encode()
        msg = SCMessage(BvlcSCFunction.CONNECT_ACCEPT, message_id=1, payload=payload)
        decoded = SCMessage.decode(msg.encode())
        accept = ConnectAcceptPayload.decode(decoded.payload)
        assert accept.vmac == vmac
        assert accept.uuid == device_uuid
        assert accept.max_bvlc_length == 4096

    def test_disconnect_request(self):
        msg = SCMessage(BvlcSCFunction.DISCONNECT_REQUEST, message_id=200)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.DISCONNECT_REQUEST
        assert decoded.message_id == 200
        assert decoded.payload == b""

    def test_disconnect_ack(self):
        msg = SCMessage(BvlcSCFunction.DISCONNECT_ACK, message_id=200)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.DISCONNECT_ACK
        assert decoded.message_id == 200

    def test_heartbeat_request(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=500)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.HEARTBEAT_REQUEST

    def test_heartbeat_ack(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_ACK, message_id=500)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.function == BvlcSCFunction.HEARTBEAT_ACK

    def test_proprietary_message(self):
        payload = ProprietaryMessagePayload(
            vendor_id=555, proprietary_function=1, proprietary_data=b"\xde\xad"
        ).encode()
        orig = SCVMAC.from_hex("020000000001")
        msg = SCMessage(
            BvlcSCFunction.PROPRIETARY_MESSAGE,
            message_id=999,
            originating=orig,
            payload=payload,
        )
        decoded = SCMessage.decode(msg.encode())
        prop = ProprietaryMessagePayload.decode(decoded.payload)
        assert prop.vendor_id == 555
        assert prop.proprietary_function == 1
        assert prop.proprietary_data == b"\xde\xad"


# ---------------------------------------------------------------------------
# Control flag permutations
# ---------------------------------------------------------------------------


class TestControlFlags:
    def test_no_flags(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0)
        encoded = msg.encode()
        assert encoded[1] == 0x00

    def test_originating_only(self):
        msg = SCMessage(
            BvlcSCFunction.HEARTBEAT_REQUEST,
            message_id=0,
            originating=SCVMAC.from_hex("020000000001"),
        )
        encoded = msg.encode()
        assert encoded[1] & SCControlFlag.ORIGINATING_VMAC
        assert not (encoded[1] & SCControlFlag.DESTINATION_VMAC)

    def test_destination_only(self):
        msg = SCMessage(
            BvlcSCFunction.HEARTBEAT_REQUEST,
            message_id=0,
            destination=SCVMAC.from_hex("020000000002"),
        )
        encoded = msg.encode()
        assert not (encoded[1] & SCControlFlag.ORIGINATING_VMAC)
        assert encoded[1] & SCControlFlag.DESTINATION_VMAC

    def test_both_vmacs(self):
        msg = SCMessage(
            BvlcSCFunction.HEARTBEAT_REQUEST,
            message_id=0,
            originating=SCVMAC.from_hex("020000000001"),
            destination=SCVMAC.from_hex("020000000002"),
        )
        encoded = msg.encode()
        assert encoded[1] & SCControlFlag.ORIGINATING_VMAC
        assert encoded[1] & SCControlFlag.DESTINATION_VMAC
        assert len(encoded) == SC_HEADER_MIN_LENGTH + 12  # 6+6 bytes for VMACs

    def test_broadcast_destination(self):
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            destination=SCVMAC.broadcast(),
            payload=b"\x01\x00",
        )
        decoded = SCMessage.decode(msg.encode())
        assert decoded.destination is not None
        assert decoded.destination.is_broadcast

    def test_dest_options_flag(self):
        opt = SCHeaderOption(type=1, must_understand=True)
        msg = SCMessage(
            BvlcSCFunction.HEARTBEAT_REQUEST,
            message_id=0,
            dest_options=(opt,),
        )
        encoded = msg.encode()
        assert encoded[1] & SCControlFlag.DESTINATION_OPTIONS

    def test_data_options_flag(self):
        opt = build_secure_path_option()
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            data_options=(opt,),
            payload=b"\x01\x00",
        )
        encoded = msg.encode()
        assert encoded[1] & SCControlFlag.DATA_OPTIONS

    def test_all_flags_set(self):
        opt = build_secure_path_option()
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            originating=SCVMAC.from_hex("020000000001"),
            destination=SCVMAC.from_hex("020000000002"),
            dest_options=(SCHeaderOption(type=31, must_understand=False, data=b"\x00\x22\x01"),),
            data_options=(opt,),
            payload=b"\x01\x00",
        )
        encoded = msg.encode()
        assert encoded[1] == 0x0F  # all 4 lower bits set
        decoded = SCMessage.decode(encoded)
        assert decoded.originating == msg.originating
        assert decoded.destination == msg.destination
        assert len(decoded.dest_options) == 1
        assert len(decoded.data_options) == 1
        assert decoded.payload == b"\x01\x00"


# ---------------------------------------------------------------------------
# Header options
# ---------------------------------------------------------------------------


class TestHeaderOptions:
    def test_secure_path_encode_no_data(self):
        opt = build_secure_path_option()
        encoded = opt.encode(more=False)
        # Marker: Must-Understand=1, Has-Data=0, Type=1 → 0b01000001 = 0x41
        assert encoded == bytes([0x41])

    def test_secure_path_with_more(self):
        opt = build_secure_path_option()
        encoded = opt.encode(more=True)
        # Marker: More=1, Must-Understand=1, Has-Data=0, Type=1 → 0b11000001 = 0xC1
        assert encoded == bytes([0xC1])

    def test_proprietary_option_with_data(self):
        opt = SCHeaderOption(
            type=SCHeaderOptionType.PROPRIETARY,
            must_understand=False,
            data=b"\x02\x2b\x01\xde\xad",
        )
        encoded = opt.encode(more=False)
        # Marker: More=0, MU=0, Has-Data=1, Type=31 → 0b00111111 = 0x3F
        assert encoded[0] == 0x3F
        # Length: 5 (big-endian 16-bit)
        assert encoded[1:3] == b"\x00\x05"
        # Data
        assert encoded[3:] == b"\x02\x2b\x01\xde\xad"

    def test_decode_single_option_no_data(self):
        raw = bytes([0x41])  # Secure Path
        options, consumed = SCHeaderOption.decode_list(memoryview(raw))
        assert len(options) == 1
        assert options[0].type == SCHeaderOptionType.SECURE_PATH
        assert options[0].must_understand is True
        assert options[0].data == b""
        assert consumed == 1

    def test_decode_single_option_with_data(self):
        data = b"\x02\x2b\x01"
        raw = bytes([0x3F]) + struct.pack("!H", len(data)) + data
        options, consumed = SCHeaderOption.decode_list(memoryview(raw))
        assert len(options) == 1
        assert options[0].type == 31
        assert options[0].data == data
        assert consumed == 1 + 2 + 3

    def test_decode_chained_options(self):
        # First: Secure Path (more=True)
        # Second: Proprietary (more=False)
        first = bytes([0xC1])  # More=1, MU=1, HasData=0, Type=1
        prop_data = b"\x00\x09\x01"
        second = bytes([0x3F]) + struct.pack("!H", len(prop_data)) + prop_data
        raw = first + second
        options, consumed = SCHeaderOption.decode_list(memoryview(raw))
        assert len(options) == 2
        assert options[0].type == 1
        assert options[1].type == 31
        assert options[1].data == prop_data
        assert consumed == len(raw)

    def test_roundtrip_chained_options(self):
        opts = (
            SCHeaderOption(type=1, must_understand=True),
            SCHeaderOption(type=31, must_understand=False, data=b"\x00\x09\x05\xaa"),
        )
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=42,
            dest_options=opts,
            payload=b"\x01\x00",
        )
        decoded = SCMessage.decode(msg.encode())
        assert len(decoded.dest_options) == 2
        assert decoded.dest_options[0].type == 1
        assert decoded.dest_options[0].must_understand is True
        assert decoded.dest_options[1].type == 31
        assert decoded.dest_options[1].data == b"\x00\x09\x05\xaa"

    def test_decode_truncated_header_length(self):
        # Has-Data=1 but no length bytes follow
        raw = bytes([0x3F])
        with pytest.raises(ValueError, match=r"truncated.*missing Header Length"):
            SCHeaderOption.decode_list(memoryview(raw))

    def test_decode_truncated_header_data(self):
        # Has-Data=1, length=10, but only 2 bytes of data
        raw = bytes([0x3F]) + struct.pack("!H", 10) + b"\x00\x01"
        with pytest.raises(ValueError, match="Header option data truncated"):
            SCHeaderOption.decode_list(memoryview(raw))


# ---------------------------------------------------------------------------
# Message wire format details
# ---------------------------------------------------------------------------


class TestSCMessageWireFormat:
    def test_function_byte(self):
        for func in BvlcSCFunction:
            msg = SCMessage(func, message_id=0)
            encoded = msg.encode()
            assert encoded[0] == func

    def test_message_id_big_endian(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0xB5EC)
        encoded = msg.encode()
        assert encoded[2:4] == b"\xb5\xec"

    def test_message_id_wrapping(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0xFFFF)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.message_id == 0xFFFF

    def test_message_id_zero(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.message_id == 0

    def test_originating_vmac_position(self):
        orig = SCVMAC(b"\x01\x02\x03\x04\x05\x06")
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0, originating=orig)
        encoded = msg.encode()
        assert encoded[4:10] == orig.address

    def test_destination_vmac_after_originating(self):
        orig = SCVMAC(b"\x01\x02\x03\x04\x05\x06")
        dest = SCVMAC(b"\x0a\x0b\x0c\x0d\x0e\x0f")
        msg = SCMessage(
            BvlcSCFunction.HEARTBEAT_REQUEST,
            message_id=0,
            originating=orig,
            destination=dest,
        )
        encoded = msg.encode()
        assert encoded[4:10] == orig.address
        assert encoded[10:16] == dest.address

    def test_destination_vmac_without_originating(self):
        dest = SCVMAC(b"\x0a\x0b\x0c\x0d\x0e\x0f")
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=0, destination=dest)
        encoded = msg.encode()
        assert encoded[4:10] == dest.address

    def test_reserved_bits_ignored_on_decode(self):
        # Set reserved bits 7..4 in control byte
        raw = bytearray(b"\x0a\xf0\x00\x01")  # HEARTBEAT_REQUEST, reserved bits set
        decoded = SCMessage.decode(bytes(raw))
        assert decoded.function == BvlcSCFunction.HEARTBEAT_REQUEST
        assert decoded.originating is None  # reserved bits don't affect flags


class TestSCMessageDecodeErrors:
    def test_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            SCMessage.decode(b"\x00\x00")

    def test_empty(self):
        with pytest.raises(ValueError, match="too short"):
            SCMessage.decode(b"")

    def test_truncated_originating_vmac(self):
        # Function=0x0A, Flags=0x08 (orig present), MsgID=0x0001, only 3 VMAC bytes
        raw = b"\x0a\x08\x00\x01\x01\x02\x03"
        with pytest.raises(ValueError, match="Originating"):
            SCMessage.decode(raw)

    def test_truncated_destination_vmac(self):
        raw = b"\x0a\x04\x00\x01\x01\x02\x03"
        with pytest.raises(ValueError, match="Destination"):
            SCMessage.decode(raw)

    def test_accepts_memoryview(self):
        msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=42)
        decoded = SCMessage.decode(memoryview(msg.encode()))
        assert decoded.message_id == 42

    def test_unknown_function_raises(self):
        raw = b"\xff\x00\x00\x01"
        with pytest.raises(ValueError):
            SCMessage.decode(raw)


# ---------------------------------------------------------------------------
# ConnectRequestPayload
# ---------------------------------------------------------------------------


class TestConnectRequestPayload:
    def test_encode_length(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        uuid_ = DeviceUUID(b"\x00" * 16)
        p = ConnectRequestPayload(vmac, uuid_, 1600, 1497)
        assert len(p.encode()) == 26

    def test_roundtrip(self):
        vmac = SCVMAC.from_hex("AABBCCDDEEFF")
        uuid_ = DeviceUUID(bytes(range(16)))
        p = ConnectRequestPayload(vmac, uuid_, 4096, 1497)
        decoded = ConnectRequestPayload.decode(p.encode())
        assert decoded.vmac == vmac
        assert decoded.uuid == uuid_
        assert decoded.max_bvlc_length == 4096
        assert decoded.max_npdu_length == 1497

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            ConnectRequestPayload.decode(b"\x00" * 10)

    def test_max_values(self):
        vmac = SCVMAC(b"\xff" * 6)
        uuid_ = DeviceUUID(b"\xff" * 16)
        p = ConnectRequestPayload(vmac, uuid_, 0xFFFF, 0xFFFF)
        decoded = ConnectRequestPayload.decode(p.encode())
        assert decoded.max_bvlc_length == 0xFFFF
        assert decoded.max_npdu_length == 0xFFFF


# ---------------------------------------------------------------------------
# ConnectAcceptPayload
# ---------------------------------------------------------------------------


class TestConnectAcceptPayload:
    def test_encode_length(self):
        p = ConnectAcceptPayload(
            SCVMAC(b"\x02\x00\x00\x00\x00\x99"), DeviceUUID(b"\xaa" * 16), 1600, 1497
        )
        assert len(p.encode()) == 26

    def test_roundtrip(self):
        vmac = SCVMAC.from_hex("020000000099")
        uuid_ = DeviceUUID(b"\xbb" * 16)
        p = ConnectAcceptPayload(vmac, uuid_, 2048, 1400)
        decoded = ConnectAcceptPayload.decode(p.encode())
        assert decoded.vmac == vmac
        assert decoded.uuid == uuid_
        assert decoded.max_bvlc_length == 2048
        assert decoded.max_npdu_length == 1400

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            ConnectAcceptPayload.decode(b"\x00" * 5)


# ---------------------------------------------------------------------------
# BvlcResultPayload
# ---------------------------------------------------------------------------


class TestBvlcResultPayload:
    def test_ack_roundtrip(self):
        p = BvlcResultPayload(BvlcSCFunction.CONNECT_REQUEST, SCResultCode.ACK)
        decoded = BvlcResultPayload.decode(p.encode())
        assert decoded.for_function == BvlcSCFunction.CONNECT_REQUEST
        assert decoded.result_code == SCResultCode.ACK
        assert decoded.error_details == ""

    def test_ack_encode_length(self):
        p = BvlcResultPayload(BvlcSCFunction.CONNECT_REQUEST, SCResultCode.ACK)
        assert len(p.encode()) == 2

    def test_nak_roundtrip(self):
        p = BvlcResultPayload(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            SCResultCode.NAK,
            error_header_marker=0xBF,
            error_class=7,
            error_code=0x0111,
            error_details="Unmöglicher Code!",
        )
        decoded = BvlcResultPayload.decode(p.encode())
        assert decoded.result_code == SCResultCode.NAK
        assert decoded.error_header_marker == 0xBF
        assert decoded.error_class == 7
        assert decoded.error_code == 0x0111
        assert decoded.error_details == "Unmöglicher Code!"

    def test_nak_without_details(self):
        p = BvlcResultPayload(
            BvlcSCFunction.CONNECT_REQUEST,
            SCResultCode.NAK,
            error_header_marker=0x00,
            error_class=7,
            error_code=0x000E,
        )
        decoded = BvlcResultPayload.decode(p.encode())
        assert decoded.error_details == ""

    def test_nak_encode_minimum_length(self):
        p = BvlcResultPayload(
            BvlcSCFunction.CONNECT_REQUEST,
            SCResultCode.NAK,
            error_header_marker=0x00,
            error_class=7,
            error_code=0x000E,
        )
        # 2 (func+result) + 1 (marker) + 2 (class) + 2 (code) = 7
        assert len(p.encode()) == 7

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            BvlcResultPayload.decode(b"\x00")

    def test_nak_decode_too_short(self):
        # Function + NAK code but no error fields
        with pytest.raises(ValueError, match=r"NAK.*too short"):
            BvlcResultPayload.decode(b"\x01\x01\x00")


# ---------------------------------------------------------------------------
# AdvertisementPayload
# ---------------------------------------------------------------------------


class TestAdvertisementPayload:
    def test_encode_length(self):
        p = AdvertisementPayload(SCHubConnectionStatus.CONNECTED_TO_PRIMARY, True, 1600, 1497)
        assert len(p.encode()) == 6

    def test_roundtrip_primary(self):
        p = AdvertisementPayload(SCHubConnectionStatus.CONNECTED_TO_PRIMARY, True, 1600, 1497)
        decoded = AdvertisementPayload.decode(p.encode())
        assert decoded.hub_connection_status == SCHubConnectionStatus.CONNECTED_TO_PRIMARY
        assert decoded.accept_direct_connections is True
        assert decoded.max_bvlc_length == 1600
        assert decoded.max_npdu_length == 1497

    def test_roundtrip_no_hub(self):
        p = AdvertisementPayload(SCHubConnectionStatus.NO_HUB_CONNECTION, False, 800, 700)
        decoded = AdvertisementPayload.decode(p.encode())
        assert decoded.hub_connection_status == SCHubConnectionStatus.NO_HUB_CONNECTION
        assert decoded.accept_direct_connections is False

    def test_roundtrip_failover(self):
        p = AdvertisementPayload(SCHubConnectionStatus.CONNECTED_TO_FAILOVER, True, 1600, 1497)
        decoded = AdvertisementPayload.decode(p.encode())
        assert decoded.hub_connection_status == SCHubConnectionStatus.CONNECTED_TO_FAILOVER

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            AdvertisementPayload.decode(b"\x00\x00")


# ---------------------------------------------------------------------------
# AddressResolutionAckPayload
# ---------------------------------------------------------------------------


class TestAddressResolutionAckPayload:
    def test_single_uri(self):
        p = AddressResolutionAckPayload(("wss://hub.example.com:4443",))
        decoded = AddressResolutionAckPayload.decode(p.encode())
        assert decoded.websocket_uris == ("wss://hub.example.com:4443",)

    def test_multiple_uris(self):
        uris = ("wss://10.0.0.1:4444", "wss://10.0.0.2:4444")
        p = AddressResolutionAckPayload(uris)
        decoded = AddressResolutionAckPayload.decode(p.encode())
        assert decoded.websocket_uris == uris

    def test_empty_uris(self):
        p = AddressResolutionAckPayload(())
        decoded = AddressResolutionAckPayload.decode(p.encode())
        assert decoded.websocket_uris == ()

    def test_space_separated_wire_format(self):
        uris = ("wss://a:1", "wss://b:2")
        p = AddressResolutionAckPayload(uris)
        raw = p.encode()
        assert raw == b"wss://a:1 wss://b:2"


# ---------------------------------------------------------------------------
# ProprietaryMessagePayload
# ---------------------------------------------------------------------------


class TestProprietaryMessagePayload:
    def test_roundtrip(self):
        p = ProprietaryMessagePayload(555, 1, b"\xde\xad\xbe\xef")
        decoded = ProprietaryMessagePayload.decode(p.encode())
        assert decoded.vendor_id == 555
        assert decoded.proprietary_function == 1
        assert decoded.proprietary_data == b"\xde\xad\xbe\xef"

    def test_no_data(self):
        p = ProprietaryMessagePayload(100, 2)
        decoded = ProprietaryMessagePayload.decode(p.encode())
        assert decoded.vendor_id == 100
        assert decoded.proprietary_function == 2
        assert decoded.proprietary_data == b""

    def test_minimum_encode_length(self):
        p = ProprietaryMessagePayload(0, 0)
        assert len(p.encode()) == 3

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            ProprietaryMessagePayload.decode(b"\x00\x01")


# ---------------------------------------------------------------------------
# Spec examples (AB.2.17)
# ---------------------------------------------------------------------------


class TestSpecExamples:
    def test_encapsulated_npdu_example_ab5(self):
        """Verify against Figure AB-5 encoding example.

        Function=0x01, Control=0x07 (DestVMAC + DestOpts + DataOpts),
        MessageID=0xB5EC, DestVMAC=927BF71A96A2.
        """
        dest = SCVMAC(bytes.fromhex("927BF71A96A2"))
        # Destination options: two proprietary options
        prop_data1 = bytes.fromhex("022B") + bytes.fromhex("BAC5ECC099")
        prop_data2 = bytes.fromhex("0309") + bytes.fromhex("39")
        dest_opt1 = SCHeaderOption(
            type=SCHeaderOptionType.PROPRIETARY, must_understand=False, data=prop_data1
        )
        dest_opt2 = SCHeaderOption(
            type=SCHeaderOptionType.PROPRIETARY, must_understand=False, data=prop_data2
        )
        # Data option: Secure Path
        secure_path = build_secure_path_option()
        # NPDU + APDU payload
        npdu_payload = bytes.fromhex("0104") + bytes.fromhex("0000010C0C00000005195500")

        msg = SCMessage(
            function=BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0xB5EC,
            destination=dest,
            dest_options=(dest_opt1, dest_opt2),
            data_options=(secure_path,),
            payload=npdu_payload,
        )
        encoded = msg.encode()
        # Verify function byte
        assert encoded[0] == 0x01
        # Verify control flags: DestVMAC(0x04) | DestOpts(0x02) | DataOpts(0x01) = 0x07
        assert encoded[1] == 0x07
        # Verify message ID
        assert encoded[2:4] == b"\xb5\xec"
        # Verify destination VMAC
        assert encoded[4:10] == bytes.fromhex("927BF71A96A2")

        # Round-trip
        decoded = SCMessage.decode(encoded)
        assert decoded.function == BvlcSCFunction.ENCAPSULATED_NPDU
        assert decoded.message_id == 0xB5EC
        assert decoded.destination == dest
        assert len(decoded.dest_options) == 2
        assert len(decoded.data_options) == 1
        assert decoded.data_options[0].type == SCHeaderOptionType.SECURE_PATH
        assert decoded.payload == npdu_payload

    def test_bvlc_result_nak_example_ab6(self):
        """Verify against Figure AB-6 encoding example.

        BVLC-Result NAK for Encapsulated-NPDU with error details.
        """
        orig = SCVMAC(bytes.fromhex("927BF71A96A2"))
        result = BvlcResultPayload(
            for_function=BvlcSCFunction.ENCAPSULATED_NPDU,
            result_code=SCResultCode.NAK,
            error_header_marker=0xBF,
            error_class=0x0007,  # COMMUNICATION
            error_code=0x0111,  # Proprietary error code 273
            error_details="Unmöglicher Code!",
        )
        msg = SCMessage(
            function=BvlcSCFunction.BVLC_RESULT,
            message_id=0xB5EC,
            originating=orig,
            payload=result.encode(),
        )
        encoded = msg.encode()
        assert encoded[0] == 0x00  # BVLC-Result
        assert encoded[1] == 0x08  # OrigVMAC only
        assert encoded[2:4] == b"\xb5\xec"
        assert encoded[4:10] == bytes.fromhex("927BF71A96A2")

        # Round-trip
        decoded = SCMessage.decode(encoded)
        r = BvlcResultPayload.decode(decoded.payload)
        assert r.for_function == BvlcSCFunction.ENCAPSULATED_NPDU
        assert r.result_code == SCResultCode.NAK
        assert r.error_header_marker == 0xBF
        assert r.error_class == 7
        assert r.error_code == 0x0111
        assert "Unmöglicher" in r.error_details


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_large_payload(self):
        payload = bytes(range(256)) * 8  # 2048 bytes
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=1, payload=payload)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.payload == payload

    def test_empty_payload(self):
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=1)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.payload == b""

    def test_message_id_boundary_values(self):
        for mid in [0, 1, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF]:
            msg = SCMessage(BvlcSCFunction.HEARTBEAT_REQUEST, message_id=mid)
            decoded = SCMessage.decode(msg.encode())
            assert decoded.message_id == mid

    def test_payload_with_all_bytes(self):
        payload = bytes(range(256))
        msg = SCMessage(BvlcSCFunction.ENCAPSULATED_NPDU, message_id=0, payload=payload)
        decoded = SCMessage.decode(msg.encode())
        assert decoded.payload == payload

    def test_multiple_data_options(self):
        opts = (
            build_secure_path_option(),
            SCHeaderOption(type=31, must_understand=False, data=b"\x00\x01\x02"),
        )
        msg = SCMessage(
            BvlcSCFunction.ENCAPSULATED_NPDU,
            message_id=0,
            data_options=opts,
            payload=b"\x01",
        )
        decoded = SCMessage.decode(msg.encode())
        assert len(decoded.data_options) == 2
        assert decoded.data_options[0].type == 1
        assert decoded.data_options[1].type == 31
        assert decoded.data_options[1].data == b"\x00\x01\x02"

    def test_header_option_zero_length_data_with_flag(self):
        # Header Data Flag set but data length is 0
        opt = SCHeaderOption(type=31, must_understand=False, data=b"")
        encoded = opt.encode(more=False)
        # Has-Data flag should NOT be set when data is empty
        assert encoded[0] & 0x20 == 0

    def test_connect_payload_extra_bytes_ignored(self):
        vmac = SCVMAC(b"\x02\x00\x00\x00\x00\x01")
        uuid_ = DeviceUUID(b"\x00" * 16)
        p = ConnectRequestPayload(vmac, uuid_, 1600, 1497)
        raw = p.encode() + b"\xff\xff"  # extra bytes
        decoded = ConnectRequestPayload.decode(raw)
        assert decoded.vmac == vmac
        assert decoded.max_bvlc_length == 1600


# ---------------------------------------------------------------------------
# Types module
# ---------------------------------------------------------------------------


class TestTypesEnums:
    def test_all_bvlc_functions(self):
        assert len(BvlcSCFunction) == 13

    def test_bvlc_function_values(self):
        assert BvlcSCFunction.BVLC_RESULT == 0x00
        assert BvlcSCFunction.PROPRIETARY_MESSAGE == 0x0C

    def test_control_flag_combinations(self):
        combined = SCControlFlag.ORIGINATING_VMAC | SCControlFlag.DESTINATION_VMAC
        assert int(combined) == 0x0C

    def test_result_codes(self):
        assert SCResultCode.ACK == 0
        assert SCResultCode.NAK == 1

    def test_hub_connection_status_values(self):
        assert SCHubConnectionStatus.NO_HUB_CONNECTION == 0
        assert SCHubConnectionStatus.CONNECTED_TO_PRIMARY == 1
        assert SCHubConnectionStatus.CONNECTED_TO_FAILOVER == 2

    def test_header_option_types(self):
        assert SCHeaderOptionType.SECURE_PATH == 1
        assert SCHeaderOptionType.PROPRIETARY == 31
