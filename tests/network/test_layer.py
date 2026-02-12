"""Tests for the network layer (layer.py)."""

import time

from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.layer import NetworkLayer, RouterCacheEntry
from bac_py.network.messages import (
    IAmRouterToNetwork,
    NetworkNumberIs,
    encode_network_message,
)
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.types.enums import NetworkMessageType


class FakeTransport:
    """Minimal fake transport for testing NetworkLayer."""

    def __init__(self):
        self.sent_unicast: list[tuple[bytes, bytes]] = []
        self.sent_broadcast: list[bytes] = []
        self._receive_callback = None
        self._local_address = BIPAddress(host="192.168.1.100", port=0xBAC0)

    def on_receive(self, callback):
        self._receive_callback = callback

    def send_unicast(self, data: bytes, dest: bytes):
        self.sent_unicast.append((data, dest))

    def send_broadcast(self, data: bytes):
        self.sent_broadcast.append(data)

    @property
    def local_address(self) -> BIPAddress:
        return self._local_address

    def inject_receive(self, data: bytes, source: bytes):
        if self._receive_callback:
            self._receive_callback(data, source)


# --------------------------------------------------------------------------
# Helpers for building network message NPDUs
# --------------------------------------------------------------------------

_ROUTER_SOURCE = BIPAddress(host="10.0.0.1", port=0xBAC0)
_ROUTER_MAC = _ROUTER_SOURCE.encode()  # b"\x0a\x00\x00\x01\xba\xc0"


def _build_i_am_router_npdu(networks: tuple[int, ...]) -> bytes:
    """Build an I-Am-Router-To-Network NPDU."""
    msg = IAmRouterToNetwork(networks=networks)
    npdu = NPDU(
        is_network_message=True,
        message_type=NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
        network_message_data=encode_network_message(msg),
    )
    return encode_npdu(npdu)


