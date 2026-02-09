"""BACnet constructed data types per ASHRAE 135-2016."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bac_py.types.primitives import BitString


@dataclass(frozen=True, slots=True)
class StatusFlags:
    """BACnet StatusFlags bit string (Clause 12.50, BACnetStatusFlags).

    Four Boolean flags indicating the "health" of an object:
      Bit 0: IN_ALARM
      Bit 1: FAULT
      Bit 2: OVERRIDDEN
      Bit 3: OUT_OF_SERVICE
    """

    in_alarm: bool = False
    fault: bool = False
    overridden: bool = False
    out_of_service: bool = False

    def to_bit_string(self) -> BitString:
        """Encode as a BACnet BitString (4 significant bits)."""
        value = (
            (self.in_alarm << 3) | (self.fault << 2) | (self.overridden << 1) | self.out_of_service
        )
        return BitString(bytes([value << 4]), unused_bits=4)

    @classmethod
    def from_bit_string(cls, bs: BitString) -> StatusFlags:
        """Decode from a BACnet BitString."""
        return cls(
            in_alarm=bs[0] if len(bs) > 0 else False,
            fault=bs[1] if len(bs) > 1 else False,
            overridden=bs[2] if len(bs) > 2 else False,
            out_of_service=bs[3] if len(bs) > 3 else False,
        )

    def to_dict(self) -> dict[str, bool]:
        """Convert to JSON-friendly dict."""
        return {
            "in_alarm": self.in_alarm,
            "fault": self.fault,
            "overridden": self.overridden,
            "out_of_service": self.out_of_service,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusFlags:
        """Reconstruct from a JSON-friendly dict."""
        return cls(
            in_alarm=data.get("in_alarm", False),
            fault=data.get("fault", False),
            overridden=data.get("overridden", False),
            out_of_service=data.get("out_of_service", False),
        )

    def __repr__(self) -> str:
        flags = []
        if self.in_alarm:
            flags.append("IN_ALARM")
        if self.fault:
            flags.append("FAULT")
        if self.overridden:
            flags.append("OVERRIDDEN")
        if self.out_of_service:
            flags.append("OUT_OF_SERVICE")
        return f"StatusFlags({', '.join(flags) if flags else 'NORMAL'})"
