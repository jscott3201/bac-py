"""Tests for BACnet/IPv6 transport (bip6.py)."""

from unittest.mock import MagicMock

import pytest

from bac_py.network.address import BIP6Address
from bac_py.transport.bip6 import (
    MULTICAST_LINK_LOCAL,
    MULTICAST_SITE_LOCAL,
    BIP6Transport,
    VMACCache,
)
from bac_py.transport.bvll_ipv6 import decode_bvll6, encode_bvll6
from bac_py.types.enums import Bvlc6Function


class TestBIP6TransportDefaults:
    def test_default_interface(self):
        transport = BIP6Transport()
        assert transport._interface == "::"

    def test_default_port(self):
        transport = BIP6Transport()
        assert transport._port == 0xBAC0

    def test_default_port_is_47808(self):
        transport = BIP6Transport()
        assert transport._port == 47808

    def test_default_multicast_address(self):
        transport = BIP6Transport()
        assert transport._multicast_address == MULTICAST_LINK_LOCAL

    def test_custom_interface(self):
        transport = BIP6Transport(interface="::1")
        assert transport._interface == "::1"

    def test_custom_port(self):
        transport = BIP6Transport(port=12345)
        assert transport._port == 12345

    def test_custom_multicast(self):
        transport = BIP6Transport(multicast_address=MULTICAST_SITE_LOCAL)
        assert transport._multicast_address == MULTICAST_SITE_LOCAL

    def test_max_npdu_length(self):
        transport = BIP6Transport()
        assert transport.max_npdu_length == 1497

    def test_initial_state_no_transport(self):
        transport = BIP6Transport()
        assert transport._transport is None

    def test_initial_state_no_callback(self):
        transport = BIP6Transport()
        assert transport._receive_callback is None

    def test_explicit_vmac(self):
        transport = BIP6Transport(vmac=b"\x01\x02\x03")
        assert transport._explicit_vmac == b"\x01\x02\x03"


class TestBIP6TransportNotStarted:
    def test_send_unicast_raises(self):
        transport = BIP6Transport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            transport.send_unicast(b"\x01\x02", b"\x04\x05\x06")

    def test_send_broadcast_raises(self):
        transport = BIP6Transport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            transport.send_broadcast(b"\x01\x02")

    def test_local_address_raises(self):
        transport = BIP6Transport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            _ = transport.local_address

    def test_local_mac_raises(self):
        transport = BIP6Transport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            _ = transport.local_mac


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_stop_loopback(self):
        transport = BIP6Transport(interface="::1", port=0)
        await transport.start()
        try:
            assert transport._transport is not None
            assert len(transport.local_mac) == 3
            assert transport.local_address.port != 0
        finally:
            await transport.stop()
        assert transport._transport is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        transport = BIP6Transport(interface="::1", port=0)
        await transport.start()
        try:
            first_vmac = transport.local_mac
            await transport.start()  # Should not error
            assert transport.local_mac == first_vmac
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_explicit_vmac_used(self):
        vmac = b"\xaa\xbb\xcc"
        transport = BIP6Transport(interface="::1", port=0, vmac=vmac)
        await transport.start()
        try:
            assert transport.local_mac == vmac
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_invalid_vmac_length(self):
        transport = BIP6Transport(interface="::1", port=0, vmac=b"\x01\x02")
        with pytest.raises(ValueError, match="VMAC must be exactly 3 bytes"):
            await transport.start()


class TestVMACGeneration:
    @pytest.mark.asyncio
    async def test_vmac_is_three_bytes(self):
        transport = BIP6Transport(interface="::1", port=0)
        await transport.start()
        try:
            assert len(transport.local_mac) == 3
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_vmac_is_random(self):
        vmacs = set()
        for _ in range(5):
            transport = BIP6Transport(interface="::1", port=0)
            await transport.start()
            vmacs.add(transport.local_mac)
            await transport.stop()
        # With 3 random bytes, collision in 5 tries is astronomically unlikely
        assert len(vmacs) > 1