def _build_what_is_network_number_npdu(
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a What-Is-Network-Number NPDU."""
    npdu = NPDU(
        is_network_message=True,
        message_type=NetworkMessageType.WHAT_IS_NETWORK_NUMBER,
        network_message_data=b"",
        source=source,
        destination=destination,
        hop_count=255 if destination is not None else None,
    )
    return encode_npdu(npdu)


def _build_network_number_is_npdu(
    network: int,
    configured: bool,
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a Network-Number-Is NPDU."""
    msg = NetworkNumberIs(network=network, configured=configured)
    npdu = NPDU(
        is_network_message=True,
        message_type=NetworkMessageType.NETWORK_NUMBER_IS,
        network_message_data=encode_network_message(msg),
        source=source,
        destination=destination,
        hop_count=255 if destination is not None else None,
    )
    return encode_npdu(npdu)


# --------------------------------------------------------------------------
# Existing tests (backward compatibility)
# --------------------------------------------------------------------------


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
        transport.inject_receive(npdu, source.encode())

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
        transport.inject_receive(b"", source.encode())
        assert len(received) == 0

    def test_receive_ignores_network_messages(self):
        """Network messages should not be delivered to the app callback."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, source: received.append((data, source)))

        # NPDU with network message flag set (control byte bit 7)
        npdu = b"\x01\x80\x00"  # network message type 0
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(npdu, source.encode())
        assert len(received) == 0

    def test_local_address(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        assert layer.local_address == BIPAddress(host="192.168.1.100", port=0xBAC0)


# --------------------------------------------------------------------------
# NetworkLayer -- Constructor enhancements
# --------------------------------------------------------------------------


class TestNetworkLayerConstructor:
    def test_default_no_network_number(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        assert layer.network_number is None

    def test_with_network_number(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number=10)
        assert layer.network_number == 10

    def test_configured_flag(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number=10, network_number_configured=True)
        assert layer.network_number == 10


# --------------------------------------------------------------------------
# NetworkLayer -- RouterCacheEntry
# --------------------------------------------------------------------------


class TestRouterCacheEntry:
    def test_create(self):
        entry = RouterCacheEntry(network=20, router_mac=b"\x01\x02\x03\x04\x05\x06", last_seen=1.0)
        assert entry.network == 20
        assert entry.router_mac == b"\x01\x02\x03\x04\x05\x06"
        assert entry.last_seen == 1.0

    def test_mutable(self):
        entry = RouterCacheEntry(network=20, router_mac=b"\x01", last_seen=1.0)
        entry.last_seen = 2.0
        assert entry.last_seen == 2.0


# --------------------------------------------------------------------------
# NetworkLayer -- Router cache population
# --------------------------------------------------------------------------


class TestRouterCachePopulation:
    def test_i_am_router_populates_cache(self):
        """Receiving I-Am-Router-To-Network should populate router cache."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        data = _build_i_am_router_npdu(networks=(20, 30))
        transport.inject_receive(data, _ROUTER_MAC)
        assert layer.get_router_for_network(20) == _ROUTER_MAC
        assert layer.get_router_for_network(30) == _ROUTER_MAC

    def test_cache_updated_on_repeated_i_am_router(self):
        """Repeated I-Am-Router updates last_seen timestamp."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(data, _ROUTER_MAC)
        first_seen = layer._router_cache[20].last_seen
        # Small delay to ensure monotonic time advances
        time.sleep(0.01)
        transport.inject_receive(data, _ROUTER_MAC)
        second_seen = layer._router_cache[20].last_seen
        assert second_seen > first_seen

    def test_cache_miss_returns_none(self):
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        assert layer.get_router_for_network(99) is None

    def test_multiple_routers_last_wins(self):
        """When a different router advertises the same DNET, cache is updated."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        router_a = BIPAddress(host="10.0.0.1", port=0xBAC0)
        router_b = BIPAddress(host="10.0.0.2", port=0xBAC0)
        data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(data, router_a.encode())
        assert layer.get_router_for_network(20) == router_a.encode()
        transport.inject_receive(data, router_b.encode())
        assert layer.get_router_for_network(20) == router_b.encode()


# --------------------------------------------------------------------------
# NetworkLayer -- Remote send with cache
# --------------------------------------------------------------------------


class TestRemoteSend:
    def test_send_remote_unicast_via_cached_router(self):
        """Remote unicast with cached router -> unicast to router MAC."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        # Populate cache
        data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        # Send to remote destination
        dest = BACnetAddress(network=20, mac_address=b"\xcc\xdd\xee\xff\xba\xc0")
        layer.send(b"\x10\x08", dest)

        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        _npdu_bytes, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

    def test_send_remote_broadcast_via_cached_router(self):
        """Remote broadcast with cached router -> unicast to router MAC."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        dest = BACnetAddress(network=20, mac_address=b"")  # remote broadcast
        layer.send(b"\x10\x08", dest)

        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        _, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

    def test_send_remote_cache_miss_broadcasts(self):
        """Remote send with no cached router -> broadcast NPDU."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        dest = BACnetAddress(network=99, mac_address=b"\xcc\xdd\xee\xff\xba\xc0")
        layer.send(b"\x10\x08", dest)

        # Should have broadcast the NPDU + a Who-Is-Router query
        assert len(transport.sent_broadcast) == 2
        assert len(transport.sent_unicast) == 0

    def test_send_remote_cache_miss_sends_who_is_router(self):
        """Remote send cache miss also sends Who-Is-Router-To-Network query."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        dest = BACnetAddress(network=42, mac_address=b"\xcc\xdd\xee\xff\xba\xc0")
        layer.send(b"\x10\x08", dest)

        # Second broadcast should be Who-Is-Router-To-Network
        assert len(transport.sent_broadcast) == 2
        who_is_npdu = decode_npdu(memoryview(transport.sent_broadcast[1]))
        assert who_is_npdu.is_network_message is True
        assert who_is_npdu.message_type == NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK

    def test_send_remote_npdu_has_dnet_dadr(self):
        """Remote send NPDU must contain DNET/DADR and hop count."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        dest = BACnetAddress(network=20, mac_address=b"\xcc\xdd\xee\xff\xba\xc0")
        layer.send(b"\x10\x08", dest)

        npdu_bytes = transport.sent_unicast[0][0]
        npdu = decode_npdu(memoryview(npdu_bytes))
        assert npdu.destination is not None
        assert npdu.destination.network == 20
        assert npdu.destination.mac_address == b"\xcc\xdd\xee\xff\xba\xc0"
        assert npdu.hop_count == 255
        assert npdu.apdu == b"\x10\x08"


# --------------------------------------------------------------------------
# NetworkLayer -- What-Is-Network-Number handling
# --------------------------------------------------------------------------


class TestWhatIsNetworkNumber:
    def test_configured_responds(self):
        """Configured device responds with Network-Number-Is broadcast."""
        transport = FakeTransport()
        NetworkLayer(
            transport,
            network_number=10,
            network_number_configured=True,
        )

        data = _build_what_is_network_number_npdu()
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        # Should broadcast Network-Number-Is
        assert len(transport.sent_broadcast) == 1
        npdu = decode_npdu(memoryview(transport.sent_broadcast[0]))
        assert npdu.is_network_message is True
        assert npdu.message_type == NetworkMessageType.NETWORK_NUMBER_IS

    def test_unconfigured_no_response(self):
        """Unconfigured device does not respond to What-Is-Network-Number."""
        transport = FakeTransport()
        NetworkLayer(transport, network_number=10, network_number_configured=False)

        data = _build_what_is_network_number_npdu()
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert len(transport.sent_broadcast) == 0

    def test_no_network_number_no_response(self):
        """Device with no network number does not respond."""
        transport = FakeTransport()
        NetworkLayer(transport)

        data = _build_what_is_network_number_npdu()
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert len(transport.sent_broadcast) == 0

    def test_routed_message_ignored(self):
        """What-Is with SNET/SADR is ignored (never routed)."""
        transport = FakeTransport()
        NetworkLayer(
            transport,
            network_number=10,
            network_number_configured=True,
        )

        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_what_is_network_number_npdu(source=src)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert len(transport.sent_broadcast) == 0

    def test_routed_with_destination_ignored(self):
        """What-Is with DNET/DADR is ignored (never routed)."""
        transport = FakeTransport()
        NetworkLayer(
            transport,
            network_number=10,
            network_number_configured=True,
        )

        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_what_is_network_number_npdu(destination=dest)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert len(transport.sent_broadcast) == 0


# --------------------------------------------------------------------------
# NetworkLayer -- Network-Number-Is handling
# --------------------------------------------------------------------------


class TestNetworkNumberIs:
    def test_unconfigured_learns_number(self):
        """Unconfigured device learns network number from configured source."""
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number_configured=False)
        assert layer.network_number is None

        data = _build_network_number_is_npdu(42, configured=True)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert layer.network_number == 42

    def test_configured_ignores(self):
        """Configured device ignores Network-Number-Is."""
        transport = FakeTransport()
        layer = NetworkLayer(
            transport,
            network_number=10,
            network_number_configured=True,
        )

        data = _build_network_number_is_npdu(99, configured=True)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert layer.network_number == 10  # unchanged

    def test_unconfigured_source_ignored(self):
        """Network-Number-Is with configured=False is ignored."""
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number_configured=False)

        data = _build_network_number_is_npdu(42, configured=False)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert layer.network_number is None  # unchanged

    def test_routed_message_ignored(self):
        """Network-Number-Is with SNET/SADR is ignored."""
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number_configured=False)

        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_network_number_is_npdu(42, configured=True, source=src)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert layer.network_number is None  # unchanged

    def test_routed_with_destination_ignored(self):
        """Network-Number-Is with DNET/DADR is ignored."""
        transport = FakeTransport()
        layer = NetworkLayer(transport, network_number_configured=False)

        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_network_number_is_npdu(42, configured=True, destination=dest)
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(data, source.encode())

        assert layer.network_number is None  # unchanged


# --------------------------------------------------------------------------
# NetworkLayer -- Malformed network messages
# --------------------------------------------------------------------------


class TestMalformedNetworkMessage:
    def test_malformed_network_message_dropped(self):
        """Malformed network message data is logged and dropped."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, source: received.append((data, source)))

        # Build NPDU with valid network message type but truncated data
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
            network_message_data=b"\x01",  # too short
        )
        source = BIPAddress(host="192.168.1.50", port=0xBAC0)
        transport.inject_receive(encode_npdu(npdu), source.encode())

        # Should not crash, should not deliver to app
        assert len(received) == 0
        assert len(transport.sent_broadcast) == 0
        assert len(transport.sent_unicast) == 0


