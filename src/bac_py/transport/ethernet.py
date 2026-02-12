"""BACnet Ethernet (ISO 8802-3) transport per ASHRAE 135-2020 Clause 7.

Provides raw 802.3 frame transport with IEEE 802.2 LLC headers for
BACnet communication over Ethernet data links.  Requires raw socket
access (``CAP_NET_RAW`` on Linux or ``/dev/bpf*`` on macOS).

Frame format (Clause 7)::

    +-----------+----------+--------+------+------+---------+------+
    | Dst MAC   | Src MAC  | Length | DSAP | SSAP | Control | NPDU |
    | (6 bytes) | (6 bytes)| (2)    | 0x82 | 0x82 | 0x03    | ...  |
    +-----------+----------+--------+------+------+---------+------+

The 802.2 LLC header uses DSAP=0x82, SSAP=0x82, Control=0x03
(Unnumbered Information) as specified in Clause 7.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# BACnet 802.2 LLC header constants (Clause 7)
LLC_DSAP = 0x82
LLC_SSAP = 0x82
LLC_CONTROL = 0x03
LLC_HEADER = bytes([LLC_DSAP, LLC_SSAP, LLC_CONTROL])
LLC_HEADER_SIZE = 3

# 802.3 frame header: 6 dst + 6 src + 2 length = 14 bytes
ETHERNET_HEADER_SIZE = 14

# Maximum Ethernet payload is 1500 bytes; subtract LLC header
MAX_NPDU_LENGTH = 1500 - LLC_HEADER_SIZE  # 1497

# Broadcast MAC address
ETHERNET_BROADCAST = b"\xff\xff\xff\xff\xff\xff"

# Minimum Ethernet frame payload (required for valid 802.3 frames)
_MIN_PAYLOAD = 46


def _encode_frame(dst_mac: bytes, src_mac: bytes, npdu: bytes) -> bytes:
    """Build an IEEE 802.3 frame with 802.2 LLC header for BACnet.

    :param dst_mac: 6-byte destination MAC address.
    :param src_mac: 6-byte source MAC address.
    :param npdu: BACnet NPDU payload bytes.
    :returns: Complete 802.3 frame bytes ready for transmission.
    """
    payload = LLC_HEADER + npdu
    # Length field in 802.3 is the LLC + data length (not including padding)
    length = len(payload)
    header = dst_mac + src_mac + struct.pack("!H", length)
    frame = header + payload
    # Pad to minimum Ethernet frame size (64 bytes - 4 CRC = 60 bytes minimum)
    min_frame_size = ETHERNET_HEADER_SIZE + _MIN_PAYLOAD
    if len(frame) < min_frame_size:
        frame += b"\x00" * (min_frame_size - len(frame))
    return frame


def _decode_frame(raw: bytes) -> tuple[bytes, bytes] | None:
    """Validate and extract NPDU + source MAC from a raw 802.3 frame.

    Checks for valid 802.2 LLC BACnet header (DSAP=0x82, SSAP=0x82,
    Control=0x03).

    :param raw: Raw Ethernet frame bytes (including header).
    :returns: ``(npdu_bytes, source_mac)`` tuple, or ``None`` if the
        frame is not a valid BACnet Ethernet frame.
    """
    if len(raw) < ETHERNET_HEADER_SIZE + LLC_HEADER_SIZE:
        return None

    # Extract source MAC (bytes 6-12 of Ethernet header)
    src_mac = raw[6:12]

    # Extract 802.3 length field
    length = struct.unpack("!H", raw[12:14])[0]

    # 802.3 frames have length <= 1500; values > 1500 are EtherType (802.2)
    if length > 1500:
        return None

    # Check LLC header
    llc_offset = ETHERNET_HEADER_SIZE
    if raw[llc_offset] != LLC_DSAP:
        return None
    if raw[llc_offset + 1] != LLC_SSAP:
        return None
    if raw[llc_offset + 2] != LLC_CONTROL:
        return None

    # Extract NPDU (after LLC header, using length field to determine size)
    npdu_start = llc_offset + LLC_HEADER_SIZE
    npdu_end = llc_offset + length
    if npdu_end > len(raw):
        npdu_end = len(raw)
    npdu = raw[npdu_start:npdu_end]

    return npdu, src_mac


def _get_mac_address(interface: str) -> bytes:
    """Get the MAC address of a network interface.

    :param interface: Interface name (e.g. ``"eth0"``).
    :returns: 6-byte MAC address.
    :raises OSError: If the interface is not found or MAC cannot be read.
    """
    import fcntl
    import socket as _socket

    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        # SIOCGIFHWADDR = 0x8927
        info = fcntl.ioctl(sock.fileno(), 0x8927, struct.pack("256s", interface.encode()[:15]))
        return info[18:24]
    finally:
        sock.close()


def _create_raw_socket_linux(interface: str) -> object:
    """Create a raw AF_PACKET socket on Linux.

    :param interface: Network interface name (e.g. ``"eth0"``).
    :returns: A raw socket object.
    :raises OSError: If socket creation fails (insufficient privileges).
    """
    import socket as _socket

    sock = _socket.socket(
        getattr(_socket, "AF_PACKET", 17),  # AF_PACKET = 17 on Linux
        _socket.SOCK_RAW,
        _socket.htons(0x0003),  # ETH_P_ALL
    )
    sock.bind((interface, 0))
    sock.setblocking(False)
    return sock


def _open_bpf_device() -> int:
    """Open an available BPF device on macOS.

    :returns: File descriptor of the BPF device.
    :raises OSError: If no BPF device is available.
    """
    import os

    for i in range(256):
        try:
            return os.open(f"/dev/bpf{i}", os.O_RDWR)
        except OSError:
            continue
    msg = "No available BPF device"
    raise OSError(msg)


class EthernetTransport:
    """BACnet Ethernet (ISO 8802-3) transport per Clause 7.

    Provides raw Ethernet frame I/O with 802.2 LLC headers for
    BACnet data-link communication.  Satisfies the :class:`TransportPort`
    protocol.

    Platform support:
        - **Linux**: Uses ``AF_PACKET`` / ``SOCK_RAW`` sockets (requires
          ``CAP_NET_RAW``).
        - **macOS**: Uses BPF devices (``/dev/bpf*``), requires root or
          appropriate permissions.
        - **Windows**: Not supported (raises ``NotImplementedError``).
          Use Npcap or WinPcap for raw Ethernet access on Windows.
    """

    def __init__(
        self,
        interface: str,
        *,
        mac_address: bytes | None = None,
    ) -> None:
        """Initialize the Ethernet transport.

        :param interface: Network interface name (e.g. ``"eth0"``).
        :param mac_address: Optional explicit 6-byte MAC address. If
            ``None``, the interface's hardware MAC is auto-detected.
        """
        self._interface = interface
        self._explicit_mac = mac_address
        self._local_mac_bytes: bytes | None = mac_address
        self._socket: object | None = None
        self._receive_callback: Callable[[bytes, bytes], None] | None = None
        self._running = False

    async def start(self) -> None:
        """Bind the raw socket and begin listening for BACnet frames.

        :raises NotImplementedError: On unsupported platforms (Windows).
        :raises OSError: If socket creation fails.
        """
        if self._running:
            return

        if sys.platform == "linux":
            self._socket = _create_raw_socket_linux(self._interface)
            if self._local_mac_bytes is None:
                self._local_mac_bytes = _get_mac_address(self._interface)
        elif sys.platform == "darwin":
            self._socket = _open_bpf_device()
            if self._local_mac_bytes is None:
                msg = (
                    "MAC address auto-detection not supported on macOS; "
                    "provide mac_address explicitly"
                )
                raise OSError(msg)
        else:
            msg = (
                f"BACnet Ethernet transport is not supported on {sys.platform}. "
                "On Windows, use Npcap or WinPcap for raw Ethernet access."
            )
            raise NotImplementedError(msg)

        self._running = True

        # Register the socket fd for async reading
        loop = asyncio.get_running_loop()
        loop.add_reader(self._get_fd(), self._on_readable)

        logger.info(
            "EthernetTransport started on %s (MAC %s)",
            self._interface,
            ":".join(f"{b:02x}" for b in self._local_mac_bytes),
        )

    async def stop(self) -> None:
        """Stop listening and close the raw socket."""
        if not self._running:
            return
        self._running = False

        loop = asyncio.get_running_loop()
        with contextlib.suppress(Exception):
            loop.remove_reader(self._get_fd())

        if self._socket is not None:
            close = getattr(self._socket, "close", None)
            if close is not None:
                close()
            elif isinstance(self._socket, int):
                import os

                os.close(self._socket)
            self._socket = None

        logger.info("EthernetTransport stopped on %s", self._interface)

    def on_receive(self, callback: Callable[[bytes, bytes], None]) -> None:
        """Register a callback for incoming NPDUs.

        :param callback: Called with ``(npdu_bytes, source_mac)`` for each
            received BACnet Ethernet frame.
        """
        self._receive_callback = callback

    def send_unicast(self, npdu: bytes, mac_address: bytes) -> None:
        """Send an NPDU to a specific station.

        :param npdu: NPDU bytes to send.
        :param mac_address: 6-byte destination Ethernet MAC address.
        """
        if self._local_mac_bytes is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        frame = _encode_frame(mac_address, self._local_mac_bytes, npdu)
        self._send_frame(frame)

    def send_broadcast(self, npdu: bytes) -> None:
        """Send an NPDU as a local broadcast.

        :param npdu: NPDU bytes to broadcast.
        """
        if self._local_mac_bytes is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        frame = _encode_frame(ETHERNET_BROADCAST, self._local_mac_bytes, npdu)
        self._send_frame(frame)

    @property
    def local_mac(self) -> bytes:
        """The 6-byte IEEE MAC address of this port."""
        if self._local_mac_bytes is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        return self._local_mac_bytes

    @property
    def max_npdu_length(self) -> int:
        """Maximum NPDU length for BACnet Ethernet: 1497 bytes (Table 6-1)."""
        return MAX_NPDU_LENGTH

    def _get_fd(self) -> int:
        """Get the file descriptor of the raw socket."""
        if self._socket is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        fileno = getattr(self._socket, "fileno", None)
        if fileno is not None:
            fd: int = fileno()
            return fd
        if isinstance(self._socket, int):
            return self._socket
        msg = "Cannot determine file descriptor"
        raise RuntimeError(msg)

    def _send_frame(self, frame: bytes) -> None:
        """Send a raw Ethernet frame."""
        if self._socket is None:
            msg = "Transport not started"
            raise RuntimeError(msg)
        try:
            send = getattr(self._socket, "send", None)
            if send is not None:
                send(frame)
            elif isinstance(self._socket, int):
                import os

                os.write(self._socket, frame)
        except OSError:
            logger.warning("Failed to send Ethernet frame on %s", self._interface, exc_info=True)

    def _on_readable(self) -> None:
        """Handle incoming data on the raw socket."""
        try:
            recv = getattr(self._socket, "recv", None)
            if recv is not None:
                raw = recv(1518)
            elif isinstance(self._socket, int):
                import os

                raw = os.read(self._socket, 1518)
            else:
                return

            if not raw:
                return

            result = _decode_frame(raw)
            if result is None:
                return  # Not a BACnet frame

            npdu, src_mac = result

            # Skip frames from ourselves
            if src_mac == self._local_mac_bytes:
                return

            if self._receive_callback is not None:
                self._receive_callback(npdu, src_mac)

        except OSError:
            if self._running:
                logger.warning("Error receiving on %s", self._interface, exc_info=True)
