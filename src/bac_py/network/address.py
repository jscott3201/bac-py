"""BACnet addressing types per ASHRAE 135-2020 Clause 6."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BIPAddress:
    """A 6-octet BACnet/IP address composed of a 4-byte IPv4 address and a 2-byte UDP port.

    Used as the MAC-layer address for BACnet/IP data links (Annex J).
    """

    host: str
    port: int

    def encode(self) -> bytes:
        """Encode this address to the 6-byte BACnet/IP wire format.

        :returns: A 6-byte ``bytes`` object (4 octets IP + 2 octets port, big-endian).
        """
        parts = [int(x) for x in self.host.split(".")]
        return bytes(parts) + self.port.to_bytes(2, "big")

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BIPAddress:
        """Decode a :class:`BIPAddress` from the 6-byte BACnet/IP wire format.

        :param data: At least 6 bytes of raw address data.
        :returns: The decoded :class:`BIPAddress`.
        """
        host = f"{data[0]}.{data[1]}.{data[2]}.{data[3]}"
        port = int.from_bytes(data[4:6], "big")
        return cls(host=host, port=port)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this address to a JSON-friendly dictionary.

        :returns: A dict with ``"host"`` and ``"port"`` keys.
        """
        return {"host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BIPAddress:
        """Reconstruct a :class:`BIPAddress` from a dictionary produced by :meth:`to_dict`.

        :param data: Dictionary containing ``"host"`` and ``"port"`` keys.
        :returns: The reconstructed :class:`BIPAddress`.
        """
        return cls(host=data["host"], port=data["port"])


@dataclass(frozen=True, slots=True)
class BIP6Address:
    """An 18-octet BACnet/IPv6 address: 16-byte IPv6 + 2-byte UDP port.

    Used as the MAC-layer address for BACnet/IPv6 data links (Annex U).
    """

    host: str
    port: int

    def encode(self) -> bytes:
        """Encode to 18-byte wire format (16 octets IPv6 + 2 octets port, big-endian)."""
        return socket.inet_pton(socket.AF_INET6, self.host) + self.port.to_bytes(2, "big")

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BIP6Address:
        """Decode from 18-byte wire format."""
        host = socket.inet_ntop(socket.AF_INET6, bytes(data[:16]))
        port = int.from_bytes(data[16:18], "big")
        return cls(host=host, port=port)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this address to a JSON-friendly dictionary."""
        return {"host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BIP6Address:
        """Reconstruct a :class:`BIP6Address` from a dictionary produced by :meth:`to_dict`."""
        return cls(host=data["host"], port=data["port"])


@dataclass(frozen=True, slots=True)
class EthernetAddress:
    """A 6-octet IEEE 802 MAC address for BACnet Ethernet (Clause 7).

    Used as the MAC-layer address for BACnet/Ethernet (ISO 8802-3) data links.
    """

    mac: bytes
    """6-byte IEEE MAC address."""

    def __post_init__(self) -> None:
        """Validate the MAC address length."""
        if len(self.mac) != 6:
            msg = f"Ethernet MAC must be 6 bytes, got {len(self.mac)}"
            raise ValueError(msg)

    def encode(self) -> bytes:
        """Encode to 6-byte wire format.

        :returns: The 6-byte MAC address.
        """
        return self.mac

    @classmethod
    def decode(cls, data: bytes | memoryview) -> EthernetAddress:
        """Decode from 6 bytes of MAC address data.

        :param data: At least 6 bytes of raw address data.
        :returns: The decoded :class:`EthernetAddress`.
        """
        return cls(mac=bytes(data[:6]))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary.

        :returns: A dict with a ``"mac"`` key containing colon-separated hex.
        """
        return {"mac": ":".join(f"{b:02x}" for b in self.mac)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EthernetAddress:
        """Reconstruct from a dictionary produced by :meth:`to_dict`.

        :param data: Dictionary with a ``"mac"`` key.
        :returns: The reconstructed :class:`EthernetAddress`.
        """
        mac_str: str = data["mac"]
        return cls(mac=bytes(int(x, 16) for x in mac_str.split(":")))

    def __str__(self) -> str:
        """Format as colon-separated hex (``AA:BB:CC:DD:EE:FF``)."""
        return ":".join(f"{b:02x}" for b in self.mac)


@dataclass(frozen=True, slots=True)
class BACnetAddress:
    """A full BACnet address: optional network number + MAC address.

    Network numbers must be ``None`` (local), 0xFFFF (global broadcast),
    or 1-65534 (valid remote network per Clause 6.2.1).
    """

    network: int | None = None
    mac_address: bytes = b""

    def __post_init__(self) -> None:
        """Validate the network number range per Clause 6.2.1."""
        if (
            self.network is not None
            and self.network != 0xFFFF
            and (self.network < 1 or self.network > 65534)
        ):
            msg = f"Network number must be 1-65534, got {self.network}"
            raise ValueError(msg)

    @property
    def is_local(self) -> bool:
        """``True`` if this address targets the local network (no DNET specified)."""
        return self.network is None

    @property
    def is_broadcast(self) -> bool:
        """``True`` if this is any type of broadcast address (global, remote, or local)."""
        return self.network == 0xFFFF or len(self.mac_address) == 0

    @property
    def is_global_broadcast(self) -> bool:
        """``True`` if this is a global broadcast (DNET = 0xFFFF)."""
        return self.network == 0xFFFF

    @property
    def is_remote_broadcast(self) -> bool:
        """True if this is a broadcast on a specific remote network.

        A remote broadcast has a network number set (not global 0xFFFF)
        and an empty MAC address (DLEN=0).
        """
        return self.network is not None and self.network != 0xFFFF and len(self.mac_address) == 0

    def __str__(self) -> str:
        """Human-readable address string.

        Produces strings that round-trip through ``parse_address()``:

        - ``"192.168.1.100:47808"`` for local BACnet/IP unicast
        - ``"2:192.168.1.100:47808"`` for remote BACnet/IP unicast
        - ``"*"`` for global broadcast
        - ``"2:*"`` for remote broadcast on network 2
        - ``"4352:01"`` for remote non-IP station (e.g. MS/TP behind router)
        - ``""`` for local broadcast (no MAC)
        """
        if self.is_global_broadcast:
            return "*"
        if self.is_remote_broadcast:
            return f"{self.network}:*"
        if len(self.mac_address) == 6:
            bip = BIPAddress.decode(self.mac_address)
            ip_port = f"{bip.host}:{bip.port}"
            if self.network is not None:
                return f"{self.network}:{ip_port}"
            return ip_port
        if len(self.mac_address) == 18:
            bip6 = BIP6Address.decode(self.mac_address)
            ip_port = f"[{bip6.host}]:{bip6.port}"
            if self.network is not None:
                return f"{self.network}:{ip_port}"
            return ip_port
        if self.mac_address:
            mac_hex = self.mac_address.hex()
            if self.network is not None:
                return f"{self.network}:{mac_hex}"
            return mac_hex
        return ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize this address to a JSON-friendly dictionary.

        :returns: A dict with optional ``"network"`` and ``"mac_address"`` keys.
        """
        result: dict[str, Any] = {}
        if self.network is not None:
            result["network"] = self.network
        if self.mac_address:
            result["mac_address"] = self.mac_address.hex()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAddress:
        """Reconstruct a :class:`BACnetAddress` from a dictionary produced by :meth:`to_dict`.

        :param data: Dictionary with optional ``"network"`` and ``"mac_address"`` keys.
        :returns: The reconstructed :class:`BACnetAddress`.
        """
        network = data.get("network")
        mac_hex = data.get("mac_address", "")
        mac = bytes.fromhex(mac_hex) if mac_hex else b""
        return cls(network=network, mac_address=mac)


# Convenience constants
LOCAL_BROADCAST = BACnetAddress()
GLOBAL_BROADCAST = BACnetAddress(network=0xFFFF)


def remote_broadcast(network: int) -> BACnetAddress:
    """Create a remote broadcast address for a specific network.

    A remote broadcast has the DNET set and an empty MAC address (DLEN=0).

    :param network: The target network number (1--65534).
    :returns: A :class:`BACnetAddress` representing a directed broadcast on *network*.
    """
    return BACnetAddress(network=network, mac_address=b"")


def remote_station(network: int, mac: bytes) -> BACnetAddress:
    """Create a unicast address for a station on a remote network.

    :param network: The target network number (1--65534).
    :param mac: The MAC address of the station on that network.
    :returns: A :class:`BACnetAddress` with both DNET and DADR set.
    """
    return BACnetAddress(network=network, mac_address=mac)


# Default BACnet/IP port
_DEFAULT_PORT = 0xBAC0

# Pattern: optional "network:" prefix, then IP with optional ":port", or "*"
_ADDR_RE = re.compile(
    r"^(?:(\d+):)?"  # optional network number + colon
    r"(?:"
    r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IPv4 address
    r"(?::(\d+))?"  # optional :port
    r"|(\*)"  # OR wildcard broadcast
    r")$"
)

# Ethernet MAC pattern: AA:BB:CC:DD:EE:FF (with optional network prefix)
_ETHER_RE = re.compile(
    r"^(?:(\d+):)?"  # optional network number + colon
    r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:"
    r"[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})$"
)

# IPv6 bracket notation: optional "network:" prefix, then [ipv6]:port or [ipv6]
_ADDR6_RE = re.compile(
    r"^(?:(\d+):)?"  # optional network number + colon
    r"\[([^\]]+)\]"  # IPv6 address in brackets
    r"(?::(\d+))?$"  # optional :port
)

# Remote station with arbitrary hex MAC: "NETWORK:HEXMAC"
# Handles MS/TP (1-byte), ARCNET (1-byte), or other non-IP data links
# behind routers. MAC must be even-length hex (at least 1 byte).
_REMOTE_HEX_RE = re.compile(r"^(\d+):([0-9a-fA-F]{2}(?:[0-9a-fA-F]{2})*)$")


def parse_address(addr: str | BACnetAddress) -> BACnetAddress:
    """Parse a human-readable address string to a BACnetAddress.

    Accepted formats::

        "192.168.1.100"           -> local BACnet/IP, default port 0xBAC0
        "192.168.1.100:47809"     -> local BACnet/IP, explicit port
        "2:192.168.1.100"         -> remote network 2, default port
        "2:192.168.1.100:47809"   -> remote network 2, explicit port
        "[::1]"                   -> local BACnet/IPv6, default port 0xBAC0
        "[::1]:47808"             -> local BACnet/IPv6, explicit port
        "2:[::1]:47808"           -> remote network 2, IPv6
        "AA:BB:CC:DD:EE:FF"       -> local Ethernet MAC
        "2:AA:BB:CC:DD:EE:FF"     -> remote Ethernet MAC on network 2
        "4352:01"                 -> remote station with hex MAC (e.g. MS/TP)
        "*"                       -> global broadcast
        "2:*"                     -> remote broadcast on network 2

    If already a :class:`BACnetAddress`, returns it unchanged (pass-through).

    :param addr: Address string or existing :class:`BACnetAddress`.
    :returns: The parsed :class:`BACnetAddress`.
    :raises ValueError: If the format is not recognised.
    """
    if isinstance(addr, BACnetAddress):
        return addr

    addr = addr.strip()
    if not addr:
        msg = "Address string must not be empty"
        raise ValueError(msg)

    # Try Ethernet MAC format (AA:BB:CC:DD:EE:FF)
    me = _ETHER_RE.match(addr)
    if me:
        network_str, mac_str = me.groups()
        network = int(network_str) if network_str is not None else None
        mac = bytes(int(x, 16) for x in mac_str.split(":"))
        if network is not None:
            return remote_station(network, mac)
        return BACnetAddress(mac_address=mac)

    # Try IPv6 bracket notation first
    m6 = _ADDR6_RE.match(addr)
    if m6:
        network_str, ipv6, port_str = m6.groups()
        network = int(network_str) if network_str is not None else None
        port = int(port_str) if port_str else _DEFAULT_PORT
        if not (0 <= port <= 65535):
            msg = f"Port number out of range: {port}"
            raise ValueError(msg)
        # Validate IPv6 address
        try:
            socket.inet_pton(socket.AF_INET6, ipv6)
        except OSError:
            msg = f"Invalid IPv6 address: {ipv6!r}"
            raise ValueError(msg) from None
        mac = BIP6Address(host=ipv6, port=port).encode()
        if network is not None:
            return remote_station(network, mac)
        return BACnetAddress(mac_address=mac)

    m = _ADDR_RE.match(addr)
    if m:
        network_str, ip, port_str, wildcard = m.groups()
        network = int(network_str) if network_str is not None else None

        if wildcard:
            # "*" or "N:*"
            if network is None:
                return GLOBAL_BROADCAST
            return remote_broadcast(network)

        # IP address with optional port
        port = int(port_str) if port_str else _DEFAULT_PORT
        if not (0 <= port <= 65535):
            msg = f"Port number out of range: {port}"
            raise ValueError(msg)
        mac = BIPAddress(host=ip, port=port).encode()

        if network is not None:
            return remote_station(network, mac)
        return BACnetAddress(mac_address=mac)

    # Try remote station with arbitrary hex MAC (e.g. MS/TP: "4352:01")
    mh = _REMOTE_HEX_RE.match(addr)
    if mh:
        network = int(mh.group(1))
        mac = bytes.fromhex(mh.group(2))
        return remote_station(network, mac)

    msg = (
        f"Cannot parse address: {addr!r}. "
        "Expected format like '192.168.1.100', '192.168.1.100:47808', "
        "'2:192.168.1.100', '[::1]:47808', 'AA:BB:CC:DD:EE:FF', "
        "'4352:01' (network:hex_mac), or '*'"
    )
    raise ValueError(msg)