# --------------------------------------------------------------------------
# Router path learning from routed APDUs (SNET/SADR)
# --------------------------------------------------------------------------


class TestRouterLearningFromRoutedAPDU:
    """When a routed APDU arrives with SNET/SADR, learn the router path."""

    def _build_routed_apdu(self, snet: int, sadr: bytes, apdu: bytes = b"\x00") -> bytes:
        """Build an NPDU with SNET/SADR set (as a router would forward)."""
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=False,
            source=BACnetAddress(network=snet, mac_address=sadr),
            apdu=apdu,
        )
        return encode_npdu(npdu)

    def test_learns_router_from_routed_apdu(self):
        """Receiving a routed APDU should populate the router cache."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, src: received.append((data, src)))

        # Simulate a router at 10.0.0.1 forwarding an APDU from network 1100
        data = self._build_routed_apdu(snet=1100, sadr=b"\x01")
        transport.inject_receive(data, _ROUTER_MAC)

        # APDU should be delivered
        assert len(received) == 1
        assert received[0][1] == BACnetAddress(network=1100, mac_address=b"\x01")

        # Router cache should have learned the path
        assert layer.get_router_for_network(1100) == _ROUTER_MAC

    def test_learns_router_for_mstp_one_byte_mac(self):
        """MS/TP device (1-byte MAC) behind a router."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        layer.on_receive(lambda data, src: None)

        data = self._build_routed_apdu(snet=4352, sadr=b"\xfe")
        transport.inject_receive(data, _ROUTER_MAC)
        assert layer.get_router_for_network(4352) == _ROUTER_MAC

    def test_does_not_overwrite_fresh_i_am_router_entry(self):
        """Explicit I-Am-Router-To-Network entries should not be overwritten."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        layer.on_receive(lambda data, src: None)

        # First: explicit I-Am-Router from router_a
        router_a = BIPAddress(host="10.0.0.1", port=0xBAC0).encode()
        i_am_data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(i_am_data, router_a)
        assert layer.get_router_for_network(20) == router_a

        # Then: receive a routed APDU from router_b for network 20
        router_b = BIPAddress(host="10.0.0.2", port=0xBAC0).encode()
        data = self._build_routed_apdu(snet=20, sadr=b"\x05")
        transport.inject_receive(data, router_b)

        # Should NOT overwrite the explicit I-Am-Router entry
        assert layer.get_router_for_network(20) == router_a

    def test_populates_empty_cache(self):
        """When no router cache entry exists, learning from SNET creates one."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        layer.on_receive(lambda data, src: None)

        assert layer.get_router_for_network(500) is None
        data = self._build_routed_apdu(snet=500, sadr=b"\x0a\x0b")
        transport.inject_receive(data, _ROUTER_MAC)
        assert layer.get_router_for_network(500) == _ROUTER_MAC

    def test_replaces_stale_entry(self):
        """Stale cache entry should be replaced by learned route."""
        transport = FakeTransport()
        layer = NetworkLayer(transport, cache_ttl=0.01)  # very short TTL
        layer.on_receive(lambda data, src: None)

        # Populate cache, then let it expire
        router_a = BIPAddress(host="10.0.0.1", port=0xBAC0).encode()
        i_am_data = _build_i_am_router_npdu(networks=(20,))
        transport.inject_receive(i_am_data, router_a)
        time.sleep(0.02)  # let it go stale

        # Now learn from a different router
        router_b = BIPAddress(host="10.0.0.2", port=0xBAC0).encode()
        data = self._build_routed_apdu(snet=20, sadr=b"\x05")
        transport.inject_receive(data, router_b)
        assert layer.get_router_for_network(20) == router_b

    def test_no_source_network_not_learned(self):
        """APDU without SNET (local) should not populate router cache."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        layer.on_receive(lambda data, src: None)

        # Local APDU — no source network
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=False,
            apdu=b"\x00",
        )
        transport.inject_receive(encode_npdu(npdu), _ROUTER_MAC)
        # Router cache should remain empty
        assert layer._router_cache == {}

    def test_subsequent_sends_use_learned_router(self):
        """After learning a router, sends to that network should use unicast."""
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        layer.on_receive(lambda data, src: None)

        # Learn router from routed APDU
        data = self._build_routed_apdu(snet=1100, sadr=b"\x01")
        transport.inject_receive(data, _ROUTER_MAC)

        # Now send to a device on network 1100
        dest = BACnetAddress(network=1100, mac_address=b"\x02")
        layer.send(b"\x00", dest, expecting_reply=True)

        # Should unicast to the learned router, not broadcast
        assert len(transport.sent_unicast) == 1
        assert transport.sent_unicast[0][1] == _ROUTER_MAC
        assert len(transport.sent_broadcast) == 0


# --------------------------------------------------------------------------
# NetworkLayer -- Remote send with variable-length MAC addresses (MS/TP, ARCNET)
# --------------------------------------------------------------------------


class TestRemoteSendVariableMac:
    """Tests for sending to remote devices with variable-length MAC addresses.

    MS/TP and ARCNET devices use 1-byte MACs; other data links may use
    2-byte or other non-IP address sizes.  The network layer must correctly
    encode DNET/DADR/DLEN in the outgoing NPDU regardless of MAC length.
    """

    def _build_routed_apdu(self, snet: int, sadr: bytes, apdu: bytes = b"\x00") -> bytes:
        """Build an NPDU with SNET/SADR set (as a router would forward)."""
        npdu = NPDU(
            is_network_message=False,
            expecting_reply=False,
            source=BACnetAddress(network=snet, mac_address=sadr),
            apdu=apdu,
        )
        return encode_npdu(npdu)

    def test_send_1byte_mstp_via_cached_router(self):
        """Send to 1-byte MS/TP address via cached router.

        Populates router cache for network 4352, sends to a 1-byte MAC,
        and verifies the NPDU encodes DNET=4352, DADR=0x01, DLEN=1.
        """
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        # Populate cache for network 4352
        data = _build_i_am_router_npdu(networks=(4352,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        # Send APDU to 1-byte MS/TP address
        dest = BACnetAddress(network=4352, mac_address=b"\x01")
        apdu = b"\x10\x08"
        layer.send(apdu, dest, expecting_reply=True)

        # Should unicast to the cached router
        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        npdu_bytes, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

        # Decode and verify NPDU destination fields
        npdu = decode_npdu(memoryview(npdu_bytes))
        assert npdu.destination is not None
        assert npdu.destination.network == 4352
        assert npdu.destination.mac_address == b"\x01"
        assert len(npdu.destination.mac_address) == 1  # DLEN=1
        assert npdu.hop_count == 255
        assert npdu.apdu == apdu
        assert npdu.expecting_reply is True

    def test_send_2byte_mac_via_cached_router(self):
        """Send to 2-byte MAC via cached router.

        Verifies DLEN=2 in the outgoing NPDU for a non-standard 2-byte
        data link address.
        """
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        # Populate cache for network 4352
        data = _build_i_am_router_npdu(networks=(4352,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        # Send APDU to 2-byte MAC
        dest = BACnetAddress(network=4352, mac_address=b"\x0a\x0b")
        apdu = b"\x10\x08"
        layer.send(apdu, dest, expecting_reply=True)

        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        npdu_bytes, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

        # Decode and verify NPDU destination fields
        npdu = decode_npdu(memoryview(npdu_bytes))
        assert npdu.destination is not None
        assert npdu.destination.network == 4352
        assert npdu.destination.mac_address == b"\x0a\x0b"
        assert len(npdu.destination.mac_address) == 2  # DLEN=2
        assert npdu.hop_count == 255
        assert npdu.apdu == apdu

    def test_send_1byte_mstp_cache_miss_broadcasts(self):
        """Send to 1-byte MS/TP address without cached router (cache miss).

        Should broadcast the NPDU and send Who-Is-Router-To-Network.
        The broadcast NPDU must still carry the correct DNET/DADR.
        """
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        # No router cached for network 4352
        dest = BACnetAddress(network=4352, mac_address=b"\xfe")
        apdu = b"\x10\x08"
        layer.send(apdu, dest, expecting_reply=True)

        # Should broadcast NPDU + Who-Is-Router-To-Network
        assert len(transport.sent_broadcast) == 2
        assert len(transport.sent_unicast) == 0

        # First broadcast: the APDU wrapped in NPDU with DNET/DADR
        npdu = decode_npdu(memoryview(transport.sent_broadcast[0]))
        assert npdu.is_network_message is False
        assert npdu.destination is not None
        assert npdu.destination.network == 4352
        assert npdu.destination.mac_address == b"\xfe"
        assert len(npdu.destination.mac_address) == 1
        assert npdu.apdu == apdu

        # Second broadcast: Who-Is-Router-To-Network
        who_npdu = decode_npdu(memoryview(transport.sent_broadcast[1]))
        assert who_npdu.is_network_message is True
        assert who_npdu.message_type == NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK

    def test_receive_routed_iam_then_send_reply(self):
        """Receive routed I-Am from MS/TP device, then send reply back.

        Injects a routed APDU with SNET=1100, SADR=0x01 (simulating an
        I-Am from an MS/TP device behind a router).  Verifies the router
        cache was learned, then sends an APDU to the same device and
        confirms it unicasts to the learned router, not broadcast.
        """
        transport = FakeTransport()
        layer = NetworkLayer(transport)
        received = []
        layer.on_receive(lambda data, src: received.append((data, src)))

        # Inject routed APDU: router at _ROUTER_MAC forwards from SNET=1100
        i_am_apdu = b"\x10\x00"  # simulated I-Am APDU
        routed_npdu = self._build_routed_apdu(snet=1100, sadr=b"\x01", apdu=i_am_apdu)
        transport.inject_receive(routed_npdu, _ROUTER_MAC)

        # APDU should be delivered with correct source address
        assert len(received) == 1
        data, src = received[0]
        assert data == i_am_apdu
        assert src == BACnetAddress(network=1100, mac_address=b"\x01")

        # Router cache should have learned the path
        assert layer.get_router_for_network(1100) == _ROUTER_MAC

        # Clear transport logs for the send phase
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        # Send APDU to the same MS/TP device
        dest = BACnetAddress(network=1100, mac_address=b"\x01")
        reply_apdu = b"\x30\x01"
        layer.send(reply_apdu, dest, expecting_reply=False)

        # Should unicast to the learned router, not broadcast
        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        npdu_bytes, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

        # Verify NPDU destination
        npdu = decode_npdu(memoryview(npdu_bytes))
        assert npdu.destination is not None
        assert npdu.destination.network == 1100
        assert npdu.destination.mac_address == b"\x01"
        assert len(npdu.destination.mac_address) == 1
        assert npdu.apdu == reply_apdu

    def test_remote_broadcast_to_mstp_network(self):
        """Remote broadcast to MS/TP network.

        Sends to BACnetAddress(network=4352, mac_address=b"") which is a
        directed broadcast on a remote network.  Verifies DNET=4352 and
        DLEN=0 in the outgoing NPDU.
        """
        transport = FakeTransport()
        layer = NetworkLayer(transport)

        # Populate cache so we can verify unicast to router
        data = _build_i_am_router_npdu(networks=(4352,))
        transport.inject_receive(data, _ROUTER_MAC)
        transport.sent_unicast.clear()
        transport.sent_broadcast.clear()

        # Remote broadcast: network set, empty MAC
        dest = BACnetAddress(network=4352, mac_address=b"")
        apdu = b"\x10\x08"
        layer.send(apdu, dest, expecting_reply=False)

        # With cached router, remote broadcast should unicast to router
        assert len(transport.sent_unicast) == 1
        assert len(transport.sent_broadcast) == 0
        npdu_bytes, bip_dest = transport.sent_unicast[0]
        assert bip_dest == _ROUTER_MAC

        # Decode and verify DNET=4352, DLEN=0 (empty DADR)
        npdu = decode_npdu(memoryview(npdu_bytes))
        assert npdu.destination is not None
        assert npdu.destination.network == 4352
        assert npdu.destination.mac_address == b""
        assert len(npdu.destination.mac_address) == 0  # DLEN=0
        assert npdu.hop_count == 255
        assert npdu.apdu == apdu