class TestVMACCache:
    def test_put_and_get(self):
        cache = VMACCache(ttl=300.0)
        addr = BIP6Address(host="::1", port=47808)
        vmac = b"\x01\x02\x03"
        cache.put(vmac, addr)
        assert cache.get(vmac) == addr

    def test_get_missing(self):
        cache = VMACCache(ttl=300.0)
        assert cache.get(b"\x01\x02\x03") is None

    def test_evict_stale(self):
        cache = VMACCache(ttl=0.0)  # Immediate expiry
        addr = BIP6Address(host="::1", port=47808)
        vmac = b"\x01\x02\x03"
        cache.put(vmac, addr)
        cache.evict_stale()
        assert cache.get(vmac) is None

    def test_get_stale_returns_none(self):
        cache = VMACCache(ttl=0.0)
        addr = BIP6Address(host="::1", port=47808)
        vmac = b"\x01\x02\x03"
        cache.put(vmac, addr)
        # TTL=0 means immediately stale
        assert cache.get(vmac) is None

    def test_update_refreshes(self):
        cache = VMACCache(ttl=300.0)
        addr1 = BIP6Address(host="::1", port=47808)
        addr2 = BIP6Address(host="::2", port=47808)
        vmac = b"\x01\x02\x03"
        cache.put(vmac, addr1)
        cache.put(vmac, addr2)
        assert cache.get(vmac) == addr2

    def test_all_entries(self):
        cache = VMACCache(ttl=300.0)
        addr = BIP6Address(host="::1", port=47808)
        cache.put(b"\x01\x02\x03", addr)
        cache.put(b"\x04\x05\x06", addr)
        entries = cache.all_entries()
        assert len(entries) == 2

    def test_evict_stale_only_removes_old(self):
        cache = VMACCache(ttl=10.0)
        addr = BIP6Address(host="::1", port=47808)
        cache.put(b"\x01\x02\x03", addr)
        cache.evict_stale()
        # TTL is 10s, entry was just added -- should still be present
        assert cache.get(b"\x01\x02\x03") == addr


class TestSendUnicast:
    @pytest.mark.asyncio
    async def test_unicast_with_cached_vmac(self):
        transport = BIP6Transport(interface="::1", port=0, vmac=b"\xaa\xbb\xcc")
        await transport.start()
        try:
            # Pre-populate cache
            dest_vmac = b"\x11\x22\x33"
            dest_addr = BIP6Address(host="::1", port=47809)
            transport._vmac_cache.put(dest_vmac, dest_addr)

            mock_transport = MagicMock()
            transport._transport = mock_transport

            transport.send_unicast(b"\x01\x00\x10", dest_vmac)

            mock_transport.sendto.assert_called_once()
            sent_data, sent_addr = mock_transport.sendto.call_args[0]
            assert sent_addr == ("::1", 47809)

            # Verify BVLL6 wrapping
            decoded = decode_bvll6(sent_data)
            assert decoded.function == Bvlc6Function.ORIGINAL_UNICAST_NPDU
            assert decoded.source_vmac == b"\xaa\xbb\xcc"
            assert decoded.dest_vmac == dest_vmac
            assert decoded.data == b"\x01\x00\x10"
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_unicast_queued_without_cache(self):
        transport = BIP6Transport(interface="::1", port=0, vmac=b"\xaa\xbb\xcc")
        await transport.start()
        try:
            mock_transport = MagicMock()
            transport._transport = mock_transport

            dest_vmac = b"\x11\x22\x33"
            transport.send_unicast(b"\x01\x00\x10", dest_vmac)

            # Should have queued the NPDU and sent address resolution
            assert dest_vmac in transport._pending_resolutions
            assert len(transport._pending_resolutions[dest_vmac]) == 1
            assert transport._pending_resolutions[dest_vmac][0].npdu == b"\x01\x00\x10"

            # Should have sent address resolution to multicast
            assert mock_transport.sendto.called
        finally:
            await transport.stop()


class TestSendBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_multicast(self):
        transport = BIP6Transport(interface="::1", port=0, vmac=b"\xaa\xbb\xcc")
        await transport.start()
        try:
            mock_transport = MagicMock()
            transport._transport = mock_transport

            transport.send_broadcast(b"\x01\x00\x10")

            mock_transport.sendto.assert_called_once()
            sent_data, sent_addr = mock_transport.sendto.call_args[0]
            assert sent_addr == (MULTICAST_LINK_LOCAL, transport._port)

            decoded = decode_bvll6(sent_data)
            assert decoded.function == Bvlc6Function.ORIGINAL_BROADCAST_NPDU
            assert decoded.source_vmac == b"\xaa\xbb\xcc"
            assert decoded.data == b"\x01\x00\x10"
        finally:
            await transport.stop()


