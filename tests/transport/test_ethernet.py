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
    _create_raw_socket_linux,
    _decode_frame,
    _encode_frame,
    _get_mac_address,
    _open_bpf_device,
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


# ---------------------------------------------------------------------------
# _decode_frame edge cases
# ---------------------------------------------------------------------------


class TestDecodeFrameEdgeCases:
    """Cover line 108: npdu_end clamped to raw length."""

    def _build_frame_with_length(
        self,
        src: bytes = b"\x0a\x0b\x0c\x0d\x0e\x0f",
        npdu: bytes = b"\xaa\xbb",
        length_override: int | None = None,
    ) -> bytes:
        """Build a frame where the 802.3 length field can be overridden."""
        dst = b"\x01\x02\x03\x04\x05\x06"
        llc = bytes([LLC_DSAP, LLC_SSAP, LLC_CONTROL])
        payload = llc + npdu
        length = length_override if length_override is not None else len(payload)
        header = dst + src + struct.pack("!H", length)
        return header + payload  # no padding — keep it short

    def test_length_field_exceeds_actual_data(self):
        """When length field exceeds raw data, npdu_end is clamped (line 108)."""
        npdu = b"\x01\x02\x03"
        # Set length field to claim much more data than actually present
        frame = self._build_frame_with_length(npdu=npdu, length_override=200)
        result = _decode_frame(frame)
        assert result is not None
        decoded_npdu, _decoded_src = result
        # The NPDU should contain whatever was available after the LLC header
        assert decoded_npdu == npdu


# ---------------------------------------------------------------------------
# _get_mac_address tests (lines 121-130)
# ---------------------------------------------------------------------------


class TestGetMacAddress:
    """Cover _get_mac_address via fcntl.ioctl mocking."""

    def test_get_mac_address_success(self):
        """_get_mac_address should return 6 bytes from ioctl result."""
        expected_mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        # ioctl returns a buffer where bytes 18-24 are the MAC
        ioctl_result = b"\x00" * 18 + expected_mac + b"\x00" * 232

        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 3

        with (
            patch("fcntl.ioctl", return_value=ioctl_result),
            patch("socket.socket", return_value=mock_sock),
        ):
            result = _get_mac_address("eth0")

        assert result == expected_mac
        mock_sock.close.assert_called_once()

    def test_get_mac_address_closes_on_error(self):
        """_get_mac_address should close the socket even if ioctl fails."""
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 3

        with (
            patch("fcntl.ioctl", side_effect=OSError("ioctl failed")),
            patch("socket.socket", return_value=mock_sock),
            pytest.raises(OSError, match="ioctl failed"),
        ):
            _get_mac_address("eth0")

        mock_sock.close.assert_called_once()


# ---------------------------------------------------------------------------
# _create_raw_socket_linux tests (lines 140-149)
# ---------------------------------------------------------------------------


class TestCreateRawSocketLinux:
    """Cover _create_raw_socket_linux via socket module mocking."""

    def test_creates_and_binds_socket(self):
        """Should create AF_PACKET raw socket, bind, and set non-blocking."""
        mock_sock = MagicMock()

        with (
            patch("socket.socket", return_value=mock_sock),
            patch("socket.htons", return_value=0x0300) as mock_htons,
        ):
            result = _create_raw_socket_linux("eth0")

        assert result is mock_sock
        mock_htons.assert_called_once_with(0x0003)
        mock_sock.bind.assert_called_once_with(("eth0", 0))
        mock_sock.setblocking.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# _open_bpf_device tests (lines 158-166)
# ---------------------------------------------------------------------------


class TestOpenBpfDevice:
    """Cover _open_bpf_device BPF iteration and failure."""

    def test_opens_first_available_bpf(self):
        """Should return fd from the first successful os.open."""
        import os as _os

        with patch("os.open", return_value=5) as mock_open:
            result = _open_bpf_device()

        assert result == 5
        mock_open.assert_called_once_with("/dev/bpf0", _os.O_RDWR)

    def test_skips_unavailable_bpf_devices(self):
        """Should try successive /dev/bpfN devices when earlier ones fail."""
        with patch("os.open", side_effect=[OSError, OSError, OSError, 42]) as mock_open:
            result = _open_bpf_device()

        assert result == 42
        assert mock_open.call_count == 4

    def test_raises_when_no_bpf_available(self):
        """Should raise OSError when all 256 BPF devices fail."""
        with (
            patch("os.open", side_effect=OSError("permission denied")) as mock_open,
            pytest.raises(OSError, match="No available BPF device"),
        ):
            _open_bpf_device()

        assert mock_open.call_count == 256


