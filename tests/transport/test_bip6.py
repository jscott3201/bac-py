"""Tests for BACnet/IPv6 transport (bip6.py)."""

from unittest.mock import MagicMock, patch

import pytest

from bac_py.network.address import BIP6Address
from bac_py.transport.bip6 import (
    MULTICAST_LINK_LOCAL,
    MULTICAST_SITE_LOCAL,
    BIP6Transport,
    VMACCache,
    _UDP6Protocol,
)
from bac_py.transport.bvll_ipv6 import Bvll6Message, decode_bvll6, encode_bvll6
from bac_py.types.enums import Bvlc6Function, Bvlc6ResultCode


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

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        transport = BIP6Transport(interface="::1", port=0)
        # Should silently do nothing
        await transport.stop()
        assert transport._transport is None


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

    def test_forwarded_address_resolution_delivered(self):
        transport = self._make_transport()

        requester_vmac = b"\x11\x22\x33"
        target_vmac = b"\xaa\xbb\xcc"  # Our VMAC
        orig = BIP6Address(host="fe80::1", port=47808)
        bvll = encode_bvll6(
            Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
            target_vmac,
            source_vmac=requester_vmac,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        # Should have sent an ACK (target matches our VMAC)
        transport._transport.sendto.assert_called_once()
        sent_data, _ = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.ADDRESS_RESOLUTION_ACK

    def test_virtual_address_resolution_ack_updates_cache(self):
        transport = self._make_transport()

        remote_vmac = b"\x11\x22\x33"
        bvll = encode_bvll6(
            Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK,
            b"",
            source_vmac=remote_vmac,
            dest_vmac=b"\xaa\xbb\xcc",
        )
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        cached = transport._vmac_cache.get(remote_vmac)
        assert cached is not None
        assert cached.host == "::1"
        assert cached.port == 47809

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


# ------------------------------------------------------------------
# Coverage gap tests
# ------------------------------------------------------------------


class TestUDP6Protocol:
    """Tests for _UDP6Protocol error_received / connection_lost (lines 89, 92, 96, 99)."""

    def test_datagram_received_invokes_callback(self):
        cb = MagicMock()
        proto = _UDP6Protocol(cb)
        proto.datagram_received(b"\x01\x02", ("::1", 47808, 0, 0))
        cb.assert_called_once_with(b"\x01\x02", ("::1", 47808, 0, 0))

    def test_error_received_logs_warning(self, caplog):
        proto = _UDP6Protocol(MagicMock())
        exc = OSError("test error")
        with caplog.at_level("WARNING"):
            proto.error_received(exc)
        assert "UDP6 transport error" in caplog.text

    def test_connection_lost_with_exception_logs_warning(self, caplog):
        cb = MagicMock()
        proto = _UDP6Protocol(MagicMock(), connection_lost_callback=cb)
        exc = OSError("lost")
        with caplog.at_level("WARNING"):
            proto.connection_lost(exc)
        assert "UDP6 connection lost" in caplog.text
        cb.assert_called_once_with(exc)

    def test_connection_lost_none_logs_debug(self, caplog):
        cb = MagicMock()
        proto = _UDP6Protocol(MagicMock(), connection_lost_callback=cb)
        with caplog.at_level("DEBUG"):
            proto.connection_lost(None)
        assert "UDP6 connection closed" in caplog.text
        cb.assert_called_once_with(None)

    def test_connection_lost_no_callback(self, caplog):
        proto = _UDP6Protocol(MagicMock(), connection_lost_callback=None)
        with caplog.at_level("WARNING"):
            proto.connection_lost(OSError("x"))
        # Should not raise even with no callback
        assert "UDP6 connection lost" in caplog.text


class TestStartWildcardResolution:
    """Test that start() with '::' resolves host to '::1' (line 171)."""

    @pytest.mark.asyncio
    async def test_wildcard_resolves_to_loopback(self):
        transport = BIP6Transport(interface="::", port=0, vmac=b"\x01\x02\x03")

        mock_udp_transport = MagicMock()
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ("::", 47808, 0, 0)
        mock_udp_transport.get_extra_info.return_value = mock_sock
        # setsockopt for multicast join may fail
        mock_sock.setsockopt.side_effect = OSError("no multicast")

        mock_protocol = MagicMock()

        with patch("asyncio.get_running_loop") as mock_loop_fn:
            mock_loop = MagicMock()
            mock_loop_fn.return_value = mock_loop

            async def fake_create(*a, **kw):
                return (mock_udp_transport, mock_protocol)

            mock_loop.create_datagram_endpoint = fake_create

            await transport.start()

        assert transport._local_address is not None
        assert transport._local_address.host == "::1"
        await transport.stop()


class TestVmacCacheProperty:
    """Test the vmac_cache property (line 281)."""

    def test_vmac_cache_returns_cache_instance(self):
        transport = BIP6Transport()
        cache = transport.vmac_cache
        assert isinstance(cache, VMACCache)
        # Should be same instance on repeated access
        assert transport.vmac_cache is cache


class TestAddressResolutionTransportNone:
    """Guards when transport is None (lines 290, 320, 346, 365)."""

    def _make_transport_no_udp(self):
        """Transport object with VMAC set but _transport is None."""
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        # Explicitly leave _transport as None
        return transport

    def test_send_address_resolution_no_transport(self):
        transport = self._make_transport_no_udp()
        # Should silently return without error
        transport._send_address_resolution(b"\x11\x22\x33")

    def test_send_address_resolution_ack_no_transport(self):
        transport = self._make_transport_no_udp()
        dest = BIP6Address(host="::1", port=47808)
        # Should silently return without error
        transport._send_address_resolution_ack(b"\x11\x22\x33", dest)

    def test_handle_virtual_address_resolution_no_transport(self):
        transport = self._make_transport_no_udp()
        sender = BIP6Address(host="::1", port=47808)
        # Should cache the VMAC but not send (transport is None)
        transport._handle_virtual_address_resolution(b"\x11\x22\x33", sender)
        # Cache should still be updated
        assert transport._vmac_cache.get(b"\x11\x22\x33") is not None

    def test_flush_pending_no_transport(self):
        transport = self._make_transport_no_udp()
        from bac_py.transport.bip6 import _PendingResolution

        vmac = b"\x11\x22\x33"
        transport._pending_resolutions[vmac] = [_PendingResolution(npdu=b"\x01\x02")]
        addr = BIP6Address(host="::1", port=47808)
        # Should remove pending but not crash
        transport._flush_pending(vmac, addr)
        assert vmac not in transport._pending_resolutions


class TestHandleAddressResolutionShortPayload:
    """Short payload < 3 bytes in _handle_address_resolution (line 306)."""

    def test_short_payload_ignored(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()

        sender = BIP6Address(host="::1", port=47809)
        # Payload is only 2 bytes, less than 3
        transport._handle_address_resolution(b"\x11\x22\x33", b"\xaa\xbb", sender)
        # Should not send any response
        transport._transport.sendto.assert_not_called()

    def test_empty_payload_ignored(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()

        sender = BIP6Address(host="::1", port=47809)
        transport._handle_address_resolution(b"\x11\x22\x33", b"", sender)
        transport._transport.sendto.assert_not_called()


class TestDatagramNoSourceVmac:
    """Messages without source_vmac should be silently ignored (lines 392-424)."""

    def _make_transport(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()
        return transport

    def _inject_message(self, transport, function, source_vmac=None, data=b""):
        """Inject a fake decoded message into _on_datagram_received via mock."""
        msg = Bvll6Message(
            function=function,
            data=data,
            source_vmac=source_vmac,
        )
        with patch("bac_py.transport.bip6.decode_bvll6", return_value=msg):
            transport._on_datagram_received(b"\x00" * 10, ("::1", 47809, 0, 0))

    def test_unicast_no_source_vmac_ignored(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))
        self._inject_message(transport, Bvlc6Function.ORIGINAL_UNICAST_NPDU)
        assert len(received) == 0

    def test_broadcast_no_source_vmac_ignored(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))
        self._inject_message(transport, Bvlc6Function.ORIGINAL_BROADCAST_NPDU)
        assert len(received) == 0

    def test_forwarded_npdu_no_source_vmac_ignored(self):
        transport = self._make_transport()
        received = []
        transport.on_receive(lambda npdu, mac: received.append((npdu, mac)))
        self._inject_message(transport, Bvlc6Function.FORWARDED_NPDU)
        assert len(received) == 0

    def test_address_resolution_no_source_vmac_ignored(self):
        transport = self._make_transport()
        self._inject_message(transport, Bvlc6Function.ADDRESS_RESOLUTION, data=b"\xaa\xbb\xcc")
        # No ACK should be sent
        transport._transport.sendto.assert_not_called()

    def test_forwarded_address_resolution_no_source_vmac_ignored(self):
        transport = self._make_transport()
        self._inject_message(
            transport,
            Bvlc6Function.FORWARDED_ADDRESS_RESOLUTION,
            data=b"\xaa\xbb\xcc",
        )
        transport._transport.sendto.assert_not_called()

    def test_address_resolution_ack_no_source_vmac_ignored(self):
        transport = self._make_transport()
        self._inject_message(transport, Bvlc6Function.ADDRESS_RESOLUTION_ACK)
        # Should not process - no cache update, no flush

    def test_virtual_address_resolution_no_source_vmac_ignored(self):
        transport = self._make_transport()
        self._inject_message(transport, Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION)
        transport._transport.sendto.assert_not_called()

    def test_virtual_address_resolution_ack_no_source_vmac_ignored(self):
        transport = self._make_transport()
        self._inject_message(transport, Bvlc6Function.VIRTUAL_ADDRESS_RESOLUTION_ACK)
        # Should not crash; no cache update


class TestNakResponses:
    """NAK responses for unsupported functions (lines 429-436, 443-448, 453)."""

    def _make_transport(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()
        return transport

    def test_delete_foreign_device_nak(self):
        transport = self._make_transport()
        bvll = encode_bvll6(Bvlc6Function.DELETE_FOREIGN_DEVICE_TABLE_ENTRY, b"\x00")
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        transport._transport.sendto.assert_called_once()
        sent_data, _sent_addr = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.BVLC_RESULT
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK

    def test_distribute_broadcast_nak(self):
        transport = self._make_transport()
        bvll = encode_bvll6(Bvlc6Function.DISTRIBUTE_BROADCAST_NPDU, b"\x01\x02")
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        transport._transport.sendto.assert_called_once()
        sent_data, _sent_addr = transport._transport.sendto.call_args[0]
        decoded = decode_bvll6(sent_data)
        assert decoded.function == Bvlc6Function.BVLC_RESULT
        result_code = int.from_bytes(decoded.data[:2], "big")
        assert result_code == Bvlc6ResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK

    def test_send_bvlc6_nak_no_transport(self):
        transport = self._make_transport()
        transport._transport = None
        dest = BIP6Address(host="::1", port=47809)
        # Should silently return
        transport._send_bvlc6_nak(Bvlc6ResultCode.REGISTER_FOREIGN_DEVICE_NAK, dest)


class TestUnknownBvlcFunction:
    """Unknown BVLC function falls through to the default case (line 436)."""

    def _make_transport(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()
        return transport

    def test_unknown_function_logged(self, caplog):
        transport = self._make_transport()
        # Use SECURE_BVLL (0x0B) which has no match case in the handler
        msg = Bvll6Message(
            function=Bvlc6Function.SECURE_BVLL,
            data=b"\x01\x02",
        )
        with (
            patch("bac_py.transport.bip6.decode_bvll6", return_value=msg),
            caplog.at_level("DEBUG"),
        ):
            transport._on_datagram_received(b"\x00" * 10, ("::1", 47809, 0, 0))
        assert "Ignoring BVLC6 function" in caplog.text


class TestResolvePendingBvlc:
    """Test _resolve_pending_bvlc method (lines 443-448)."""

    def _make_transport(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._local_address = BIP6Address(host="::1", port=47808)
        transport._transport = MagicMock()
        return transport

    def test_resolve_pending_with_matching_future(self):
        import asyncio

        transport = self._make_transport()
        source = BIP6Address(host="::1", port=47809)
        key = (Bvlc6Function.BVLC_RESULT, source)
        future = asyncio.Future()
        transport._pending_bvlc[key] = future

        result = transport._resolve_pending_bvlc(Bvlc6Function.BVLC_RESULT, b"\x00\x00", source)
        assert result is True
        assert future.done()
        assert future.result() == b"\x00\x00"

    def test_resolve_pending_no_matching_future(self):
        transport = self._make_transport()
        source = BIP6Address(host="::1", port=47809)
        result = transport._resolve_pending_bvlc(Bvlc6Function.BVLC_RESULT, b"\x00\x00", source)
        assert result is False

    def test_resolve_pending_future_already_done(self):
        import asyncio

        transport = self._make_transport()
        source = BIP6Address(host="::1", port=47809)
        key = (Bvlc6Function.BVLC_RESULT, source)
        future = asyncio.Future()
        future.set_result(b"already")
        transport._pending_bvlc[key] = future

        result = transport._resolve_pending_bvlc(Bvlc6Function.BVLC_RESULT, b"\x00\x00", source)
        assert result is False

    def test_bvlc_result_datagram_resolves_pending(self):
        """End-to-end: BVLC_RESULT datagram triggers _resolve_pending_bvlc."""
        import asyncio

        transport = self._make_transport()
        source = BIP6Address(host="::1", port=47809)
        key = (Bvlc6Function.BVLC_RESULT, source)
        future = asyncio.Future()
        transport._pending_bvlc[key] = future

        bvll = encode_bvll6(Bvlc6Function.BVLC_RESULT, b"\x00\x00")
        transport._on_datagram_received(bvll, ("::1", 47809, 0, 0))

        assert future.done()


class TestOnConnectionLost:
    """Test _on_connection_lost clears transport and protocol."""

    def test_on_connection_lost_clears_state(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._transport = MagicMock()
        transport._protocol = MagicMock()

        transport._on_connection_lost(None)

        assert transport._transport is None
        assert transport._protocol is None

    def test_on_connection_lost_with_exception(self):
        transport = BIP6Transport(vmac=b"\xaa\xbb\xcc")
        transport._vmac = b"\xaa\xbb\xcc"
        transport._transport = MagicMock()
        transport._protocol = MagicMock()

        transport._on_connection_lost(OSError("connection reset"))

        assert transport._transport is None
        assert transport._protocol is None
