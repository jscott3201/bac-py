"""Integration tests for NetworkRouter with BBMD co-existence (Phase 8)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bac_py.network.address import BACnetAddress, BIPAddress
from bac_py.network.npdu import NPDU, decode_npdu, encode_npdu
from bac_py.network.router import NetworkRouter, RouterPort
from bac_py.transport.bbmd import BBMDManager, BDTEntry
from bac_py.transport.bip import BIPTransport
from bac_py.transport.bvll import decode_bvll, encode_bvll
from bac_py.types.enums import BvlcFunction

# --- Constants ---

ALL_ONES_MASK = b"\xff\xff\xff\xff"


def _make_mock_transport(*, local_mac: bytes = b"\x7f\x00\x00\x01\xba\xc0") -> MagicMock:
    """Create a mock TransportPort."""
    transport = MagicMock()
    transport.local_mac = local_mac
    transport.max_npdu_length = 1497
    transport.start = AsyncMock()
    transport.stop = AsyncMock()
    return transport


class TestBroadcastFromBBMDPeerForwardedAcrossNetworks:
    """When a BBMD peer sends a Forwarded-NPDU to a router port, the
    router should forward the NPDU to other networks.
    """

    def test_forwarded_npdu_from_peer_routed_to_other_port(self):
        # Port 1: network 10, receives Forwarded-NPDU from BBMD peer
        t1 = _make_mock_transport(local_mac=b"\xc0\xa8\x01\x01\xba\xc0")
        # Port 2: network 20
        t2 = _make_mock_transport(local_mac=b"\x0a\x00\x00\x01\xba\xc0")

        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=t1.local_mac,
            max_npdu_length=1497,
        )
        p2 = RouterPort(
            port_id=2,
            network_number=20,
            transport=t2,
            mac_address=t2.local_mac,
            max_npdu_length=1497,
        )

        app_cb = MagicMock()
        router = NetworkRouter([p1, p2], application_port_id=1, application_callback=app_cb)

        # Build a global-broadcast NPDU (Who-Is)
        apdu = b"\x10\x08\x00"
        dest = BACnetAddress(network=0xFFFF, mac_address=b"")
        npdu = NPDU(destination=dest, apdu=apdu, hop_count=255)
        npdu_bytes = encode_npdu(npdu)

        # Originating device on network 10, remote subnet (via BBMD)
        orig_device_mac = BIPAddress(host="192.168.2.100", port=47808).encode()

        # Router receives this NPDU on port 1
        router._on_port_receive(1, npdu_bytes, orig_device_mac)

        # Should forward to port 2 as broadcast
        t2.send_broadcast.assert_called_once()
        forwarded_bytes = t2.send_broadcast.call_args[0][0]
        forwarded_npdu = decode_npdu(forwarded_bytes)
        assert forwarded_npdu.apdu == apdu
        # SNET/SADR should be injected for port 1
        assert forwarded_npdu.source is not None
        assert forwarded_npdu.source.network == 10
        assert forwarded_npdu.source.mac_address == orig_device_mac

    def test_remote_broadcast_from_peer_forwarded_to_specific_network(self):
        """Remote broadcast to network 20 via BBMD peer on port 1."""
        t1 = _make_mock_transport(local_mac=b"\xc0\xa8\x01\x01\xba\xc0")
        t2 = _make_mock_transport(local_mac=b"\x0a\x00\x00\x01\xba\xc0")

        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,
            mac_address=t1.local_mac,
            max_npdu_length=1497,
        )
        p2 = RouterPort(
            port_id=2,
            network_number=20,
            transport=t2,
            mac_address=t2.local_mac,
            max_npdu_length=1497,
        )

        router = NetworkRouter([p1, p2], application_port_id=1)

        # Build a remote-broadcast NPDU targeting network 20
        apdu = b"\x10\x08\x00"
        dest = BACnetAddress(network=20, mac_address=b"")
        npdu = NPDU(destination=dest, apdu=apdu, hop_count=255)
        npdu_bytes = encode_npdu(npdu)

        orig_device_mac = BIPAddress(host="192.168.2.50", port=47808).encode()
        router._on_port_receive(1, npdu_bytes, orig_device_mac)

        # Should forward to port 2 as broadcast (DNET stripped)
        t2.send_broadcast.assert_called_once()


class TestForeignDeviceRegistrationThroughRouterBBMD:
    """Foreign device registration through a BBMD attached to a router port."""

    @pytest.mark.asyncio
    async def test_fd_register_via_attached_bbmd(self):
        """A foreign device can register with the BBMD on a router port."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            bbmd = await transport.attach_bbmd()

            fd_addr = BIPAddress(host="10.0.0.50", port=47808)

            # Simulate incoming Register-Foreign-Device
            ttl_bytes = (60).to_bytes(2, "big")
            bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, ttl_bytes)
            transport._on_datagram_received(bvll, (fd_addr.host, fd_addr.port))

            assert fd_addr in bbmd.fdt
            assert bbmd.fdt[fd_addr].ttl == 60
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_fd_distribute_broadcast_reaches_callback(self):
        """Distribute-Broadcast from a registered FD is delivered via callback."""
        transport, mock_udp = _make_bip_transport_with_mock()
        received: list[tuple[bytes, BIPAddress]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )

            fd_addr = BIPAddress(host="10.0.0.50", port=47808)
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                fd_addr,
            )

            npdu = b"\x01\x00\x10\x08\x00"
            bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, npdu)
            transport._on_datagram_received(bvll, (fd_addr.host, fd_addr.port))

            assert len(received) == 1
            assert received[0][0] == npdu
            assert received[0][1] == fd_addr
        finally:
            await transport.stop()