# ---------------------------------------------------------------------------
# start() tests (lines 211, 214-216, 218-224, 232-238)
# ---------------------------------------------------------------------------


class TestEthernetTransportStart:
    """Cover start() method platform paths and early return."""

    async def test_start_already_running_returns_early(self):
        """start() should return immediately if already running (line 211)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._running = True
        # If start() doesn't return early it would try to create a socket
        # and fail, so no exception means the early return works.
        await transport.start()

    async def test_start_linux_path(self):
        """start() on Linux should use _create_raw_socket_linux (lines 214-216)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)

        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 10
        mock_loop = MagicMock()

        with (
            patch("bac_py.transport.ethernet.sys") as mock_sys,
            patch(
                "bac_py.transport.ethernet._create_raw_socket_linux",
                return_value=mock_sock,
            ) as mock_create,
            patch(
                "bac_py.transport.ethernet.asyncio.get_running_loop",
                return_value=mock_loop,
            ),
        ):
            mock_sys.platform = "linux"
            await transport.start()

        mock_create.assert_called_once_with("eth0")
        assert transport._running is True
        assert transport._socket is mock_sock
        mock_loop.add_reader.assert_called_once()

    async def test_start_linux_auto_detects_mac(self):
        """start() on Linux without explicit MAC calls _get_mac_address."""
        transport = EthernetTransport("eth0")  # no mac_address

        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 10
        mock_loop = MagicMock()
        detected_mac = b"\x11\x22\x33\x44\x55\x66"

        with (
            patch("bac_py.transport.ethernet.sys") as mock_sys,
            patch(
                "bac_py.transport.ethernet._create_raw_socket_linux",
                return_value=mock_sock,
            ),
            patch(
                "bac_py.transport.ethernet._get_mac_address",
                return_value=detected_mac,
            ) as mock_get_mac,
            patch(
                "bac_py.transport.ethernet.asyncio.get_running_loop",
                return_value=mock_loop,
            ),
        ):
            mock_sys.platform = "linux"
            await transport.start()

        mock_get_mac.assert_called_once_with("eth0")
        assert transport._local_mac_bytes == detected_mac

    async def test_start_darwin_path_with_mac(self):
        """start() on macOS should use _open_bpf_device (lines 218-224)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)

        mock_loop = MagicMock()

        with (
            patch("bac_py.transport.ethernet.sys") as mock_sys,
            patch(
                "bac_py.transport.ethernet._open_bpf_device",
                return_value=7,
            ) as mock_bpf,
            patch(
                "bac_py.transport.ethernet.asyncio.get_running_loop",
                return_value=mock_loop,
            ),
        ):
            mock_sys.platform = "darwin"
            await transport.start()

        mock_bpf.assert_called_once()
        assert transport._socket == 7
        assert transport._running is True

    async def test_start_darwin_without_mac_raises(self):
        """start() on macOS without explicit MAC should raise OSError."""
        transport = EthernetTransport("eth0")  # no mac_address

        with (
            patch("bac_py.transport.ethernet.sys") as mock_sys,
            patch(
                "bac_py.transport.ethernet._open_bpf_device",
                return_value=7,
            ),
        ):
            mock_sys.platform = "darwin"
            with pytest.raises(OSError, match="MAC address auto-detection not supported"):
                await transport.start()


# ---------------------------------------------------------------------------
# stop() tests (lines 248-264)
# ---------------------------------------------------------------------------


class TestEthernetTransportStop:
    """Cover stop() cleanup paths."""

    async def test_stop_with_socket_object(self):
        """stop() should close a socket object via close() (lines 254-257)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._running = True

        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 10
        transport._socket = mock_sock

        mock_loop = MagicMock()
        with patch(
            "bac_py.transport.ethernet.asyncio.get_running_loop",
            return_value=mock_loop,
        ):
            await transport.stop()

        assert transport._running is False
        mock_sock.close.assert_called_once()
        assert transport._socket is None
        mock_loop.remove_reader.assert_called_once()

    async def test_stop_with_bpf_fd(self):
        """stop() should os.close() an int fd (BPF) (lines 258-261)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._running = True
        transport._socket = 42  # BPF fd is an int

        mock_loop = MagicMock()
        with (
            patch(
                "bac_py.transport.ethernet.asyncio.get_running_loop",
                return_value=mock_loop,
            ),
            patch("os.close") as mock_os_close,
        ):
            await transport.stop()

        assert transport._running is False
        mock_os_close.assert_called_once_with(42)
        assert transport._socket is None

    async def test_stop_remove_reader_exception_suppressed(self):
        """stop() should suppress exceptions from remove_reader."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._running = True
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 10
        transport._socket = mock_sock

        mock_loop = MagicMock()
        mock_loop.remove_reader.side_effect = ValueError("not registered")

        with patch(
            "bac_py.transport.ethernet.asyncio.get_running_loop",
            return_value=mock_loop,
        ):
            await transport.stop()  # should not raise

        assert transport._running is False
        assert transport._socket is None


