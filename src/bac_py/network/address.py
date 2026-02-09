"""BACnet addressing types per ASHRAE 135-2016 Clause 6."""

from __future__ import annotations

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
