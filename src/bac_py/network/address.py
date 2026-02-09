"""BACnet addressing types per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BIPAddress:
    """6-octet BACnet/IP address: 4 bytes IP + 2 bytes port."""

    host: str
    port: int

    def encode(self) -> bytes:
        """Encode to 6-byte wire format."""
        parts = [int(x) for x in self.host.split(".")]
        return bytes(parts) + self.port.to_bytes(2, "big")

    @classmethod
    def decode(cls, data: bytes | memoryview) -> BIPAddress:
        """Decode from 6-byte wire format."""
        host = f"{data[0]}.{data[1]}.{data[2]}.{data[3]}"
        port = int.from_bytes(data[4:6], "big")
        return cls(host=host, port=port)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        return {"host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BIPAddress:
        """Reconstruct from JSON-friendly dict."""
        return cls(host=data["host"], port=data["port"])


@dataclass(frozen=True, slots=True)
class BACnetAddress:
    """A full BACnet address: optional network number + MAC address.

    Network numbers must be ``None`` (local), 0xFFFF (global broadcast),
    or 1-65534 (valid remote network per Clause 6.2.1).
    """

    network: int | None = None
    mac_address: bytes = b""

    def __post_init__(self) -> None:
        if (
            self.network is not None
            and self.network != 0xFFFF
            and (self.network < 1 or self.network > 65534)
        ):
            msg = f"Network number must be 1-65534, got {self.network}"
            raise ValueError(msg)

    @property
    def is_local(self) -> bool:
        """True if addressing the local network."""
        return self.network is None

    @property
    def is_broadcast(self) -> bool:
        """True if this is any type of broadcast address."""
        return self.network == 0xFFFF or len(self.mac_address) == 0

    @property
    def is_global_broadcast(self) -> bool:
        """True if this is a global broadcast address."""
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
        if self.mac_address:
            mac_hex = self.mac_address.hex()
            if self.network is not None:
                return f"{self.network}:{mac_hex}"
            return mac_hex
        return ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly dict."""
        result: dict[str, Any] = {}
        if self.network is not None:
            result["network"] = self.network
        if self.mac_address:
            result["mac_address"] = self.mac_address.hex()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACnetAddress:
        """Reconstruct from JSON-friendly dict."""
        network = data.get("network")
        mac_hex = data.get("mac_address", "")
        mac = bytes.fromhex(mac_hex) if mac_hex else b""
        return cls(network=network, mac_address=mac)


# Convenience constants
LOCAL_BROADCAST = BACnetAddress()
GLOBAL_BROADCAST = BACnetAddress(network=0xFFFF)


def remote_broadcast(network: int) -> BACnetAddress:
    """Create a remote broadcast address for a specific network."""
    return BACnetAddress(network=network, mac_address=b"")


def remote_station(network: int, mac: bytes) -> BACnetAddress:
    """Create a remote station address."""
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


def parse_address(addr: str | BACnetAddress) -> BACnetAddress:
    """Parse a human-readable address string to a BACnetAddress.

    Accepted formats::

        "192.168.1.100"           -> local BACnet/IP, default port 0xBAC0
        "192.168.1.100:47809"     -> local BACnet/IP, explicit port
        "2:192.168.1.100"         -> remote network 2, default port
        "2:192.168.1.100:47809"   -> remote network 2, explicit port
        "*"                       -> global broadcast
        "2:*"                     -> remote broadcast on network 2

    If already a ``BACnetAddress``, returns it unchanged (pass-through).

    Args:
        addr: Address string or existing BACnetAddress.

    Returns:
        Parsed BACnetAddress.

    Raises:
        ValueError: If the format is not recognised.
    """
    if isinstance(addr, BACnetAddress):
        return addr

    addr = addr.strip()
    if not addr:
        msg = "Address string must not be empty"
        raise ValueError(msg)

    m = _ADDR_RE.match(addr)
    if not m:
        msg = (
            f"Cannot parse address: {addr!r}. "
            "Expected format like '192.168.1.100', '192.168.1.100:47808', "
            "'2:192.168.1.100', or '*'"
        )
        raise ValueError(msg)

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
