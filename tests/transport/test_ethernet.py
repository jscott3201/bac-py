"""Tests for BACnet Ethernet (ISO 8802-3) transport per Clause 7."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from bac_py.transport.ethernet import (
    ETHERNET_BROADCAST,
    ETHERNET_HEADER_SIZE,
    LLC_CONTROL,
    LLC_DSAP,
    LLC_HEADER_SIZE,
    LLC_SSAP,
    MAX_NPDU_LENGTH,
    EthernetTransport,
    _decode_frame,
    _encode_frame,
)
from bac_py.transport.port import TransportPort

# ---------------------------------------------------------------------------
# Frame encoding tests
# ---------------------------------------------------------------------------


class TestEncodeFrame:
    def test_correct_llc_header(self):
        """Frame should contain LLC header (DSAP=0x82, SSAP=0x82, Ctrl=0x03)."""
        dst = b"\x01\x02\x03\x04\x05\x06"
        src = b"\x0a\x0b\x0c\x0d\x0e\x0f"
        npdu = b"\xaa\xbb\xcc"
        frame = _encode_frame(dst, src, npdu)

        # LLC header starts at offset 14 (after Ethernet header)
        assert frame[14] == LLC_DSAP
        assert frame[15] == LLC_SSAP
        assert frame[16] == LLC_CONTROL

    def test_correct_mac_addresses(self):
        """Frame should have correct destination and source MACs."""
        dst = b"\x01\x02\x03\x04\x05\x06"
        src = b"\x0a\x0b\x0c\x0d\x0e\x0f"
        frame = _encode_frame(dst, src, b"\x00")

        assert frame[:6] == dst
        assert frame[6:12] == src

    def test_correct_length_field(self):
        """802.3 length field = LLC header + NPDU data length."""
        npdu = b"\xaa\xbb\xcc\xdd"
        frame = _encode_frame(b"\x00" * 6, b"\x00" * 6, npdu)

        expected_length = LLC_HEADER_SIZE + len(npdu)  # 3 + 4 = 7
        actual_length = struct.unpack("!H", frame[12:14])[0]
        assert actual_length == expected_length

    def test_npdu_in_payload(self):
        """NPDU data should follow the LLC header."""
        npdu = b"\x01\x02\x03\x04"
        frame = _encode_frame(b"\x00" * 6, b"\x00" * 6, npdu)

        payload_start = ETHERNET_HEADER_SIZE + LLC_HEADER_SIZE
        assert frame[payload_start : payload_start + len(npdu)] == npdu

    def test_minimum_frame_padding(self):
        """Short frames should be padded to minimum 60 bytes."""
        frame = _encode_frame(b"\x00" * 6, b"\x00" * 6, b"\x01")
        # 14 (header) + 46 (min payload) = 60
        assert len(frame) >= 60

    def test_large_npdu_no_padding(self):
        """Frames with enough data should not be padded."""
        npdu = b"\xaa" * 100
        frame = _encode_frame(b"\x00" * 6, b"\x00" * 6, npdu)
        expected_size = ETHERNET_HEADER_SIZE + LLC_HEADER_SIZE + len(npdu)
        assert len(frame) == expected_size

    def test_broadcast_destination(self):
        """Broadcast frames use FF:FF:FF:FF:FF:FF."""
        frame = _encode_frame(ETHERNET_BROADCAST, b"\x00" * 6, b"\x01")
        assert frame[:6] == b"\xff\xff\xff\xff\xff\xff"


# ---------------------------------------------------------------------------
# Frame decoding tests
# ---------------------------------------------------------------------------


class TestDecodeFrame:
    def _build_frame(
        self,
        dst: bytes = b"\x01\x02\x03\x04\x05\x06",
        src: bytes = b"\x0a\x0b\x0c\x0d\x0e\x0f",
        npdu: bytes = b"\xaa\xbb",
        dsap: int = LLC_DSAP,
        ssap: int = LLC_SSAP,
        control: int = LLC_CONTROL,
        length: int | None = None,
    ) -> bytes:
        """Build a raw 802.3 frame for testing."""
        llc = bytes([dsap, ssap, control])
        payload = llc + npdu
        if length is None:
            length = len(payload)
        header = dst + src + struct.pack("!H", length)
        frame = header + payload
        # Pad to minimum
        if len(frame) < 60:
            frame += b"\x00" * (60 - len(frame))
        return frame

    def test_valid_frame(self):
        """Valid BACnet frame should decode correctly."""
        npdu = b"\x01\x02\x03\x04"
        src = b"\x0a\x0b\x0c\x0d\x0e\x0f"
        frame = self._build_frame(src=src, npdu=npdu)
        result = _decode_frame(frame)
        assert result is not None
        decoded_npdu, decoded_src = result
        assert decoded_npdu == npdu
        assert decoded_src == src

    def test_reject_non_bacnet_dsap(self):
        """Frames with wrong DSAP should be rejected."""
        frame = self._build_frame(dsap=0x00)
        assert _decode_frame(frame) is None

    def test_reject_non_bacnet_ssap(self):
        """Frames with wrong SSAP should be rejected."""
        frame = self._build_frame(ssap=0x00)
        assert _decode_frame(frame) is None

    def test_reject_non_bacnet_control(self):
        """Frames with wrong LLC control byte should be rejected."""
        frame = self._build_frame(control=0x00)
        assert _decode_frame(frame) is None

    def test_reject_ethertype_frame(self):
        """Frames with EtherType > 1500 (not 802.3) should be rejected."""
        frame = self._build_frame(length=0x0800)  # IPv4 EtherType
        assert _decode_frame(frame) is None

    def test_reject_too_short(self):
        """Frames shorter than header + LLC should be rejected."""
        assert _decode_frame(b"\x00" * 10) is None
        assert _decode_frame(b"\x00" * 16) is None

    def test_round_trip(self):
        """Encode then decode should preserve NPDU and source MAC."""
        src = b"\xaa\xbb\xcc\xdd\xee\xff"
        dst = b"\x11\x22\x33\x44\x55\x66"
        npdu = b"\x01\x02\x03\x04\x05"
        frame = _encode_frame(dst, src, npdu)
        result = _decode_frame(frame)
        assert result is not None
        decoded_npdu, decoded_src = result
        assert decoded_npdu == npdu
        assert decoded_src == src


# ---------------------------------------------------------------------------
# Transport properties
# ---------------------------------------------------------------------------


class TestEthernetTransportProperties:
    def test_max_npdu_length(self):
        """Max NPDU length should be 1497 (1500 - 3 LLC header)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        assert transport.max_npdu_length == 1497
        assert MAX_NPDU_LENGTH == 1497

    def test_transport_port_protocol(self):
        """EthernetTransport should satisfy the TransportPort protocol."""
        assert isinstance(EthernetTransport("eth0", mac_address=b"\x00" * 6), TransportPort)


