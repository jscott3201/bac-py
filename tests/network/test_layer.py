import pytest

from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.layer import NetworkLayer


class FakeTransport:
    """Minimal fake transport for testing NetworkLayer."""

    def __init__(self):
        self.sent_unicast: list[tuple[bytes, BIPAddress]] = []
        self.sent_broadcast: list[bytes] = []
        self._receive_callback = None
        self._local_address = BIPAddress(host="192.168.1.100", port=0xBAC0)

    def on_receive(self, callback):
        self._receive_callback = callback

    def send_unicast(self, data: bytes, dest: BIPAddress):
        self.sent_unicast.append((data, dest))

    def send_broadcast(self, data: bytes):
        self.sent_broadcast.append(data)

    @property
    def local_address(self) -> BIPAddress:
        return self._local_address

    def inject_receive(self, data: bytes, source: BIPAddress):
        if self._receive_callback:
            self._receive_callback(data, source)


class TestNetworkLayer:
    def test_send_unicast_wraps_in_npdu(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        dest = BACnetAddress(mac_address=b"\xc0\xa8\x01\x01\xba\xc0")
        apdu = b"\x10\x08"  # some APDU bytes
        layer.send(apdu, dest, expecting_reply=True)
        assert len(transport.sent_unicast) == 1
        npdu_bytes, _bip_dest = transport.sent_unicast[0]
        # NPDU should start with version 0x01
        assert npdu_bytes[0] == 0x01
        # The APDU should be contained within the NPDU
        assert apdu in npdu_bytes

    def test_send_broadcast(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        dest = BACnetAddress(network=0xFFFF)  # global broadcast
        apdu = b"\x10\x08"
        layer.send(apdu, dest, expecting_reply=False)
        assert len(transport.sent_broadcast) == 1
        assert len(transport.sent_unicast) == 0

    def test_send_local_broadcast(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        dest = BACnetAddress()  # local broadcast (no MAC, no network)
        apdu = b"\x10\x00"
        layer.send(apdu, dest, expecting_reply=False)
        assert len(transport.sent_broadcast) == 1

    def test_receive_dispatches_apdu(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, source: received.append((data, source)))

        # Construct a minimal valid NPDU: version=1, control=0x00, then APDU
        apdu_payload = b"\x10\x08"
        npdu = b"\x01\x00" + apdu_payload

        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(npdu, source)

        assert len(received) == 1
        data, src = received[0]
        assert data == apdu_payload
        assert isinstance(src, BACnetAddress)

    def test_receive_ignores_malformed(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, source: received.append((data, source)))

        # Inject malformed data (too short)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(b"", source)
        assert len(received) == 0

    def test_receive_ignores_network_messages(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, source: received.append((data, source)))

        # NPDU with network message flag set (control byte bit 7)
        npdu = b"\x01\x80\x00"  # network message type 0
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(npdu, source)
        assert len(received) == 0

    def test_local_address(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        assert layer.local_address == BIPAddress(host="192.168.1.100", port=0xBAC0)

    def test_bacnet_to_bip_conversion(self):
        bip = NetworkLayer._bacnet_to_bip(BACnetAddress(mac_address=b"\xc0\xa8\x01\x64\xba\xc0"))
        assert bip.host == "192.168.1.100"
        assert bip.port == 0xBAC0

    def test_bacnet_to_bip_invalid_mac_raises(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            NetworkLayer._bacnet_to_bip(BACnetAddress(mac_address=b"\x01\x02\x03"))