# ---------------------------------------------------------------------------
# _get_fd() tests (lines 312-322)
# ---------------------------------------------------------------------------


class TestGetFd:
    """Cover _get_fd branches: socket object, int fd, errors."""

    def test_get_fd_socket_object(self):
        """_get_fd with socket object returns fileno() (lines 315-318)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 42
        transport._socket = mock_sock

        assert transport._get_fd() == 42

    def test_get_fd_int_fd(self):
        """_get_fd with int socket (BPF) returns the int (lines 319-320)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._socket = 99

        assert transport._get_fd() == 99

    def test_get_fd_not_started_raises(self):
        """_get_fd with no socket raises RuntimeError (lines 312-314)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._socket = None

        with pytest.raises(RuntimeError, match="not started"):
            transport._get_fd()

    def test_get_fd_unsupported_type_raises(self):
        """_get_fd with non-socket non-int raises RuntimeError (lines 321-322)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        # Use a plain object without fileno and not an int
        transport._socket = "not_a_socket"

        with pytest.raises(RuntimeError, match="Cannot determine file descriptor"):
            transport._get_fd()


# ---------------------------------------------------------------------------
# _send_frame() tests (lines 327-328, 333-338)
# ---------------------------------------------------------------------------


class TestSendFrame:
    """Cover _send_frame paths: not started, os.write for BPF, OSError."""

    def test_send_frame_not_started_raises(self):
        """_send_frame with no socket raises RuntimeError (lines 326-328)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._socket = None

        with pytest.raises(RuntimeError, match="not started"):
            transport._send_frame(b"\x00" * 60)

    def test_send_frame_os_write_for_bpf(self):
        """_send_frame with int socket uses os.write (lines 333-336)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._socket = 42  # BPF fd

        frame = b"\x00" * 60
        with patch("os.write") as mock_write:
            transport._send_frame(frame)

        mock_write.assert_called_once_with(42, frame)

    def test_send_frame_oserror_suppressed(self):
        """_send_frame should log warning on OSError (lines 337-338)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        mock_sock = MagicMock()
        mock_sock.send.side_effect = OSError("write failed")
        transport._socket = mock_sock

        # Should not raise
        transport._send_frame(b"\x00" * 60)

    def test_send_frame_oserror_on_bpf_write(self):
        """_send_frame with BPF should also suppress OSError."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._socket = 42

        with patch("os.write", side_effect=OSError("write failed")):
            transport._send_frame(b"\x00" * 60)  # should not raise


# ---------------------------------------------------------------------------
# _on_readable() tests (lines 346-351, 354, 366->exit, 369-371)
# ---------------------------------------------------------------------------


