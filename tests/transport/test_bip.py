"""Tests for BACnet/IP transport (bip.py)."""

import logging
from unittest.mock import MagicMock

import pytest

from bac_py.network.address import BIPAddress
from bac_py.transport.bip import BIPTransport, _UDPProtocol
from bac_py.transport.bvll import encode_bvll
from bac_py.types.enums import BvlcFunction


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
            transport.send_unicast(b"\x01\x02", dest)

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
        assert delivered_source.host == "192.168.1.50"
        assert delivered_source.port == 47808

    def test_original_broadcast_npdu_delivers_data(self):
        transport, callback = self._make_transport_with_callback()
        npdu = b"\x01\x00\x10\x08\x00"
        bvll_data = encode_bvll(BvlcFunction.ORIGINAL_BROADCAST_NPDU, npdu)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_called_once()
        delivered_npdu, delivered_source = callback.call_args[0]
        assert delivered_npdu == npdu
        assert delivered_source.host == "192.168.1.50"
        assert delivered_source.port == 47808

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
        assert delivered_source.host == "10.0.0.99"
        assert delivered_source.port == 47808

    def test_bvlc_result_not_delivered_as_npdu(self):
        transport, callback = self._make_transport_with_callback()
        result_data = b"\x00\x00"
        bvll_data = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        addr = ("192.168.1.1", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_not_called()

    def test_bvlc_result_handled_logs_debug(self, caplog):
        transport, _callback = self._make_transport_with_callback()
        result_data = b"\x00\x30"  # register-foreign-device NAK
        bvll_data = encode_bvll(BvlcFunction.BVLC_RESULT, result_data)
        addr = ("192.168.1.1", 47808)

        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._on_datagram_received(bvll_data, addr)

        assert "BVLC-Result: 48" in caplog.text

    def test_unknown_bvlc_function_ignored(self):
        transport, callback = self._make_transport_with_callback()
        # Use REGISTER_FOREIGN_DEVICE -- not handled in the match cases.
        payload = b"\x00\x3c"  # 60-second TTL
        bvll_data = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, payload)
        addr = ("192.168.1.50", 47808)

        transport._on_datagram_received(bvll_data, addr)

        callback.assert_not_called()

    def test_unknown_bvlc_function_logs_debug(self, caplog):
        transport, _callback = self._make_transport_with_callback()
        payload = b"\x00\x3c"
        bvll_data = encode_bvll(BvlcFunction.REGISTER_FOREIGN_DEVICE, payload)
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

        transport.send_unicast(npdu, dest)

        mock_udp.sendto.assert_called_once()

    def test_send_unicast_destination_address(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="192.168.1.100", port=47808)

        transport.send_unicast(npdu, dest)

        _, addr = mock_udp.sendto.call_args[0]
        assert addr == ("192.168.1.100", 47808)

    def test_send_unicast_bvll_encoding(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x00\x10\x02\x00"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        expected_bvll = encode_bvll(BvlcFunction.ORIGINAL_UNICAST_NPDU, npdu)
        assert sent_bvll == expected_bvll

    def test_send_unicast_bvll_header_type_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x02\x03"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[0] == 0x81  # BVLC type for BACnet/IP

    def test_send_unicast_bvll_header_function_byte(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\x01\x02\x03"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest)

        sent_bvll = mock_udp.sendto.call_args[0][0]
        assert sent_bvll[1] == BvlcFunction.ORIGINAL_UNICAST_NPDU

    def test_send_unicast_bvll_contains_npdu(self):
        transport = BIPTransport()
        mock_udp = MagicMock()
        transport._transport = mock_udp

        npdu = b"\xde\xad\xbe\xef"
        dest = BIPAddress(host="10.0.0.1", port=47808)

        transport.send_unicast(npdu, dest)

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


class TestHandleBvlcResult:
    """Test _handle_bvlc_result edge cases."""

    def test_short_data_does_not_raise(self):
        transport = BIPTransport()
        # Less than 2 bytes -- should not raise or log.
        transport._handle_bvlc_result(b"\x00")

    def test_empty_data_does_not_raise(self):
        transport = BIPTransport()
        transport._handle_bvlc_result(b"")

    def test_valid_result_code_logs_debug(self, caplog):
        transport = BIPTransport()
        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._handle_bvlc_result(b"\x00\x00")
        assert "BVLC-Result: 0" in caplog.text

    def test_nonzero_result_code_logs_debug(self, caplog):
        transport = BIPTransport()
        with caplog.at_level(logging.DEBUG, logger="bac_py.transport.bip"):
            transport._handle_bvlc_result(b"\x00\x30")
        assert "BVLC-Result: 48" in caplog.text