# ---------------------------------------------------------------------------
# Mock socket tests
# ---------------------------------------------------------------------------


class TestEthernetTransportSend:
    def _make_transport(self, mac: bytes = b"\xaa\xbb\xcc\xdd\xee\xff") -> EthernetTransport:
        """Create a transport with mock internals."""
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._local_mac_bytes = mac
        transport._running = True
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 99
        transport._socket = mock_sock
        return transport

    def test_send_unicast(self):
        """send_unicast should send a correctly formed frame."""
        transport = self._make_transport()
        dest_mac = b"\x11\x22\x33\x44\x55\x66"
        npdu = b"\x01\x02\x03"

        transport.send_unicast(npdu, dest_mac)

        transport._socket.send.assert_called_once()
        frame = transport._socket.send.call_args[0][0]
        # Verify destination MAC in the frame
        assert frame[:6] == dest_mac
        # Verify source MAC
        assert frame[6:12] == transport._local_mac_bytes

    def test_send_broadcast(self):
        """send_broadcast should send to FF:FF:FF:FF:FF:FF."""
        transport = self._make_transport()
        npdu = b"\x01\x02\x03"

        transport.send_broadcast(npdu)

        transport._socket.send.assert_called_once()
        frame = transport._socket.send.call_args[0][0]
        assert frame[:6] == ETHERNET_BROADCAST

    def test_local_mac_property(self):
        """local_mac should return the configured MAC address."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = self._make_transport(mac)
        assert transport.local_mac == mac

    def test_local_mac_not_started_raises(self):
        """Accessing local_mac before start should raise RuntimeError."""
        transport = EthernetTransport("eth0")
        with pytest.raises(RuntimeError, match="not started"):
            _ = transport.local_mac

    def test_send_unicast_not_started_raises(self):
        """send_unicast before start should raise RuntimeError."""
        transport = EthernetTransport("eth0")
        with pytest.raises(RuntimeError, match="not started"):
            transport.send_unicast(b"\x01", b"\x00" * 6)

    def test_send_broadcast_not_started_raises(self):
        """send_broadcast before start should raise RuntimeError."""
        transport = EthernetTransport("eth0")
        with pytest.raises(RuntimeError, match="not started"):
            transport.send_broadcast(b"\x01")

    def test_on_receive_callback(self):
        """on_receive should register a callback."""
        transport = self._make_transport()
        callback = MagicMock()
        transport.on_receive(callback)
        assert transport._receive_callback is callback

    def test_on_readable_delivers_npdu(self):
        """_on_readable should decode frame and call the callback."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = self._make_transport(mac)
        callback = MagicMock()
        transport.on_receive(callback)

        # Build a valid frame from a different source
        src = b"\x11\x22\x33\x44\x55\x66"
        npdu = b"\x01\x02\x03\x04"
        frame = _encode_frame(mac, src, npdu)
        transport._socket.recv.return_value = frame

        transport._on_readable()

        callback.assert_called_once()
        received_npdu, received_src = callback.call_args[0]
        assert received_npdu == npdu
        assert received_src == src

    def test_on_readable_skips_own_frames(self):
        """Frames from our own MAC should be ignored."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = self._make_transport(mac)
        callback = MagicMock()
        transport.on_receive(callback)

        # Build a frame from ourselves
        frame = _encode_frame(b"\x00" * 6, mac, b"\x01\x02")
        transport._socket.recv.return_value = frame

        transport._on_readable()

        callback.assert_not_called()

    def test_on_readable_skips_non_bacnet(self):
        """Non-BACnet frames should be silently ignored."""
        transport = self._make_transport()
        callback = MagicMock()
        transport.on_receive(callback)

        # Build a non-BACnet frame (wrong DSAP)
        raw = b"\x00" * 6 + b"\x11" * 6 + struct.pack("!H", 10)
        raw += b"\x00\x00\x03" + b"\x01" * 7  # wrong DSAP/SSAP
        raw += b"\x00" * (60 - len(raw))
        transport._socket.recv.return_value = raw

        transport._on_readable()

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Platform detection tests
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    async def test_unsupported_platform_raises(self):
        """Unsupported platforms should raise NotImplementedError."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        with patch("bac_py.transport.ethernet.sys") as mock_sys:
            mock_sys.platform = "win32"
            with pytest.raises(NotImplementedError, match="not supported"):
                await transport.start()

    async def test_stop_idempotent(self):
        """stop() on a non-started transport should not raise."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        await transport.stop()  # Should not raise
