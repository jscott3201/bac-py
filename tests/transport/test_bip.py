"""Tests for BACnet/IP transport (bip.py)."""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bip import BIPTransport, _UDPProtocol
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
