"""VMAC addressing and Device UUID for BACnet/SC (AB.1.5)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from bac_py.transport.sc.types import UUID_LENGTH, VMAC_BROADCAST, VMAC_LENGTH


@dataclass(frozen=True, slots=True)
class SCVMAC:
    """6-byte virtual MAC address for BACnet/SC nodes (AB.1.5.2).

    VMAC addresses use the EUI-48 format.  The broadcast VMAC is
    ``FF:FF:FF:FF:FF:FF``.  The all-zeros address ``00:00:00:00:00:00``
    is reserved to indicate an unknown or uninitialized VMAC.
    """

    address: bytes

    def __post_init__(self) -> None:
        if len(self.address) != VMAC_LENGTH:
            msg = f"VMAC must be {VMAC_LENGTH} bytes, got {len(self.address)}"
            raise ValueError(msg)

    # -- Factories --

    @classmethod
    def _from_trusted(cls, data: bytes) -> SCVMAC:
        """Fast-path: skip validation (caller guarantees 6 bytes)."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "address", data)
        return obj

    @classmethod
    def random(cls) -> SCVMAC:
        """Generate a random locally-administered unicast VMAC.

        Sets the locally-administered bit (bit 1 of first octet) and
        clears the multicast bit (bit 0 of first octet) per IEEE 802.
        """
        raw = bytearray(os.urandom(VMAC_LENGTH))
        raw[0] = (raw[0] | 0x02) & 0xFE  # local-admin, unicast
        return cls(bytes(raw))

    @classmethod
    def broadcast(cls) -> SCVMAC:
        """Return the local broadcast VMAC (FF:FF:FF:FF:FF:FF)."""
        return cls(VMAC_BROADCAST)

    @classmethod
    def from_hex(cls, hex_str: str) -> SCVMAC:
        """Parse a VMAC from hex string (with or without colons/hyphens).

        Accepts formats: ``"AABBCCDDEEFF"``, ``"AA:BB:CC:DD:EE:FF"``,
        ``"AA-BB-CC-DD-EE-FF"``.
        """
        cleaned = hex_str.replace(":", "").replace("-", "")
        if len(cleaned) != VMAC_LENGTH * 2:
            msg = f"Invalid VMAC hex string length: {hex_str!r}"
            raise ValueError(msg)
        return cls(bytes.fromhex(cleaned))

    # -- Properties --

    @property
    def is_broadcast(self) -> bool:
        """Return True if this is the broadcast VMAC."""
        return self.address == VMAC_BROADCAST

    @property
    def is_uninitialized(self) -> bool:
        """Return True if this is the all-zeros (uninitialized) VMAC."""
        return self.address == b"\x00\x00\x00\x00\x00\x00"

    # -- Display --

    def __str__(self) -> str:
        return ":".join(f"{b:02X}" for b in self.address)

    def __repr__(self) -> str:
        return f"SCVMAC('{self}')"


@dataclass(frozen=True, slots=True)
class DeviceUUID:
    """16-byte device UUID for BACnet/SC (AB.1.5.3).

    Every BACnet/SC device has a UUID (RFC 4122) that persists across
    restarts and is independent of VMAC or device instance.
    """

    value: bytes

    def __post_init__(self) -> None:
        if len(self.value) != UUID_LENGTH:
            msg = f"Device UUID must be {UUID_LENGTH} bytes, got {len(self.value)}"
            raise ValueError(msg)

    @classmethod
    def generate(cls) -> DeviceUUID:
        """Generate a new random UUID (version 4)."""
        return cls(uuid.uuid4().bytes)

    @classmethod
    def from_hex(cls, hex_str: str) -> DeviceUUID:
        """Parse UUID from hex string (with or without hyphens).

        Accepts ``"550e8400e29b41d4a716446655440000"`` or standard
        ``"550e8400-e29b-41d4-a716-446655440000"`` format.
        """
        cleaned = hex_str.replace("-", "")
        if len(cleaned) != UUID_LENGTH * 2:
            msg = f"Invalid UUID hex string length: {hex_str!r}"
            raise ValueError(msg)
        return cls(bytes.fromhex(cleaned))

    def __str__(self) -> str:
        h = self.value.hex()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    def __repr__(self) -> str:
        return f"DeviceUUID('{self}')"
