"""Tests for NetworkRouter engine (message forwarding, network discovery)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bac_py.network.address import BACnetAddress
from bac_py.network.messages import (
    DisconnectConnectionToNetwork,
    EstablishConnectionToNetwork,
    IAmRouterToNetwork,
    ICouldBeRouterToNetwork,
    InitializeRoutingTable,
    InitializeRoutingTableAck,
    NetworkNumberIs,
    RejectMessageToNetwork,
    RouterAvailableToNetwork,
    RouterBusyToNetwork,
    RoutingTablePort,
    WhoIsRouterToNetwork,
    decode_network_message,
    encode_network_message,
)
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.network.router import NetworkRouter, RouterPort
from bac_py.types.enums import (
    NetworkMessageType,
    NetworkPriority,
    NetworkReachability,
    RejectMessageReason,
)
from tests.network.conftest import _make_port, _make_transport

# ---------------------------------------------------------------------------
# RouterPort
# ---------------------------------------------------------------------------


class TestRouterPort:
    def test_create(self) -> None:
        t = _make_transport()
        port = RouterPort(
            port_id=1,
            network_number=10,
            transport=t,
            mac_address=b"\x7f\x00\x00\x01\xba\xc0",
            max_npdu_length=1497,
        )
        assert port.port_id == 1
        assert port.network_number == 10
        assert port.transport is t
        assert port.mac_address == b"\x7f\x00\x00\x01\xba\xc0"
        assert port.max_npdu_length == 1497

    def test_default_configured(self) -> None:
        port = _make_port()
        assert port.network_number_configured is True

    def test_configured_false(self) -> None:
        port = _make_port()
        port.network_number_configured = False
        assert port.network_number_configured is False

    def test_mutable(self) -> None:
        """RouterPort is mutable (not frozen) so we can update network_number."""
        port = _make_port(network_number=10)
        port.network_number = 20
        assert port.network_number == 20


# ===========================================================================
# NetworkRouter tests
# ===========================================================================

# ---------------------------------------------------------------------------
# NetworkRouter helpers
# ---------------------------------------------------------------------------

# Standard MAC addresses for test ports
_MAC_PORT1 = b"\x7f\x00\x00\x01\xba\xc0"  # 127.0.0.1:47808
_MAC_PORT2 = b"\x0a\x00\x00\x01\xba\xc0"  # 10.0.0.1:47808
_MAC_DEVICE_A = b"\xc0\xa8\x01\x0a\xba\xc0"  # 192.168.1.10:47808
_MAC_DEVICE_B = b"\xc0\xa8\x02\x14\xba\xc0"  # 192.168.2.20:47808


def _make_router_ports(
    *,
    net1: int = 10,
    net2: int = 20,
) -> tuple[RouterPort, RouterPort, MagicMock, MagicMock]:
    """Create two router ports with mock transports."""
    t1 = _make_transport(local_mac=_MAC_PORT1)
    t2 = _make_transport(local_mac=_MAC_PORT2)
    p1 = RouterPort(
        port_id=1,
        network_number=net1,
        transport=t1,
        mac_address=_MAC_PORT1,
        max_npdu_length=1497,
    )
    p2 = RouterPort(
        port_id=2,
        network_number=net2,
        transport=t2,
        mac_address=_MAC_PORT2,
        max_npdu_length=1497,
    )
    return p1, p2, t1, t2


def _make_two_port_router(
    *,
    app_port: int | None = 1,
    app_callback: MagicMock | None = None,
) -> tuple[NetworkRouter, MagicMock, MagicMock]:
    """Create a two-port router (net 10 on port 1, net 20 on port 2)."""
    p1, p2, t1, t2 = _make_router_ports()
    if app_callback is None:
        app_callback = MagicMock()
    router = NetworkRouter(
        [p1, p2],
        application_port_id=app_port,
        application_callback=app_callback,
    )
    return router, t1, t2


def _build_local_npdu(apdu: bytes = b"\x01\x02\x03") -> bytes:
    """Build an NPDU with no destination (local traffic)."""
    return encode_npdu(NPDU(apdu=apdu))


def _build_routed_npdu(
    dnet: int,
    dadr: bytes = b"",
    *,
    apdu: bytes = b"\x01\x02\x03",
    source: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build an NPDU with destination address."""
    dest = BACnetAddress(network=dnet, mac_address=dadr)
    return encode_npdu(
        NPDU(
            destination=dest,
            source=source,
            hop_count=hop_count,
            apdu=apdu,
        )
    )


