"""Tests for BACnet/IP transport (bip.py)."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bip import (
    BIPTransport,
    _is_confirmed_request_npdu,
    _resolve_local_ip,
    _UDPProtocol,
)
from bac_py.transport.bvll import encode_bvll
from bac_py.types.enums import BvlcFunction, BvlcResultCode


class TestBIPTransportDefaults:
    """Test default construction parameters."""

    def test_default_interface(self):
        transport = BIPTransport()
        assert transport._interface == "0.0.0.0"

    def test_default_port(self):
        transport = BIPTransport()
        assert transport._port == 0xBAC0

    def test_default_port_is_47808(self):
        transport = BIPTransport()
        assert transport._port == 47808

    def test_custom_interface(self):
        transport = BIPTransport(interface="192.168.1.100")
        assert transport._interface == "192.168.1.100"

    def test_custom_port(self):
        transport = BIPTransport(port=12345)
        assert transport._port == 12345

    def test_max_npdu_length(self):
        transport = BIPTransport()
        assert transport.max_npdu_length == 1497

    def test_initial_state_no_transport(self):
        transport = BIPTransport()
        assert transport._transport is None

    def test_initial_state_no_protocol(self):
        transport = BIPTransport()
        assert transport._protocol is None

    def test_initial_state_no_callback(self):
        transport = BIPTransport()
        assert transport._receive_callback is None

    def test_initial_state_no_local_address(self):
        transport = BIPTransport()
        assert transport._local_address is None


class TestBIPTransportNotStarted:
    """Test that operations raise RuntimeError when transport is not started."""

    def test_send_unicast_raises(self):
        transport = BIPTransport()
        dest = BIPAddress(host="10.0.0.1", port=47808)
        with pytest.raises(RuntimeError, match="Transport not started"):
            transport.send_unicast(b"\x01\x02", dest.encode())

    def test_send_broadcast_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            transport.send_broadcast(b"\x01\x02")

    def test_local_address_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            _ = transport.local_address


class TestUDPProtocol:
    """Test _UDPProtocol datagram handling."""

    def test_datagram_received_calls_callback(self):
        callback = MagicMock()
        protocol = _UDPProtocol(callback)
        data = b"\x81\x0a\x00\x05\x01"
        addr = ("192.168.1.10", 47808)

        protocol.datagram_received(data, addr)

        callback.assert_called_once_with(data, addr)

    def test_datagram_received_passes_exact_data(self):
        received = []

        def _collect(data, addr):
            received.append((data, addr))

        protocol = _UDPProtocol(_collect)

        protocol.datagram_received(b"\xff\xfe", ("10.0.0.1", 9999))

        assert len(received) == 1
        assert received[0][0] == b"\xff\xfe"
        assert received[0][1] == ("10.0.0.1", 9999)

    def test_error_received_logs_warning(self, caplog):
        callback = MagicMock()
        protocol = _UDPProtocol(callback)
        exc = OSError("Connection refused")

        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            protocol.error_received(exc)

        assert "UDP transport error" in caplog.text
        assert "Connection refused" in caplog.text

    def test_error_received_does_not_call_callback(self):
        callback = MagicMock()
        protocol = _UDPProtocol(callback)

        protocol.error_received(OSError("test"))

        callback.assert_not_called()


class TestOnDatagramReceived:
    """Test BIPTransport._on_datagram_received with various BVLC functions."""

    def _make_transport_with_callback(self):
        """Create a BIPTransport with a mock receive callback registered."""
        transport = BIPTransport()
        callback = MagicMock()
        transport.on_receive(callback)
        return transport, callback

    def test_original_unicast_npdu_delivers_data(self):
        transport, callback = self._make_transport_with_callback()
        npdu = b"\x01\x00\x10\x02\x00"
        bvll_data = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_called_once()
        delivered_npdu, delivered_source = callback.call_args[0]
        assert delivered_npdu == npdu
        assert delivered_source == BIPAddress(host="192.168.1.50", port=47808).encode()

    def test_original_broadcast_npdu_delivers_data(self):
        transport, callback = self._make_transport_with_callback()
        npdu = b"\x01\x00\x10\x08\x00"
        bvll_data = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_called_once()
        delivered_npdu, delivered_source = callback.call_args[0]
        assert delivered_npdu == npdu
        assert delivered_source == BIPAddress(host="192.168.1.50", port=47808).encode()

    def test_forwarded_npdu_delivers_with_originating_address(self):
        transport, callback = self._make_transport_with_callback()
        npdu = b"\x01\x00\x10"
        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll_data = encode_bvll(BvlcFunction.FORWARDED_NPDU, npdu, originating_address=orig)
        # The addr here is the BBMD that forwarded the packet, not the origin.
        addr = ("192.168.1.1", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_called_once()
        delivered_npdu, delivered_source = callback.call_args[0]
        assert delivered_npdu == npdu
        # Should use the originating address, not the forwarder.
        assert delivered_source == BIPAddress(host="10.0.0.99", port=47808).encode()

    def test_bvlc_result_not_delivered_as_npdu(self):
        transport, callback = self._make_transport_with_callback()
        result_data = b"\x00\x00"
        bvll_data = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        addr = ("192.168.1.1", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_not_called()

    def test_bvlc_result_handled_logs_warning(self, caplog):
        transport, _callback = self._make_transport_with_callback()
        result_data = b"\x00\x30"  # register-foreign-device NAK
        bvll_data = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        addr = ("192.168.1.1", 47808)

        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            transport._on_datagram_received(bvll_data, addr)

        assert "BVLC-Result NAK: code 48" in caplog.text

    def test_unknown_bvlc_function_ignored(self):
        transport, callback = self._make_transport_with_callback()
        # Use SECURE_BVLL -- not handled by the normal receive path.
        payload = b"\x00" * 10
        bvll_data = encode_bvll(BvlcFunction.SECURE_BVLL, payload)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_not_called()

    def test_unknown_bvlc_function_logs_debug(self, caplog):
        transport, _callback = self._make_transport_with_callback()
        payload = b"\x00" * 10
        bvll_data = encode_bvll(BvlcFunction.SECURE_BVLL, payload)
        addr = ("192.168.1.50", 47808)

        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._on_datagram_received(bvll_data, addr)

        assert "Ignoring BVLC function" in caplog.text

    def test_malformed_bvll_dropped_silently(self):
        transport, callback = self._make_transport_with_callback()
        garbage = b"\xff\xff\xff"
        addr = ("10.0.0.1", 47808)

        # Should not raise even though the data is malformed.
        transport._on_datagram_received(garbage, addr)

        callback.assert_not_called()

    def test_malformed_bvll_logs_warning(self, caplog):
        transport, _callback = self._make_transport_with_callback()
        garbage = b"\xff\xff\xff"
        addr = ("10.0.0.1", 47808)

        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            transport._on_datagram_received(garbage, addr)

        assert "Dropped malformed BVLL" in caplog.text
        assert "10.0.0.1" in caplog.text

    def test_empty_data_dropped_silently(self):
        transport, callback = self._make_transport_with_callback()
        addr = ("10.0.0.1", 47808)

        transport._on_datagram_received(b"", addr)

        callback.assert_not_called()

    def test_no_callback_registered_does_not_raise(self):
        transport = BIPTransport()
        # No callback registered via on_receive.
        npdu = b"\x01\x00\x10"
        bvll_data = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        addr = ("192.168.1.50", 47808)

        # Should not raise even without a callback.
        transport._on_datagram_received(bvll_data, addr)

    def test_no_callback_broadcast_does_not_raise(self):
        transport = BIPTransport()
        npdu = b"\x01\x00\x10"
        bvll_data = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

    def test_no_callback_forwarded_does_not_raise(self):
        transport = BIPTransport()
        npdu = b"\x01\x00\x10"
        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll_data = encode_bvll(BvlcFunction.FORWARDED_NPDU, npdu, originating_address=orig)
        addr = ("192.168.1.1", 47808)

        transport._on_datagram_received(bvll_data, addr)


class TestStartStop:
    """Test start/stop lifecycle with a real asyncio UDP socket."""

    async def test_start_idempotent(self):
        """Calling start() twice should not raise or rebind."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            first_port = transport.local_address.port
            # Second start() should be a no-op
            await transport.start()
            assert transport.local_address.port == first_port
        finally:
            await transport.stop()

    async def test_start_sets_local_address(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            addr = transport.local_address
            assert addr.host == "127.0.0.1"
            assert addr.port > 0
        finally:
            await transport.stop()

    async def test_start_sets_internal_transport(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            assert transport._transport is not None
            assert transport._protocol is not None
        finally:
            await transport.stop()

    async def test_stop_clears_transport(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        await transport.stop()
        assert transport._transport is None
        assert transport._protocol is None

    async def test_stop_when_not_started(self):
        transport = BIPTransport()
        # Should not raise.
        await transport.stop()

    async def test_local_address_port_is_ephemeral(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            assert transport.local_address.port != 0
        finally:
            await transport.stop()

    async def test_max_npdu_length_after_start(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            assert transport.max_npdu_length == 1497
        finally:
            await transport.stop()


class TestSendUnicast:
    """Test send_unicast wraps NPDU in correct BVLL and sends."""

    def test_send_unicast_calls_sendto(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="192.168.1.100", port=47808)

        transport.send_unicast(npdu, dest.encode())

        mock_udp.sendto.assert_called_once()

    def test_send_unicast_destination_address(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="192.168.1.100", port=47808)

        transport.send_unicast(npdu, dest.encode())

        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("192.168.1.100", 47808)

    def test_send_unicast_bvll_encoding(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest.encode())

        sent_bvll = mock_udp.sendto.call_args[0][0]
        expected_bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        assert sent_bvll == expected_bvll

    def test_send_unicast_bvll_header_type_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x02\x03"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest.encode())

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[0] == 0x81  # BVLC type for BACnet/IP

    def test_send_unicast_bvll_header_function_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x02\x03"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest.encode())

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[1] == BvlcFunction.ORIGINAL_UNICAST_NPDU

    def test_send_unicast_bvll_contains_npdu(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\xde\xad\xbe\xef"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest.encode())

        sent_bvll = mock_udp.sendto.call_args[0][0]
        # NPDU follows the 4-byte BVLL header.
        assert sent_bvll[4:] == npdu


class TestSendBroadcast:
    """Test send_broadcast wraps NPDU and sends to 255.255.255.255."""

    def test_send_broadcast_calls_sendto(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x08\x00"

        transport.send_broadcast(npdu)

        mock_udp.sendto.assert_called_once()

    def test_send_broadcast_destination_address(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        transport.send_broadcast(b"\x01")

        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("255.255.255.255", 0xBAC0)

    def test_send_broadcast_custom_port(self):
        transport = BIPTransport(port=12345)
        mock_udp = MagicMock()
        transport._transport = mock_udp

        transport.send_broadcast(b"\x01")

        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("255.255.255.255", 12345)

    def test_send_broadcast_bvll_encoding(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x08\x00"

        transport.send_broadcast(npdu)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        expected_bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        assert sent_bvll == expected_bvll

    def test_send_broadcast_bvll_header_type_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        transport.send_broadcast(b"\x01\x02\x03")

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[0] == 0x81

    def test_send_broadcast_bvll_header_function_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        transport.send_broadcast(b"\x01\x02\x03")

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[1] == BvlcFunction.ORIGINAL_BROADCAST_NPDU

    def test_send_broadcast_bvll_contains_npdu(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\xca\xfe\xba\xbe"

        transport.send_broadcast(npdu)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[4:] == npdu


class TestOnReceiveCallback:
    """Test the on_receive callback registration."""

    def test_on_receive_registers_callback(self):
        transport = BIPTransport()
        callback = MagicMock()
        transport.on_receive(callback)
        assert transport._receive_callback is callback

    def test_on_receive_replaces_callback(self):
        transport = BIPTransport()
        first = MagicMock()
        second = MagicMock()
        transport.on_receive(first)
        transport.on_receive(second)
        assert transport._receive_callback is second


class TestLocalMac:
    """Test the local_mac property."""

    def test_local_mac_raises_when_not_started(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            _ = transport.local_mac

    async def test_local_mac_returns_6_bytes(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            mac = transport.local_mac
            assert isinstance(mac, bytes)
            assert len(mac) == 6
        finally:
            await transport.stop()

    async def test_local_mac_matches_local_address_encode(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            assert transport.local_mac == transport.local_address.encode()
        finally:
            await transport.stop()

    async def test_local_mac_ip_bytes(self):
        transport = BIPTransport(interface="127.0.0.1", port=0)
        try:
            await transport.start()
            mac = transport.local_mac
            # First 4 bytes are the IP address 127.0.0.1
            assert mac[0] == 127
            assert mac[1] == 0
            assert mac[2] == 0
            assert mac[3] == 1
        finally:
            await transport.stop()


class TestSendUnicastWithMac:
    """Test send_unicast accepting raw MAC bytes."""

    def test_send_unicast_mac_bytes(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        # 192.168.1.100 = 0xC0.0xA8.0x01.0x64, port 47808 = 0xBAC0
        mac = b"\xc0\xa8\x01\x64\xba\xc0"

        transport.send_unicast(npdu, mac)

        mock_udp.sendto.assert_called_once()
        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("192.168.1.100", 47808)

    def test_send_unicast_mac_bvll_encoding(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        mac = b"\x0a\x00\x00\x01\xba\xc0"

        transport.send_unicast(npdu, mac)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        expected_bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        assert sent_bvll == expected_bvll

    def test_send_unicast_mac_not_started_raises(self):
        transport = BIPTransport()
        mac = b"\xc0\xa8\x01\x64\xba\xc0"
        with pytest.raises(RuntimeError, match="Transport not started"):
            transport.send_unicast(b"\x01\x02", mac)

    def test_send_unicast_encoded_bip_address(self):
        """Encoded BIPAddress (bytes) works with send_unicast."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="192.168.1.100", port=47808)

        transport.send_unicast(npdu, dest.encode())

        mock_udp.sendto.assert_called_once()
        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("192.168.1.100", 47808)


class TestTransportPortProtocol:
    """Test that BIPTransport satisfies the TransportPort protocol."""

    def test_isinstance_check(self):
        from bac_py.transport.port import TransportPort

        transport = BIPTransport()
        assert isinstance(transport, TransportPort)

    def test_has_start_method(self):
        transport = BIPTransport()
        assert callable(transport.start)

    def test_has_stop_method(self):
        transport = BIPTransport()
        assert callable(transport.stop)

    def test_has_on_receive_method(self):
        transport = BIPTransport()
        assert callable(transport.on_receive)

    def test_has_send_unicast_method(self):
        transport = BIPTransport()
        assert callable(transport.send_unicast)

    def test_has_send_broadcast_method(self):
        transport = BIPTransport()
        assert callable(transport.send_broadcast)

    def test_has_local_mac_property(self):
        assert isinstance(BIPTransport.__dict__["local_mac"], property)

    def test_has_max_npdu_length_property(self):
        assert isinstance(BIPTransport.__dict__["max_npdu_length"], property)


class TestHandleBvlcResult:
    """Test _handle_bvlc_result edge cases."""

    def test_short_data_does_not_raise(self):
        transport = BIPTransport()
        source = BIPAddress(host="192.168.1.1", port=47808)
        # Less than 2 bytes -- should not raise or log.
        transport._handle_bvlc_result(b"\x00", source)

    def test_empty_data_does_not_raise(self):
        transport = BIPTransport()
        source = BIPAddress(host="192.168.1.1", port=47808)
        transport._handle_bvlc_result(b"", source)

    def test_valid_result_code_logs_debug(self, caplog):
        transport = BIPTransport()
        source = BIPAddress(host="192.168.1.1", port=47808)
        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._handle_bvlc_result(b"\x00\x00", source)
        assert "BVLC-Result: 0" in caplog.text

    def test_nonzero_result_code_logs_warning(self, caplog):
        transport = BIPTransport()
        source = BIPAddress(host="192.168.1.1", port=47808)
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            transport._handle_bvlc_result(b"\x00\x30", source)
        assert "BVLC-Result NAK: code 48" in caplog.text


class TestBvlcResultSenderValidation:
    """S3: BVLC-Result should only be routed to ForeignDeviceManager.

    When it comes from the expected BBMD address.
    """

    def test_result_from_correct_bbmd_updates_fd_state(self):
        """BVLC-Result from the BBMD we registered with is accepted."""
        from bac_py.transport.foreign_device import ForeignDeviceManager

        transport = BIPTransport()
        transport._transport = MagicMock()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)
        transport._foreign_device = ForeignDeviceManager(
            bbmd_address=bbmd_addr,
            ttl=60,
            send_callback=lambda d, a: None,
        )

        result_data = b"\x00\x00"  # SUCCESSFUL_COMPLETION
        bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        transport._on_datagram_received(bvll, (bbmd_addr.host, bbmd_addr.port))

        assert transport._foreign_device.is_registered is True

    def test_result_from_wrong_address_ignored_by_fd(self):
        """S3: BVLC-Result from a different address is NOT routed to FD."""
        from bac_py.transport.foreign_device import ForeignDeviceManager

        transport = BIPTransport()
        transport._transport = MagicMock()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)
        rogue_addr = BIPAddress(host="10.99.99.99", port=47808)
        transport._foreign_device = ForeignDeviceManager(
            bbmd_address=bbmd_addr,
            ttl=60,
            send_callback=lambda d, a: None,
        )

        result_data = b"\x00\x00"  # SUCCESSFUL_COMPLETION
        bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        transport._on_datagram_received(bvll, (rogue_addr.host, rogue_addr.port))

        # FD should NOT be marked as registered
        assert transport._foreign_device.is_registered is False

    def test_result_from_wrong_address_still_logged(self, caplog):
        """S3: BVLC-Result from wrong address is still logged."""
        from bac_py.transport.foreign_device import ForeignDeviceManager

        transport = BIPTransport()
        transport._transport = MagicMock()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)
        rogue_addr = BIPAddress(host="10.99.99.99", port=47808)
        transport._foreign_device = ForeignDeviceManager(
            bbmd_address=bbmd_addr,
            ttl=60,
            send_callback=lambda d, a: None,
        )

        result_data = b"\x00\x30"  # NAK code
        bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            transport._on_datagram_received(bvll, (rogue_addr.host, rogue_addr.port))

        # NAK is logged even though FD is not updated
        assert "BVLC-Result NAK" in caplog.text


class TestNonBBMDNakResponses:
    """F3: Non-BBMD devices should respond with NAK to BVLC management messages."""

    def _make_transport_with_mock(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        return transport, mock_udp

    def _find_bvlc_result_code(
        self, mock_udp: MagicMock, dest_addr: tuple[str, int]
    ) -> int | None:
        """Extract the BVLC-Result code from sendto calls to a specific destination."""
        from bac_py.transport.bvll import decode_bvll as _decode

        for call in mock_udp.sendto.call_args_list:
            data, addr = call[0]
            if addr == dest_addr:
                msg = _decode(data)
                if msg.function == BvlcFunction.BVLC_RESULT and len(msg.data) >= 2:
                    return int.from_bytes(msg.data[:2], "big")
        return None

    def test_register_fd_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        payload = (60).to_bytes(2, "big")
        bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, payload)
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.REGISTER_FOREIGN_DEVICE_NAK

    def test_write_bdt_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        bvll = encode_bvll(BvlcFunction.WRITE_BROADCAST_DISTRIBUTION_TABLE, b"\x00" * 10)
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK

    def test_read_bdt_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        bvll = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE, b"")
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.READ_BROADCAST_DISTRIBUTION_TABLE_NAK

    def test_read_fdt_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        bvll = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE, b"")
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.READ_FOREIGN_DEVICE_TABLE_NAK

    def test_delete_fdt_entry_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        bvll = encode_bvll(BvlcFunction.DELETE_FOREIGN_DEVICE_TABLE_ENTRY, b"\x00" * 6)
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK

    def test_distribute_broadcast_nak_without_bbmd(self):
        transport, mock_udp = self._make_transport_with_mock()
        bvll = encode_bvll(BvlcFunction.DISTRIBUTE_BROADCAST_TO_NETWORK, b"\x01\x00\x10")
        addr = ("10.0.0.50", 47808)

        transport._on_datagram_received(bvll, addr)

        code = self._find_bvlc_result_code(mock_udp, addr)
        assert code == BvlcResultCode.DISTRIBUTE_BROADCAST_TO_NETWORK_NAK

    def test_nak_not_delivered_to_callback(self):
        transport, _mock_udp = self._make_transport_with_mock()
        callback = MagicMock()
        transport.on_receive(callback)

        bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, (60).to_bytes(2, "big"))
        transport._on_datagram_received(bvll, ("10.0.0.50", 47808))

        callback.assert_not_called()

    def test_no_nak_when_transport_not_ready(self):
        """NAK is not sent when UDP transport is not available."""
        transport = BIPTransport()
        # No _transport set -- _send_bvlc_nak should silently return.
        bvll = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, (60).to_bytes(2, "big"))
        # Should not raise.
        transport._on_datagram_received(bvll, ("10.0.0.50", 47808))


class TestConfirmedRequestBroadcastRejection:
    """F7: Confirmed service requests received via broadcast should be dropped."""

    # NPDU with confirmed request: version=0x01, control=0x04 (expect reply),
    # APDU type byte 0x00 (Confirmed-Request, top nibble = 0)
    CONFIRMED_REQUEST_NPDU = b"\x01\x04\x00\x02\x01\x0c"

    # NPDU with unconfirmed request: version=0x01, control=0x00,
    # APDU type byte 0x10 (Unconfirmed-Request, top nibble = 1)
    UNCONFIRMED_REQUEST_NPDU = b"\x01\x00\x10\x08\x00"

    def test_confirmed_request_broadcast_dropped(self):
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, self.CONFIRMED_REQUEST_NPDU)
        transport._on_datagram_received(bvll, ("192.168.1.50", 47808))

        assert len(received) == 0

    def test_unconfirmed_request_broadcast_delivered(self):
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, self.UNCONFIRMED_REQUEST_NPDU)
        transport._on_datagram_received(bvll, ("192.168.1.50", 47808))

        assert len(received) == 1
        assert received[0][0] == self.UNCONFIRMED_REQUEST_NPDU

    def test_confirmed_request_unicast_not_dropped(self):
        """Confirmed requests via unicast should NOT be dropped."""
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, self.CONFIRMED_REQUEST_NPDU)
        transport._on_datagram_received(bvll, ("192.168.1.50", 47808))

        assert len(received) == 1
        assert received[0][0] == self.CONFIRMED_REQUEST_NPDU

    def test_confirmed_request_forwarded_npdu_dropped(self):
        """Confirmed request via Forwarded-NPDU (broadcast) should be dropped."""
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            self.CONFIRMED_REQUEST_NPDU,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("192.168.1.1", 47808))

        assert len(received) == 0

    def test_unconfirmed_request_forwarded_npdu_delivered(self):
        """Unconfirmed request via Forwarded-NPDU should be delivered."""
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            self.UNCONFIRMED_REQUEST_NPDU,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("192.168.1.1", 47808))

        assert len(received) == 1
        assert received[0][0] == self.UNCONFIRMED_REQUEST_NPDU

    def test_network_message_broadcast_not_dropped(self):
        """Network messages via broadcast should NOT be dropped (not confirmed requests)."""
        transport = BIPTransport()
        transport._transport = MagicMock()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        # NPDU with network message flag: version=0x01, control=0x80, msg_type=0x01
        network_msg_npdu = b"\x01\x80\x01\x00\x01"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, network_msg_npdu)
        transport._on_datagram_received(bvll, ("192.168.1.50", 47808))

        assert len(received) == 1


class TestIsConfirmedRequestNpdu:
    """Test the _is_confirmed_request_npdu helper function."""

    def test_confirmed_request(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        # Version=1, control=0x04, APDU type=0x00 (confirmed request)
        assert _is_confirmed_request_npdu(b"\x01\x04\x00\x02\x01") is True

    def test_unconfirmed_request(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        # Version=1, control=0x00, APDU type=0x10 (unconfirmed request)
        assert _is_confirmed_request_npdu(b"\x01\x00\x10\x08\x00") is False

    def test_network_message(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        # Version=1, control=0x80 (network message)
        assert _is_confirmed_request_npdu(b"\x01\x80\x01") is False

    def test_too_short(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        assert _is_confirmed_request_npdu(b"\x01\x00") is False
        assert _is_confirmed_request_npdu(b"\x01") is False
        assert _is_confirmed_request_npdu(b"") is False

    def test_with_source_address(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        # Version=1, control=0x08 (SNET present),
        # SNET=0x0001, SLEN=1, SADR=0x05,
        # APDU type=0x00 (confirmed request)
        npdu = b"\x01\x08\x00\x01\x01\x05\x00\x02"
        assert _is_confirmed_request_npdu(npdu) is True

    def test_with_destination_address(self):
        from bac_py.transport.bip import _is_confirmed_request_npdu

        # Version=1, control=0x20 (DNET present),
        # DNET=0xFFFF, DLEN=0 (broadcast),
        # Hop count=255,
        # APDU type=0x10 (unconfirmed request)
        npdu = b"\x01\x20\xff\xff\x00\xff\x10\x08"
        assert _is_confirmed_request_npdu(npdu) is False


# --- Phase 4: F5 - BBMD client functions ---


class TestBBMDClientFunctions:
    """F5: Client-side BBMD management functions.

    Tests the async read_bdt/write_bdt/read_fdt/delete_fdt_entry methods.
    """

    BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)

    def _make_transport_with_mock(self) -> tuple[BIPTransport, MagicMock]:
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        return transport, mock_udp

    @pytest.mark.asyncio
    async def test_read_bdt_sends_request(self):
        transport, _mock_udp = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            # Simulate Read-BDT-Ack response
            from bac_py.transport.bbmd import BDTEntry

            entry = BDTEntry(
                address=self.BBMD_ADDR,
                broadcast_mask=b"\xff\xff\xff\xff",
            )
            ack = encode_bvll(
                BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK,
                entry.encode(),
            )
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_bdt(self.BBMD_ADDR, timeout=1.0)
        await task

        assert len(result) == 1
        assert result[0].address == self.BBMD_ADDR
        assert result[0].broadcast_mask == b"\xff\xff\xff\xff"

    @pytest.mark.asyncio
    async def test_read_bdt_sends_correct_bvll(self):
        transport, mock_udp = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            ack = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK, b"")
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        await transport.read_bdt(self.BBMD_ADDR, timeout=1.0)
        await task

        # Verify what was sent
        mock_udp.sendto.assert_called_once()
        sent_data = mock_udp.sendto.call_args[0][0]
        from bac_py.transport.bvll import decode_bvll

        msg = decode_bvll(sent_data)
        assert msg.function == BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE

    @pytest.mark.asyncio
    async def test_read_bdt_timeout(self):
        transport, _ = self._make_transport_with_mock()

        with pytest.raises(TimeoutError):
            await transport.read_bdt(self.BBMD_ADDR, timeout=0.05)

    @pytest.mark.asyncio
    async def test_read_bdt_not_started_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.read_bdt(self.BBMD_ADDR)

    @pytest.mark.asyncio
    async def test_read_bdt_empty_response(self):
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            ack = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK, b"")
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_bdt(self.BBMD_ADDR, timeout=1.0)
        await task
        assert result == []

    @pytest.mark.asyncio
    async def test_write_bdt_success(self):
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            result_data = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
            bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
            transport._on_datagram_received(bvll, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        from bac_py.transport.bbmd import BDTEntry

        entries = [
            BDTEntry(address=self.BBMD_ADDR, broadcast_mask=b"\xff\xff\xff\xff"),
        ]
        task = asyncio.create_task(respond())
        result = await transport.write_bdt(self.BBMD_ADDR, entries, timeout=1.0)
        await task
        assert result == BvlcResultCode.SUCCESSFUL_COMPLETION

    @pytest.mark.asyncio
    async def test_write_bdt_nak(self):
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            result_data = BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK.to_bytes(2, "big")
            bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
            transport._on_datagram_received(bvll, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        from bac_py.transport.bbmd import BDTEntry

        entries = [
            BDTEntry(address=self.BBMD_ADDR, broadcast_mask=b"\xff\xff\xff\xff"),
        ]
        task = asyncio.create_task(respond())
        result = await transport.write_bdt(self.BBMD_ADDR, entries, timeout=1.0)
        await task
        assert result == BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK

    @pytest.mark.asyncio
    async def test_write_bdt_not_started_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.write_bdt(self.BBMD_ADDR, [])

    @pytest.mark.asyncio
    async def test_read_fdt_returns_entries(self):
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            fd_addr = BIPAddress(host="10.0.0.50", port=47808)
            payload = fd_addr.encode() + (60).to_bytes(2, "big") + (45).to_bytes(2, "big")
            ack = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK, payload)
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_fdt(self.BBMD_ADDR, timeout=1.0)
        await task

        assert len(result) == 1
        assert result[0].address == BIPAddress(host="10.0.0.50", port=47808)
        assert result[0].ttl == 60

    @pytest.mark.asyncio
    async def test_read_fdt_empty_response(self):
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            ack = encode_bvll(BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK, b"")
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_fdt(self.BBMD_ADDR, timeout=1.0)
        await task
        assert result == []

    @pytest.mark.asyncio
    async def test_read_fdt_not_started_raises(self):
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.read_fdt(self.BBMD_ADDR)

    @pytest.mark.asyncio
    async def test_delete_fdt_entry_success(self):
        transport, _ = self._make_transport_with_mock()
        fd_addr = BIPAddress(host="10.0.0.50", port=47808)

        async def respond():
            await asyncio.sleep(0.01)
            result_data = BvlcResultCode.SUCCESSFUL_COMPLETION.to_bytes(2, "big")
            bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
            transport._on_datagram_received(bvll, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.delete_fdt_entry(self.BBMD_ADDR, fd_addr, timeout=1.0)
        await task
        assert result == BvlcResultCode.SUCCESSFUL_COMPLETION

    @pytest.mark.asyncio
    async def test_delete_fdt_entry_nak(self):
        transport, _ = self._make_transport_with_mock()
        fd_addr = BIPAddress(host="10.0.0.50", port=47808)

        async def respond():
            await asyncio.sleep(0.01)
            result_data = BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK.to_bytes(2, "big")
            bvll = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
            transport._on_datagram_received(bvll, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.delete_fdt_entry(self.BBMD_ADDR, fd_addr, timeout=1.0)
        await task
        assert result == BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK

    @pytest.mark.asyncio
    async def test_delete_fdt_entry_not_started_raises(self):
        transport = BIPTransport()
        fd_addr = BIPAddress(host="10.0.0.50", port=47808)
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.delete_fdt_entry(self.BBMD_ADDR, fd_addr)

    @pytest.mark.asyncio
    async def test_pending_future_cleaned_on_timeout(self):
        """Pending future is cleaned up even when timeout occurs."""
        transport, _ = self._make_transport_with_mock()

        with pytest.raises(TimeoutError):
            await transport.read_bdt(self.BBMD_ADDR, timeout=0.05)

        # Future should be cleaned up
        assert len(transport._pending_bvlc) == 0

    @pytest.mark.asyncio
    async def test_response_from_wrong_address_ignored(self):
        """Response from a different address does not resolve the future."""
        transport, _ = self._make_transport_with_mock()
        wrong_addr = BIPAddress(host="10.99.99.99", port=47808)

        async def respond():
            await asyncio.sleep(0.01)
            # Response from wrong address
            ack = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK, b"")
            transport._on_datagram_received(ack, (wrong_addr.host, wrong_addr.port))

        task = asyncio.create_task(respond())

        with pytest.raises(TimeoutError):
            await transport.read_bdt(self.BBMD_ADDR, timeout=0.1)
        await task


# --- Coverage gap tests ---


class TestIsConfirmedRequestNpduEdgeCases:
    """Cover edge cases in _is_confirmed_request_npdu: truncated DNET/SNET."""

    def test_dnet_present_but_truncated(self):
        """Line 48: DNET flag set but data truncated before DLEN byte."""
        # control=0x20 (DNET present), but only 2 bytes after version+control
        npdu = b"\x01\x20\xff"
        assert _is_confirmed_request_npdu(npdu) is False

    def test_snet_present_but_truncated(self):
        """Line 53: SNET flag set but data truncated before SLEN byte."""
        # control=0x08 (SNET present), only 2 bytes after version+control
        npdu = b"\x01\x08\x00"
        assert _is_confirmed_request_npdu(npdu) is False

    def test_dnet_plus_snet_offset_overflow(self):
        """Line 59: DNET+SNET present, offset overflows past data length."""
        # control=0x28 (DNET+SNET both present)
        # DNET=0x0001, DLEN=0 (broadcast dest), hop count consumed,
        # but SNET data truncated
        npdu = b"\x01\x28\x00\x01\x00"
        assert _is_confirmed_request_npdu(npdu) is False

    def test_dnet_with_hop_count_overflow(self):
        """DNET present but hop count pushes offset past data."""
        # control=0x20 (DNET), DNET=0x0001, DLEN=0, hop count byte needed
        # but no APDU byte after hop count
        npdu = b"\x01\x20\x00\x01\x00\xff"
        assert _is_confirmed_request_npdu(npdu) is False

    def test_snet_present_alone_truncated_at_slen(self):
        """SNET flag set with just enough for offset+3 check to fail."""
        # control=0x08, only one byte of SNET data (need 3)
        npdu = b"\x01\x08\x00\x01"
        assert _is_confirmed_request_npdu(npdu) is False

    def test_dnet_and_snet_confirmed_request(self):
        """Full DNET+SNET with confirmed request at the end."""
        # control=0x28 (DNET+SNET), DNET=0x0001, DLEN=1, DADR=0x05,
        # SNET=0x0002, SLEN=1, SADR=0x06, hop_count=0xFF,
        # APDU type=0x00 (confirmed request)
        npdu = b"\x01\x28\x00\x01\x01\x05\x00\x02\x01\x06\xff\x00\x02"
        assert _is_confirmed_request_npdu(npdu) is True


class TestResolveLocalIp:
    """Cover _resolve_local_ip OSError fallback (lines 71-77)."""

    def test_oserror_returns_loopback(self):
        """When socket.connect raises OSError, return 127.0.0.1."""
        with patch("bac_py.transport.bip.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.connect.side_effect = OSError("Network unreachable")
            mock_sock_cls.return_value = mock_sock

            result = _resolve_local_ip()
            assert result == "127.0.0.1"

    def test_successful_resolution_returns_ip(self):
        """Normal path returns the IP from getsockname."""
        with patch("bac_py.transport.bip.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.getsockname.return_value = ("192.168.1.100", 0)
            mock_sock_cls.return_value = mock_sock

            result = _resolve_local_ip()
            assert result == "192.168.1.100"


class TestUDPProtocolConnectionLost:
    """Cover _UDPProtocol.connection_lost paths (lines 102, 105)."""

    def test_connection_lost_with_exception_logs_warning(self, caplog):
        """Line 102: exc is not None => warning log."""
        callback = MagicMock()
        lost_callback = MagicMock()
        protocol = _UDPProtocol(callback, connection_lost_callback=lost_callback)

        exc = OSError("Socket closed unexpectedly")
        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            protocol.connection_lost(exc)

        assert "UDP connection lost" in caplog.text
        assert "Socket closed unexpectedly" in caplog.text
        lost_callback.assert_called_once_with(exc)

    def test_connection_lost_without_exception_logs_debug(self, caplog):
        """Exc is None => debug log, callback still invoked."""
        callback = MagicMock()
        lost_callback = MagicMock()
        protocol = _UDPProtocol(callback, connection_lost_callback=lost_callback)

        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            protocol.connection_lost(None)

        assert "UDP connection closed" in caplog.text
        lost_callback.assert_called_once_with(None)

    def test_connection_lost_no_callback(self, caplog):
        """Line 105: connection_lost_callback is None => no call."""
        callback = MagicMock()
        protocol = _UDPProtocol(callback, connection_lost_callback=None)

        with caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"):
            protocol.connection_lost(OSError("test"))

        assert "UDP connection lost" in caplog.text


class TestStartWildcardIP:
    """Cover start() with wildcard interface resolving local IP (line 171)."""

    async def test_start_wildcard_resolves_local_ip(self):
        """Line 171: When interface is 0.0.0.0, _resolve_local_ip is called."""
        transport = BIPTransport(interface="0.0.0.0", port=0)
        with patch(
            "bac_py.transport.bip._resolve_local_ip", return_value="10.0.0.42"
        ) as mock_resolve:
            try:
                await transport.start()
                mock_resolve.assert_called_once()
                assert transport.local_address.host == "10.0.0.42"
            finally:
                await transport.stop()


class TestStartMulticastJoinFailure:
    """Cover multicast join OSError path (lines 183-184)."""

    async def test_multicast_join_failure_logged_as_warning(self, caplog):
        """Lines 183-184: OSError during multicast join logged as warning."""
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            multicast_enabled=True,
        )
        # Patch socket.inet_aton to raise OSError during multicast join
        # (called after endpoint creation, so the socket bind succeeds)
        original_inet_aton = __import__("socket").inet_aton

        call_count = 0

        def failing_inet_aton(addr):
            nonlocal call_count
            call_count += 1
            # The first call to inet_aton within the multicast block is
            # for the group address. Let it fail.
            if call_count == 1:
                raise OSError("Multicast join failed")
            return original_inet_aton(addr)

        try:
            with (
                patch(
                    "bac_py.transport.bip.socket.inet_aton",
                    side_effect=failing_inet_aton,
                ),
                caplog.at_level(logging.WARNING, logger="bac_py.transport.bip"),
            ):
                await transport.start()
            assert "Failed to join multicast group" in caplog.text
        finally:
            await transport.stop()


class TestStopForeignDeviceCleanup:
    """Cover stop() foreign device cleanup path (lines 191-192)."""

    async def test_stop_calls_foreign_device_stop(self):
        """Lines 191-192: stop() calls _foreign_device.stop() and clears it."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()

        mock_fd = AsyncMock()
        mock_fd.stop = AsyncMock()
        transport._foreign_device = mock_fd

        await transport.stop()

        mock_fd.stop.assert_awaited_once()
        assert transport._foreign_device is None


class TestStopMulticastLeaveOSError:
    """Cover stop() multicast leave OSError path (lines 206-207)."""

    async def test_multicast_leave_oserror_suppressed(self):
        """Lines 206-207: OSError during multicast leave is silently caught."""
        transport = BIPTransport(
            interface="127.0.0.1",
            port=0,
            multicast_enabled=True,
        )
        await transport.start()

        # Patch socket.inet_aton to raise OSError during multicast leave.
        # stop() calls socket.inet_aton inside the try/except OSError block.
        with patch(
            "bac_py.transport.bip.socket.inet_aton",
            side_effect=OSError("Cannot leave multicast group"),
        ):
            # Should not raise despite OSError
            await transport.stop()

        assert transport._transport is None


class TestSendBroadcastForeignDevice:
    """Cover send_broadcast() foreign device distribute path (lines 252-253)."""

    def test_send_broadcast_uses_distribute_when_registered(self):
        """Lines 252-253: Foreign device uses distribute instead of broadcast."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        mock_fd = MagicMock()
        mock_fd.is_registered = True
        mock_fd.send_distribute_broadcast = MagicMock()
        transport._foreign_device = mock_fd

        npdu = b"\x01\x00\x10"
        transport.send_broadcast(npdu)

        mock_fd.send_distribute_broadcast.assert_called_once_with(npdu)
        # Regular sendto should NOT have been called
        mock_udp.sendto.assert_not_called()

    def test_send_broadcast_normal_when_fd_not_registered(self):
        """When foreign device exists but not registered, use normal broadcast."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        mock_fd = MagicMock()
        mock_fd.is_registered = False
        transport._foreign_device = mock_fd

        npdu = b"\x01\x00\x10"
        transport.send_broadcast(npdu)

        # Normal broadcast should happen
        mock_udp.sendto.assert_called_once()


class TestAttachForeignDevice:
    """Cover attach_foreign_device method (lines 353-372)."""

    @pytest.mark.asyncio
    async def test_attach_foreign_device_success(self):
        """Lines 353-372: Full attach_foreign_device path."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)

        try:
            fd = await transport.attach_foreign_device(bbmd_addr, ttl=60)

            assert fd is not None
            assert transport._foreign_device is fd
            assert fd.bbmd_address == bbmd_addr
            assert fd.ttl == 60
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_foreign_device_not_started_raises(self):
        """Line 353-355: RuntimeError when transport not started."""
        transport = BIPTransport()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)

        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.attach_foreign_device(bbmd_addr, ttl=60)

    @pytest.mark.asyncio
    async def test_attach_foreign_device_already_attached_raises(self):
        """Lines 356-358: RuntimeError when FD already attached."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)

        try:
            await transport.attach_foreign_device(bbmd_addr, ttl=60)
            with pytest.raises(RuntimeError, match="Foreign device manager already attached"):
                await transport.attach_foreign_device(bbmd_addr, ttl=60)
        finally:
            await transport.stop()


class TestForeignDeviceProperty:
    """Cover foreign_device property (line 331)."""

    def test_foreign_device_none_initially(self):
        """Line 331: Returns None when no FD is attached."""
        transport = BIPTransport()
        assert transport.foreign_device is None

    @pytest.mark.asyncio
    async def test_foreign_device_returns_manager_after_attach(self):
        """Line 331: Returns the ForeignDeviceManager after attach."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        bbmd_addr = BIPAddress(host="192.168.1.1", port=47808)

        try:
            fd = await transport.attach_foreign_device(bbmd_addr, ttl=60)
            assert transport.foreign_device is fd
        finally:
            await transport.stop()


class TestBBMDLocalDeliverConfirmedDrop:
    """Cover _bbmd_local_deliver confirmed request drop (lines 567-572)."""

    def test_confirmed_request_dropped_via_bbmd_local_deliver(self, caplog):
        """Lines 567-572: Confirmed request via BBMD broadcast is dropped."""
        transport = BIPTransport()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        # Confirmed request NPDU: version=1, control=0x04, APDU type=0x00
        confirmed_npdu = b"\x01\x04\x00\x02\x01\x0c"
        source = BIPAddress(host="10.0.0.50", port=47808)

        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._bbmd_local_deliver(confirmed_npdu, source)

        assert len(received) == 0
        assert "Dropped confirmed request via BBMD broadcast" in caplog.text

    def test_unconfirmed_request_delivered_via_bbmd_local_deliver(self):
        """Unconfirmed requests via BBMD are delivered normally."""
        transport = BIPTransport()
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        # Unconfirmed request NPDU: version=1, control=0x00, APDU type=0x10
        unconfirmed_npdu = b"\x01\x00\x10\x08\x00"
        source = BIPAddress(host="10.0.0.50", port=47808)

        transport._bbmd_local_deliver(unconfirmed_npdu, source)

        assert len(received) == 1
        assert received[0][0] == unconfirmed_npdu

    def test_bbmd_local_deliver_no_callback(self):
        """No callback registered => no delivery, no error."""
        transport = BIPTransport()
        unconfirmed_npdu = b"\x01\x00\x10\x08\x00"
        source = BIPAddress(host="10.0.0.50", port=47808)

        # Should not raise
        transport._bbmd_local_deliver(unconfirmed_npdu, source)


class TestReadBdtTruncatedEntry:
    """Cover read_bdt truncated entry path (line 404)."""

    BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)

    def _make_transport_with_mock(self) -> tuple[BIPTransport, MagicMock]:
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        return transport, mock_udp

    @pytest.mark.asyncio
    async def test_read_bdt_truncated_entry_skipped(self):
        """Line 404: Truncated BDT entry at end of response is skipped."""
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            from bac_py.transport.bbmd import BDTEntry

            entry = BDTEntry(
                address=self.BBMD_ADDR,
                broadcast_mask=b"\xff\xff\xff\xff",
            )
            full_entry = entry.encode()
            # Add 5 extra bytes (truncated second entry)
            truncated = full_entry + b"\x01\x02\x03\x04\x05"
            ack = encode_bvll(
                BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK,
                truncated,
            )
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_bdt(self.BBMD_ADDR, timeout=1.0)
        await task

        # Only the first complete entry should be returned
        assert len(result) == 1


class TestWriteBdtShortResponse:
    """Cover write_bdt short response fallback (line 441)."""

    BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)

    def _make_transport_with_mock(self) -> tuple[BIPTransport, MagicMock]:
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        return transport, mock_udp

    @pytest.mark.asyncio
    async def test_write_bdt_short_response_returns_nak(self):
        """Line 441: Response with < 2 bytes returns WRITE_BDT_NAK."""
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            # Inject a BVLC-Result with only 1 byte of data
            key = (BvlcFunction.BVLC_RESULT, self.BBMD_ADDR)
            future = transport._pending_bvlc.get(key)
            if future and not future.done():
                future.set_result(b"\x00")  # Only 1 byte

        from bac_py.transport.bbmd import BDTEntry

        entries = [
            BDTEntry(address=self.BBMD_ADDR, broadcast_mask=b"\xff\xff\xff\xff"),
        ]

        task = asyncio.create_task(respond())
        result = await transport.write_bdt(self.BBMD_ADDR, entries, timeout=1.0)
        await task
        assert result == BvlcResultCode.WRITE_BROADCAST_DISTRIBUTION_TABLE_NAK


class TestDeleteFdtEntryShortResponse:
    """Cover delete_fdt_entry short response fallback (line 514)."""

    BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)

    def _make_transport_with_mock(self) -> tuple[BIPTransport, MagicMock]:
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        return transport, mock_udp

    @pytest.mark.asyncio
    async def test_delete_fdt_entry_short_response_returns_nak(self):
        """Line 514: Response with < 2 bytes returns DELETE_FDT_ENTRY_NAK."""
        transport, _ = self._make_transport_with_mock()
        fd_addr = BIPAddress(host="10.0.0.50", port=47808)

        async def respond():
            await asyncio.sleep(0.01)
            key = (BvlcFunction.BVLC_RESULT, self.BBMD_ADDR)
            future = transport._pending_bvlc.get(key)
            if future and not future.done():
                future.set_result(b"\x00")  # Only 1 byte

        task = asyncio.create_task(respond())
        result = await transport.delete_fdt_entry(self.BBMD_ADDR, fd_addr, timeout=1.0)
        await task
        assert result == BvlcResultCode.DELETE_FOREIGN_DEVICE_TABLE_ENTRY_NAK


class TestSendRawNoTransport:
    """Cover _send_raw when transport is None (line 555)."""

    def test_send_raw_no_transport_does_not_raise(self):
        """Line 555: _send_raw with None transport silently returns."""
        transport = BIPTransport()
        dest = BIPAddress(host="10.0.0.1", port=47808)

        # Should not raise
        transport._send_raw(b"\x81\x0a\x00\x05\x01", dest)


class TestReadFdtTruncatedEntry:
    """Cover read_fdt truncated entry path (line 471)."""

    BBMD_ADDR = BIPAddress(host="192.168.1.1", port=47808)

    def _make_transport_with_mock(self) -> tuple[BIPTransport, MagicMock]:
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        return transport, mock_udp

    @pytest.mark.asyncio
    async def test_read_fdt_truncated_entry_skipped(self):
        """Line 471: Truncated FDT entry at end of response is skipped."""
        transport, _ = self._make_transport_with_mock()

        async def respond():
            await asyncio.sleep(0.01)
            fd_addr = BIPAddress(host="10.0.0.50", port=47808)
            full_entry = fd_addr.encode() + (60).to_bytes(2, "big") + (45).to_bytes(2, "big")
            # Add 5 truncated bytes (incomplete second entry)
            truncated = full_entry + b"\x01\x02\x03\x04\x05"
            ack = encode_bvll(
                BvlcFunction.READ_FOREIGN_DEVICE_TABLE_ACK,
                truncated,
            )
            transport._on_datagram_received(ack, (self.BBMD_ADDR.host, self.BBMD_ADDR.port))

        task = asyncio.create_task(respond())
        result = await transport.read_fdt(self.BBMD_ADDR, timeout=1.0)
        await task

        assert len(result) == 1
        assert result[0].address == BIPAddress(host="10.0.0.50", port=47808)


class TestBvlcRequestTransportNone:
    """Cover _bvlc_request path when transport is None during send (line 539)."""

    @pytest.mark.asyncio
    async def test_bvlc_request_transport_none_skips_sendto(self):
        """Line 539: If transport becomes None, sendto is skipped."""
        transport = BIPTransport()
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        # Transport is None -- sendto should be skipped, will timeout
        dest = BIPAddress(host="192.168.1.1", port=47808)
        bvll = encode_bvll(BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE, b"")

        with pytest.raises(TimeoutError):
            await transport._bvlc_request(
                bvll,
                dest,
                BvlcFunction.READ_BROADCAST_DISTRIBUTION_TABLE_ACK,
                timeout=0.05,
            )


class TestStopBBMDCleanup:
    """Cover stop() BBMD cleanup path (lines 194-195)."""

    async def test_stop_calls_bbmd_stop(self):
        """Lines 194-195: stop() calls _bbmd.stop() and clears it."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()

        mock_bbmd = AsyncMock()
        mock_bbmd.stop = AsyncMock()
        transport._bbmd = mock_bbmd

        await transport.stop()

        mock_bbmd.stop.assert_awaited_once()
        assert transport._bbmd is None


class TestSendBroadcastMulticast:
    """Cover send_broadcast() multicast path (line 258)."""

    def test_send_broadcast_multicast_sends_to_group(self):
        """Line 258: When multicast is enabled, send to multicast group."""
        transport = BIPTransport(
            multicast_enabled=True,
            multicast_address="239.255.186.192",
        )
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10"
        transport.send_broadcast(npdu)

        # Should have two sendto calls: multicast group + directed broadcast
        assert mock_udp.sendto.call_count == 2
        first_call_addr = mock_udp.sendto.call_args_list[0][0][1]
        assert first_call_addr == ("239.255.186.192", 0xBAC0)


class TestSendBroadcastWithBBMD:
    """Cover send_broadcast() BBMD forward path (line 264)."""

    def test_send_broadcast_forwards_to_bbmd(self):
        """Line 264: When BBMD is attached, handle_bvlc is called."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)

        mock_bbmd = MagicMock()
        transport._bbmd = mock_bbmd

        npdu = b"\x01\x00\x10"
        transport.send_broadcast(npdu)

        mock_bbmd.handle_bvlc.assert_called_once_with(
            BvlcFunction.ORIGINAL_BROADCAST_NPDU,
            npdu,
            transport.local_address,
        )


class TestBBMDProperty:
    """Cover bbmd property (line 287)."""

    def test_bbmd_none_initially(self):
        """Line 287: Returns None when no BBMD is attached."""
        transport = BIPTransport()
        assert transport.bbmd is None

    @pytest.mark.asyncio
    async def test_bbmd_returns_manager_after_attach(self):
        """Line 287: Returns the BBMDManager after attach."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        try:
            bbmd = await transport.attach_bbmd()
            assert transport.bbmd is bbmd
        finally:
            await transport.stop()


class TestAttachBBMD:
    """Cover attach_bbmd method (lines 305-326)."""

    @pytest.mark.asyncio
    async def test_attach_bbmd_success(self):
        """Lines 305-326: Full attach_bbmd path."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        try:
            bbmd = await transport.attach_bbmd()
            assert bbmd is not None
            assert transport._bbmd is bbmd
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_bbmd_with_bdt_entries(self):
        """Lines 318-319: attach_bbmd with initial BDT entries."""
        from bac_py.transport.bbmd import BDTEntry

        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        try:
            entries = [
                BDTEntry(
                    address=transport.local_address,
                    broadcast_mask=b"\xff\xff\xff\x00",
                ),
            ]
            bbmd = await transport.attach_bbmd(bdt_entries=entries)
            assert bbmd is not None
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_attach_bbmd_not_started_raises(self):
        """Lines 305-307: RuntimeError when transport not started."""
        transport = BIPTransport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.attach_bbmd()

    @pytest.mark.asyncio
    async def test_attach_bbmd_already_attached_raises(self):
        """Lines 308-310: RuntimeError when BBMD already attached."""
        transport = BIPTransport(interface="127.0.0.1", port=0)
        await transport.start()
        try:
            await transport.attach_bbmd()
            with pytest.raises(RuntimeError, match="BBMD already attached"):
                await transport.attach_bbmd()
        finally:
            await transport.stop()


class TestSendRawWithTransport:
    """Cover _send_raw when transport is present (line 556)."""

    def test_send_raw_with_transport_sends_data(self):
        """Line 556: _send_raw with active transport calls sendto."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        dest = BIPAddress(host="10.0.0.1", port=47808)

        data = b"\x81\x0a\x00\x05\x01"
        transport._send_raw(data, dest)

        mock_udp.sendto.assert_called_once_with(data, ("10.0.0.1", 47808))


class TestSelfAddressDrop:
    """Cover F6 self-address drop (line 603)."""

    def test_own_datagram_dropped(self):
        """Line 603: Datagrams from own address are dropped."""
        transport = BIPTransport()
        transport._local_address = BIPAddress(host="192.168.1.50", port=47808)
        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        npdu = b"\x01\x00\x10"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        # Send from our own address
        transport._on_datagram_received(bvll, ("192.168.1.50", 47808))

        assert len(received) == 0


class TestBBMDInterceptPaths:
    """Cover BBMD intercept paths in _on_datagram_received (lines 609-629)."""

    def _make_transport_with_bbmd(self):
        """Create transport with a mock BBMD attached."""
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp
        transport._local_address = BIPAddress(host="10.0.0.1", port=47808)
        mock_bbmd = MagicMock()
        transport._bbmd = mock_bbmd
        return transport, mock_bbmd

    def test_bbmd_intercept_handled_returns_early(self):
        """Lines 618-622: BBMD handles message exclusively (returns True)."""
        transport, mock_bbmd = self._make_transport_with_bbmd()
        mock_bbmd.handle_bvlc.return_value = True

        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        bvll = encode_bvll(
            BvlcFunction.REGISTER_FOREIGN_DEVICE,
            (60).to_bytes(2, "big"),
        )
        transport._on_datagram_received(bvll, ("10.0.0.50", 47808))

        mock_bbmd.handle_bvlc.assert_called_once()
        assert len(received) == 0

    def test_bbmd_intercept_forwarded_npdu_not_double_delivered(self):
        """Lines 628-629: Forwarded-NPDU skips normal path after BBMD."""
        transport, mock_bbmd = self._make_transport_with_bbmd()
        # BBMD returns False (not exclusively handled) for broadcast NPDUs
        mock_bbmd.handle_bvlc.return_value = False

        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        npdu = b"\x01\x00\x10\x08\x00"
        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("192.168.1.1", 47808))

        # Should NOT be delivered via normal path (BBMD already did it)
        assert len(received) == 0

    def test_bbmd_intercept_forwarded_npdu_uses_originating_address(self):
        """Lines 609-610: Forwarded-NPDU passes originating address to BBMD."""
        transport, mock_bbmd = self._make_transport_with_bbmd()
        mock_bbmd.handle_bvlc.return_value = True

        npdu = b"\x01\x00\x10"
        orig = BIPAddress(host="10.0.0.99", port=47808)
        bvll = encode_bvll(
            BvlcFunction.FORWARDED_NPDU,
            npdu,
            originating_address=orig,
        )
        transport._on_datagram_received(bvll, ("192.168.1.1", 47808))

        call_args = mock_bbmd.handle_bvlc.call_args
        # The source passed to BBMD should be the originating address
        assert call_args[0][2] == orig

    def test_bbmd_intercept_non_forwarded_uses_udp_source(self):
        """Lines 611-612: Non-forwarded uses UDP source for BBMD."""
        transport, mock_bbmd = self._make_transport_with_bbmd()
        mock_bbmd.handle_bvlc.return_value = False

        npdu = b"\x01\x00\x10"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        transport._on_datagram_received(bvll, ("10.0.0.50", 47808))

        call_args = mock_bbmd.handle_bvlc.call_args
        expected_source = BIPAddress(host="10.0.0.50", port=47808)
        assert call_args[0][2] == expected_source

    def test_bbmd_intercept_original_broadcast_delivered_normally(self):
        """When BBMD returns False for Original-Broadcast, normal delivery."""
        transport, mock_bbmd = self._make_transport_with_bbmd()
        mock_bbmd.handle_bvlc.return_value = False

        received: list[tuple[bytes, bytes]] = []
        transport.on_receive(lambda d, s: received.append((d, s)))

        npdu = b"\x01\x00\x10\x08\x00"
        bvll = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        transport._on_datagram_received(bvll, ("10.0.0.50", 47808))

        assert len(received) == 1
        assert received[0][0] == npdu