class TestOnReadable:
    """Cover _on_readable paths: os.read for BPF, empty data, no callback, OSError."""

    def _make_transport(self, mac: bytes = b"\xaa\xbb\xcc\xdd\xee\xff") -> EthernetTransport:
        """Create a transport with mock internals."""
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._local_mac_bytes = mac
        transport._running = True
        mock_sock = MagicMock()
        mock_sock.fileno.return_value = 99
        transport._socket = mock_sock
        return transport

    def test_on_readable_os_read_for_bpf(self):
        """_on_readable with int socket uses os.read (lines 346-349)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._local_mac_bytes = mac
        transport._running = True
        transport._socket = 42  # BPF fd

        callback = MagicMock()
        transport.on_receive(callback)

        # Build a valid frame from a different source
        src = b"\x11\x22\x33\x44\x55\x66"
        npdu = b"\x01\x02\x03"
        frame = _encode_frame(mac, src, npdu)

        with patch("os.read", return_value=frame) as mock_read:
            transport._on_readable()

        mock_read.assert_called_once_with(42, 1518)
        callback.assert_called_once()
        received_npdu, received_src = callback.call_args[0]
        assert received_npdu == npdu
        assert received_src == src

    def test_on_readable_unsupported_socket_returns(self):
        """_on_readable with unsupported socket type returns (lines 350-351)."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)
        transport._running = True
        transport._socket = "not_a_socket"  # No recv, not an int

        callback = MagicMock()
        transport.on_receive(callback)

        transport._on_readable()  # Should return without calling callback
        callback.assert_not_called()

    def test_on_readable_empty_data_returns(self):
        """_on_readable with empty recv data returns early (line 354)."""
        transport = self._make_transport()
        callback = MagicMock()
        transport.on_receive(callback)

        transport._socket.recv.return_value = b""

        transport._on_readable()
        callback.assert_not_called()

    def test_on_readable_no_callback(self):
        """_on_readable with no callback should not raise (line 366->exit)."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = self._make_transport(mac)
        transport._receive_callback = None

        # Build a valid frame from a different source
        src = b"\x11\x22\x33\x44\x55\x66"
        npdu = b"\x01\x02"
        frame = _encode_frame(mac, src, npdu)
        transport._socket.recv.return_value = frame

        transport._on_readable()  # Should not raise

    def test_on_readable_oserror_while_running(self):
        """_on_readable logs warning on OSError while running (lines 369-371)."""
        transport = self._make_transport()
        transport._running = True
        transport._socket.recv.side_effect = OSError("read failed")

        transport._on_readable()  # Should not raise

    def test_on_readable_oserror_while_stopped(self):
        """_on_readable does not log when not running."""
        transport = self._make_transport()
        transport._running = False
        transport._socket.recv.side_effect = OSError("read failed")

        transport._on_readable()  # Should not raise


# ---------------------------------------------------------------------------
# Coverage: stop() with unsupported socket type (branch 254->264)
# ---------------------------------------------------------------------------


class TestEthernetTransportStopUnsupportedSocket:
    """Branch 254->264: stop() when socket has no close() and is not an int."""

    async def test_stop_with_non_closable_non_int_socket(self):
        """stop() with socket that has no close() and is not int skips close."""
        mac = b"\xaa\xbb\xcc\xdd\xee\xff"
        transport = EthernetTransport("eth0", mac_address=mac)
        transport._running = True

        # Use an object without close attribute and not an int
        class FakeSocket:
            def fileno(self):
                return 10

        transport._socket = FakeSocket()

        mock_loop = MagicMock()
        with patch(
            "bac_py.transport.ethernet.asyncio.get_running_loop",
            return_value=mock_loop,
        ):
            await transport.stop()

        assert transport._running is False
        assert transport._socket is None


# ---------------------------------------------------------------------------
# Coverage: _send_frame() with unsupported socket type (branch 333->exit)
# ---------------------------------------------------------------------------


class TestSendFrameUnsupportedSocket:
    """Branch 333->exit: _send_frame when socket has no send() and is not int."""

    def test_send_frame_non_sendable_non_int_socket(self):
        """_send_frame with socket that has no send() and is not int does nothing."""
        transport = EthernetTransport("eth0", mac_address=b"\x00" * 6)

        # Use an object without send attribute and not an int
        class FakeSocket:
            pass

        transport._socket = FakeSocket()

        # Should not raise -- the frame is silently dropped
        transport._send_frame(b"\x00" * 60)