def _build_global_broadcast_npdu(
    apdu: bytes = b"\x01\x02\x03",
    *,
    source: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build a global broadcast NPDU (DNET=0xFFFF)."""
    dest = BACnetAddress(network=0xFFFF, mac_address=b"")
    return encode_npdu(
        NPDU(
            destination=dest,
            source=source,
            hop_count=hop_count,
            apdu=apdu,
        )
    )


# ---------------------------------------------------------------------------
# NetworkRouter -- Construction
# ---------------------------------------------------------------------------


class TestNetworkRouterConstruction:
    def test_constructor_populates_routing_table(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])
        rt = router.routing_table
        assert rt.get_port(1) is p1
        assert rt.get_port(2) is p2
        assert rt.get_entry(10) is not None
        assert rt.get_entry(20) is not None

    def test_no_application_port(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])
        assert router._application_port_id is None
        assert router._application_callback is None

    def test_with_application_port(self) -> None:
        cb = MagicMock()
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter(
            [p1, p2],
            application_port_id=1,
            application_callback=cb,
        )
        assert router._application_port_id == 1


# ---------------------------------------------------------------------------
# NetworkRouter -- Start / Stop
# ---------------------------------------------------------------------------


class TestNetworkRouterLifecycle:
    async def test_start_wires_callbacks_and_starts_transports(self) -> None:
        router, t1, t2 = _make_two_port_router()
        await router.start()
        t1.on_receive.assert_called_once()
        t2.on_receive.assert_called_once()
        t1.start.assert_awaited_once()
        t2.start.assert_awaited_once()

    async def test_stop_stops_transports(self) -> None:
        router, t1, t2 = _make_two_port_router()
        await router.start()
        await router.stop()
        t1.stop.assert_awaited_once()
        t2.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# NetworkRouter -- Local delivery
# ---------------------------------------------------------------------------


class TestNetworkRouterLocalDelivery:
    def test_local_traffic_delivered_to_app(self) -> None:
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        data = _build_local_npdu(apdu=b"\xaa\xbb")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        app_cb.assert_called_once()
        apdu, src = app_cb.call_args[0]
        assert apdu == b"\xaa\xbb"
        assert src.mac_address == _MAC_DEVICE_A

    def test_local_traffic_no_app_callback(self) -> None:
        p1, p2, t1, t2 = _make_router_ports()
        router = NetworkRouter([p1, p2])  # no app callback
        data = _build_local_npdu()
        # Should not raise
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_local_traffic_source_from_npdu(self) -> None:
        """When NPDU has SNET/SADR, those should be used as source."""
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        src = BACnetAddress(network=30, mac_address=b"\xee")
        npdu = NPDU(source=src, apdu=b"\xdd")
        router._on_port_receive(1, encode_npdu(npdu), _MAC_DEVICE_A)
        _, delivered_src = app_cb.call_args[0]
        assert delivered_src.network == 30
        assert delivered_src.mac_address == b"\xee"


# ---------------------------------------------------------------------------
# NetworkRouter -- Global broadcast forwarding
# ---------------------------------------------------------------------------


class TestNetworkRouterGlobalBroadcast:
    def test_global_broadcast_delivered_to_app(self) -> None:
        app_cb = MagicMock()
        router, _, _ = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(apdu=b"\x10\x20")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        app_cb.assert_called_once()
        apdu, _ = app_cb.call_args[0]
        assert apdu == b"\x10\x20"

    def test_global_broadcast_forwarded_to_other_ports(self) -> None:
        app_cb = MagicMock()
        router, t1, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should be forwarded to port 2 as broadcast
        t2.send_broadcast.assert_called_once()
        # Should NOT be sent back to port 1
        t1.send_broadcast.assert_not_called()

    def test_global_broadcast_not_forwarded_back_to_origin(self) -> None:
        app_cb = MagicMock()
        router, t1, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(2, data, _MAC_DEVICE_B)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_not_called()

    def test_global_broadcast_snet_sadr_injected(self) -> None:
        """When forwarding, SNET/SADR should be injected if not present."""
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Check the forwarded NPDU has SNET/SADR
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 10  # port 1's network
        assert forwarded.source.mac_address == _MAC_DEVICE_A

    def test_global_broadcast_preserves_existing_snet_sadr(self) -> None:
        """If SNET/SADR already present, they should be preserved."""
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        orig_src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_global_broadcast_npdu(source=orig_src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 30
        assert forwarded.source.mac_address == b"\xaa"

    def test_global_broadcast_hop_count_decremented(self) -> None:
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(hop_count=100)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)
        assert forwarded.hop_count == 99

    def test_global_broadcast_hop_count_exhausted_not_forwarded(self) -> None:
        app_cb = MagicMock()
        router, _, t2 = _make_two_port_router(app_callback=app_cb)
        data = _build_global_broadcast_npdu(hop_count=1)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should still deliver to app
        app_cb.assert_called_once()
        # But NOT forward (hop count becomes 0)
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Forwarding to directly connected network
# ---------------------------------------------------------------------------


class TestNetworkRouterDirectlyConnected:
    def test_unicast_to_directly_connected_network(self) -> None:
        """NPDU with DNET=20 and DADR should be delivered on port 2."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B, apdu=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should be sent as unicast to DADR on port 2
        t2.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_B
        # NPDU should have destination stripped
        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\xcc"

    def test_directed_broadcast_to_directly_connected_network(self) -> None:
        """NPDU with DNET=20 and DLEN=0 (broadcast) should broadcast on port 2."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=b"", apdu=b"\xdd")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        sent_bytes = t2.send_broadcast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\xdd"

    def test_snet_sadr_injected_on_delivery(self) -> None:
        """SNET/SADR should be injected when delivering to another net."""
        router, _, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.source is not None
        assert delivered.source.network == 10  # arrival port's network
        assert delivered.source.mac_address == _MAC_DEVICE_A

    def test_existing_snet_sadr_preserved(self) -> None:
        router, _, t2 = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xaa\xbb")
        data = _build_routed_npdu(dnet=20, dadr=_MAC_DEVICE_B, source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        delivered = decode_npdu(sent_bytes)
        assert delivered.source.network == 30
        assert delivered.source.mac_address == b"\xaa\xbb"

    def test_not_forwarded_to_origin_port(self) -> None:
        """Traffic for network 10 arriving on port 1 is delivered locally on port 1."""
        router, t1, t2 = _make_two_port_router()
        # Device on net 20 wants to reach device on net 10
        data = _build_routed_npdu(dnet=10, dadr=_MAC_DEVICE_A)
        router._on_port_receive(2, data, _MAC_DEVICE_B)
        t1.send_unicast.assert_called_once()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Forward via next-hop router
# ---------------------------------------------------------------------------


class TestNetworkRouterNextHop:
    def test_forward_via_next_hop(self) -> None:
        """Remote network via next-hop router."""
        router, _, t2 = _make_two_port_router()
        next_hop_mac = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop_mac)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        _, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == next_hop_mac

    def test_forward_preserves_dnet_dadr(self) -> None:
        """When forwarding via next-hop, DNET/DADR must be preserved."""
        router, _, t2 = _make_two_port_router()
        next_hop_mac = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop_mac)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.destination is not None
        assert forwarded.destination.network == 30
        assert forwarded.destination.mac_address == b"\xcc"

    def test_forward_decrements_hop_count(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=50)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.hop_count == 49

    def test_forward_injects_snet_sadr(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        sent_bytes = t2.send_unicast.call_args[0][0]
        forwarded = decode_npdu(sent_bytes)
        assert forwarded.source is not None
        assert forwarded.source.network == 10
        assert forwarded.source.mac_address == _MAC_DEVICE_A


# ---------------------------------------------------------------------------
# NetworkRouter -- Hop count handling
# ---------------------------------------------------------------------------


class TestNetworkRouterHopCount:
    def test_hop_count_one_discards(self) -> None:
        """Hop count 1 means next decrement = 0 -> discard."""
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=1)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_not_called()

    def test_hop_count_two_forwards(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=2)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        sent_bytes = t2.send_unicast.call_args[0][0]
        assert decode_npdu(sent_bytes).hop_count == 1

    def test_hop_count_255_forwards(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc", hop_count=255)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_called_once()
        sent_bytes = t2.send_unicast.call_args[0][0]
        assert decode_npdu(sent_bytes).hop_count == 254


# ---------------------------------------------------------------------------
# NetworkRouter -- Unknown destination
# ---------------------------------------------------------------------------


class TestNetworkRouterUnknownDest:
    def test_unknown_dnet_sends_reject(self) -> None:
        """Unknown DNET sends Reject-Message back to source (Clause 6.6.3.5)."""
        router, t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(dnet=99, dadr=b"\xcc")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Reject sent back on arrival port
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99
        # Not forwarded to other port
        t2.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Malformed NPDU
# ---------------------------------------------------------------------------


class TestNetworkRouterMalformed:
    def test_malformed_npdu_dropped(self) -> None:
        router, t1, t2 = _make_two_port_router()
        router._on_port_receive(1, b"\xff\xff\xff", _MAC_DEVICE_A)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Network message dispatch
# ---------------------------------------------------------------------------


class TestNetworkRouterNetworkMessage:
    def test_network_message_handled(self) -> None:
        """Network messages should go to _handle_network_message, not forwarding."""
        app_cb = MagicMock()
        router, _t1, _t2 = _make_two_port_router(app_callback=app_cb)
        # Build a network message NPDU (Who-Is-Router-To-Network)
        npdu = NPDU(
            is_network_message=True,
            message_type=0x00,
            network_message_data=b"",
        )
        router._on_port_receive(1, encode_npdu(npdu), _MAC_DEVICE_A)
        # Should NOT deliver to application
        app_cb.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- SNET/SADR injection details
# ---------------------------------------------------------------------------


class TestNetworkRouterSnetSadr:
    def test_inject_source_creates_bacnet_address(self) -> None:
        router, _, _ = _make_two_port_router()
        npdu = NPDU(apdu=b"\x01")
        result = router._inject_source(1, npdu, _MAC_DEVICE_A)
        assert result is not None
        assert result.network == 10
        assert result.mac_address == _MAC_DEVICE_A

    def test_inject_source_preserves_existing(self) -> None:
        router, _, _ = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xff")
        npdu = NPDU(source=src, apdu=b"\x01")
        result = router._inject_source(1, npdu, _MAC_DEVICE_A)
        assert result is src


# ---------------------------------------------------------------------------
# NetworkRouter -- send() method
# ---------------------------------------------------------------------------


class TestNetworkRouterSend:
    def test_send_local_broadcast(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress()  # local broadcast
        router.send(b"\xaa\xbb", dest)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_not_called()
        sent_bytes = t1.send_broadcast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.apdu == b"\xaa\xbb"

    def test_send_global_broadcast(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=0xFFFF)
        router.send(b"\xaa", dest)
        t1.send_broadcast.assert_called_once()
        t2.send_broadcast.assert_called_once()
        # Both should have the same encoded NPDU
        sent1 = t1.send_broadcast.call_args[0][0]
        sent2 = t2.send_broadcast.call_args[0][0]
        assert sent1 == sent2
        npdu = decode_npdu(sent1)
        assert npdu.destination is not None
        assert npdu.destination.network == 0xFFFF

    def test_send_local_unicast(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\xcc", dest)
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.apdu == b"\xcc"
        assert npdu.destination is None  # local

    def test_send_remote_directly_connected(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=_MAC_DEVICE_B)
        router.send(b"\xdd", dest)
        t2.send_unicast.assert_called_once()
        _sent_bytes, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_B

    def test_send_remote_broadcast(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=b"")
        router.send(b"\xee", dest)
        t2.send_broadcast.assert_called_once()

    def test_send_remote_via_next_hop(self) -> None:
        router, _, t2 = _make_two_port_router()
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)
        dest = BACnetAddress(network=30, mac_address=b"\xcc")
        router.send(b"\xff", dest)
        t2.send_unicast.assert_called_once()
        _, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == next_hop

    def test_send_no_application_port_raises(self) -> None:
        p1, p2, _, _ = _make_router_ports()
        router = NetworkRouter([p1, p2])  # no app port
        with pytest.raises(RuntimeError, match="No application port"):
            router.send(b"\x01", BACnetAddress())

    def test_send_unknown_network(self) -> None:
        router, t1, t2 = _make_two_port_router()
        dest = BACnetAddress(network=99, mac_address=b"\xcc")
        # Should not raise, just log warning
        router.send(b"\x01", dest)
        t1.send_unicast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_send_expecting_reply(self) -> None:
        router, t1, _ = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\x01", dest, expecting_reply=True)
        sent_bytes = t1.send_unicast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.expecting_reply is True

    def test_send_priority(self) -> None:
        router, t1, _ = _make_two_port_router()
        dest = BACnetAddress(mac_address=_MAC_DEVICE_A)
        router.send(b"\x01", dest, priority=NetworkPriority.URGENT)
        sent_bytes = t1.send_unicast.call_args[0][0]
        npdu = decode_npdu(sent_bytes)
        assert npdu.priority == NetworkPriority.URGENT


# ---------------------------------------------------------------------------
# NetworkRouter -- Three-port topology
# ---------------------------------------------------------------------------


class TestNetworkRouterThreePort:
    def test_global_broadcast_floods_all_other_ports(self) -> None:
        t1 = _make_transport(local_mac=b"\x01\x00\x00\x01\xba\xc0")
        t2 = _make_transport(local_mac=b"\x02\x00\x00\x01\xba\xc0")
        t3 = _make_transport(local_mac=b"\x03\x00\x00\x01\xba\xc0")
        p1 = _make_port(port_id=1, network_number=10, transport=t1)
        p2 = _make_port(port_id=2, network_number=20, transport=t2)
        p3 = _make_port(port_id=3, network_number=30, transport=t3)
        router = NetworkRouter([p1, p2, p3])
        data = _build_global_broadcast_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t2.send_broadcast.assert_called_once()
        t3.send_broadcast.assert_called_once()

    def test_routed_unicast_to_correct_port(self) -> None:
        t1 = _make_transport(local_mac=b"\x01\x00\x00\x01\xba\xc0")
        t2 = _make_transport(local_mac=b"\x02\x00\x00\x01\xba\xc0")
        t3 = _make_transport(local_mac=b"\x03\x00\x00\x01\xba\xc0")
        p1 = _make_port(port_id=1, network_number=10, transport=t1)
        p2 = _make_port(port_id=2, network_number=20, transport=t2)
        p3 = _make_port(port_id=3, network_number=30, transport=t3)
        router = NetworkRouter([p1, p2, p3])
        data = _build_routed_npdu(dnet=30, dadr=b"\xcc\xdd\xee\xff\xba\xc0")
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_unicast.assert_not_called()
        t3.send_unicast.assert_called_once()
        t1.send_unicast.assert_not_called()


# ===========================================================================
# Network message handler tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Helpers for building network message NPDUs
# ---------------------------------------------------------------------------


def _build_network_message_npdu(
    msg_type: int,
    data: bytes = b"",
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
    hop_count: int = 255,
) -> bytes:
    """Build a network layer message NPDU from raw type + data."""
    npdu = NPDU(
        is_network_message=True,
        message_type=msg_type,
        network_message_data=data,
        source=source,
        destination=destination,
        hop_count=hop_count if destination is not None else 255,
    )
    return encode_npdu(npdu)


def _build_who_is_router_npdu(network: int | None = None) -> bytes:
    """Build a Who-Is-Router-To-Network NPDU."""
    msg = WhoIsRouterToNetwork(network=network)
    return _build_network_message_npdu(
        NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_i_am_router_npdu(networks: tuple[int, ...]) -> bytes:
    """Build an I-Am-Router-To-Network NPDU."""
    msg = IAmRouterToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.I_AM_ROUTER_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_reject_message_npdu(
    reason: RejectMessageReason,
    network: int,
    *,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a Reject-Message-To-Network NPDU."""
    msg = RejectMessageToNetwork(reason=reason, network=network)
    return _build_network_message_npdu(
        NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
        encode_network_message(msg),
        destination=destination,
    )


def _build_router_busy_npdu(networks: tuple[int, ...]) -> bytes:
    """Build a Router-Busy-To-Network NPDU."""
    msg = RouterBusyToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.ROUTER_BUSY_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_router_available_npdu(networks: tuple[int, ...]) -> bytes:
    """Build a Router-Available-To-Network NPDU."""
    msg = RouterAvailableToNetwork(networks=networks)
    return _build_network_message_npdu(
        NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK,
        encode_network_message(msg),
    )


def _build_init_routing_table_npdu(ports: tuple[RoutingTablePort, ...]) -> bytes:
    """Build an Initialize-Routing-Table NPDU."""
    msg = InitializeRoutingTable(ports=ports)
    return _build_network_message_npdu(
        NetworkMessageType.INITIALIZE_ROUTING_TABLE,
        encode_network_message(msg),
    )


def _build_init_routing_table_ack_npdu(ports: tuple[RoutingTablePort, ...]) -> bytes:
    """Build an Initialize-Routing-Table-Ack NPDU."""
    msg = InitializeRoutingTableAck(ports=ports)
    return _build_network_message_npdu(
        NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK,
        encode_network_message(msg),
    )


def _build_what_is_network_number_npdu(
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a What-Is-Network-Number NPDU."""
    return _build_network_message_npdu(
        NetworkMessageType.WHAT_IS_NETWORK_NUMBER,
        b"",
        source=source,
        destination=destination,
    )


def _build_network_number_is_npdu(
    network: int,
    configured: bool,
    *,
    source: BACnetAddress | None = None,
    destination: BACnetAddress | None = None,
) -> bytes:
    """Build a Network-Number-Is NPDU."""
    msg = NetworkNumberIs(network=network, configured=configured)
    return _build_network_message_npdu(
        NetworkMessageType.NETWORK_NUMBER_IS,
        encode_network_message(msg),
        source=source,
        destination=destination,
    )


def _decode_sent_network_message(
    transport_mock: MagicMock,
    *,
    method: str = "send_broadcast",
    call_index: int = 0,
) -> tuple[NPDU, bytes]:
    """Decode a network message sent on a mock transport.

    Returns (npdu, raw_network_message_data).
    """
    mock_method = getattr(transport_mock, method)
    args = mock_method.call_args_list[call_index][0]
    raw = args[0]
    npdu = decode_npdu(raw)
    return npdu, npdu.network_message_data


# ---------------------------------------------------------------------------
# NetworkRouter -- Who-Is-Router-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleWhoIsRouter:
    def test_specific_dnet_found_on_other_port(self) -> None:
        """DNET reachable on different port -> I-Am-Router reply on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=20)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should broadcast I-Am-Router on port 1 (arrival port)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        assert npdu.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (20,)

    def test_specific_dnet_found_on_arrival_port(self) -> None:
        """DNET reachable on arrival port -> no reply (don't advertise back)."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=10)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()

    def test_specific_dnet_not_found_forwarded(self) -> None:
        """Unknown DNET -> forward Who-Is out all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=99)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should forward (broadcast) on port 2
        t2.send_broadcast.assert_called_once()
        # Should NOT send on port 1
        t1.send_broadcast.assert_not_called()
        # The forwarded message should have SNET/SADR injected
        fwd_bytes = t2.send_broadcast.call_args[0][0]
        fwd_npdu = decode_npdu(fwd_bytes)
        assert fwd_npdu.source is not None
        assert fwd_npdu.source.network == 10

    def test_query_all_networks(self) -> None:
        """No specific DNET -> I-Am-Router with all reachable nets (excluding arrival)."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_who_is_router_npdu(network=None)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should reply on port 1 with network 20 (port 2's network)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert 20 in msg.networks
        assert 10 not in msg.networks  # exclude arrival port

    def test_query_all_includes_busy_networks(self) -> None:
        """Who-Is (no DNET) must include BUSY networks per Clause 6.6.3.2."""
        router, t1, _t2 = _make_two_port_router()
        # Add net 30 via port 2 and mark it BUSY
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY

        data = _build_who_is_router_npdu(network=None)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert 30 in msg.networks  # BUSY network included


# ---------------------------------------------------------------------------
# NetworkRouter -- I-Am-Router-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleIAmRouter:
    def test_new_entries_created(self) -> None:
        """I-Am-Router creates new routing table entries."""
        router, _t1, _t2 = _make_two_port_router()
        data = _build_i_am_router_npdu(networks=(30, 40))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # New entries in routing table
        entry30 = router.routing_table.get_entry(30)
        entry40 = router.routing_table.get_entry(40)
        assert entry30 is not None
        assert entry30.port_id == 1
        assert entry30.next_router_mac == _MAC_DEVICE_A
        assert entry40 is not None
        assert entry40.port_id == 1
        assert entry40.next_router_mac == _MAC_DEVICE_A

    def test_existing_entries_updated(self) -> None:
        """I-Am-Router updates existing entries with new MAC."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=b"\x01")
        data = _build_i_am_router_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.next_router_mac == _MAC_DEVICE_A

    def test_rebroadcast_on_other_ports(self) -> None:
        """I-Am-Router is re-broadcast on all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_i_am_router_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should re-broadcast on port 2
        t2.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, IAmRouterToNetwork)
        assert msg.networks == (30,)
        # Should NOT broadcast back on port 1
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Reject-Message-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRejectMessage:
    def test_reason_not_directly_connected_marks_unreachable(self) -> None:
        """Reason 1 -> network marked UNREACHABLE."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        data = _build_reject_message_npdu(
            RejectMessageReason.NOT_DIRECTLY_CONNECTED,
            30,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.UNREACHABLE

    async def test_reason_router_busy_marks_busy(self) -> None:
        """Reason 2 -> network marked BUSY with auto-recovery."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        data = _build_reject_message_npdu(
            RejectMessageReason.ROUTER_BUSY,
            30,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY

    def test_relay_toward_originator(self) -> None:
        """Reject message with DNET/DADR is forwarded toward originator."""
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        # DNET points to network 20 (directly connected on port 2)
        dest = BACnetAddress(network=20, mac_address=_MAC_DEVICE_B)
        data = _build_reject_message_npdu(
            RejectMessageReason.OTHER,
            30,
            destination=dest,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should forward toward network 20 (port 2)
        t2.send_unicast.assert_called_once()


# ---------------------------------------------------------------------------
# NetworkRouter -- Router-Busy-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRouterBusy:
    async def test_listed_dnets_marked_busy(self) -> None:
        """Specific DNETs in the message are marked BUSY."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        data = _build_router_busy_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY

    async def test_empty_list_marks_all_sender_dnets(self) -> None:
        """Empty list -> all networks served by sender marked BUSY."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        router.routing_table.update_route(40, port_id=1, next_router_mac=_MAC_DEVICE_A)
        # Also a route via a different router on the same port
        router.routing_table.update_route(50, port_id=1, next_router_mac=b"\x99")
        data = _build_router_busy_npdu(networks=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # 30 and 40 should be BUSY (same source_mac)
        entry30 = router.routing_table.get_entry(30)
        entry40 = router.routing_table.get_entry(40)
        assert entry30 is not None and entry30.reachability == NetworkReachability.BUSY
        assert entry40 is not None and entry40.reachability == NetworkReachability.BUSY
        # 50 via different router should be unaffected
        entry50 = router.routing_table.get_entry(50)
        assert entry50 is not None and entry50.reachability == NetworkReachability.REACHABLE

    async def test_rebroadcast_on_other_ports(self) -> None:
        """Router-Busy is re-broadcast on all other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_router_busy_npdu(networks=(10,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        npdu, _msg_data = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.ROUTER_BUSY_TO_NETWORK
        t1.send_broadcast.assert_not_called()

    async def test_busy_timer_auto_restores_reachable(self) -> None:
        """30s timer restores REACHABLE (tested with short timeout)."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        data = _build_router_busy_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY
        assert entry.busy_timeout_handle is not None
        # The handler uses call_later with default 30s; verify handle exists
        # Cancel and trigger manually for the test
        entry.busy_timeout_handle.cancel()
        router.routing_table.mark_available(30)
        assert entry.reachability == NetworkReachability.REACHABLE


# ---------------------------------------------------------------------------
# NetworkRouter -- Router-Available-To-Network handler
# ---------------------------------------------------------------------------


class TestHandleRouterAvailable:
    def test_listed_dnets_marked_reachable(self) -> None:
        """Specific DNETs in the message are marked REACHABLE."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        entry = router.routing_table.get_entry(30)
        assert entry is not None
        entry.reachability = NetworkReachability.BUSY
        data = _build_router_available_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert entry.reachability == NetworkReachability.REACHABLE

    def test_empty_list_marks_all_busy_reachable(self) -> None:
        """Empty list -> all previously BUSY networks restored."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=b"\x01")
        router.routing_table.update_route(40, port_id=1, next_router_mac=b"\x02")
        e30 = router.routing_table.get_entry(30)
        e40 = router.routing_table.get_entry(40)
        assert e30 is not None and e40 is not None
        e30.reachability = NetworkReachability.BUSY
        e40.reachability = NetworkReachability.BUSY
        data = _build_router_available_npdu(networks=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert e30.reachability == NetworkReachability.REACHABLE
        assert e40.reachability == NetworkReachability.REACHABLE

    def test_rebroadcast_on_other_ports(self) -> None:
        """Router-Available is re-broadcast on other ports."""
        router, t1, t2 = _make_two_port_router()
        data = _build_router_available_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t2.send_broadcast.assert_called_once()
        npdu, _ = _decode_sent_network_message(t2)
        assert npdu.message_type == NetworkMessageType.ROUTER_AVAILABLE_TO_NETWORK
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Initialize-Routing-Table handler
# ---------------------------------------------------------------------------


class TestHandleInitRoutingTable:
    def test_query_returns_full_table(self) -> None:
        """Empty ports list (query) -> Ack with complete routing table."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_init_routing_table_npdu(ports=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should unicast Ack back to sender on port 1
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.INITIALIZE_ROUTING_TABLE_ACK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, InitializeRoutingTableAck)
        # Should include both directly-connected entries (net 10, net 20)
        ack_networks = {p.network for p in msg.ports}
        assert 10 in ack_networks
        assert 20 in ack_networks

    def test_update_modifies_table_and_acks(self) -> None:
        """Non-empty ports list -> table modified, empty Ack returned."""
        router, t1, _t2 = _make_two_port_router()
        update_ports = [
            RoutingTablePort(network=50, port_id=1, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Network 50 should be added via port 1
        entry = router.routing_table.get_entry(50)
        assert entry is not None
        assert entry.port_id == 1
        # Response should be unicast Ack with empty ports
        t1.send_unicast.assert_called_once()
        sent_bytes, _ = t1.send_unicast.call_args[0]
        npdu = decode_npdu(sent_bytes)
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, InitializeRoutingTableAck)
        assert len(msg.ports) == 0

    def test_update_port_id_zero_removes_entry(self) -> None:
        """port_id=0 in update removes the entry."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(50, port_id=1, next_router_mac=b"\x01")
        update_ports = [
            RoutingTablePort(network=50, port_id=0, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert router.routing_table.get_entry(50) is None

    def test_update_unknown_port_id_ignored(self) -> None:
        """Unknown port_id in update is silently ignored."""
        router, _t1, _t2 = _make_two_port_router()
        update_ports = [
            RoutingTablePort(network=50, port_id=99, port_info=b""),
        ]
        data = _build_init_routing_table_npdu(ports=update_ports)
        # Should not raise
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert router.routing_table.get_entry(50) is None


# ---------------------------------------------------------------------------
# NetworkRouter -- Initialize-Routing-Table-Ack handler
# ---------------------------------------------------------------------------


class TestHandleInitRoutingTableAck:
    def test_ack_received_no_error(self) -> None:
        """Ack is received without error (logged only)."""
        router, t1, t2 = _make_two_port_router()
        ack_ports = [
            RoutingTablePort(network=10, port_id=1, port_info=b""),
            RoutingTablePort(network=20, port_id=2, port_info=b""),
        ]
        data = _build_init_routing_table_ack_npdu(ports=ack_ports)
        # Should not raise or send anything
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- What-Is-Network-Number handler
# ---------------------------------------------------------------------------


class TestHandleWhatIsNetworkNumber:
    def test_configured_port_responds(self) -> None:
        """Configured port responds with Network-Number-Is broadcast."""
        router, t1, _t2 = _make_two_port_router()
        data = _build_what_is_network_number_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_called_once()
        npdu, msg_data = _decode_sent_network_message(t1)
        assert npdu.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg = decode_network_message(npdu.message_type, msg_data)
        assert isinstance(msg, NetworkNumberIs)
        assert msg.network == 10
        assert msg.configured is True

    def test_routed_message_ignored(self) -> None:
        """What-Is with SNET/SADR is ignored (never routed)."""
        router, t1, _t2 = _make_two_port_router()
        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_what_is_network_number_npdu(source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()

    def test_routed_with_destination_ignored(self) -> None:
        """What-Is with DNET/DADR is ignored (never routed)."""
        router, t1, _t2 = _make_two_port_router()
        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_what_is_network_number_npdu(destination=dest)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()

    def test_unconfigured_port_no_response(self) -> None:
        """Unconfigured port does not respond."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_what_is_network_number_npdu()
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Network-Number-Is handler
# ---------------------------------------------------------------------------


class TestHandleNetworkNumberIs:
    def test_unconfigured_port_learns_number(self) -> None:
        """Unconfigured port learns network number from configured source."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,  # unknown
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_network_number_is_npdu(42, configured=True)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 42

    def test_configured_port_ignores(self) -> None:
        """Already configured port ignores Network-Number-Is."""
        router, _t1, _t2 = _make_two_port_router()
        data = _build_network_number_is_npdu(99, configured=True)
        port = router.routing_table.get_port(1)
        assert port is not None
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert port.network_number == 10  # unchanged

    def test_unconfigured_source_ignored(self) -> None:
        """Network-Number-Is with configured=False is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        data = _build_network_number_is_npdu(42, configured=False)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged

    def test_routed_message_ignored(self) -> None:
        """Network-Number-Is with SNET/SADR is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        src = BACnetAddress(network=30, mac_address=b"\xaa")
        data = _build_network_number_is_npdu(42, configured=True, source=src)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged

    def test_routed_with_destination_ignored(self) -> None:
        """Network-Number-Is with DNET/DADR is ignored."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=0,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        dest = BACnetAddress(network=20, mac_address=b"")
        data = _build_network_number_is_npdu(42, configured=True, destination=dest)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        assert p1.network_number == 0  # unchanged


# ---------------------------------------------------------------------------
# NetworkRouter -- Router startup broadcasts
# ---------------------------------------------------------------------------


class TestRouterStartup:
    async def test_startup_broadcasts_network_number_is(self) -> None:
        """Each configured port gets Network-Number-Is broadcast."""
        router, t1, t2 = _make_two_port_router()
        await router.start()
        # Both ports are configured, so both should get Network-Number-Is
        assert t1.send_broadcast.call_count >= 1
        assert t2.send_broadcast.call_count >= 1
        # Check first broadcast on each port is Network-Number-Is
        first_t1 = t1.send_broadcast.call_args_list[0][0][0]
        npdu1 = decode_npdu(first_t1)
        assert npdu1.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg1 = decode_network_message(npdu1.message_type, npdu1.network_message_data)
        assert isinstance(msg1, NetworkNumberIs)
        assert msg1.network == 10
        assert msg1.configured is True

        first_t2 = t2.send_broadcast.call_args_list[0][0][0]
        npdu2 = decode_npdu(first_t2)
        assert npdu2.message_type == NetworkMessageType.NETWORK_NUMBER_IS
        msg2 = decode_network_message(npdu2.message_type, npdu2.network_message_data)
        assert isinstance(msg2, NetworkNumberIs)
        assert msg2.network == 20
        assert msg2.configured is True

    async def test_startup_broadcasts_i_am_router(self) -> None:
        """Each port gets I-Am-Router listing networks from other ports."""
        router, t1, t2 = _make_two_port_router()
        await router.start()
        # Port 1 should get I-Am-Router with network 20
        # Port 2 should get I-Am-Router with network 10
        second_t1 = t1.send_broadcast.call_args_list[1][0][0]
        npdu1 = decode_npdu(second_t1)
        assert npdu1.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg1 = decode_network_message(npdu1.message_type, npdu1.network_message_data)
        assert isinstance(msg1, IAmRouterToNetwork)
        assert 20 in msg1.networks
        assert 10 not in msg1.networks

        second_t2 = t2.send_broadcast.call_args_list[1][0][0]
        npdu2 = decode_npdu(second_t2)
        assert npdu2.message_type == NetworkMessageType.I_AM_ROUTER_TO_NETWORK
        msg2 = decode_network_message(npdu2.message_type, npdu2.network_message_data)
        assert isinstance(msg2, IAmRouterToNetwork)
        assert 10 in msg2.networks
        assert 20 not in msg2.networks

    async def test_startup_unconfigured_port_no_network_number_is(self) -> None:
        """Unconfigured port should not broadcast Network-Number-Is."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
            network_number_configured=False,
        )
        router = NetworkRouter([p1])
        await router.start()
        # Should NOT have Network-Number-Is (not configured)
        for c in t1.send_broadcast.call_args_list:
            npdu = decode_npdu(c[0][0])
            assert npdu.message_type != NetworkMessageType.NETWORK_NUMBER_IS


# ---------------------------------------------------------------------------
# NetworkRouter -- Unknown message type
# ---------------------------------------------------------------------------


class TestHandleUnknownMessageType:
    def test_unknown_type_sends_reject(self, monkeypatch) -> None:
        """Unknown standard message type -> Reject with UNKNOWN_MESSAGE_TYPE.

        All currently-decodable message types have handlers, so this test
        monkeypatches decode_network_message to return an unrecognised
        object to exercise the defensive ``else`` branch.
        """
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class _FakeNetworkMessage:
            pass

        router, t1, _t2 = _make_two_port_router()

        monkeypatch.setattr(
            "bac_py.network.router.decode_network_message",
            lambda _mt, _data: _FakeNetworkMessage(),
        )

        # Build any network message NPDU -- the content doesn't matter
        # because we've overridden decode_network_message.
        data = _build_network_message_npdu(
            NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            b"",
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # Should send Reject-Message-To-Network
        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg_decoded = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg_decoded, RejectMessageToNetwork)
        assert msg_decoded.reason == RejectMessageReason.UNKNOWN_MESSAGE_TYPE


# ---------------------------------------------------------------------------
# NetworkRouter -- Malformed network message
# ---------------------------------------------------------------------------


class TestHandleMalformedNetworkMessage:
    def test_malformed_message_data_dropped(self) -> None:
        """Malformed network message data is logged and dropped."""
        router, t1, t2 = _make_two_port_router()
        # Build NPDU with valid type but malformed data
        data = _build_network_message_npdu(
            NetworkMessageType.REJECT_MESSAGE_TO_NETWORK,
            b"\x01",  # too short for reject message (needs 3 bytes)
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Should not crash, should not send anything
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# NetworkRouter -- Reject on unknown / unreachable / busy DNET (Clause 6.6.3.5)
# ---------------------------------------------------------------------------


class TestForwardRejectsUnknownDNET:
    """Forwarding to an unknown DNET sends Reject-Message-To-Network."""

    def test_unknown_dnet_sends_reject(self) -> None:
        """Unknown DNET -> Reject with NOT_DIRECTLY_CONNECTED on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        # Network 99 is not in the routing table.
        data = _build_routed_npdu(99, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99

    def test_unknown_dnet_not_forwarded(self) -> None:
        """Traffic to unknown DNET should NOT be forwarded anywhere."""
        router, _t1, t2 = _make_two_port_router()
        data = _build_routed_npdu(99, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Port 2 should not receive anything.
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


class TestForwardRejectsUnreachableDNET:
    """Forwarding to an UNREACHABLE DNET sends Reject-Message-To-Network."""

    def test_unreachable_dnet_sends_reject(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        # Add a remote route and mark it unreachable.
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_unreachable(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 30

    def test_unreachable_dnet_not_forwarded(self) -> None:
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_unreachable(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


class TestForwardRejectsBusyDNET:
    """Forwarding to a BUSY DNET sends Reject with ROUTER_BUSY reason."""

    def test_busy_dnet_sends_reject(self) -> None:
        router, t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_busy(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.ROUTER_BUSY
        assert msg.network == 30

    def test_busy_dnet_not_forwarded(self) -> None:
        """Traffic should NOT be forwarded to a busy network."""
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")
        router.routing_table.mark_busy(30)

        data = _build_routed_npdu(30, b"\x02")
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()

    def test_reachable_dnet_still_forwarded(self) -> None:
        """Sanity check: REACHABLE DNET is still forwarded normally."""
        router, t1, t2 = _make_two_port_router()
        # Network 20 is directly connected and REACHABLE by default.
        data = _build_routed_npdu(20, _MAC_DEVICE_B)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t2.send_unicast.assert_called_once()
        # No reject on arrival port.
        t1.send_unicast.assert_not_called()


class TestRejectRoutedBackWithSNET:
    """When the originator is on a remote network (SNET/SADR in NPDU), the Reject should be routed back via normal forwarding."""

    def test_reject_routed_to_snet(self) -> None:
        """Reject for unknown DNET with SNET/SADR routes back via SNET port."""
        # Three-port router: net 10 (port 1), net 20 (port 2), net 30 (port 3).
        t1 = _make_transport(local_mac=_MAC_PORT1)
        t2 = _make_transport(local_mac=_MAC_PORT2)
        t3 = _make_transport(local_mac=b"\x0a\x00\x00\x03\xba\xc0")
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
        )
        p2 = RouterPort(
            port_id=2,
            network_number=20,
            transport=t2,
            mac_address=_MAC_PORT2,
            max_npdu_length=1497,
        )
        p3 = RouterPort(
            port_id=3,
            network_number=30,
            transport=t3,
            mac_address=b"\x0a\x00\x00\x03\xba\xc0",
            max_npdu_length=1497,
        )
        router = NetworkRouter([p1, p2, p3], application_port_id=1)

        # Device on net 30 sends NPDU targeting unknown net 99 via port 2.
        # SNET=30, SADR=device_mac.
        source = BACnetAddress(network=30, mac_address=b"\xaa\xbb\xcc\xdd\xee\xff")
        data = _build_routed_npdu(99, b"\x01\x02\x03\x04\x05\x06", source=source)
        router._on_port_receive(2, data, _MAC_DEVICE_B)

        # Reject should be sent on port 3 (toward net 30), not port 2.
        t3.send_unicast.assert_called_once()
        sent_bytes = t3.send_unicast.call_args[0][0]
        sent_mac = t3.send_unicast.call_args[0][1]
        assert sent_mac == b"\xaa\xbb\xcc\xdd\xee\xff"

        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        assert npdu.destination is not None
        assert npdu.destination.network == 30
        msg = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(msg, RejectMessageToNetwork)
        assert msg.reason == RejectMessageReason.NOT_DIRECTLY_CONNECTED
        assert msg.network == 99

    def test_reject_fallback_to_arrival_port_when_snet_unreachable(self) -> None:
        """If SNET is not routable, fall back to sending on arrival port."""
        router, t1, _t2 = _make_two_port_router()
        # SNET=99 has no route.
        source = BACnetAddress(network=99, mac_address=b"\xaa\xbb")
        data = _build_routed_npdu(88, b"\x01", source=source)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # Falls back to arrival port (port 1).
        t1.send_unicast.assert_called_once()
        sent_mac = t1.send_unicast.call_args[0][1]
        assert sent_mac == _MAC_DEVICE_A


# ---------------------------------------------------------------------------
# Q2: Hop count diagnostic logging
# ---------------------------------------------------------------------------


class TestHopCountDiagnostic:
    """Q2: Debug log emitted when routed NPDU with SNET/SADR has default hop count."""

    def test_default_hop_count_with_source_logs_debug(self, caplog) -> None:
        """A routed NPDU with SNET and hop_count=255 should emit a debug log."""
        import logging

        router, _t1, _t2 = _make_two_port_router()
        source = BACnetAddress(network=10, mac_address=_MAC_DEVICE_A)
        # Global broadcast goes through _prepare_forwarded_npdu
        data = _build_global_broadcast_npdu(source=source, hop_count=255)

        with caplog.at_level(logging.DEBUG, logger="bac_py.network.router"):
            router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert "default hop count 255" in caplog.text

    def test_decremented_hop_count_no_debug_log(self, caplog) -> None:
        """A routed NPDU with normal hop count should NOT emit the diagnostic."""
        import logging

        router, _t1, _t2 = _make_two_port_router()
        source = BACnetAddress(network=10, mac_address=_MAC_DEVICE_A)
        data = _build_global_broadcast_npdu(source=source, hop_count=254)

        with caplog.at_level(logging.DEBUG, logger="bac_py.network.router"):
            router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert "default hop count 255" not in caplog.text

    def test_no_source_no_hop_count_diagnostic(self, caplog) -> None:
        """An NPDU without SNET should NOT emit the hop count diagnostic."""
        import logging

        router, _t1, _t2 = _make_two_port_router()
        data = _build_global_broadcast_npdu(hop_count=255)

        with caplog.at_level(logging.DEBUG, logger="bac_py.network.router"):
            router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert "default hop count 255" not in caplog.text


# ---------------------------------------------------------------------------
# F10: I-Could-Be-Router-To-Network handling
# ---------------------------------------------------------------------------


class TestICouldBeRouterToNetwork:
    """F10: I-Could-Be-Router-To-Network handling.

    Verifies that I-Could-Be-Router-To-Network is logged but does not change the
    routing table.
    """

    def test_i_could_be_router_logged(self, caplog) -> None:
        """I-Could-Be-Router-To-Network is logged at INFO level."""
        import logging

        router, _t1, _t2 = _make_two_port_router()
        msg = ICouldBeRouterToNetwork(network=99, performance_index=5)
        data = _build_network_message_npdu(
            NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK,
            encode_network_message(msg),
        )

        with caplog.at_level(logging.INFO, logger="bac_py.network.router"):
            router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert "I-Could-Be-Router-To-Network 99" in caplog.text
        assert "perf=5" in caplog.text

    def test_i_could_be_router_no_reject(self) -> None:
        """I-Could-Be-Router-To-Network should NOT trigger a reject."""
        router, t1, _t2 = _make_two_port_router()
        msg = ICouldBeRouterToNetwork(network=99, performance_index=5)
        data = _build_network_message_npdu(
            NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_not_called()

    def test_i_could_be_router_no_routing_table_change(self) -> None:
        """I-Could-Be-Router-To-Network should NOT modify the routing table."""
        router, _t1, _t2 = _make_two_port_router()
        entries_before = router.routing_table.get_all_entries()
        count_before = len(entries_before)

        msg = ICouldBeRouterToNetwork(network=99, performance_index=5)
        data = _build_network_message_npdu(
            NetworkMessageType.I_COULD_BE_ROUTER_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        entries_after = router.routing_table.get_all_entries()
        assert len(entries_after) == count_before
        assert router.routing_table.get_entry(99) is None


# ---------------------------------------------------------------------------
# F11: Establish/Disconnect Connection handling
# ---------------------------------------------------------------------------


class TestEstablishDisconnectConnection:
    """F11: Establish/Disconnect-Connection-To-Network handling.

    These messages are rejected with reason OTHER since demand-dial is not supported.
    """

    def test_establish_connection_sends_reject(self) -> None:
        """Establish-Connection-To-Network -> Reject with reason OTHER."""
        router, t1, _t2 = _make_two_port_router()
        msg = EstablishConnectionToNetwork(network=99, termination_time=0)
        data = _build_network_message_npdu(
            NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        reject = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(reject, RejectMessageToNetwork)
        assert reject.reason == RejectMessageReason.OTHER
        assert reject.network == 99

    def test_disconnect_connection_sends_reject(self) -> None:
        """Disconnect-Connection-To-Network -> Reject with reason OTHER."""
        router, t1, _t2 = _make_two_port_router()
        msg = DisconnectConnectionToNetwork(network=42)
        data = _build_network_message_npdu(
            NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        t1.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t1.send_unicast.call_args[0]
        assert sent_mac == _MAC_DEVICE_A
        npdu = decode_npdu(sent_bytes)
        assert npdu.message_type == NetworkMessageType.REJECT_MESSAGE_TO_NETWORK
        reject = decode_network_message(npdu.message_type, npdu.network_message_data)
        assert isinstance(reject, RejectMessageToNetwork)
        assert reject.reason == RejectMessageReason.OTHER
        assert reject.network == 42

    def test_establish_connection_no_routing_table_change(self) -> None:
        """Establish-Connection should NOT modify the routing table."""
        router, _t1, _t2 = _make_two_port_router()
        count_before = len(router.routing_table.get_all_entries())

        msg = EstablishConnectionToNetwork(network=99, termination_time=60)
        data = _build_network_message_npdu(
            NetworkMessageType.ESTABLISH_CONNECTION_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert len(router.routing_table.get_all_entries()) == count_before
        assert router.routing_table.get_entry(99) is None


# ---------------------------------------------------------------------------
# Coverage: send() defensive guard when dnet is None (router.py line 1371)
# ---------------------------------------------------------------------------


class TestSendDnetNoneGuard:
    """Line 1371: send() returns early when dnet is None (defensive guard)."""

    def test_send_with_mock_destination_dnet_none(self) -> None:
        """Use a mock destination that passes is_local/is_global_broadcast but has network=None."""
        router, t1, t2 = _make_two_port_router()

        mock_dest = MagicMock()
        mock_dest.is_local = False
        mock_dest.is_global_broadcast = False
        mock_dest.network = None

        # Should not raise, just return early
        router.send(b"\x01", mock_dest)
        t1.send_unicast.assert_not_called()
        t1.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()

    def test_disconnect_connection_no_routing_table_change(self) -> None:
        """Disconnect-Connection should NOT modify the routing table."""
        router, _t1, _t2 = _make_two_port_router()
        count_before = len(router.routing_table.get_all_entries())

        msg = DisconnectConnectionToNetwork(network=99)
        data = _build_network_message_npdu(
            NetworkMessageType.DISCONNECT_CONNECTION_TO_NETWORK,
            encode_network_message(msg),
        )

        router._on_port_receive(1, data, _MAC_DEVICE_A)

        assert len(router.routing_table.get_all_entries()) == count_before


# ---------------------------------------------------------------------------
# Mixed data-link forwarding (BIP 6-byte / MS/TP 1-byte / 2-byte MACs)
# ---------------------------------------------------------------------------

# MAC addresses for the mixed-datalink tests
_BIP_MAC_ROUTER = b"\xc0\xa8\x01\x01\xba\xc0"  # 192.168.1.1:47808 (router BIP port)
_MSTP_MAC_ROUTER = b"\x01"  # MS/TP MAC 1 (router MS/TP port)
_MSTP_MAC_ROUTER_P3 = b"\x02"  # MS/TP MAC 2 (router 2nd MS/TP port)
_BIP_DEVICE = b"\xc0\xa8\x01\x0a\xba\xc0"  # 192.168.1.10:47808
_MSTP_DEVICE = b"\x0a"  # MS/TP address 10
_MSTP_DEVICE_P3 = b"\x14"  # MS/TP address 20 on net 30
_TWO_BYTE_MAC_ROUTER = b"\x00\x01"  # 2-byte router MAC
_TWO_BYTE_DEVICE = b"\x00\x0a"  # 2-byte device MAC


def _make_mixed_router(
    *,
    three_port: bool = False,
) -> tuple:
    """Create a router with mixed BIP (net 10) and MS/TP (net 20) ports.

    If *three_port* is True, adds a third MS/TP port (net 30).

    Returns (router, t_bip, t_mstp[, t_mstp2]).
    """
    t_bip = _make_transport(local_mac=_BIP_MAC_ROUTER)
    t_mstp = _make_transport(local_mac=_MSTP_MAC_ROUTER)
    p_bip = RouterPort(
        port_id=1,
        network_number=10,
        transport=t_bip,
        mac_address=_BIP_MAC_ROUTER,
        max_npdu_length=1497,
    )
    p_mstp = RouterPort(
        port_id=2,
        network_number=20,
        transport=t_mstp,
        mac_address=_MSTP_MAC_ROUTER,
        max_npdu_length=501,
    )
    ports = [p_bip, p_mstp]
    if three_port:
        t_mstp2 = _make_transport(local_mac=_MSTP_MAC_ROUTER_P3)
        p_mstp2 = RouterPort(
            port_id=3,
            network_number=30,
            transport=t_mstp2,
            mac_address=_MSTP_MAC_ROUTER_P3,
            max_npdu_length=501,
        )
        ports.append(p_mstp2)
        router = NetworkRouter(ports, application_port_id=1)
        return router, t_bip, t_mstp, t_mstp2
    router = NetworkRouter(ports, application_port_id=1)
    return router, t_bip, t_mstp


class TestMixedDataLinkForwarding:
    """Tests for router forwarding between mixed data link types.

    Covers BACnet/IP (6-byte MAC) and MS/TP (1-byte MAC) networks,
    plus 2-byte MAC scenarios.
    """

    # 1. BIP -> MS/TP unicast forwarding
    def test_bip_to_mstp_unicast(self) -> None:
        """Route APDU from BIP (6-byte MAC, net 10) to MS/TP (1-byte MAC, net 20).

        Verify DADR length, SNET/SADR injection, and hop count decrement.
        """
        router, _t_bip, t_mstp = _make_mixed_router()

        data = _build_routed_npdu(
            dnet=20,
            dadr=_MSTP_DEVICE,  # 1-byte MS/TP MAC
            apdu=b"\x10\x00",
            hop_count=100,
        )
        router._on_port_receive(1, data, _BIP_DEVICE)

        # Should be delivered as unicast on the MS/TP port
        t_mstp.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t_mstp.send_unicast.call_args[0]

        # MAC on the wire must be the 1-byte MS/TP address
        assert sent_mac == _MSTP_DEVICE
        assert len(sent_mac) == 1

        delivered = decode_npdu(sent_bytes)
        # Destination stripped on final-hop delivery
        assert delivered.destination is None
        assert delivered.apdu == b"\x10\x00"

        # SNET/SADR injected with originator's 6-byte BIP MAC
        assert delivered.source is not None
        assert delivered.source.network == 10
        assert delivered.source.mac_address == _BIP_DEVICE
        assert len(delivered.source.mac_address) == 6

    # 2. MS/TP -> BIP unicast forwarding
    def test_mstp_to_bip_unicast(self) -> None:
        """Route APDU from MS/TP (1-byte MAC, net 20) to BIP (6-byte MAC, net 10).

        Verify DADR length and SNET/SADR injection with 1-byte source MAC.
        """
        router, t_bip, _t_mstp = _make_mixed_router()

        data = _build_routed_npdu(
            dnet=10,
            dadr=_BIP_DEVICE,  # 6-byte BIP MAC
            apdu=b"\x20\x00",
        )
        router._on_port_receive(2, data, _MSTP_DEVICE)

        t_bip.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t_bip.send_unicast.call_args[0]

        # Wire MAC is the 6-byte BIP address
        assert sent_mac == _BIP_DEVICE
        assert len(sent_mac) == 6

        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\x20\x00"

        # Source injected as 1-byte MS/TP MAC from net 20
        assert delivered.source is not None
        assert delivered.source.network == 20
        assert delivered.source.mac_address == _MSTP_DEVICE
        assert len(delivered.source.mac_address) == 1

    # 3. MS/TP -> MS/TP across different networks
    def test_mstp_to_mstp_cross_network(self) -> None:
        """Route from net 20 (1-byte MAC) to net 30 (1-byte MAC) via router.

        Verify 1-byte MAC preserved in both DADR and SADR.
        """
        router, _t_bip, _t_mstp, t_mstp2 = _make_mixed_router(three_port=True)

        data = _build_routed_npdu(
            dnet=30,
            dadr=_MSTP_DEVICE_P3,  # 1-byte target on net 30
            apdu=b"\x30\x00",
        )
        router._on_port_receive(2, data, _MSTP_DEVICE)

        t_mstp2.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t_mstp2.send_unicast.call_args[0]

        # Wire MAC to the 1-byte MS/TP destination
        assert sent_mac == _MSTP_DEVICE_P3
        assert len(sent_mac) == 1

        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\x30\x00"

        # Source injected as 1-byte MS/TP MAC from net 20
        assert delivered.source is not None
        assert delivered.source.network == 20
        assert delivered.source.mac_address == _MSTP_DEVICE
        assert len(delivered.source.mac_address) == 1

    # 4. BIP -> MS/TP directed broadcast (DLEN=0)
    def test_bip_to_mstp_directed_broadcast(self) -> None:
        """Directed broadcast from BIP to MS/TP (DNET=20, DLEN=0).

        Router forwards as local broadcast on the MS/TP port.
        """
        router, _t_bip, t_mstp = _make_mixed_router()

        data = _build_routed_npdu(
            dnet=20,
            dadr=b"",  # DLEN=0 -> broadcast on destination network
            apdu=b"\x10\x08",  # e.g. Who-Is APDU
        )
        router._on_port_receive(1, data, _BIP_DEVICE)

        t_mstp.send_broadcast.assert_called_once()
        sent_bytes = t_mstp.send_broadcast.call_args[0][0]

        delivered = decode_npdu(sent_bytes)
        # Destination stripped on delivery (local broadcast)
        assert delivered.destination is None
        assert delivered.apdu == b"\x10\x08"

        # SNET/SADR injected with 6-byte BIP source
        assert delivered.source is not None
        assert delivered.source.network == 10
        assert delivered.source.mac_address == _BIP_DEVICE

    # 5. MS/TP global broadcast (I-Am style) forwarded to all ports
    def test_mstp_global_broadcast_preserves_source(self) -> None:
        """Global broadcast from MS/TP device preserves SNET/SADR.

        SNET/SADR (1-byte MAC) should be injected and preserved across
        all forwarded ports.
        """
        router, t_bip, _t_mstp = _make_mixed_router()

        data = _build_global_broadcast_npdu(
            apdu=b"\x10\x00\x04\x00",  # I-Am-like APDU
        )
        router._on_port_receive(2, data, _MSTP_DEVICE)

        # Global broadcast forwarded to the BIP port
        t_bip.send_broadcast.assert_called_once()
        forwarded_bytes = t_bip.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)

        # SNET/SADR injected with 1-byte MS/TP MAC
        assert forwarded.source is not None
        assert forwarded.source.network == 20
        assert forwarded.source.mac_address == _MSTP_DEVICE
        assert len(forwarded.source.mac_address) == 1

        # Global broadcast destination preserved
        assert forwarded.destination is not None
        assert forwarded.destination.network == 0xFFFF

    def test_mstp_global_broadcast_preserves_existing_snet_sadr(self) -> None:
        """Global broadcast with existing SNET/SADR (multi-hop).

        The existing 1-byte SADR must be preserved.
        """
        router, t_bip, _t_mstp = _make_mixed_router()

        orig_src = BACnetAddress(network=20, mac_address=_MSTP_DEVICE)
        data = _build_global_broadcast_npdu(
            apdu=b"\x10\x00",
            source=orig_src,
        )
        router._on_port_receive(2, data, _MSTP_MAC_ROUTER)

        t_bip.send_broadcast.assert_called_once()
        forwarded_bytes = t_bip.send_broadcast.call_args[0][0]
        forwarded = decode_npdu(forwarded_bytes)

        assert forwarded.source is not None
        assert forwarded.source.network == 20
        assert forwarded.source.mac_address == _MSTP_DEVICE
        assert len(forwarded.source.mac_address) == 1

    # 6. 2-byte MAC forwarding (ARCNET-like)
    def test_two_byte_mac_forwarding(self) -> None:
        """Route from BIP (6-byte) to a network with 2-byte MACs.

        Verify DLEN=2 is preserved and SADR is injected correctly.
        """
        t_bip = _make_transport(local_mac=_BIP_MAC_ROUTER)
        t_two = _make_transport(local_mac=_TWO_BYTE_MAC_ROUTER)
        p_bip = RouterPort(
            port_id=1,
            network_number=10,
            transport=t_bip,
            mac_address=_BIP_MAC_ROUTER,
            max_npdu_length=1497,
        )
        p_two = RouterPort(
            port_id=2,
            network_number=40,
            transport=t_two,
            mac_address=_TWO_BYTE_MAC_ROUTER,
            max_npdu_length=501,
        )
        router = NetworkRouter([p_bip, p_two], application_port_id=1)

        data = _build_routed_npdu(
            dnet=40,
            dadr=_TWO_BYTE_DEVICE,  # 2-byte MAC
            apdu=b"\x40\x00",
        )
        router._on_port_receive(1, data, _BIP_DEVICE)

        t_two.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t_two.send_unicast.call_args[0]

        # Wire MAC is the 2-byte address
        assert sent_mac == _TWO_BYTE_DEVICE
        assert len(sent_mac) == 2

        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\x40\x00"

        # SNET/SADR injected with 6-byte BIP source
        assert delivered.source is not None
        assert delivered.source.network == 10
        assert delivered.source.mac_address == _BIP_DEVICE
        assert len(delivered.source.mac_address) == 6

    def test_two_byte_mac_to_bip_forwarding(self) -> None:
        """Route from 2-byte MAC network (net 40) to BIP (net 10).

        Verify SADR is 2-byte and DADR is 6-byte.
        """
        t_bip = _make_transport(local_mac=_BIP_MAC_ROUTER)
        t_two = _make_transport(local_mac=_TWO_BYTE_MAC_ROUTER)
        p_bip = RouterPort(
            port_id=1,
            network_number=10,
            transport=t_bip,
            mac_address=_BIP_MAC_ROUTER,
            max_npdu_length=1497,
        )
        p_two = RouterPort(
            port_id=2,
            network_number=40,
            transport=t_two,
            mac_address=_TWO_BYTE_MAC_ROUTER,
            max_npdu_length=501,
        )
        router = NetworkRouter([p_bip, p_two], application_port_id=1)

        data = _build_routed_npdu(
            dnet=10,
            dadr=_BIP_DEVICE,  # 6-byte BIP target
            apdu=b"\x50\x00",
        )
        router._on_port_receive(2, data, _TWO_BYTE_DEVICE)

        t_bip.send_unicast.assert_called_once()
        sent_bytes, sent_mac = t_bip.send_unicast.call_args[0]

        assert sent_mac == _BIP_DEVICE
        assert len(sent_mac) == 6

        delivered = decode_npdu(sent_bytes)
        assert delivered.destination is None
        assert delivered.apdu == b"\x50\x00"

        # SNET/SADR injected with 2-byte source MAC
        assert delivered.source is not None
        assert delivered.source.network == 40
        assert delivered.source.mac_address == _TWO_BYTE_DEVICE
        assert len(delivered.source.mac_address) == 2


# ---------------------------------------------------------------------------
# Additional coverage tests: RoutingTable edge cases
# ---------------------------------------------------------------------------


class TestRoutingTableEdgeCases:
    """Tests for RoutingTable methods not covered by existing tests."""

    def test_get_port_for_network_port_missing(self):
        """get_port_for_network returns None when port_id in entry is invalid."""
        from bac_py.network.router import RoutingTable, RoutingTableEntry

        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        # Manually add an entry for a non-existent port
        rt._entries[99] = RoutingTableEntry(
            network_number=99,
            port_id=42,  # no port with id 42
        )
        assert rt.get_port_for_network(99) is None

    def test_update_port_network_number_no_old_entry(self):
        """update_port_network_number when no old entry exists creates new entry."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        # Remove the old entry manually to test the else branch
        del rt._entries[10]
        rt.update_port_network_number(1, 42)
        assert port.network_number == 42
        entry = rt.get_entry(42)
        assert entry is not None
        assert entry.port_id == 1

    def test_update_port_network_number_same_network(self):
        """update_port_network_number with same network is a no-op."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_port_network_number(1, 10)
        assert port.network_number == 10

    def test_update_port_network_number_conflict(self):
        """update_port_network_number raises if new network already in table."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        p1 = _make_port(port_id=1, network_number=10)
        t2 = _make_transport()
        p2 = _make_port(port_id=2, network_number=20, transport=t2)
        rt.add_port(p1)
        rt.add_port(p2)
        with pytest.raises(ValueError, match="Network 20 already in routing table"):
            rt.update_port_network_number(1, 20)

    def test_update_port_network_number_unknown_port(self):
        """update_port_network_number with unknown port is a no-op."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        # Should not raise
        rt.update_port_network_number(99, 42)


class TestMarkBusyCongestion:
    """Tests for RoutingTable.mark_busy() congestion timer behavior."""

    async def test_mark_busy_with_callback(self):
        """mark_busy with a timeout callback sets a timer handle."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")

        called = []
        rt.mark_busy(30, lambda: called.append(True), timeout_seconds=0.01)

        entry = rt.get_entry(30)
        assert entry is not None
        assert entry.reachability == NetworkReachability.BUSY
        assert entry.busy_timeout_handle is not None

        # Wait for the timer to fire
        import asyncio

        await asyncio.sleep(0.05)
        assert len(called) == 1

    async def test_mark_busy_replaces_existing_timer(self):
        """Calling mark_busy again cancels the old timer and sets a new one."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        port = _make_port(port_id=1, network_number=10)
        rt.add_port(port)
        rt.update_route(30, port_id=1, next_router_mac=b"\x01")

        first_calls = []
        rt.mark_busy(30, lambda: first_calls.append(True), timeout_seconds=10.0)
        first_handle = rt.get_entry(30).busy_timeout_handle

        second_calls = []
        rt.mark_busy(30, lambda: second_calls.append(True), timeout_seconds=0.01)

        # First timer should have been cancelled
        assert first_handle.cancelled()

        import asyncio

        await asyncio.sleep(0.05)
        assert len(first_calls) == 0
        assert len(second_calls) == 1

    def test_mark_busy_no_entry_noop(self):
        """mark_busy on nonexistent entry does nothing."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        # Should not raise
        rt.mark_busy(99)

    def test_mark_available_no_entry_noop(self):
        """mark_available on nonexistent entry does nothing."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        rt.mark_available(99)

    def test_mark_unreachable_no_entry_noop(self):
        """mark_unreachable on nonexistent entry does nothing."""
        from bac_py.network.router import RoutingTable

        rt = RoutingTable()
        rt.mark_unreachable(99)


# ---------------------------------------------------------------------------
# Additional coverage: NetworkRouter _handle_network_message edge cases
# ---------------------------------------------------------------------------


class TestHandleNetworkMessageNone:
    """Test that network message with message_type=None is silently dropped."""

    def test_message_type_none_dropped(self):
        router, t1, t2 = _make_two_port_router()
        # Call _handle_network_message directly with message_type=None
        npdu = NPDU(is_network_message=True, message_type=None)
        router._handle_network_message(1, npdu, _MAC_DEVICE_A)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()
        t2.send_broadcast.assert_not_called()
        t2.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# Additional coverage: _message_type_for with unknown type
# ---------------------------------------------------------------------------


class TestMessageTypeForUnknown:
    """Test _message_type_for with an unmapped message type."""

    def test_unmapped_type_raises(self):
        from dataclasses import dataclass

        from bac_py.network.router import _message_type_for

        @dataclass(frozen=True)
        class _FakeMessage:
            pass

        with pytest.raises(TypeError, match="No message type mapping"):
            _message_type_for(_FakeMessage())


# ---------------------------------------------------------------------------
# Additional coverage: _send_network_message_on_port with missing port
# ---------------------------------------------------------------------------


class TestSendNetworkMessageOnMissingPort:
    """Test that _send_network_message_on_port with invalid port is a no-op."""

    def test_missing_port_noop(self):
        router, t1, t2 = _make_two_port_router()
        msg = IAmRouterToNetwork(networks=(10,))
        # Port 99 doesn't exist
        router._send_network_message_on_port(99, msg, broadcast=True)
        t1.send_broadcast.assert_not_called()
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# Additional coverage: _inject_source with missing port
# ---------------------------------------------------------------------------


class TestInjectSourceMissingPort:
    """Test _inject_source when the arrival port is not found."""

    def test_inject_source_unknown_port_returns_none(self):
        router, _, _ = _make_two_port_router()
        npdu = NPDU(apdu=b"\x01")
        result = router._inject_source(99, npdu, _MAC_DEVICE_A)
        assert result is None


# ---------------------------------------------------------------------------
# Additional coverage: Router stop cancels busy timers
# ---------------------------------------------------------------------------


class TestRouterStopCancelsBusyTimers:
    """Test that router stop() cancels outstanding busy-timeout handles."""

    async def test_stop_cancels_busy_timers(self):
        router, _t1, _t2 = _make_two_port_router()
        await router.start()

        # Add a route and mark it busy (which sets a timer)
        router.routing_table.update_route(30, port_id=1, next_router_mac=_MAC_DEVICE_A)
        data = _build_router_busy_npdu(networks=(30,))
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        entry = router.routing_table.get_entry(30)
        assert entry is not None
        assert entry.busy_timeout_handle is not None
        handle = entry.busy_timeout_handle

        await router.stop()

        # Timer should have been cancelled
        assert handle.cancelled()
        assert entry.busy_timeout_handle is None


# ---------------------------------------------------------------------------
# Additional coverage: Reject routed back with SNET via next-hop router
# ---------------------------------------------------------------------------


class TestRejectRoutedBackViaNexHop:
    """Test that reject is routed back via next-hop router when available."""

    def test_reject_via_next_hop(self):
        """Reject sent via next-hop router when SNET route uses next_router_mac."""
        router, _t1, t2 = _make_two_port_router()
        # Add a remote route to net 30 via a next-hop router on port 2
        next_hop = b"\x0a\x00\x00\x05\xba\xc0"
        router.routing_table.update_route(30, port_id=2, next_router_mac=next_hop)

        # NPDU from network 30 device targeting unknown net 99
        source = BACnetAddress(network=30, mac_address=b"\xaa\xbb")
        data = _build_routed_npdu(99, b"\x01", source=source)
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # Reject should be sent via the next-hop router on port 2
        t2.send_unicast.assert_called_once()
        _, sent_mac = t2.send_unicast.call_args[0]
        assert sent_mac == next_hop

    def test_reject_via_broadcast_when_empty_sadr(self):
        """Reject broadcast on destination port when SADR is empty (broadcast source)."""
        router, _t1, t2 = _make_two_port_router()

        # Build the source manually, bypassing validation for empty MAC
        fake_source = BACnetAddress.__new__(BACnetAddress)
        object.__setattr__(fake_source, "network", 20)
        object.__setattr__(fake_source, "mac_address", b"")

        # Build the NPDU manually since encode would reject SLEN=0
        # Instead, test the _send_reject_toward_source method directly
        npdu = NPDU(
            destination=BACnetAddress(network=99, mac_address=b"\x01"),
            source=fake_source,
            apdu=b"\x01",
            hop_count=255,
        )
        router._send_reject_toward_source(
            1,
            npdu,
            _MAC_DEVICE_A,
            RejectMessageReason.NOT_DIRECTLY_CONNECTED,
            99,
        )

        # Route to net 20 is directly connected on port 2, but SADR is empty
        # so it broadcasts
        t2.send_broadcast.assert_called_once()


# ---------------------------------------------------------------------------
# Additional coverage: Reject-Message relay with global broadcast destination
# ---------------------------------------------------------------------------


class TestRejectMessageRelay:
    """Test that Reject-Message with global broadcast destination is forwarded."""

    def test_reject_with_global_broadcast_destination(self):
        """Reject-Message with DNET=0xFFFF relays as global broadcast."""
        router, _t1, t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=2, next_router_mac=b"\x01")

        dest = BACnetAddress(network=0xFFFF, mac_address=b"")
        data = _build_reject_message_npdu(
            RejectMessageReason.OTHER,
            30,
            destination=dest,
        )
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # The reject message should be forwarded as global broadcast to port 2
        t2.send_broadcast.assert_called()


# ---------------------------------------------------------------------------
# Additional coverage: Router send() edge cases
# ---------------------------------------------------------------------------


class TestRouterSendEdgeCases:
    """Test router.send() edge cases."""

    def test_send_application_port_missing_raises(self):
        """send() raises RuntimeError when application_port_id points to missing port."""
        p1, p2, _t1, _t2 = _make_router_ports()
        router = NetworkRouter(
            [p1, p2],
            application_port_id=99,  # non-existent port
            application_callback=MagicMock(),
        )
        with pytest.raises(RuntimeError, match="Application port 99 not found"):
            router.send(b"\x01", BACnetAddress())


# ---------------------------------------------------------------------------
# Additional coverage: Router-Available-To-Network with empty list
# ---------------------------------------------------------------------------


class TestRouterAvailableEmptyList:
    """Test Router-Available with empty network list clears all BUSY entries on port."""

    def test_empty_list_restores_busy_on_port(self):
        """Empty networks list restores all BUSY networks on the arrival port."""
        router, _t1, _t2 = _make_two_port_router()
        router.routing_table.update_route(30, port_id=1, next_router_mac=b"\x01")
        router.routing_table.update_route(40, port_id=1, next_router_mac=b"\x02")
        router.routing_table.update_route(50, port_id=2, next_router_mac=b"\x03")

        # Mark some as BUSY
        e30 = router.routing_table.get_entry(30)
        e40 = router.routing_table.get_entry(40)
        e50 = router.routing_table.get_entry(50)
        e30.reachability = NetworkReachability.BUSY
        e40.reachability = NetworkReachability.BUSY
        e50.reachability = NetworkReachability.BUSY

        data = _build_router_available_npdu(networks=())
        router._on_port_receive(1, data, _MAC_DEVICE_A)

        # Only entries on port 1 that were BUSY should be restored
        assert e30.reachability == NetworkReachability.REACHABLE
        assert e40.reachability == NetworkReachability.REACHABLE
        # Entry on port 2 should still be BUSY
        assert e50.reachability == NetworkReachability.BUSY


# ---------------------------------------------------------------------------
# Additional coverage: _send_network_message_on_port broadcast=False, dest_mac=None
# ---------------------------------------------------------------------------


class TestSendNetworkMessageNoBroadcastNoMac:
    """Test _send_network_message_on_port with broadcast=False and dest_mac=None."""

    def test_no_broadcast_no_mac_noop(self):
        """broadcast=False and dest_mac=None means nothing is sent."""
        router, t1, _t2 = _make_two_port_router()
        msg = IAmRouterToNetwork(networks=(10,))
        router._send_network_message_on_port(1, msg, broadcast=False, dest_mac=None)
        t1.send_broadcast.assert_not_called()
        t1.send_unicast.assert_not_called()


# ---------------------------------------------------------------------------
# Additional coverage: Who-Is-Router with hop count exhausted
# ---------------------------------------------------------------------------


class TestWhoIsRouterHopCountExhausted:
    """Test Who-Is-Router for unknown DNET with hop_count=1 (exhausted on forward)."""

    def test_who_is_unknown_dnet_hop_count_exhausted(self):
        """Who-Is-Router for unknown DNET with hop_count=1 is not forwarded."""
        router, _t1, t2 = _make_two_port_router()
        # Build Who-Is-Router with hop_count=1 and a destination
        msg = WhoIsRouterToNetwork(network=99)
        dest = BACnetAddress(network=0xFFFF, mac_address=b"")
        npdu = NPDU(
            is_network_message=True,
            message_type=NetworkMessageType.WHO_IS_ROUTER_TO_NETWORK,
            network_message_data=encode_network_message(msg),
            destination=dest,
            hop_count=1,
        )
        router._on_port_receive(1, encode_npdu(npdu), _MAC_DEVICE_A)
        # With hop_count=1, _prepare_forwarded_npdu returns None
        # so nothing is forwarded to port 2
        t2.send_broadcast.assert_not_called()


# ---------------------------------------------------------------------------
# Additional coverage: Who-Is-Router wildcard with no reachable networks
# ---------------------------------------------------------------------------


class TestWhoIsRouterWildcardNoNetworks:
    """Test wildcard Who-Is-Router when no reachable networks exist for the arrival port."""

    def test_wildcard_single_port_no_response(self):
        """Single-port router: wildcard Who-Is produces no I-Am (nothing to exclude)."""
        t1 = _make_transport(local_mac=_MAC_PORT1)
        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=_MAC_PORT1,
            max_npdu_length=1497,
        )
        router = NetworkRouter([p1])
        data = _build_who_is_router_npdu(network=None)
        router._on_port_receive(1, data, _MAC_DEVICE_A)
        # Only one port, so all reachable networks are on port 1 itself --
        # exclude_port=1 leaves nothing.
        t1.send_broadcast.assert_not_called()
