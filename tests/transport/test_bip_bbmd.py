"""Tests for BIPTransport + BBMDManager integration (Phase 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bbmd import BBMDManager, BDTEntry
from bac_py.transport.bip import BIPTransport
from bac_py.transport.bvll import decode_bvll, encode_bvll
from bac_py.types.enums import BvlcFunction

# --- Constants ---

ALL_ONES_MASK = b"\xff\xff\xff\xff"
PEER_ADDR = BIPAddress(host="192.168.2.1", port=47808)
CLIENT_ADDR = BIPAddress(host="192.168.1.100", port=47808)
FD_ADDR = BIPAddress(host="10.0.0.50", port=47808)
FD_ADDR2 = BIPAddress(host="10.0.0.51", port=47808)

# --- Helpers ---


def _make_transport_with_mock_udp(
    *, host: str = "192.168.1.1", port: int = 47808
) -> tuple[BIPTransport, MagicMock]:
    """Create a BIPTransport with a mock UDP transport."""
    transport = BIPTransport(interface=host, port=port)
    transport._local_address = BIPAddress(host=host, port=port)
    transport._port = port
    mock_udp = MagicMock()
    transport._transport = mock_udp
    return transport, mock_udp


def _find_sendto_calls_to(mock_udp: MagicMock, dest: BIPAddress) -> list[bytes]:
    """Find sendto call data targeting a specific address."""
    return [
        call[0][0]
        for call in mock_udp.sendto.call_args_list
        if call[0][1] == (dest.host, dest.port)
    ]


# --- Test classes ---


class TestAttachBBMD:
    """Test BBMD attachment lifecycle."""

    @pytest.mark.asyncio
    async def test_attach_creates_bbmd(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            bbmd = await transport.attach_bbmd()
            assert bbmd is not None
            assert transport.bbmd is bbmd
            assert isinstance(bbmd, BBMDManager)
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_with_bdt_entries(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            entries = [
                BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
            ]
            bbmd = await transport.attach_bbmd(entries)
            assert len(bbmd.bdt) == 2
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_twice_raises(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            await transport.attach_bbmd()
            with pytest.raises(RuntimeError, match="BBMD already attached"):
                await transport.attach_bbmd()
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_before_start_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.attach_bbmd()

    def test_bbmd_property_none_when_not_attached(self):
        transport = BIPTransport()
        assert transport.bbmd is None


class TestIncomingBroadcastWithBBMD:
    """Test incoming Original-Broadcast-NPDU with BBMD attached."""

    @pytest.mark.asyncio
    async def test_original_broadcast_forwarded_to_peers(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            local_addr = transport.local_address
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=local_addr, broadcast_mask=ALL_ONES_MASK),
                    BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10\x08\x00"
            bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            # BBMD should have forwarded to peer as Forwarded-NPDU
            peer_data = _find_sendto_calls_to(mock_udp, PEER_ADDR)
            assert len(peer_data) == 1
            msg = decode_bvll(peer_data[0])
            assert msg.function == BvlcFunction.FORWARDED_NPDU
            assert msg.originating_address == CLIENT_ADDR
            assert msg.data == npdu
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_original_broadcast_also_delivered_locally(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )

            npdu = b"\x01\x00\x10\x08\x00"
            bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            assert len(received) == 1
            assert received[0][0] == npdu
            assert received[0][1] == CLIENT_ADDR.encode()
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_original_broadcast_forwarded_to_fds(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                FD_ADDR,
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            fd_data = _find_sendto_calls_to(mock_udp, FD_ADDR)
            assert len(fd_data) == 1
        finally:
            await transport.stop()


class TestIncomingForwardedNPDU:
    """Test incoming Forwarded-NPDU with BBMD attached."""

    @pytest.mark.asyncio
    async def test_forwarded_npdu_delivered_once(self):
        """Forwarded-NPDU should be delivered exactly once (via BBMD callback)."""
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )

            npdu = b"\x01\x00\x10"
            orig_addr = BIPAddress(host="10.0.0.99", port=47808)
            bvll = encode_bvll(BvlcFunction.FORWARDED_NPDU, npdu, originating_address=orig_addr)
            transport._on_datagram_received(bvll, (PEER_ADDR.host, PEER_ADDR.port))

            # Delivered exactly once with the originating address
            assert len(received) == 1
            assert received[0][0] == npdu
            assert received[0][1] == orig_addr.encode()
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_forwarded_npdu_forwarded_to_fds(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                FD_ADDR,
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            orig_addr = BIPAddress(host="10.0.0.99", port=47808)
            bvll = encode_bvll(BvlcFunction.FORWARDED_NPDU, npdu, originating_address=orig_addr)
            transport._on_datagram_received(bvll, (PEER_ADDR.host, PEER_ADDR.port))

            fd_data = _find_sendto_calls_to(mock_udp, FD_ADDR)
            assert len(fd_data) == 1
            msg = decode_bvll(fd_data[0])
            assert msg.function == BvlcFunction.FORWARDED_NPDU
        finally:
            await transport.stop()


class TestIncomingDistributeBroadcast:
    """Test Distribute-Broadcast-To-Network delivery."""

    @pytest.mark.asyncio
    async def test_distribute_broadcast_delivered_locally(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                    BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            # Register the foreign device that will send
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                FD_ADDR,
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, npdu)
            transport._on_datagram_received(bvll, (FD_ADDR.host, FD_ADDR.port))

            # NPDU should be delivered to the local callback
            assert len(received) == 1
            assert received[0][0] == npdu
            assert received[0][1] == FD_ADDR.encode()
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_distribute_broadcast_forwarded_to_peer(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                    BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                FD_ADDR,
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, npdu)
            transport._on_datagram_received(bvll, (FD_ADDR.host, FD_ADDR.port))

            peer_data = _find_sendto_calls_to(mock_udp, PEER_ADDR)
            assert len(peer_data) == 1
            msg = decode_bvll(peer_data[0])
            assert msg.function == BvlcFunction.FORWARDED_NPDU
            assert msg.originating_address == FD_ADDR
        finally:
            await transport.stop()


class TestOutgoingBroadcastWithBBMD:
    """Test that send_broadcast also forwards via BBMD."""

    @pytest.mark.asyncio
    async def test_send_broadcast_forwards_to_peers(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                    BDTEntry(address=PEER_ADDR, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            transport.send_broadcast(npdu)

            # Local broadcast
            broadcast_calls = [
                c for c in mock_udp.sendto.call_args_list if c[0][1][0] == "255.255.255.255"
            ]
            assert len(broadcast_calls) == 1

            # Forwarded-NPDU to peer
            peer_data = _find_sendto_calls_to(mock_udp, PEER_ADDR)
            assert len(peer_data) == 1
            msg = decode_bvll(peer_data[0])
            assert msg.function == BvlcFunction.FORWARDED_NPDU
            assert msg.originating_address == transport.local_address
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_send_broadcast_forwards_to_fds(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        try:
            bbmd = await transport.attach_bbmd(
                [
                    BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK),
                ]
            )
            bbmd.handle_bvlc(
                BvlcFunction.REGISTER_FOREIGN_DEVICE,
                (60).to_bytes(2, "big"),
                FD_ADDR,
            )
            mock_udp.reset_mock()

            npdu = b"\x01\x00\x10"
            transport.send_broadcast(npdu)

            fd_data = _find_sendto_calls_to(mock_udp, FD_ADDR)
            assert len(fd_data) == 1
        finally:
            await transport.stop()

    def test_send_broadcast_without_bbmd_no_forwarding(self):
        """Without BBMD, send_broadcast only sends local broadcast."""
        transport, mock_udp = _make_transport_with_mock_udp()

        npdu = b"\x01\x00\x10"
        transport.send_broadcast(npdu)

        # Only one call (local broadcast)
        assert mock_udp.sendto.call_count == 1
        assert mock_udp.sendto.call_args[0][1][0] == "255.255.255.255"


class TestBVLCManagementExclusivelyHandled:
    """Test that BVLC management messages are handled exclusively by BBMD."""

    @pytest.mark.asyncio
    async def test_register_fd_not_delivered_to_callback(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd()

            bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, (60).to_bytes(2, "big"))
            transport._on_datagram_received(bvll, (FD_ADDR.host, FD_ADDR.port))

            assert len(received) == 0
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_read_bdt_not_delivered_to_callback(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd()

            bvll = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE, b"")
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            assert len(received) == 0
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_write_bdt_not_delivered_to_callback(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd()

            entry = BDTEntry(address=transport.local_address, broadcast_mask=ALL_ONES_MASK)
            bvll = encode_bvll(BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE, entry.encode())
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            assert len(received) == 0
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_read_fdt_not_delivered_to_callback(self):
        transport, mock_udp = _make_transport_with_mock_udp()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        try:
            await transport.attach_bbmd()

            bvll = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE, b"")
            transport._on_datagram_received(bvll, (CLIENT_ADDR.host, CLIENT_ADDR.port))

            assert len(received) == 0
        finally:
            await transport.stop()


class TestStartStopLifecycle:
    """Test start/stop lifecycle with BBMD attached."""

    @pytest.mark.asyncio
    async def test_stop_stops_bbmd(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        bbmd = await transport.attach_bbmd()
        assert bbmd._cleanup_task is not None
        await transport.stop()
        assert transport.bbmd is None

    @pytest.mark.asyncio
    async def test_stop_without_bbmd(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        await transport.stop()  # Should not raise


class TestNoBBMDFallback:
    """Test that transport works normally without BBMD."""

    def test_original_unicast_works_without_bbmd(self):
        transport = BIPTransport()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        transport._transport = MagicMock()

        npdu = b"\x01\x00\x10"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        transport._on_datagram_received(bvll, ("192.168.1.10", 47808))

        assert len(received) == 1
        assert received[0][0] == npdu

    def test_original_broadcast_works_without_bbmd(self):
        transport = BIPTransport()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        transport._transport = MagicMock()

        npdu = b"\x01\x00\x10"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        transport._on_datagram_received(bvll, ("192.168.1.10", 47808))

        assert len(received) == 1
        assert received[0][0] == npdu

    def test_forwarded_npdu_works_without_bbmd(self):
        transport = BIPTransport()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))
        transport._transport = MagicMock()

        npdu = b"\x01\x00\x10"
        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll = encode_bvll(BvlcFunction.FORWARDED_NPDU, npdu, originating_address=orig)
        transport._on_datagram_received(bvll, ("192.168.1.1", 47808))

        assert len(received) == 1
        assert received[0][0] == npdu
        assert received[0][1] == orig.encode()