class TestRouterBroadcastOnBBMDPortForwardsToPeers:
    """When a router broadcasts on a BBMD-enabled port, the broadcast
    should also be forwarded to BBMD peers.
    """

    def test_router_broadcast_forwarded_to_bbmd_peers(self):
        """Router's send_broadcast on a BBMD port sends to BDT peers."""
        local_addr = BIPAddress(host="192.168.1.1", port=47808)
        peer_addr = BIPAddress(host="192.168.2.1", port=47808)

        transport = BIPTransport(interface="127.0.0.1", port=47808)
        transport._local_address = local_addr
        transport._port = 47808
        mock_udp = MagicMock()
        transport._transport = mock_udp

        # Directly set up BBMD (bypass async attach for this unit test)
        transport._bbmd = BBMDManager(
            local_address=local_addr,
            send_callback=lambda d, a: mock_udp.sendto(d, (a.host, a.port)),
            local_broadcast_callback=None,
        )
        transport._bbmd.set_bdt(
            [
                BDTEntry(address=local_addr, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=peer_addr, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        npdu = b"\x01\x00\x10\x08\x00"
        transport.send_broadcast(npdu)

        calls = mock_udp.sendto.call_args_list

        # Local broadcast
        local_calls = [c for c in calls if c[0][1][0] == "255.255.255.255"]
        assert len(local_calls) == 1

        # Forwarded-NPDU to peer
        peer_calls = [c for c in calls if c[0][1] == (peer_addr.host, peer_addr.port)]
        assert len(peer_calls) == 1
        msg = decode_bvll(peer_calls[0][0][0])
        assert msg.function == BvlcFunction.FORWARDED_NPDU
        assert msg.originating_address == local_addr


class TestGlobalBroadcastAcrossRouterWithBBMD:
    """Global broadcast from one network should be forwarded on the BBMD
    port and also reach BBMD peers.
    """

    def test_global_broadcast_forwarded_and_distributed(self):
        local_addr = BIPAddress(host="192.168.1.1", port=47808)
        peer_addr = BIPAddress(host="192.168.2.1", port=47808)

        # Port 1: BIPTransport with BBMD enabled
        t1 = BIPTransport(interface="127.0.0.1", port=47808)
        t1._local_address = local_addr
        t1._port = 47808
        mock_udp1 = MagicMock()
        t1._transport = mock_udp1
        t1._bbmd = BBMDManager(
            local_address=local_addr,
            send_callback=lambda d, a: mock_udp1.sendto(d, (a.host, a.port)),
            local_broadcast_callback=None,
        )
        t1._bbmd.set_bdt(
            [
                BDTEntry(address=local_addr, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=peer_addr, broadcast_mask=ALL_ONES_MASK),
            ]
        )

        # Port 2: plain mock transport
        t2 = _make_mock_transport(local_mac=b"\x0a\x00\x00\x01\xba\xc0")

        p1 = RouterPort(
            port_id=1,
            network_number=10,
            transport=t1,  # type: ignore[arg-type]
            mac_address=local_addr.encode(),
            max_npdu_length=1497,
        )
        p2 = RouterPort(
            port_id=2,
            network_number=20,
            transport=t2,
            mac_address=t2.local_mac,
            max_npdu_length=1497,
        )

        router = NetworkRouter([p1, p2], application_port_id=1)

        # Device on net 20 sends global broadcast
        device_mac = b"\xc0\xa8\x02\x0a\xba\xc0"
        apdu = b"\x10\x08\x00"
        npdu = NPDU(
            destination=BACnetAddress(network=0xFFFF, mac_address=b""),
            apdu=apdu,
            hop_count=255,
        )
        router._on_port_receive(2, encode_npdu(npdu), device_mac)

        # Should be broadcast on port 1 (local subnet)
        local_calls = [
            c for c in mock_udp1.sendto.call_args_list if c[0][1][0] == "255.255.255.255"
        ]
        assert len(local_calls) == 1

        # Port 1 broadcast should also trigger BBMD forwarding to peer
        peer_calls = [
            c
            for c in mock_udp1.sendto.call_args_list
            if c[0][1] == (peer_addr.host, peer_addr.port)
        ]
        assert len(peer_calls) == 1
        msg = decode_bvll(peer_calls[0][0][0])
        assert msg.function == BvlcFunction.FORWARDED_NPDU


# --- Helper ---


def _make_bip_transport_with_mock(
    *, host: str = "192.168.1.1", port: int = 47808
) -> tuple[BIPTransport, MagicMock]:
    """Create a BIPTransport with a mock UDP transport for testing."""
    transport = BIPTransport(interface=host, port=port)
    transport._local_address = BIPAddress(host=host, port=port)
    transport._port = port
    mock_udp = MagicMock()
    transport._transport = mock_udp
    return transport, mock_udp