class TestOnDatagramReceived:
    def _make_transport(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()
        return transport

    def test_original_unicast_delivered(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))

        src_vmac = b"\x11\x22\x33"
        payload = b"\x01\x00\x10"
        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_UNICAST_NPDU,
            payload,
            source_vmac=src_vmac,
            dest_vmac=b"\xaa\xbb\xcc",
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))
        assert len(received) == 1
        assert received[0] == (payload, src_vmac)

    def test_original_broadcast_delivered(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))

        src_vmac = b"\x11\x22\x33"
        payload = b"\x01\x00\x10\x08"
        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            payload,
            source_vmac=src_vmac,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))
        assert len(received) == 1
        assert received[0] == (payload, src_vmac)

    def test_forwarded_npdu_delivered(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))

        src_vmac = b"\x11\x22\x33"
        orig = BIP6Address(host="fe80::1", port=47808)
        payload = b"\x01\x00"
        bvll = encode_bvll6(
            Bvlc6Function.FORWARDED_NPDU,
            payload,
            source_vmac=src_vmac,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))
        assert len(received) == 1
        assert received[0] == (payload, src_vmac)

    def test_address_resolution_response(self):
        transport = self._make_transport()

        requester_vmac = b"\x11\x22\x33"
        target_vmac = b"\xaa\xbb\xcc"  # Our VMAC
        bvll = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=requester_vmac,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        # Should have sent an ACK
        transport._transport.sendto.assert_called_once()
        sent_data, _ = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.ADDRESS_RESOLUTION_ACK
        assert decoded.source_vmac == b"\xaa\xbb\xcc"
        assert decoded.dest_vmac == requester_vmac

    def test_address_resolution_ignored_for_other_vmac(self):
        transport = self._make_transport()

        requester_vmac = b"\x11\x22\x33"
        target_vmac = b"\xdd\xee\xff"  # Not our VMAC
        bvll = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=requester_vmac,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        # Should NOT send an ACK
        transport._transport.sendto.assert_not_called()

    def test_address_resolution_ack_updates_cache(self):
        transport = self._make_transport()

        remote_vmac = b"\x11\x22\x33"
        bvll = encode_bvll6(
            Bvlc6Function.ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=remote_vmac,
            dest_vmac=b"\xaa\xbb\xcc",
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        cached = transport._vmac_cache.get(remote_vmac)
        assert cached is not None
        assert cached.host == "::1"
        assert cached.port == 47809

    def test_virtual_address_resolution_response(self):
        transport = self._make_transport()

        requester_vmac = b"\x11\x22\x33"
        bvll = encode_bvll6(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION,
            b"",
            source_vmac=requester_vmac,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        transport._transport.sendto.assert_called_once()
        sent_data, _ = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK
        assert decoded.source_vmac == b"\xaa\xbb\xcc"
        assert decoded.dest_vmac == requester_vmac

    def test_malformed_data_dropped(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))

        transport._on_datagram_received(b"\xff\xff", ("::1", 47809, 0, 0))
        assert len(received) == 0

    def test_register_foreign_device_nak(self):
        transport = self._make_transport()

        bvll = encode_bvll6(Bvlc6Function.REGISTER_FOREIGN_DEVICE, b"\x00\x3c")
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        transport._transport.sendto.assert_called_once()
        sent_data, _ = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.BVLC_RESULT


class TestAddressResolution:
    def test_full_resolution_cycle(self):
        """Test NPDU queued → address resolution → ACK → flush."""
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()

        dest_vmac = b"\x11\x22\x33"

        # Send unicast to unknown VMAC -- should queue
        transport.send_unicast(b"\x01\x00\x10", dest_vmac)
        assert dest_vmac in transport._pending_resolutions

        # Simulate ACK received
        dest_addr = BIP6Address(host="::2", port=47808)
        transport._handle_address_resolution_ack(dest_vmac, dest_addr)

        # Pending should be flushed
        assert dest_vmac not in transport._pending_resolutions

        # Should have sent: address resolution + the flushed unicast
        assert transport._transport.sendto.call_count >= 2

    def test_cache_updated_on_broadcast_receive(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()

        src_vmac = b"\x11\x22\x33"
        bvll = encode_bvll6(
            Bvlc6Function.ORIGINAL_BROADCAST_NPDU,
            b"\x01\x00",
            source_vmac=src_vmac,
        )
        transport._on_datagram_received(bvll, ("::2", 47808, 0, 0))

        cached = transport._vmac_cache.get(src_vmac)
        assert cached is not None
        assert cached.host == "::2"


class TestOnReceiveCallback:
    @pytest.mark.asyncio
    async def test_on_receive_registers_callback(self):
        transport = BIP6Transport(interface="::1", port=0)
        callback = MagicMock()
        transport.on_receive(callback)
        assert transport._receive_callback is callback


class TestMulticastConstants:
    def test_link_local_constant(self):
        assert MULTICAST_LINK_LOCAL == "ff02::bac0"

    def test_site_local_constant(self):
        assert MULTICAST_SITE_LOCAL == "ff05::bac0"
